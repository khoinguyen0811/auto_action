from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional


SceneMode = Literal["manual_pause", "skip", "auto_excel"]
MultiClipMode = Literal["off", "auto", "2", "3"]
SceneBuilderMode = Literal["native_flow", "bot_merge", "off"]
DownloadMode = Literal["capture_only", "save_local", "save_local_and_zip"]
TtsProvider = Literal["edge_tts", "gtts", "azure", "openai", "none"]
VideoModel = Literal[
    "auto",
    "Omni Flash",
    "Veo 3.1 - Lite",
    "Veo 3.1 - Fast",
    "Veo 3.1 - Quality",
]


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
    flow_url: str = "https://labs.google/fx/vi/tools/flow/project/29290e6e-cefb-45dc-bb4a-7d536bf5b33f/tool/fd2e21f2-9304-4ec9-8026-866a0672264c"
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
    video_model: VideoModel = "Veo 3.1 - Lite"
    aspect_ratio: str = "9:16"
    enable_logo_overlay: bool = True
    logo_file_path: Optional[str] = None
    logo_position: str = "top-right"
    logo_width_percent: int = 12
    logo_margin: int = 32
    strict_logo_overlay: bool = False
    auto_logo_overlay_after_batch: bool = False
    enable_subtitles: bool = True
    subtitle_source: str = "voiceover"
    subtitle_position: str = "bottom"
    subtitle_font_size: int = 18
    subtitle_style: str = "clean"
    enable_external_tts: bool = True
    tts_provider: TtsProvider = "edge_tts"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    tts_rate: str = "+0%"
    tts_pitch: str = "+0Hz"
    tts_volume: float = 1.0
    background_audio_volume: float = 0.35
    voice_audio_volume: float = 1.0
    enable_product_image_cleanup: bool = True
    cleanup_mode: str = "auto"
    cleanup_background: str = "transparent"
    cleanup_sharpen: bool = True
    cleanup_white_background_fallback: bool = True
    cleanup_cache_enabled: bool = True
    enable_flow_product_cleanup: bool = True
    flow_product_cleanup_timeout_ms: int = 120_000
    max_upload_dialog_retries: int = 3
    max_page_refresh_retries: int = 1
    max_browser_reconnect_retries: int = 3
    scene_field_keys: tuple[str, ...] = ()
    merge_after_group_complete: bool = False
    multi_clip_mode: MultiClipMode = "auto"
    scene_builder_mode: SceneBuilderMode = "native_flow"
    target_final_duration: int = 20
    download_mode: DownloadMode = "save_local"
    max_generate_retries: int = 1
    manual_scene_pause_timeout_ms: int = 1_800_000
    wait_for_manual_scene_continue: Optional[Callable[[int], bool]] = None
    notify_manual_scene_pause: Optional[Callable[[bool, str], None]] = None


@dataclass(slots=True)
class MappingResult:
    mapped_headers: dict[str, Optional[str]] = field(default_factory=dict)
    row_count: int = 0
    sheet_name: str = ""
