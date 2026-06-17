from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    dataset_id: str
    mapping: dict[str, str | None] | None = None
    preset_json: str | None = None
    website_logo_path: str | None = None
    start: int = Field(default=1, ge=1)
    count: int | None = Field(default=None, ge=1)
    headless: bool = False
    slow_mo: int = Field(default=350, ge=0, le=5000)
    wait_timeout_seconds: int = Field(default=600, ge=30, le=3600)
    auto_next: bool = True
    auto_generate: bool = True
    auto_restart: bool = True
    continue_on_video_failure: bool = False
    scene_mode: Literal["manual_pause", "skip", "auto_excel"] = "skip"
    video_model: Literal[
        "auto",
        "Omni Flash",
        "Veo 3.1 - Lite",
        "Veo 3.1 - Fast",
        "Veo 3.1 - Quality",
    ] = "Veo 3.1 - Lite"
    enable_logo_overlay: bool = True
    logo_file_path: str | None = None
    logo_position: Literal["top-left", "top-right", "bottom-left", "bottom-right"] = "top-right"
    logo_width_percent: int = Field(default=12, ge=5, le=25)
    logo_margin: int = Field(default=32, ge=0, le=512)
    strict_logo_overlay: bool = False
    auto_logo_overlay_after_batch: bool = False
    enable_subtitles: bool = True
    subtitle_source: Literal["voiceover", "caption", "final_prompt", "short_description", "auto"] = "voiceover"
    subtitle_position: Literal["bottom", "top"] = "bottom"
    subtitle_font_size: int = Field(default=18, ge=10, le=48)
    subtitle_style: Literal["clean"] = "clean"
    merge_after_group_complete: bool = False
    keep_browser_open: bool = False
    ui_base_url: str | None = None
    user_data_dir: str | None = None
    profile_directory: str | None = None
    cdp_port: int = 9222


class LoginOpenRequest(BaseModel):
    headless: bool = False
    slow_mo: int = Field(default=350, ge=0, le=5000)
    flow_url: str = "https://labs.google/fx/vi/tools/flow/project/f59c99c2-23b5-44a8-b9c7-e89f1fd6a39e/tool/f5f0a297-5a81-48b0-bcec-e4a6e63ec4d9"
    user_data_dir: str | None = None
    profile_directory: str | None = None
    cdp_port: int = 9222


class RunContinueRequest(BaseModel):
    action: Literal["continue_after_scene_manual"] = "continue_after_scene_manual"


class LogoOverlayRequest(BaseModel):
    logo_file_path: str
    logo_position: Literal["top-left", "top-right", "bottom-left", "bottom-right"] = "top-right"
    logo_width_percent: int = Field(default=12, ge=5, le=25)
    logo_margin: int = Field(default=32, ge=0, le=512)
