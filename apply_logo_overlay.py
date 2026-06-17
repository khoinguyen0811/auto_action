from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from flow_bot.video_postprocess import LOGO_POSITIONS, overlay_logo_with_ffmpeg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply FFmpeg logo overlay to stored batch videos.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--logo", required=True, help="Path to logo image.")
    parser.add_argument("--position", default="top-right", choices=sorted(LOGO_POSITIONS))
    parser.add_argument("--width-percent", type=int, default=12)
    parser.add_argument("--margin", type=int, default=32)
    parser.add_argument("--output-dir", default="bot-output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    batch_dir = output_dir / "storage" / args.batch_id
    manifest_path = batch_dir / "manifest.json"
    logo_path = Path(args.logo).expanduser()
    if not logo_path.is_absolute():
        logo_path = (Path.cwd() / logo_path).resolve()

    if not manifest_path.exists():
        raise FileNotFoundError(f"Batch manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    processed = 0
    failed = 0
    for item in manifest.get("items", []):
        if str(item.get("status") or "").lower() != "completed":
            continue
        raw_rel = str(item.get("raw_video_file") or "")
        if not raw_rel:
            raw_rel = relative_to_batch(item.get("raw_storage_path") or item.get("storage_path"), args.batch_id)
        if not raw_rel:
            continue
        raw_video = batch_dir / raw_rel
        final_rel = str(item.get("final_video_file") or f"videos/{raw_video.name}")
        final_video = batch_dir / final_rel
        try:
            overlay_logo_with_ffmpeg(
                raw_video,
                logo_path,
                final_video,
                position=args.position,
                logo_width_percent=args.width_percent,
                margin=args.margin,
            )
            item.update(
                {
                    "raw_video_file": raw_rel,
                    "final_video_file": final_rel,
                    "video_file": final_rel,
                    "storage_path": (final_video.relative_to(output_dir)).as_posix(),
                    "logo_overlay_enabled": True,
                    "logo_overlay_status": "success",
                    "logo_overlay_error": "",
                    "logo_position": args.position,
                    "logo_width_percent": args.width_percent,
                    "logo_margin": args.margin,
                }
            )
            processed += 1
            print(f"[SUCCESS] {raw_rel} -> {final_rel}")
        except Exception as exc:
            item.update(
                {
                    "logo_overlay_enabled": True,
                    "logo_overlay_status": "failed",
                    "logo_overlay_error": str(exc),
                    "logo_position": args.position,
                    "logo_width_percent": args.width_percent,
                    "logo_margin": args.margin,
                }
            )
            failed += 1
            print(f"[ERROR] {raw_rel}: {exc}")

    manifest["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] processed={processed} failed={failed}")


def relative_to_batch(path_value: object, batch_id: str) -> str:
    value = str(path_value or "").strip().replace("\\", "/")
    if not value:
        return ""
    if value.startswith("storage/"):
        value = value.removeprefix("storage/")
    if value.startswith(f"{batch_id}/"):
        value = value[len(batch_id) + 1 :]
    return value


if __name__ == "__main__":
    main()
