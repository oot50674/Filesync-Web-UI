from __future__ import annotations

import json
import logging
import fnmatch
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

DEFAULT_PATTERN = "*"


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
    bar = "█" * filled + " " * (width - filled)
    return f"[{bar}] {percent}%"


def parse_patterns(pattern_value: str) -> list[str]:
    """콤마(,) 구분 패턴 문자열을 리스트로 변환."""
    if not pattern_value:
        return [DEFAULT_PATTERN]
    parts = [part.strip() for part in pattern_value.split(",")]
    patterns = [part for part in parts if part]
    return patterns or [DEFAULT_PATTERN]


def matches_patterns(file_name: str, patterns: list[str]) -> bool:
    """대소문자를 무시하고 파일명이 패턴 목록 중 하나와 일치하는지 확인."""
    lowered_name = file_name.casefold()
    for pattern in patterns:
        if fnmatch.fnmatch(lowered_name, pattern.casefold()):
            return True
    return False


def build_history_key(root: Path, file_path: Path) -> str:
    try:
        return file_path.relative_to(root).as_posix()
    except ValueError:
        return file_path.name


def history_file_path(destination: Path) -> Path:
    return destination / ".history" / "sync_history.json"


def load_sync_history(history_path: Path) -> Dict[str, str]:
    if not history_path.exists():
        return {}
    try:
        with history_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict):
            return {str(key): str(value) for key, value in data.items()}
    except Exception:
        logging.exception("Failed to load sync history: %s", history_path)
    return {}


def save_sync_history(history_path: Path, history: Dict[str, str]) -> None:
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("w", encoding="utf-8") as fp:
            json.dump(history, fp, indent=2, ensure_ascii=False)
    except Exception:
        logging.exception("Failed to persist sync history: %s", history_path)


