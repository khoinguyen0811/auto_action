from __future__ import annotations

import json
import subprocess
from pathlib import Path


VIDEOS_DIR = Path("bot-output/videos")
FINAL_DIR = Path("bot-output/final-videos")


def iter_manifests() -> list[Path]:
    if not VIDEOS_DIR.exists():
        return []
    return sorted(VIDEOS_DIR.glob("*/manifest.json"))


def main() -> None:
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    manifests = iter_manifests()
    if not manifests:
        print("[INFO] No manifest.json files found.")
        return

    for manifest_path in manifests:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        scene_group_id = data.get("scene_group_id", manifest_path.parent.name)
        scenes = sorted(
            data.get("scenes", []),
            key=lambda item: int(item.get("scene_number", 0)),
        )
        completed = [
            manifest_path.parent / scene.get("video_file", "")
            for scene in scenes
            if scene.get("status") == "completed" and scene.get("video_file")
        ]
        completed = [path for path in completed if path.exists()]
        if not completed:
            print(f"[SKIP] No completed scene files for {scene_group_id}")
            continue

        concat_file = manifest_path.parent / "ffmpeg_concat.txt"
        concat_file.write_text(
            "\n".join(f"file '{path.resolve().as_posix()}'" for path in completed),
            encoding="utf-8",
        )
        final_path = FINAL_DIR / f"final_{scene_group_id}.mp4"
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file.as_posix(),
            "-c",
            "copy",
            final_path.as_posix(),
        ]
        print(f"[INFO] Merging {scene_group_id} -> {final_path.name}")
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[SUCCESS] Saved {final_path}")
        else:
            print(f"[ERROR] ffmpeg failed for {scene_group_id}")
            if result.stderr:
                print(result.stderr.strip())


if __name__ == "__main__":
    main()
