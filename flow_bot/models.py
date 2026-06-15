from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional


SceneMode = Literal["manual_pause", "skip", "auto_excel"]


@dataclass(slots=True)
class ProductRow:
    product_image: str = ""
    product_name: str = ""
    short_description: str = ""
    long_description: str = ""
    scene_group_id: str = ""
    scene_number: int = 1
    scene_total: int = 1
    scene_role: str = "single"
    scene_title: str = ""
    scene_continuity_notes: str = ""

    def validate(self) -> None:
        if not self.product_name.strip():
            raise ValueError("Missing product_name")
        if not self.short_description.strip():
            raise ValueError("Missing short_description")
        if not self.long_description.strip():
            raise ValueError("Missing long_description")


@dataclass(slots=True)
class RunConfig:
    file_path: Path
    run_id: str = ""
    sheet_name: Optional[str] = None
    start_index: int = 0
    limit: Optional[int] = None
    flow_url: str = "https://labs.google/fx/vi/tools/flow/project/f59c99c2-23b5-44a8-b9c7-e89f1fd6a39e/tool/f5f0a297-5a81-48b0-bcec-e4a6e63ec4d9"
    auth_state_path: Path = Path("playwright/.auth/flow.json")
    chrome_user_data_dir: Optional[Path] = None
    chrome_profile_directory: Optional[str] = None
    ui_base_url: Optional[str] = None
    cdp_port: int = 9222
    headless: bool = False
    slow_mo_ms: int = 250
    wait_timeout_ms: int = 600_000
    channel: str = "chrome"
    auto_next: bool = True
    auto_generate: bool = True
    auto_restart: bool = True
    keep_browser_open: bool = False
    output_dir: Path = Path("bot-output")
    temp_dir: Path = Path("tmp")
    save_debug_screenshot_on_error: bool = True
    extra_wait_after_fill_ms: int = 800
    extra_wait_after_upload_ms: int = 2500
    extra_wait_before_confirm_ms: int = 1000
    preset_json: Optional[str] = None
    website_logo_path: Optional[Path] = None
    continue_on_video_failure: bool = False
    scene_mode: SceneMode = "skip"
    scene_field_keys: tuple[str, ...] = ()
    merge_after_group_complete: bool = False
    manual_scene_pause_timeout_ms: int = 1_800_000
    wait_for_manual_scene_continue: Optional[Callable[[int], bool]] = None
    notify_manual_scene_pause: Optional[Callable[[bool, str], None]] = None


@dataclass(slots=True)
class MappingResult:
    mapped_headers: dict[str, Optional[str]] = field(default_factory=dict)
    row_count: int = 0
    sheet_name: str = ""
