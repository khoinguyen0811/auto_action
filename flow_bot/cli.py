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
    common.add_argument("--flow-url", default="https://labs.google/fx/vi/tools/flow/project/f59c99c2-23b5-44a8-b9c7-e89f1fd6a39e/tool/f5f0a297-5a81-48b0-bcec-e4a6e63ec4d9")
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
    run.add_argument("--continue-on-video-failure", action="store_true")
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
        continue_on_video_failure=getattr(args, "continue_on_video_failure", False),
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
