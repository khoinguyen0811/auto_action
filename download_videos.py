from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

import requests


RESULTS_CSV = Path("bot-output/video_results.csv")
VIDEOS_DIR = Path("bot-output/videos")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()
    return slug or "single"


def parse_scene_int(value: object, fallback: int) -> int:
    try:
        return max(1, int(float(str(value))))
    except (TypeError, ValueError):
        return fallback


def iter_rows() -> list[dict[str, str]]:
    if not RESULTS_CSV.exists():
        print(f"[ERROR] Missing CSV: {RESULTS_CSV}")
        return []
    with RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def download_file(url: str, target: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        total = 0
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                handle.write(chunk)
                total += len(chunk)
        print(f"[SUCCESS] Saved {target} ({total} bytes)")


def target_file_for_row(row: dict[str, str]) -> Path:
    scene_group_id = slugify(row.get("scene_group_id", ""))
    scene_number = parse_scene_int(row.get("scene_number"), 1)
    scene_role = slugify(row.get("scene_role", "single"))
    video_file = row.get("video_file", "").strip() or f"scene_{scene_number:02d}_{scene_role}.mp4"
    return VIDEOS_DIR / scene_group_id / video_file


def main() -> None:
    rows = iter_rows()
    if not rows:
        return

    completed_rows = [
        row for row in rows
        if row.get("status", "").strip().lower() == "completed"
        and row.get("video_url", "").strip()
    ]
    if not completed_rows:
        print("[INFO] No completed rows with video_url to download.")
        return

    for row in completed_rows:
        target = target_file_for_row(row)
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            print(f"[SKIP] {target.name} already exists.")
            continue

        print(
            f"[INFO] Downloading scene #{parse_scene_int(row.get('scene_number'), 1)} "
            f"for {row.get('product_name', '')}"
        )
        print(f"[INFO] URL: {row.get('video_url', '').strip()}")
        try:
            download_file(row.get("video_url", "").strip(), target)
        except Exception as exc:
            print(f"[ERROR] Failed {target.name}: {exc}")


if __name__ == "__main__":
    main()
