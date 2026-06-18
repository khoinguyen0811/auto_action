from __future__ import annotations

import argparse
from pathlib import Path

from .excel_mapper import build_products
from .flow_runner import FlowBot, log, print_products
from .models import RunConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Google Flow batch bot powered by Playwright.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--flow-url", default="https://labs.google/fx/vi/tools/flow/project/29290e6e-cefb-45dc-bb4a-7d536bf5b33f/tool/fd2e21f2-9304-4ec9-8026-866a0672264c")
    common.add_argument("--auth-state", default="playwright/.auth/flow.json")
    common.add_argument("--user-data-dir", help="Chrome User Data directory for persistent profile mode")
    common.add_argument("--profile-directory", help="Chrome profile directory name, e.g. Default or Profile 1")
    common.add_argument("--headless", action="store_true")
    common.add_argument("--channel", default="chrome")
    common.add_argument("--slow-mo", type=int, default=250)
    common.add_argument("--sheet")

    login = subparsers.add_parser("login", parents=[common], help="Open Flow and save login session.")
    login.add_argument("--keep-browser-open", action="store_true")

    inspect_cmd = subparsers.add_parser("inspect", parents=[common], help="Read Excel and print mapped products.")
    inspect_cmd.add_argument("--file", required=True)

    run = subparsers.add_parser("run", parents=[common], help="Run Flow batch from Excel/CSV.")
    run.add_argument("--file", required=True)
    run.add_argument("--start", type=int, default=1, help="1-based start row in normalized product list.")
    run.add_argument("--count", type=int, help="How many products to run.")
    run.add_argument("--wait-timeout", type=int, default=600, help="Seconds to wait for video completion.")
    run.add_argument("--no-auto-next", action="store_true")
    run.add_argument("--no-auto-generate", action="store_true")
    run.add_argument("--no-auto-restart", action="store_true")
    run.add_argument(
        "--video-model",
        default="Veo 3.1 - Lite",
        choices=[
            "auto",
            "Omni Flash",
            "Veo 3.1 - Lite",
            "Veo 3.1 - Fast",
            "Veo 3.1 - Quality",
        ],
        help="Video model to select on Step 2 before Brainstorm.",
    )
    run.add_argument(
        "--aspect-ratio",
        default="9:16",
        choices=["9:16", "16:9", "1:1"],
        help="Aspect ratio to select in the Flow tool when available.",
    )
    run.add_argument("--continue-on-video-failure", action="store_true")
    run.add_argument(
        "--multi-clip-mode",
        default="auto",
        choices=["off", "auto", "2", "3"],
        help="Generate one final product video from 2-3 connected clips, or keep single-video mode with off.",
    )
    run.add_argument(
        "--scene-builder-mode",
        default="native_flow",
        choices=["native_flow", "bot_merge", "off"],
        help="Use Flow Scenebuilder when available, bot-side FFmpeg merge, or no scene builder.",
    )
    run.add_argument(
        "--target-final-duration",
        type=int,
        default=20,
        choices=[15, 20, 24, 30],
        help="Target total duration for multi-clip final videos.",
    )
    run.add_argument(
        "--download-mode",
        default="save_local",
        choices=["capture_only", "save_local", "save_local_and_zip"],
        help="How generated videos should be captured and saved.",
    )
    run.add_argument(
        "--max-generate-retries",
        type=int,
        default=1,
        help="Retry count for each failed clip generation.",
    )
    run.add_argument("--no-product-image-cleanup", action="store_true")
    run.add_argument(
        "--cleanup-mode",
        default="auto",
        choices=["auto", "remove_background", "sharpen_only", "none"],
        help="Product image cleanup mode before upload.",
    )
    run.add_argument("--keep-browser-open", action="store_true")

    return parser


def build_config(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        file_path=Path(getattr(args, "file", ".")),
        sheet_name=args.sheet,
        start_index=max(0, getattr(args, "start", 1) - 1),
        limit=getattr(args, "count", None),
        flow_url=args.flow_url,
        auth_state_path=Path(args.auth_state),
        chrome_user_data_dir=Path(args.user_data_dir) if getattr(args, "user_data_dir", None) else None,
        chrome_profile_directory=getattr(args, "profile_directory", None),
        headless=args.headless,
        slow_mo_ms=args.slow_mo,
        wait_timeout_ms=getattr(args, "wait_timeout", 600) * 1000,
        channel=args.channel,
        auto_next=not getattr(args, "no_auto_next", False),
        auto_generate=not getattr(args, "no_auto_generate", False),
        auto_restart=not getattr(args, "no_auto_restart", False),
        video_model=getattr(args, "video_model", "Veo 3.1 - Lite"),
        aspect_ratio=getattr(args, "aspect_ratio", "9:16"),
        continue_on_video_failure=getattr(args, "continue_on_video_failure", False),
        multi_clip_mode=getattr(args, "multi_clip_mode", "auto"),
        scene_builder_mode=getattr(args, "scene_builder_mode", "native_flow"),
        target_final_duration=getattr(args, "target_final_duration", 20),
        download_mode=getattr(args, "download_mode", "save_local"),
        max_generate_retries=max(0, getattr(args, "max_generate_retries", 1)),
        enable_product_image_cleanup=not getattr(args, "no_product_image_cleanup", False),
        cleanup_mode=getattr(args, "cleanup_mode", "auto"),
        keep_browser_open=getattr(args, "keep_browser_open", False),
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config = build_config(args)

    if args.command == "inspect":
        products, mapping = build_products(config.file_path, config.sheet_name)
        log(f"Mapped sheet: {mapping.sheet_name}")
        log(f"Mapped headers: {mapping.mapped_headers}")
        print_products(products)
        return

    with FlowBot(config) as bot:
        if args.command == "login":
            bot.save_auth_interactive()
            if config.keep_browser_open:
                input("Press Enter to close browser...")
            return

        if args.command == "run":
            products, mapping = build_products(config.file_path, config.sheet_name)
            log(f"Using sheet: {mapping.sheet_name}")
            log(f"Mapped headers: {mapping.mapped_headers}")
            log(f"Prepared {len(products)} products.")
            bot.run_batch(products)


if __name__ == "__main__":
    main()
