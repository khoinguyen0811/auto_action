from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


@dataclass(slots=True)
class UploadedDataset:
    dataset_id: str
    file_path: Path
    original_name: str
    created_at: str
    sheet_name: Optional[str] = None
    mapping: dict[str, Optional[str]] = field(default_factory=dict)
    row_count: int = 0
    preview: list[dict[str, str]] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    raw_preview: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class RunRecord:
    run_id: str
    dataset_id: str
    created_at: str
    status: str = "queued"
    paused: bool = False
    pause_message: str = ""
    logs: list[dict[str, str]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    continue_event: threading.Event = field(default_factory=threading.Event)

    def add_log(self, message: str, level: str = "INFO") -> None:
        self.logs.append({"time": now_iso(), "level": level.upper(), "message": message})


class AppState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.datasets: dict[str, UploadedDataset] = {}
        self.runs: dict[str, RunRecord] = {}
        self.active_login_bot = None

    def create_dataset_id(self) -> str:
        return f"ds_{uuid.uuid4().hex[:10]}"

    def create_run_id(self) -> str:
        return f"run_{uuid.uuid4().hex[:10]}"


app_state = AppState()
