from __future__ import annotations

import argparse
import fnmatch
import logging
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

DEFAULT_PATTERN = "*"
DEFAULT_RETENTION_DAYS = 60
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_SETTLE_SECONDS = 10
COPY_CHUNK_SIZE = 8 * 1024 * 1024
PROGRESS_LOG_STEP = 0.01


@dataclass
class PendingFile:
    path: Path
    last_size: int
    last_mtime: float
    stable_since: float  # 안정화가 시작된 시간 (timestamp)


class CopyCancelled(Exception):
    """복사 작업이 중단 요청으로 취소되었음을 나타내는 예외."""


class SyncConfig:
    def __init__(
        self,
        source: Path,
        destination: Path,
        pattern: str = DEFAULT_PATTERN,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        settle_seconds: int = DEFAULT_SETTLE_SECONDS,
        log_level: str = "INFO",
    ):
        self.source = source
        self.destination = destination
        self.pattern = pattern
        self.retention_days = retention_days
        self.scan_interval = scan_interval
        self.settle_seconds = settle_seconds
        self.log_level = log_level


def parse_args() -> SyncConfig:
    parser = argparse.ArgumentParser(
        description=(
            "소스 폴더에서 새로 생성된 백업 파일을 감시하고, 지정된 패턴과 일치하는 파일을 대상 폴더로 복사한 뒤, 보존 기간을 초과한 복사본을 자동으로 정리합니다."
        )
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="새 백업을 감시할 폴더 경로 (필수).",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        required=True,
        help="일치하는 백업을 복사할 대상 폴더 경로 (필수).",
    )
    parser.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help="파일명을 거를 글롭 패턴 (기본값: %(default)s).",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        help="대상 폴더에서 복사본을 유지할 일 수 (기본값: %(default)s).",
    )
    parser.add_argument(
        "--scan-interval",
        type=int,
        default=DEFAULT_SCAN_INTERVAL,
        help="폴더 스캔 간격(초) (기본값: %(default)s).",
    )
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=DEFAULT_SETTLE_SECONDS,
        help="파일을 복사하기 전에 안정화될 때까지 대기할 시간(초) (기본값: %(default)s).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 상세 수준 (기본값: %(default)s).",
    )
    args = parser.parse_args()
    return SyncConfig(
        source=args.source,
        destination=args.destination,
        pattern=args.pattern,
        retention_days=args.retention_days,
        scan_interval=args.scan_interval,
        settle_seconds=args.settle_seconds,
        log_level=args.log_level,
    )


def validate_paths(source: Path, destination: Path) -> None:
    if not source.exists() or not source.is_dir():
        raise ValueError(f"Source folder does not exist or is not a directory: {source}")
    destination.mkdir(parents=True, exist_ok=True)


def snapshot_matching_files(source: Path, pattern: str) -> Dict[Path, float]:
    matches: Dict[Path, float] = {}
    if not source.exists():
        return matches
    for file_path in source.rglob(pattern):
        if file_path.is_file():
            matches[file_path] = file_path.stat().st_mtime
    return matches


def detect_new_files(
    source: Path,
    pattern: str,
    known_files: Dict[Path, float],
) -> list[Path]:
    current_snapshot = snapshot_matching_files(source, pattern)
    new_files: list[Path] = []
    for file_path, mtime in current_snapshot.items():
        if file_path not in known_files:
            new_files.append(file_path)
        elif mtime > known_files[file_path]:
            new_files.append(file_path)
    known_files.clear()
    known_files.update(current_snapshot)
    return new_files


def wait_for_settle(file_path: Path, settle_seconds: int) -> bool:
    if settle_seconds <= 0:
        return True
    try:
        stat = file_path.stat()
    except FileNotFoundError:
        return False
    signature = (stat.st_size, stat.st_mtime)
    stable_start = time.time()
    while True:
        time.sleep(1)
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            return False
        current_signature = (stat.st_size, stat.st_mtime)
        if current_signature != signature:
            signature = current_signature
            stable_start = time.time()
        if time.time() - stable_start >= settle_seconds:
            return True


def build_destination_path(
    destination: Path,
    source_file: Path,
    source_root: Path,
    overwrite_existing: bool = False
) -> Path:
    try:
        rel_path = source_file.relative_to(source_root)
    except ValueError:
        rel_path = Path(source_file.name)
        
    target_path = destination / rel_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        if overwrite_existing:
            return target_path
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        # 확장자 앞에 타임스탬프 삽입
        stem = target_path.stem
        suffix = target_path.suffix
        new_name = f"{stem}_{timestamp}{suffix}"
        return target_path.with_name(new_name)
    return target_path


def format_size(num_bytes: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} {units[-1]}"


def progress_bar(percent: int, width: int = 20) -> str:
    filled = int(width * percent / 100)
    bar = '█' * filled + ' ' * (width - filled)
    return f"[{bar}] {percent}%"


_PROGRESS_LINE_LENGTH = 0


def _get_log_stream():
    logger = logging.getLogger()
    if logger.handlers:
        handler = logger.handlers[0]
        stream = getattr(handler, "stream", None)
        if stream is not None:
            return stream
    return sys.stderr


_PROGRESS_LOGGER = logging.getLogger("backup_watcher_progress")


def _log_progress_message(message: str) -> None:
    if not _PROGRESS_LOGGER.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _PROGRESS_LOGGER.addHandler(handler)
        _PROGRESS_LOGGER.propagate = False
    _PROGRESS_LOGGER.info(message)


def _update_progress_line(message: str, finalize: bool = False) -> None:
    global _PROGRESS_LINE_LENGTH
    stream = _get_log_stream()
    clean_message = message.rstrip("\n")
    if stream is None:
        _log_progress_message(clean_message)
        if finalize:
            _PROGRESS_LINE_LENGTH = 0
        return
    is_tty = getattr(stream, "isatty", lambda: False)()
    if not is_tty:
        _log_progress_message(clean_message)
        if finalize:
            _PROGRESS_LINE_LENGTH = 0
        return
    padded = clean_message.ljust(max(len(clean_message), _PROGRESS_LINE_LENGTH))
    stream.write("\r" + padded)
    if finalize:
        stream.write("\n")
        _PROGRESS_LINE_LENGTH = 0
    else:
        _PROGRESS_LINE_LENGTH = len(clean_message)
    stream.flush()


def copy_file_with_progress(
    source_file: Path,
    destination_path: Path,
    progress_callback=None,
    cancel_event: Optional[threading.Event] = None,
) -> None:
    total_size = source_file.stat().st_size
    copied = 0
    next_log_threshold = PROGRESS_LOG_STEP
    total_size_str = format_size(total_size)
    progress_finished = False

    def _should_cancel() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    if progress_callback:
        progress_callback(source_file.name, copied, total_size)
    _update_progress_line(
        f"Copying {source_file.name}: {progress_bar(0)} (0.0 B / {total_size_str})"
    )
    try:
        with source_file.open("rb") as src, destination_path.open("wb") as dst:
            while True:
                if _should_cancel():
                    raise CopyCancelled(f"Copy cancelled: {source_file}")
                chunk = src.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
                copied += len(chunk)
                if _should_cancel():
                    raise CopyCancelled(f"Copy cancelled: {source_file}")
                if progress_callback:
                    progress_callback(source_file.name, copied, total_size)
                if total_size:
                    progress = copied / total_size
                    should_log = False
                    if copied == total_size:
                        should_log = True
                    elif progress >= next_log_threshold:
                        should_log = True
                        while next_log_threshold <= progress:
                            next_log_threshold += PROGRESS_LOG_STEP
                    if should_log:
                        percent = min(int(progress * 100), 100)
                        progress_finished = copied == total_size
                        _update_progress_line(
                            f"Copying {source_file.name}: {progress_bar(percent)} ({format_size(copied)} / {total_size_str})",
                            finalize=progress_finished,
                        )
                else:
                    _update_progress_line(
                        f"Copying {source_file.name}: {format_size(copied)} copied"
                    )
    except CopyCancelled:
        _update_progress_line(
            f"Copying {source_file.name}: cancelled",
            finalize=True,
        )
        raise
    except Exception:
        # 에러 발생 시(중단 포함) 파일 핸들이 닫힌 후 불완전한 파일 삭제 시도
        # 여기서 삭제하지 않으면 0바이트 또는 잘린 파일이 남아 Lock의 원인이 될 수 있음
        # 하지만 open 컨텍스트 매니저가 닫힌 후에 처리해야 함
        raise 
    
    if not total_size:
        _update_progress_line(
            f"Copying {source_file.name}: {progress_bar(100)} (0.0 B / 0.0 B)",
            finalize=True,
        )
        progress_finished = True
    if not progress_finished:
        _update_progress_line("", finalize=True)
    if progress_callback:
        progress_callback(source_file.name, total_size, total_size)


def copy_backup(
    source_file: Path,
    destination: Path,
    source_root: Path,
    overwrite_existing: bool = False,
    progress_callback=None,
    cancel_event: Optional[threading.Event] = None,
) -> Optional[Path]:
    destination_path = build_destination_path(
        destination,
        source_file,
        source_root,
        overwrite_existing=overwrite_existing
    )
    copy_completed = False
    try:
        total_size = format_size(source_file.stat().st_size)
        logging.info(
            "Starting copy %s (%s) -> %s",
            source_file,
            total_size,
            destination_path,
        )
        if overwrite_existing and destination_path.exists():
            try:
                destination_path.unlink()
            except PermissionError:
                logging.warning(f"Cannot delete existing file (in use): {destination_path}. Skipping copy.")
                return None
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        copy_file_with_progress(
            source_file,
            destination_path,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
        shutil.copystat(source_file, destination_path, follow_symlinks=True)
        logging.info("Copied %s -> %s", source_file, destination_path)
        copy_completed = True
        return destination_path
    except CopyCancelled:
        logging.info("Copy cancelled for %s -> %s", source_file, destination_path)
        raise
    except Exception:
        logging.exception("Failed to copy %s", source_file)
    finally:
        if not copy_completed:
            try:
                if destination_path.exists():
                    destination_path.unlink()
                    logging.info(f"Removed incomplete backup: {destination_path}")
            except PermissionError:
                logging.warning(f"Failed to remove incomplete backup (in use): {destination_path}")
            except Exception:
                logging.exception(f"Unexpected error while removing incomplete backup: {destination_path}")
    return None


def enforce_retention(destination: Path, retention_days: int, pattern: str) -> None:
    """
    Retention 정책에 따라 destination 경로 내에서 pattern에 맞는 파일 중 
    retention_days를 초과한 오래된 파일을 삭제합니다.

    Args:
        destination (Path): 백업 파일들이 위치한 루트 폴더.
        retention_days (int): 보존 일수. 0 이하일 경우 retention 적용하지 않음.
        pattern (str): 삭제대상 파일 이름 패턴(fnmatch 패턴).
    """
    if retention_days <= 0:
        # 보존일이 0 이하이면 retention policy를 적용하지 않음
        return
    threshold = datetime.now() - timedelta(days=retention_days)  # 삭제 임계점 시간 계산
    deleted = 0  # 삭제된 파일 개수 카운터
    base_path = destination
    if not base_path.exists():
        # 목적지 폴더가 존재하지 않으면 아무것도 하지 않음
        return
    for file_path in base_path.rglob("*"):  # 하위 모든 파일과 폴더 순회
        try:
            if not file_path.is_file():
                # 디렉토리 등 파일이 아니면 건너뜀
                continue
            if not fnmatch.fnmatch(file_path.name, pattern):
                # 패턴에 일치하지 않으면 건너뜀
                continue
            
            modified = datetime.fromtimestamp(file_path.stat().st_mtime)  # 마지막 수정시간
            if modified < threshold:
                # 임계점 이전(즉, retention 기간을 초과함!)이면 삭제
                file_path.unlink()
                deleted += 1
                logging.info("Removed expired backup: %s", file_path)
        except Exception:
            logging.exception("Failed to evaluate retention for %s", file_path)
    if deleted:
        logging.info("Retention cleanup removed %s file(s).", deleted)


def get_existing_backups(destination: Path, pattern: str) -> Dict[str, int]:
    existing: Dict[str, int] = {}
    if not destination.exists():
        return existing
    for file_path in destination.rglob("*"): # iterdir -> rglob for recursive check
        if not file_path.is_file():
            continue
        if not fnmatch.fnmatch(file_path.name, pattern):
            continue
        existing[file_path.name] = file_path.stat().st_size
    return existing


def remove_destination_file(destination: Path, file_name: str) -> None:
    # This simple removal might need update if we want to support nested files deletion by name
    # But for now, let's keep it simple or use rglob if needed.
    # Given the structure change, exact path matching is better.
    pass # Not heavily used in main loop logic provided


class FileSyncManager:
    def __init__(self, config: SyncConfig):
        self.config = config
        self.running = False
        self._stop_event = threading.Event()
        self._status_lock = threading.Lock()
        self._status = {
            "state": "IDLE",
            "current_file": "",
            "progress_percent": 0,
            "details": "",
            "last_sync_time": "",
            "updated_at": "",
        }
        # 변경점: 대기 중인 파일들을 관리할 딕셔너리
        self.pending_files: Dict[Path, PendingFile] = {}

    def _update_status(self, **kwargs) -> None:
        with self._status_lock:
            self._status.update(kwargs)
            self._status["updated_at"] = datetime.utcnow().isoformat()

    def _progress_callback(self, filename: str, copied: int, total: int) -> None:
        # (기존 코드와 동일)
        percent = 0
        if total:
            percent = int((float(copied) / float(total)) * 100)
        detail = f"Copying {filename}"
        if total:
            detail = (
                f"{filename}: {format_size(copied)} / {format_size(total)}"
            )
        self._update_status(
            state="COPYING",
            current_file=filename,
            progress_percent=min(percent, 100),
            details=detail,
        )

    def get_status(self) -> Dict[str, str]:
        with self._status_lock:
            return dict(self._status)

    def _process_pending_files(self, existing_backups: Dict[str, int]):
        """대기열에 있는 파일들의 안정화 여부를 확인하고 복사 수행"""
        now = time.time()
        # 처리 완료되어 목록에서 제거할 파일들
        processed_paths = []

        if self.pending_files:
            logging.debug(f"대기열 상태 확인 - 총 {len(self.pending_files)}개 파일 처리 중")

        # 딕셔너리 복사본으로 순회 (순회 중 삭제 방지)
        for file_path, info in list(self.pending_files.items()):
            if not self.running:
                break

            try:
                # 파일이 삭제된 경우 처리
                if not file_path.exists():
                    logging.warning(f"File disappeared pending copy: {file_path}")
                    processed_paths.append(file_path)
                    continue

                stat = file_path.stat()
                current_size = stat.st_size
                current_mtime = stat.st_mtime

                # 파일 상태가 변했는지 확인
                if current_size != info.last_size or current_mtime != info.last_mtime:
                    # 변했다면 정보 갱신하고 타이머 리셋
                    info.last_size = current_size
                    info.last_mtime = current_mtime
                    info.stable_since = now
                    logging.debug(f"대기열 - 파일 변경 감지: {file_path.name} ({format_size(current_size)}), 안정화 타이머 리셋")
                    continue

                # 안정화 시간 충족 여부 확인
                elapsed = now - info.stable_since
                if elapsed >= self.config.settle_seconds:
                    
                    # [NEW] Retention 기간 체크: 이미 오래된 파일이면 복사 스킵
                    if self.config.retention_days > 0:
                        threshold = datetime.now() - timedelta(days=self.config.retention_days)
                        file_mod_time = datetime.fromtimestamp(current_mtime)
                        if file_mod_time < threshold:
                            logging.info(f"Skipping old file (exceeds retention): {file_path.name}")
                            processed_paths.append(file_path)
                            continue

                    # 복사 로직 시작
                    logging.info(f"대기열 - 파일 안정화 완료: {file_path.name} ({format_size(current_size)}), 대기시간: {elapsed:.1f}s, 복사 시작")

                    file_key = file_path.name
                    dest_size = existing_backups.get(file_key)
                    overwrite = False

                    if dest_size is not None:
                        if dest_size == current_size:
                            # 이미 완료된 파일이면 스킵
                            processed_paths.append(file_path)
                            continue
                        # 크기가 다르면 덮어쓰기
                        overwrite = True
                        logging.warning(f"Incomplete backup detected for {file_path.name}, overwriting.")

                    self._update_status(
                        state="COPYING",
                        current_file=file_path.name,
                        details=f"Starting copy for {file_path.name}"
                    )

                    try:
                        copied_path = copy_backup(
                            file_path,
                            self.config.destination,
                            self.config.source, # source_root 전달
                            overwrite_existing=overwrite,
                            progress_callback=self._progress_callback,
                            cancel_event=self._stop_event,
                        )
                    except CopyCancelled:
                        logging.info(f"Copy operation cancelled for {file_path.name}")
                        processed_paths.append(file_path)
                        break

                    if copied_path:
                        existing_backups[file_key] = current_size
                        self._update_status(
                            state="IDLE",
                            details=f"Synced: {file_path.name}",
                            last_sync_time=datetime.utcnow().isoformat()
                        )
                        # 보존 정책 적용
                        enforce_retention(
                            self.config.destination,
                            self.config.retention_days,
                            self.config.pattern
                        )

                    processed_paths.append(file_path)

            except Exception:
                logging.exception(f"Error processing pending file: {file_path}")
                processed_paths.append(file_path)

        # 처리된 파일 대기열에서 제거
        for path in processed_paths:
            self.pending_files.pop(path, None)

        if processed_paths:
            logging.info(f"대기열 정리 완료: {len(processed_paths)}개 파일 처리됨, 남은 대기 파일: {len(self.pending_files)}개")
            
        if not self.pending_files and self.running:
             self._update_status(
                state="IDLE",
                details="Monitoring for changes..."
            )

    def run(self) -> None:
        self._stop_event.clear()
        self.running = True
        self._update_status(
            state="SCANNING",
            details=f"Watching {self.config.source} -> {self.config.destination}",
        )
        logging.info(f"Started Watcher. Poll interval: {self.config.scan_interval}s, Settle time: {self.config.settle_seconds}s")

        validate_paths(self.config.source, self.config.destination)

        # 초기 스냅샷
        known_files = snapshot_matching_files(self.config.source, self.config.pattern)
        existing_backups = get_existing_backups(
            self.config.destination,
            self.config.pattern
        )

        # 초기 파일들을 모두 Pending 상태로 등록 (즉시 복사가 아니라 안정화 체크를 거치도록 함)
        now = time.time()

        for file_path, mtime in known_files.items():
            # 이미 백업이 있고 크기도 같다면 스킵
            file_key = file_path.name
            if file_key in existing_backups:
                if file_path.stat().st_size == existing_backups[file_key]:
                    continue

            # 새로 발견된 것으로 간주하고 등록
            try:
                stat = file_path.stat()
                self.pending_files[file_path] = PendingFile(
                    path=file_path,
                    last_size=stat.st_size,
                    last_mtime=stat.st_mtime,
                    stable_since=now
                )
                logging.info(f"대기열 등록 - 초기 파일: {file_path.name} ({format_size(stat.st_size)}), 총 대기 파일: {len(self.pending_files)}개")
            except FileNotFoundError:
                continue

        # 초기 스캔 후 대기 중인 파일이 없으면 상태를 IDLE로 변경
        if not self.pending_files:
            self._update_status(
                state="IDLE",
                details="Monitoring for changes..."
            )

        try:
            while self.running:
                # 1. 새로운 파일 스캔
                new_detected = detect_new_files(self.config.source, self.config.pattern, known_files)
                if new_detected:
                    now = time.time()
                    for file_path in new_detected:
                        if file_path not in self.pending_files:
                            try:
                                stat = file_path.stat()
                                self.pending_files[file_path] = PendingFile(
                                    path=file_path,
                                    last_size=stat.st_size,
                                    last_mtime=stat.st_mtime,
                                    stable_since=now
                                )
                                logging.info(f"대기열 등록 - 새 파일 감지: {file_path.name} ({format_size(stat.st_size)}), 총 대기 파일: {len(self.pending_files)}개")
                            except FileNotFoundError:
                                pass

                # 2. 대기열에 있는 파일들의 안정화 확인 및 복사 수행
                # 대기열이 비어있지 않다면 1초 간격으로 체크 (빠른 반응)
                # 대기열이 비어있다면 scan_interval 만큼 대기

                if self.pending_files:
                    self._process_pending_files(existing_backups)
                    time.sleep(1) # 파일 처리 중에는 1초 딜레이 (CPU 과부하 방지)
                else:
                    # 대기 중인 파일이 없으면 설정된 스캔 간격만큼 대기하되, 반응성을 위해 1초씩 끊어서 대기
                    for _ in range(self.config.scan_interval):
                        if not self.running or self.pending_files: # 새 파일이 감지되면 즉시 루프 탈출 로직 추가 가능
                            break
                        time.sleep(1)

        except KeyboardInterrupt:
            logging.info("Stopping backup watcher.")
        finally:
            self.running = False
            self._update_status(state="STOPPED", details="Sync stopped")

    def stop(self):
        logging.info("Stop signal received.")
        self._stop_event.set()
        self.running = False
        self._update_status(
            state="STOPPED",
            current_file="",
            progress_percent=0,
            details="Stopping...",
        )


def main() -> None:
    config = parse_args()
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    manager = FileSyncManager(config)
    try:
        manager.run()
    except ValueError as exc:
        logging.error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
