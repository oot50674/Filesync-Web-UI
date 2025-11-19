from __future__ import annotations

import argparse
import fnmatch
import logging
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

DEFAULT_PATTERN = "*"
DEFAULT_RETENTION_DAYS = 60
DEFAULT_SCAN_INTERVAL = 10
DEFAULT_SETTLE_SECONDS = 10
COPY_CHUNK_SIZE = 8 * 1024 * 1024
PROGRESS_LOG_STEP = 0.01


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


def build_destination_path(destination: Path, source_file: Path, overwrite_existing: bool = False) -> Path:
    candidate = destination / source_file.name
    if not candidate.exists():
        return candidate
    if overwrite_existing:
        return candidate
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return destination / f"{source_file.stem}_{timestamp}{source_file.suffix}"


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


def copy_file_with_progress(source_file: Path, destination_path: Path) -> None:
    total_size = source_file.stat().st_size
    copied = 0
    next_log_threshold = PROGRESS_LOG_STEP
    total_size_str = format_size(total_size)
    progress_finished = False
    _update_progress_line(
        f"Copying {source_file.name}: {progress_bar(0)} (0.0 B / {total_size_str})"
    )
    with source_file.open("rb") as src, destination_path.open("wb") as dst:
        while True:
            chunk = src.read(COPY_CHUNK_SIZE)
            if not chunk:
                break
            dst.write(chunk)
            copied += len(chunk)
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
    if not total_size:
        _update_progress_line(
            f"Copying {source_file.name}: {progress_bar(100)} (0.0 B / 0.0 B)",
            finalize=True,
        )
        progress_finished = True
    if not progress_finished:
        _update_progress_line("", finalize=True)


def copy_backup(source_file: Path, destination: Path, overwrite_existing: bool = False) -> Optional[Path]:
    destination_path = build_destination_path(destination, source_file, overwrite_existing=overwrite_existing)
    try:
        total_size = format_size(source_file.stat().st_size)
        logging.info(
            "Starting copy %s (%s) -> %s",
            source_file,
            total_size,
            destination_path,
        )
        if overwrite_existing and destination_path.exists():
            destination_path.unlink()
        copy_file_with_progress(source_file, destination_path)
        shutil.copystat(source_file, destination_path, follow_symlinks=True)
        logging.info("Copied %s -> %s", source_file, destination_path)
        return destination_path
    except Exception:
        logging.exception("Failed to copy %s", source_file)
    return None


def enforce_retention(destination: Path, retention_days: int, pattern: str) -> None:
    if retention_days <= 0:
        return
    threshold = datetime.now() - timedelta(days=retention_days)
    deleted = 0
    for file_path in destination.iterdir():
        try:
            if not file_path.is_file():
                continue
            if not fnmatch.fnmatch(file_path.name, pattern):
                continue
            modified = datetime.fromtimestamp(file_path.stat().st_mtime)
            if modified < threshold:
                file_path.unlink()
                deleted += 1
                logging.info("Removed expired backup: %s", file_path)
        except Exception:
            logging.exception("Failed to evaluate retention for %s", file_path)
    if deleted:
        logging.info("Retention cleanup removed %s file(s).", deleted)


def get_existing_backups(destination: Path, pattern: str) -> Dict[str, int]:
    return {
        f.name: f.stat().st_size
        for f in destination.iterdir()
        if f.is_file() and fnmatch.fnmatch(f.name, pattern)
    }


def remove_destination_file(destination: Path, file_name: str) -> None:
    target = destination / file_name
    try:
        target.unlink()
    except FileNotFoundError:
        return
    except Exception:
        logging.exception("Failed to remove incomplete backup %s", target)


class FileSyncManager:
    def __init__(self, config: SyncConfig):
        self.config = config
        self.running = False

    def run(self) -> None:
        self.running = True
        logging.info(
            "Configured parameters: source=%s, destination=%s, pattern=%s, retention_days=%d, scan_interval=%d, settle_seconds=%d, log_level=%s",
            self.config.source,
            self.config.destination,
            self.config.pattern,
            self.config.retention_days,
            self.config.scan_interval,
            self.config.settle_seconds,
            self.config.log_level,
        )
        validate_paths(self.config.source, self.config.destination)
        known_files = snapshot_matching_files(self.config.source, self.config.pattern)
        existing_backups = get_existing_backups(self.config.destination, self.config.pattern)
        logging.info(
            "Watching %s for files matching '%s'. Copying to %s. Retention: %s day(s).",
            self.config.source,
            self.config.pattern,
            self.config.destination,
            self.config.retention_days,
        )
        
        # Initial copy loop
        for file_path in known_files:
            if not self.running:
                break
            source_size = file_path.stat().st_size
            dest_size = existing_backups.get(file_path.name)
            if dest_size == source_size:
                continue
            overwrite_existing = dest_size is not None and dest_size != source_size
            if overwrite_existing:
                logging.warning("Detected incomplete backup %s (%s vs %s), re-copying.", file_path.name, format_size(dest_size), format_size(source_size))
                remove_destination_file(self.config.destination, file_path.name)
            else:
                logging.info("Initial copy: %s not found in destination, copying...", file_path.name)
            
            if not wait_for_settle(file_path, self.config.settle_seconds):
                logging.warning("Skipping %s because it did not stabilize.", file_path)
                continue
            
            copied = copy_backup(file_path, self.config.destination, overwrite_existing=overwrite_existing)
            if copied:
                enforce_retention(self.config.destination, self.config.retention_days, self.config.pattern)
                existing_backups[file_path.name] = source_size

        # Monitoring loop
        try:
            while self.running:
                logging.debug("Scanning for new files...")
                new_files = detect_new_files(self.config.source, self.config.pattern, known_files)
                if new_files:
                    logging.info("Detected %d new file(s).", len(new_files))
                for file_path in new_files:
                    if not self.running:
                        break
                    if not fnmatch.fnmatch(file_path.name, self.config.pattern):
                        continue
                    source_size = file_path.stat().st_size
                    dest_size = existing_backups.get(file_path.name)
                    if dest_size == source_size:
                        continue
                    overwrite_existing = dest_size is not None and dest_size != source_size
                    if overwrite_existing:
                        logging.warning("Detected incomplete backup %s (%s vs %s), re-copying.", file_path.name, format_size(dest_size), format_size(source_size))
                        remove_destination_file(self.config.destination, file_path.name)
                    
                    if not wait_for_settle(file_path, self.config.settle_seconds):
                        logging.warning("Skipping %s because it did not stabilize.", file_path)
                        continue
                    
                    copied = copy_backup(file_path, self.config.destination, overwrite_existing=overwrite_existing)
                    if copied:
                        enforce_retention(self.config.destination, self.config.retention_days, self.config.pattern)
                        existing_backups[file_path.name] = source_size
                
                # Sleep in small chunks to allow faster stopping
                for _ in range(max(1, self.config.scan_interval)):
                    if not self.running:
                        break
                    time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Stopping backup watcher.")
        finally:
            self.running = False

    def stop(self):
        logging.info("Stop signal received.")
        self.running = False


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
