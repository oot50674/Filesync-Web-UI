from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import time
from queue import Empty, Queue
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from app.utils import (
    format_size,
    parse_patterns,
    matches_patterns,
    build_history_key,
    history_file_path,
    load_sync_history,
    save_sync_history,
)

DEFAULT_PATTERN = "*"
DEFAULT_RETENTION = 60
DEFAULT_RETENTION_MODE = "days"
DEFAULT_SETTLE_SECONDS = 3
DEFAULT_SCAN_INTERVAL_MINUTES = 60
COPY_CHUNK_SIZE = 8 * 1024 * 1024
HISTORY_DIR_NAME = ".history"
HISTORY_FILE_NAME = "sync_history.json"


class _CopyLane:
    """동일 소스 경로를 공유하는 작업 간 COPY 순서를 직렬화하는 대기열."""

    def __init__(self, source_key: str):
        self.source_key = source_key
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._active_id: Optional[int] = None
        self._waiting: list[int] = []
        self._last_served_id: Optional[int] = None

    def _remove_waiter(self, config_id: int) -> None:
        self._waiting = [cid for cid in self._waiting if cid != config_id]

    def _next_candidate(self) -> Optional[int]:
        if not self._waiting:
            return None
        unique_sorted = sorted(set(self._waiting))
        if self._last_served_id is None:
            return unique_sorted[0]
        higher = [cid for cid in unique_sorted if cid > self._last_served_id]
        if higher:
            return higher[0]
        return unique_sorted[0]

    def acquire(
        self,
        config_id: int,
        cancel_event: threading.Event,
        on_wait=None,
    ) -> bool:
        with self._condition:
            if config_id not in self._waiting:
                self._waiting.append(config_id)
            while True:
                if cancel_event.is_set():
                    self._remove_waiter(config_id)
                    self._condition.notify_all()
                    return False

                next_candidate = self._next_candidate()
                can_take_slot = (
                    (self._active_id is None or self._active_id == config_id)
                    and next_candidate == config_id
                )
                if can_take_slot:
                    self._remove_waiter(config_id)
                    self._active_id = config_id
                    return True

                if on_wait:
                    try:
                        on_wait(config_id, self._active_id, next_candidate)
                    except Exception:
                        logging.exception("Copy lane wait callback failed.")
                self._condition.wait(timeout=0.5)

    def release(self, config_id: int) -> None:
        with self._condition:
            if self._active_id == config_id:
                self._active_id = None
                self._last_served_id = config_id
                self._condition.notify_all()

    def abandon(self, config_id: int) -> None:
        with self._condition:
            self._remove_waiter(config_id)
            if self._active_id == config_id:
                self._active_id = None
                self._last_served_id = config_id
            self._condition.notify_all()


class SourceCopyCoordinator:
    """소스 경로 단위로 COPY 실행을 직렬화하여 충돌을 방지합니다."""

    def __init__(self):
        self._lanes: Dict[str, _CopyLane] = {}
        self._lock = threading.Lock()

    def _normalize_key(self, source_path: Path) -> str:
        try:
            return str(source_path.resolve())
        except Exception:
            return str(source_path)

    def _lane_for(self, source_path: Path) -> _CopyLane:
        key = self._normalize_key(source_path)
        with self._lock:
            if key not in self._lanes:
                self._lanes[key] = _CopyLane(key)
            return self._lanes[key]

    def acquire(
        self,
        source_path: Path,
        config_id: Optional[int],
        cancel_event: threading.Event,
        on_wait=None,
    ) -> bool:
        if config_id is None:
            return True
        lane = self._lane_for(source_path)
        return lane.acquire(config_id, cancel_event, on_wait=on_wait)

    def release(self, source_path: Path, config_id: Optional[int]) -> None:
        if config_id is None:
            return
        key = self._normalize_key(source_path)
        with self._lock:
            lane = self._lanes.get(key)
        if lane:
            lane.release(config_id)

    def abandon(self, source_path: Path, config_id: Optional[int]) -> None:
        if config_id is None:
            return
        key = self._normalize_key(source_path)
        with self._lock:
            lane = self._lanes.get(key)
        if lane:
            lane.abandon(config_id)


_copy_coordinator = SourceCopyCoordinator()


@dataclass
class PendingFile:
    path: Path
    last_size: int
    last_mtime: float
    stable_since: float  # 안정화가 시작된 시간 (timestamp)


class CopyCancelled(Exception):
    """복사 작업이 중단 요청으로 취소되었음을 나타내는 예외."""


class _SyncEventHandler(FileSystemEventHandler):
    def __init__(self, manager: "FileSyncManager"):
        super().__init__()
        self.manager = manager

    def on_created(self, event):
        self._handle_event(event)

    def on_modified(self, event):
        self._handle_event(event)

    def on_moved(self, event):
        target_path = getattr(event, "dest_path", None) or event.src_path
        self._handle_event(event, override_path=target_path)
        self.manager.queue_delete_event(Path(event.src_path))

    def on_deleted(self, event):
        self.manager.queue_delete_event(Path(event.src_path))

    def _handle_event(self, event, override_path=None):
        if event.is_directory:
            return
        target = Path(override_path or event.src_path)
        self.manager.queue_file_event(target)


class SyncConfig:
    def __init__(
        self,
        source: Path,
        destination: Path,
        pattern: str = DEFAULT_PATTERN,
        retention: int = DEFAULT_RETENTION,
        retention_mode: str = DEFAULT_RETENTION_MODE,
        settle_seconds: int = DEFAULT_SETTLE_SECONDS,
        log_level: str = "INFO",
        scan_interval_minutes: int = DEFAULT_SCAN_INTERVAL_MINUTES,
    ):
        self.source = source.resolve()
        self.destination = destination.resolve()
        self.pattern = pattern
        self.patterns = parse_patterns(pattern)
        self.retention = max(0, int(retention))
        self.retention_mode = retention_mode if retention_mode in ("days", "count", "sync") else DEFAULT_RETENTION_MODE
        self.settle_seconds = settle_seconds
        self.log_level = log_level
        try:
            interval_value = int(scan_interval_minutes)
        except (TypeError, ValueError):
            interval_value = DEFAULT_SCAN_INTERVAL_MINUTES
        self.scan_interval_minutes = max(0, interval_value)
        self.scan_interval_seconds = self.scan_interval_minutes * 60


def parse_args() -> SyncConfig:
    parser = argparse.ArgumentParser(
        description=(
            "소스 폴더에서 새로 생성된 백업 파일을 감시하고, 지정된 패턴과 일치하는 파일을 "
            "대상 폴더로 복사한 뒤, 보존 기간을 초과한 복사본을 자동으로 정리합니다."
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
        help="콤마(,)로 구분된 글롭 패턴 목록 (예: *.bak,*.zip).",
    )
    parser.add_argument(
        "--retention-mode",
        choices=["days", "count", "sync"],
        default=DEFAULT_RETENTION_MODE,
        help="보존 방식: 기간(일), 파일 개수, 또는 동기화(삭제 전파).",
    )
    parser.add_argument(
        "--retention",
        type=int,
        default=DEFAULT_RETENTION,
        help="보존 값 (일수 또는 파일 개수). 동기화 모드에서는 무시됩니다.",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        help="호환용: 기간 기반 보존 일수 (retention-mode=days일 때만 사용).",
    )
    parser.add_argument(
        "--retention-files",
        type=int,
        help="호환용: 개수 기반 보존 파일 수 (retention-mode=count일 때만 사용).",
    )
    parser.add_argument(
        "--settle-seconds",
        type=int,
        default=DEFAULT_SETTLE_SECONDS,
        help="파일을 복사하기 전에 안정화될 때까지 대기할 시간(초) (기본값: %(default)s).",
    )
    parser.add_argument(
        "--scan-interval-minutes",
        type=int,
        default=DEFAULT_SCAN_INTERVAL_MINUTES,
        help="주기적 전체 스캔 주기(분). 0이면 비활성화됩니다.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로그 상세 수준 (기본값: %(default)s).",
    )
    args = parser.parse_args()
    retention_value = args.retention
    if args.retention_mode == "days" and args.retention_days is not None:
        retention_value = args.retention_days
    elif args.retention_mode == "count" and args.retention_files is not None:
        retention_value = args.retention_files

    if args.retention_mode == "sync":
        retention_value = 0

    retention_value = max(retention_value, 0)
    return SyncConfig(
        source=args.source,
        destination=args.destination,
        pattern=args.pattern,
        retention=retention_value,
        retention_mode=args.retention_mode,
        settle_seconds=args.settle_seconds,
        log_level=args.log_level,
        scan_interval_minutes=args.scan_interval_minutes,
    )


def validate_paths(source: Path, destination: Path) -> None:
    if not source.exists() or not source.is_dir():
        raise ValueError(f"Source folder does not exist or is not a directory: {source}")
    destination.mkdir(parents=True, exist_ok=True)


def snapshot_matching_files(source: Path, patterns: list[str]) -> Dict[Path, float]:
    matches: Dict[Path, float] = {}
    if not source.exists():
        return matches
    for file_path in source.rglob("*"):
        if not file_path.is_file():
            continue
        if not matches_patterns(file_path.name, patterns):
            continue
        matches[file_path] = file_path.stat().st_mtime
    return matches


def detect_new_files(
    source: Path,
    patterns: list[str],
    known_files: Dict[Path, float],
) -> list[Path]:
    current_snapshot = snapshot_matching_files(source, patterns)
    new_files: list[Path] = []
    for file_path, mtime in current_snapshot.items():
        if file_path not in known_files or mtime > known_files[file_path]:
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
    overwrite_existing: bool = False,
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
        stem = target_path.stem
        suffix = target_path.suffix
        new_name = f"{stem}_{timestamp}{suffix}"
        return target_path.with_name(new_name)
    return target_path


def copy_file_with_progress(
    source_file: Path,
    destination_path: Path,
    progress_callback=None,
    cancel_event: Optional[threading.Event] = None,
    mode: str = "wb",
    start_pos: int = 0,
) -> None:
    total_size = source_file.stat().st_size
    copied = start_pos

    def should_cancel() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    if progress_callback:
        progress_callback(source_file.name, copied, total_size)
    try:
        with source_file.open("rb") as src, destination_path.open(mode) as dst:
            if start_pos > 0:
                src.seek(start_pos)
            while True:
                if should_cancel():
                    raise CopyCancelled(f"Copy cancelled: {source_file}")
                chunk = src.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                dst.write(chunk)
                copied += len(chunk)
                if should_cancel():
                    raise CopyCancelled(f"Copy cancelled: {source_file}")
                if progress_callback:
                    progress_callback(source_file.name, copied, total_size)
    except CopyCancelled:
        raise
    except Exception:
        raise

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
        overwrite_existing=overwrite_existing,
    )

    temp_path = destination_path.with_suffix(destination_path.suffix + ".part")

    copy_completed = False
    try:
        total_size = source_file.stat().st_size

        resume_mode = False
        start_pos = 0
        mode = "wb"

        if temp_path.exists():
            temp_size = temp_path.stat().st_size
            if temp_size < total_size:
                logging.info("Resuming incomplete transfer: %s", temp_path.name)
                resume_mode = True
                start_pos = temp_size
                mode = "ab"
            else:
                logging.info("Temp file invalid (size mismatch). Restarting: %s", temp_path.name)

        logging.info(
            "Starting copy %s -> %s (resume=%s)",
            source_file,
            destination_path,
            resume_mode,
        )

        destination_path.parent.mkdir(parents=True, exist_ok=True)

        copy_file_with_progress(
            source_file,
            temp_path,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
            mode=mode,
            start_pos=start_pos,
        )

        if destination_path.exists():
            try:
                if overwrite_existing:
                    destination_path.unlink()
                else:
                    logging.warning("Target exists and overwrite is False. Skipping replacement.")
                    return None
            except OSError:
                pass

        os.replace(temp_path, destination_path)

        shutil.copystat(source_file, destination_path, follow_symlinks=True)

        logging.info("Sync completed: %s", destination_path.name)
        copy_completed = True
        return destination_path

    except CopyCancelled:
        logging.info("Copy cancelled. Saved progress in: %s", temp_path.name)
        raise
    except Exception:
        logging.exception("Failed to copy %s", source_file)

    return None


def enforce_retention(
    destination: Path,
    retention: int,
    patterns: list[str],
    sync_history: Dict[str, str],
    retention_mode: str = DEFAULT_RETENTION_MODE,
) -> bool:
    if retention_mode == "sync":
        return False
    if retention_mode == "count":
        return _enforce_count_retention(
            destination,
            patterns,
            sync_history,
            retention,
        )
    return _enforce_days_retention(destination, patterns, sync_history, retention)


def _iter_backup_entries(destination: Path, patterns: list[str]):
    """보존 대상이 될 파일/디렉터리 목록을 생성한다.

    기존 로직은 파일만 대상으로 삼았기 때문에 .pbd 확장자를 가진 폴더형 백업이
    카운트 기준 보존에서 제외되는 문제가 있었다.
    """
    if not destination.exists():
        return

    for file_path in destination.rglob("*"):
        try:
            if file_path.is_dir():
                relative_parts = file_path.relative_to(destination).parts
                if relative_parts and relative_parts[0] == HISTORY_DIR_NAME:
                    continue
                if not matches_patterns(file_path.name, patterns):
                    continue
                yield file_path
            elif file_path.is_file():
                relative_parts = file_path.relative_to(destination).parts
                if relative_parts and relative_parts[0] == HISTORY_DIR_NAME:
                    continue
                if file_path.suffix == ".part":
                    continue
                if not matches_patterns(file_path.name, patterns):
                    continue
                yield file_path
        except Exception:
            logging.exception("Failed to evaluate retention for %s", file_path)


def _resolve_entry_timestamp(path: Path, history_value: Optional[str]) -> datetime:
    """히스토리 값 또는 파일/디렉터리 mtime으로 대표 타임스탬프 산출."""
    if history_value:
        try:
            return datetime.fromisoformat(history_value)
        except ValueError:
            logging.warning("Invalid sync history timestamp for %s", path)

    try:
        base_mtime = path.stat().st_mtime
    except FileNotFoundError:
        return datetime.utcfromtimestamp(0)

    if path.is_file():
        return datetime.fromtimestamp(base_mtime)

    newest = base_mtime
    try:
        for child in path.rglob("*"):
            try:
                newest = max(newest, child.stat().st_mtime)
            except FileNotFoundError:
                continue
    except Exception:
        logging.exception("Failed to scan directory mtime for %s", path)
    return datetime.fromtimestamp(newest)


def _delete_entry(path: Path) -> None:
    """파일 또는 디렉터리를 안전하게 삭제."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=False)
    else:
        path.unlink()


def _enforce_days_retention(
    destination: Path,
    patterns: list[str],
    sync_history: Dict[str, str],
    retention_days: int,
) -> bool:
    if retention_days <= 0:
        return False
    if not destination.exists():
        return False

    threshold = datetime.utcnow() - timedelta(days=retention_days)
    deleted = 0
    history_changed = False
    history_keys_to_remove: set[str] = set()

    for file_path in _iter_backup_entries(destination, patterns):
        try:
            history_key = build_history_key(destination, file_path)
            synced_at = _resolve_entry_timestamp(file_path, sync_history.get(history_key))

            if synced_at < threshold:
                _delete_entry(file_path)
                deleted += 1
                history_keys_to_remove.add(history_key)
                logging.info("Removed expired backup: %s", file_path)
        except Exception:
            logging.exception("Failed to evaluate retention for %s", file_path)

    for key in history_keys_to_remove:
        if sync_history.pop(key, None) is not None:
            history_changed = True

    if deleted:
        logging.info("Retention cleanup removed %s file(s).", deleted)

    return history_changed


def _enforce_count_retention(
    destination: Path,
    patterns: list[str],
    sync_history: Dict[str, str],
    retention_limit: int,
) -> bool:
    if retention_limit <= 0:
        return False
    if not destination.exists():
        return False

    file_entries: list[tuple[Path, datetime, str]] = []

    for file_path in _iter_backup_entries(destination, patterns):
        try:
            history_key = build_history_key(destination, file_path)
            synced_at = _resolve_entry_timestamp(file_path, sync_history.get(history_key))
            file_entries.append((file_path, synced_at, history_key))
        except Exception:
            logging.exception("Failed to evaluate retention for %s", file_path)

    if len(file_entries) <= retention_limit:
        return False

    sorted_entries = sorted(file_entries, key=lambda item: item[1], reverse=True)
    targets = sorted_entries[retention_limit:]
    history_changed = False

    for file_path, _, history_key in targets:
        try:
            _delete_entry(file_path)
            if sync_history.pop(history_key, None) is not None:
                history_changed = True
            logging.info("Removed overflow backup: %s", file_path)
        except Exception:
            logging.exception("Failed to remove overflow file: %s", file_path)

    return history_changed


def get_existing_backups(destination: Path, patterns: list[str]) -> Dict[str, int]:
    existing: Dict[str, int] = {}
    if not destination.exists():
        return existing
    for file_path in destination.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix == ".part":
            continue
        try:
            relative_parts = file_path.relative_to(destination).parts
        except ValueError:
            continue
        if relative_parts and relative_parts[0] == HISTORY_DIR_NAME:
            continue
        if not matches_patterns(file_path.name, patterns):
            continue
        try:
            rel_key = file_path.relative_to(destination).as_posix()
        except ValueError:
            rel_key = file_path.name
        existing[rel_key] = file_path.stat().st_size
    return existing


class FileSyncManager:
    def __init__(
        self,
        config: SyncConfig,
        status_callback=None,
        config_id: Optional[int] = None,
        copy_coordinator: Optional[SourceCopyCoordinator] = None,
    ):
        self.config = config
        self.config_id = config_id
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
        self.pending_files: Dict[Path, PendingFile] = {}
        self._event_queue: Queue = Queue()
        self._delete_queue: Queue = Queue()
        self._observer: Optional[BaseObserver] = None
        self._existing_backups: Dict[str, int] = {}
        self.history_path = history_file_path(self.config.destination)
        self.sync_history: Dict[str, str] = load_sync_history(self.history_path)
        self._queue_total_bytes = 0
        self._queue_completed_bytes = 0
        self._status_callback = status_callback
        self._copy_coordinator = copy_coordinator or _copy_coordinator
        self._last_wait_notice = 0.0
        self._rescan_interval = max(0, getattr(self.config, "scan_interval_seconds", 0))
        self._last_rescan_time = 0.0

    def _reset_queue_progress(self) -> None:
        self._queue_total_bytes = 0
        self._queue_completed_bytes = 0
        self._update_status(progress_percent=0)

    def _add_queue_bytes(self, size: int) -> None:
        if size <= 0:
            return
        self._queue_total_bytes += size

    def _remove_queue_bytes(self, size: int) -> None:
        if size <= 0:
            return
        self._queue_total_bytes = max(0, self._queue_total_bytes - size)
        if self._queue_completed_bytes > self._queue_total_bytes:
            self._queue_completed_bytes = self._queue_total_bytes

    def _calculate_overall_percent(self, current_copied: int = 0) -> int:
        total_bytes = self._queue_total_bytes
        if total_bytes <= 0:
            return 0
        completed_bytes = self._queue_completed_bytes + max(0, current_copied)
        percent = int((float(completed_bytes) / float(total_bytes)) * 100)
        return min(100, percent)

    def _mark_queue_active(self, details: str = "") -> None:
        status = self.get_status()
        state = status.get("state", "")
        if state in ("IDLE", "STOPPED"):
            self._update_status(
                state="SCANNING",
                details=details or "Pending files detected",
                current_file=status.get("current_file", ""),
                progress_percent=self._calculate_overall_percent(),
            )

    def _notify_status(self, status_snapshot: Dict[str, str]) -> None:
        if not self._status_callback:
            return
        try:
            self._status_callback(status_snapshot)
        except Exception:
            logging.exception("Status callback failed.")

    def _update_status(self, notify: bool = True, **kwargs) -> None:
        status_snapshot: Dict[str, str] = {}
        with self._status_lock:
            self._status.update(kwargs)
            self._status["updated_at"] = datetime.utcnow().isoformat()
            status_snapshot = dict(self._status)
        if notify:
            self._notify_status(status_snapshot)

    def _on_waiting_for_slot(
        self,
        config_id: int,
        active_id: Optional[int],
        next_candidate: Optional[int],
    ) -> None:
        if self.config_id != config_id:
            return
        now = time.time()
        if now - self._last_wait_notice < 1.0:
            return
        self._last_wait_notice = now
        blocker = active_id if active_id and active_id != config_id else next_candidate
        with self._status_lock:
            current_file = self._status.get("current_file", "")
        detail = "동일 소스 경합 대기 중"
        if blocker and blocker != config_id:
            detail = f"config {blocker} 작업 완료 대기 중"
        self._update_status(
            state="WAITING",
            current_file=current_file,
            progress_percent=self._calculate_overall_percent(),
            details=detail,
        )

    def _acquire_copy_slot(self) -> bool:
        if not self._copy_coordinator or self.config_id is None:
            return True
        return self._copy_coordinator.acquire(
            self.config.source,
            self.config_id,
            self._stop_event,
            on_wait=self._on_waiting_for_slot,
        )

    def _release_copy_slot(self) -> None:
        if not self._copy_coordinator or self.config_id is None:
            return
        self._last_wait_notice = 0.0
        self._copy_coordinator.release(self.config.source, self.config_id)

    def _abandon_copy_slot(self) -> None:
        if not self._copy_coordinator or self.config_id is None:
            return
        self._copy_coordinator.abandon(self.config.source, self.config_id)
        self._last_wait_notice = 0.0

    def _progress_callback(self, filename: str, copied: int, total: int) -> None:
        detail = f"Copying {filename}"
        if total:
            detail = f"{filename}: {format_size(copied)} / {format_size(total)}"
        overall_percent = self._calculate_overall_percent(copied)
        self._update_status(
            state="COPYING",
            current_file=filename,
            progress_percent=overall_percent,
            details=detail,
        )

    def get_status(self) -> Dict[str, str]:
        with self._status_lock:
            return dict(self._status)

    def _persist_history(self) -> None:
        save_sync_history(self.history_path, self.sync_history)

    def _record_sync(self, destination_path: Path) -> None:
        key = build_history_key(self.config.destination, destination_path)
        self.sync_history[key] = datetime.utcnow().isoformat()
        self._persist_history()

    def queue_file_event(self, file_path: Path) -> None:
        if not self.running:
            return
        try:
            self._event_queue.put_nowait(Path(file_path))
        except Exception:
            logging.exception("Failed to queue file event: %s", file_path)

    def queue_delete_event(self, file_path: Path) -> None:
        if not self.running or self.config.retention_mode != "sync":
            return
        try:
            self._delete_queue.put_nowait(Path(file_path))
        except Exception:
            logging.exception("Failed to queue delete event: %s", file_path)

    def _register_pending_file(self, file_path: Path, reason: str = "") -> bool:
        try:
            normalized_path = Path(file_path).resolve()
        except OSError:
            return False

        if not normalized_path.exists() or not normalized_path.is_file():
            return False

        try:
            relative_path = normalized_path.relative_to(self.config.source)
        except ValueError:
            return False

        if not matches_patterns(normalized_path.name, self.config.patterns):
            return False

        try:
            stat = normalized_path.stat()
        except FileNotFoundError:
            return False

        file_key = relative_path.as_posix()
        dest_size = self._existing_backups.get(file_key)
        if dest_size is not None and dest_size == stat.st_size:
            return False

        if normalized_path in self.pending_files:
            return False

        if not self.pending_files:
            self._reset_queue_progress()

        self.pending_files[normalized_path] = PendingFile(
            path=normalized_path,
            last_size=stat.st_size,
            last_mtime=stat.st_mtime,
            stable_since=time.time(),
        )
        self._add_queue_bytes(stat.st_size)
        label = reason or "변경 감지"
        self._mark_queue_active(f"{normalized_path.name} {label}")
        logging.info(
            "대기열 등록 - %s: %s (%s), 총 대기 파일: %s개",
            label,
            normalized_path.name,
            format_size(stat.st_size),
            len(self.pending_files),
        )
        return True

    def _pending_items_snapshot(self) -> list[tuple[Path, PendingFile]]:
        items = list(self.pending_files.items())
        if self.config.retention_mode == "count" and self.config.retention > 0:
            items.sort(key=lambda entry: entry[1].last_mtime, reverse=True)
        return items

    def _drain_event_queue(self) -> int:
        added = 0
        while True:
            try:
                path = self._event_queue.get_nowait()
            except Empty:
                break
            if self._register_pending_file(path, reason="변경 감지"):
                added += 1
        return added

    def _drain_delete_queue(self) -> None:
        while True:
            try:
                self._delete_queue.get_nowait()
            except Empty:
                break

    def _handle_source_deletion(self, source_path: Path) -> tuple[bool, bool]:
        try:
            normalized_path = Path(source_path).resolve()
        except OSError:
            return False, False

        try:
            relative_path = normalized_path.relative_to(self.config.source)
        except ValueError:
            return False, False

        if not matches_patterns(relative_path.name, self.config.patterns):
            return False, False

        target_path = self.config.destination / relative_path
        history_key = build_history_key(self.config.destination, target_path)
        history_changed = False

        if not target_path.exists() or target_path.is_dir():
            self._existing_backups.pop(relative_path.as_posix(), None)
            history_changed = self.sync_history.pop(history_key, None) is not None
            return False, history_changed

        try:
            target_path.unlink()
            history_changed = self.sync_history.pop(history_key, None) is not None
            self._existing_backups.pop(relative_path.as_posix(), None)
            logging.info("Source 삭제 감지 -> Replica 삭제: %s", target_path)
            return True, history_changed
        except Exception:
            logging.exception("Failed to mirror deletion for %s", target_path)
            return False, False

    def _process_delete_events(self) -> None:
        if self.config.retention_mode != "sync":
            self._drain_delete_queue()
            return

        removed = 0
        history_changed = False

        while True:
            try:
                path = self._delete_queue.get_nowait()
            except Empty:
                break

            deleted, history_updated = self._handle_source_deletion(path)
            if deleted:
                removed += 1
            if history_updated:
                history_changed = True

        if history_changed:
            self._persist_history()
        if removed:
            logging.info("삭제 동기화 처리 완료: %s개 파일", removed)

    def _start_observer(self) -> None:
        handler = _SyncEventHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self.config.source), recursive=True)
        observer.start()
        self._observer = observer

    def _stop_observer(self) -> None:
        if not self._observer:
            return
        try:
            self._observer.stop()
            self._observer.join(timeout=5)
        except Exception:
            logging.exception("Failed to stop observer cleanly.")
        finally:
            self._observer = None

    def _process_pending_files(self):
        now = time.time()
        processed_paths = []

        if self.pending_files:
            logging.debug("대기열 상태 확인 - 총 %s개 파일 처리 중", len(self.pending_files))

        for file_path, info in self._pending_items_snapshot():
            if not self.running:
                break

            try:
                if not file_path.exists():
                    logging.warning("File disappeared pending copy: %s", file_path)
                    self._remove_queue_bytes(info.last_size)
                    processed_paths.append(file_path)
                    continue

                stat = file_path.stat()
                current_size = stat.st_size
                current_mtime = stat.st_mtime

                if current_size != info.last_size or current_mtime != info.last_mtime:
                    size_delta = current_size - info.last_size
                    if size_delta > 0:
                        self._add_queue_bytes(size_delta)
                    elif size_delta < 0:
                        self._remove_queue_bytes(-size_delta)

                    info.last_size = current_size
                    info.last_mtime = current_mtime
                    info.stable_since = now
                    logging.debug(
                        "대기열 - 파일 변경 감지: %s (%s), 안정화 타이머 리셋",
                        file_path.name,
                        format_size(current_size),
                    )
                    continue

                elapsed = now - info.stable_since
                if elapsed >= self.config.settle_seconds:
                    logging.info(
                        "대기열 - 파일 안정화 완료: %s (%s), 대기시간: %.1fs, 복사 시작",
                        file_path.name,
                        format_size(current_size),
                        elapsed,
                    )

                    try:
                        file_key = file_path.relative_to(self.config.source).as_posix()
                    except ValueError:
                        file_key = file_path.name
                    dest_size = self._existing_backups.get(file_key)
                    overwrite = self.config.retention_mode == "sync"

                    if dest_size is not None:
                        if dest_size == current_size:
                            self._remove_queue_bytes(current_size)
                            processed_paths.append(file_path)
                            continue
                        if overwrite:
                            logging.info("동기화 모드 - 기존 파일 덮어쓰기: %s", file_path.name)
                        else:
                            overwrite = True
                            logging.warning("Incomplete backup detected for %s, overwriting.", file_path.name)

                    copy_slot_acquired = self._acquire_copy_slot()
                    if not copy_slot_acquired:
                        self._remove_queue_bytes(current_size)
                        processed_paths.append(file_path)
                        break

                    self._update_status(
                        state="COPYING",
                        current_file=file_path.name,
                        details=f"Starting copy for {file_path.name}",
                        progress_percent=self._calculate_overall_percent(),
                    )

                    try:
                        copied_path = copy_backup(
                            file_path,
                            self.config.destination,
                            self.config.source,
                            overwrite_existing=overwrite,
                            progress_callback=self._progress_callback,
                            cancel_event=self._stop_event,
                        )
                    except CopyCancelled:
                        logging.info("Copy operation cancelled for %s", file_path.name)
                        self._remove_queue_bytes(info.last_size)
                        processed_paths.append(file_path)
                        break
                    finally:
                        self._release_copy_slot()

                    if copied_path:
                        self._existing_backups[file_key] = current_size
                        self._record_sync(copied_path)
                        self._queue_completed_bytes += current_size
                        overall_percent = self._calculate_overall_percent()
                        self._update_status(
                            state="COPYING",
                            current_file="",
                            details=f"Synced: {file_path.name}",
                            last_sync_time=datetime.utcnow().isoformat(),
                            progress_percent=overall_percent,
                        )
                        history_changed = enforce_retention(
                            self.config.destination,
                            self.config.retention,
                            self.config.patterns,
                            self.sync_history,
                            self.config.retention_mode,
                        )
                        if history_changed:
                            self._persist_history()
                    else:
                        self._remove_queue_bytes(current_size)

                    processed_paths.append(file_path)

            except Exception:
                logging.exception("Error processing pending file: %s", file_path)
                self._remove_queue_bytes(info.last_size)
                processed_paths.append(file_path)

        for path in processed_paths:
            self.pending_files.pop(path, None)

        if processed_paths:
            logging.info(
                "대기열 정리 완료: %s개 파일 처리됨, 남은 대기 파일: %s개",
                len(processed_paths),
                len(self.pending_files),
            )

        if not self.pending_files and self.running:
            if self._queue_total_bytes and self._queue_completed_bytes < self._queue_total_bytes:
                self._queue_completed_bytes = self._queue_total_bytes
            self._update_status(
                state="IDLE",
                current_file="",
                progress_percent=self._calculate_overall_percent(),
                details="Watching for file changes...",
            )

    def _should_trigger_rescan(self) -> bool:
        if self._rescan_interval <= 0:
            return False
        if self._last_rescan_time == 0.0:
            self._last_rescan_time = time.time()
            return False
        return (time.time() - self._last_rescan_time) >= self._rescan_interval

    def _perform_periodic_rescan(self) -> None:
        self._last_rescan_time = time.time()
        matches = snapshot_matching_files(self.config.source, self.config.patterns)
        added = 0
        for file_path in matches:
            if self._register_pending_file(file_path, reason="주기적 스캔"):
                added += 1
        if added:
            logging.info("주기적 스캔 - 신규 파일 %s개 대기열 추가", added)

    def _seed_initial_pending(self) -> None:
        initial_matches = snapshot_matching_files(self.config.source, self.config.patterns)
        matches_items = list(initial_matches.items())

        if self.config.retention_mode == "count" and self.config.retention > 0:
            matches_items.sort(key=lambda item: item[1], reverse=True)
            limit = min(self.config.retention, len(matches_items))
            if len(matches_items) > limit:
                logging.info(
                    "Count retention mode - limiting initial sync to %s of %s source files",
                    limit,
                    len(matches_items),
                )
            matches_items = matches_items[:limit]

        for file_path, _ in matches_items:
            self._register_pending_file(file_path, reason="초기 스캔")

    def run(self) -> None:
        self._stop_event.clear()
        self.running = True
        self._update_status(
            state="SCANNING",
            details=f"Watching {self.config.source} -> {self.config.destination}",
        )
        logging.info(
            "Started watcher (watchdog). Settle time: %ss",
            self.config.settle_seconds,
        )

        try:
            validate_paths(self.config.source, self.config.destination)
        except ValueError as exc:
            logging.error(str(exc))
            self.running = False
            self._update_status(state="STOPPED", details=str(exc))
            return

        self._existing_backups = get_existing_backups(
            self.config.destination,
            self.config.patterns,
        )

        # 서버/서비스 재기동 시점에도 기존 백업에 대해 보존 정책을 한 번 적용
        try:
            history_changed = enforce_retention(
                self.config.destination,
                self.config.retention,
                self.config.patterns,
                self.sync_history,
                self.config.retention_mode,
            )
            if history_changed:
                self._persist_history()
        except Exception:
            logging.exception("Initial retention enforcement failed.")

        try:
            self._start_observer()
        except Exception:
            logging.exception("Failed to start filesystem observer.")
            self.running = False
            self._update_status(state="STOPPED", details="파일 감시 초기화 실패")
            return

        self._seed_initial_pending()

        if not self.pending_files:
            self._update_status(
                state="IDLE",
                details="Watching for file changes...",
            )

        try:
            while self.running and not self._stop_event.is_set():
                self._drain_event_queue()
                self._process_delete_events()
                if self._should_trigger_rescan():
                    self._perform_periodic_rescan()

                if self.pending_files:
                    self._process_pending_files()
                else:
                    current_state = self.get_status().get("state")
                    if current_state not in ("IDLE", "STOPPED"):
                        self._update_status(
                            state="IDLE",
                            current_file="",
                            progress_percent=self._calculate_overall_percent(),
                            details="Watching for file changes...",
                        )

                time.sleep(1)

        except KeyboardInterrupt:
            logging.info("Stopping backup watcher.")
        finally:
            self.running = False
            self._stop_observer()
            self._abandon_copy_slot()
            self._update_status(state="STOPPED", details="Sync stopped")

    def stop(self):
        logging.info("Stop signal received.")
        self._stop_event.set()
        self.running = False
        self._stop_observer()
        self._abandon_copy_slot()
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
