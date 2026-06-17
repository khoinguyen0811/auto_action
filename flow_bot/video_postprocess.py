from __future__ import annotations

import shutil
import subprocess
import re
from pathlib import Path
from contextlib import suppress


LOGO_POSITIONS = {"top-left", "top-right", "bottom-left", "bottom-right"}


def find_ffmpeg_path() -> str | None:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path
    with suppress(Exception):
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    return None


def find_ffprobe_path() -> str | None:
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        return ffprobe_path
    ffmpeg_path = find_ffmpeg_path()
    if ffmpeg_path:
        sibling = Path(ffmpeg_path).with_name("ffprobe.exe")
        if sibling.exists():
            return str(sibling)
        sibling = Path(ffmpeg_path).with_name("ffprobe")
        if sibling.exists():
            return str(sibling)
    return None


def overlay_logo_with_ffmpeg(
    input_video: Path,
    logo_path: Path,
    output_video: Path,
    position: str = "top-right",
    logo_width_percent: int = 12,
    margin: int = 32,
) -> None:
    ffmpeg_path = find_ffmpeg_path()
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg is not available. Install FFmpeg or run: pip install -r requirements.txt")
    if not input_video.exists() or not input_video.is_file():
        raise FileNotFoundError(f"Input video not found: {input_video}")
    if not logo_path.exists() or not logo_path.is_file():
        raise FileNotFoundError(f"Logo file not found: {logo_path}")

    position = position if position in LOGO_POSITIONS else "top-right"
    logo_width_percent = min(25, max(5, int(logo_width_percent)))
    margin = max(0, int(margin))
    percent = logo_width_percent / 100
    x_expr, y_expr = overlay_xy(position, margin)
    filter_complex = (
        f"[1:v]format=rgba,scale=iw*sar:ih,setsar=1[logo_src];"
        f"[logo_src][0:v]scale2ref=w=ref_w*{percent:.4f}:h=ow/main_dar[logo_final][base];"
        f"[base][logo_final]overlay={x_expr}:{y_expr}:format=auto[v]"
    )

    output_video.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_video),
        "-loop",
        "1",
        "-i",
        str(logo_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-shortest",
        str(output_video),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0 and video_has_readable_frame(ffmpeg_path, output_video):
        return

    with suppress(Exception):
        output_video.unlink()
    fallback = list(command)
    audio_codec_index = fallback.index("copy")
    fallback[audio_codec_index] = "aac"
    fallback[audio_codec_index + 1:audio_codec_index + 1] = ["-b:a", "192k"]
    result = subprocess.run(fallback, capture_output=True, text=True)
    if result.returncode != 0 or not video_has_readable_frame(ffmpeg_path, output_video):
        with suppress(Exception):
            output_video.unlink()
        error = (result.stderr or result.stdout or "FFmpeg logo overlay failed.").strip()
        raise RuntimeError(error[-1600:])


def get_video_duration_seconds(video_path: Path) -> float:
    if not video_path.exists() or not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    ffprobe_path = find_ffprobe_path()
    if ffprobe_path:
        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            with suppress(ValueError):
                return max(0.0, float(result.stdout.strip()))

    ffmpeg_path = find_ffmpeg_path()
    if not ffmpeg_path:
        raise RuntimeError("FFprobe is not available and FFmpeg fallback could not be found.")
    result = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-i", str(video_path)],
        capture_output=True,
        text=True,
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or result.stdout)
    if not match:
        raise RuntimeError("Could not read video duration.")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def split_vietnamese_subtitle_text(text: str) -> list[str]:
    cleaned = normalize_subtitle_text(text)
    if not cleaned:
        return []

    chunks: list[str] = []
    for piece in re.split(r"(?<=[.!?,;:])\s+", cleaned):
        piece = piece.strip()
        if not piece:
            continue
        chunks.extend(split_long_subtitle_piece(piece, max_chars=32))
    return chunks


def normalize_subtitle_text(text: str) -> str:
    cleaned = re.sub(r"https?://\S+|www\.\S+", " ", str(text or ""))
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def split_long_subtitle_piece(piece: str, max_chars: int = 32) -> list[str]:
    if len(piece) <= max_chars:
        return [piece]

    words = piece.split()
    if not words:
        return []

    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(word[index : index + max_chars] for index in range(0, len(word), max_chars))
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def seconds_to_srt_time(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(text: str, duration: float, output_srt: Path) -> None:
    chunks = split_vietnamese_subtitle_text(text)
    output_srt.parent.mkdir(parents=True, exist_ok=True)
    if not chunks or duration <= 0.6:
        output_srt.write_text("", encoding="utf-8")
        return

    available = max(0.3, duration - 0.3)
    segment_duration = min(3.0, max(1.2, available / max(1, len(chunks))))
    lines: list[str] = []
    start = 0.0
    for index, chunk in enumerate(chunks, start=1):
        end = min(available, start + segment_duration)
        if end <= start:
            break
        lines.extend(
            [
                str(index),
                f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}",
                format_subtitle_lines(chunk),
                "",
            ]
        )
        start = end
        if start >= available:
            break

    output_srt.write_text("\n".join(lines).strip() + ("\n" if lines else ""), encoding="utf-8")


def format_subtitle_lines(chunk: str) -> str:
    chunk = chunk.strip()
    if len(chunk) <= 32:
        return chunk
    words = chunk.split()
    first = ""
    second = ""
    for word in words:
        candidate = f"{first} {word}".strip()
        if len(candidate) <= 32 and (not second):
            first = candidate
        else:
            second = f"{second} {word}".strip()
    return "\n".join(line for line in (first, second[:32]) if line)


def burn_subtitles_with_ffmpeg(
    input_video: Path,
    srt_path: Path,
    output_video: Path,
    font_size: int = 18,
) -> None:
    ffmpeg_path = find_ffmpeg_path()
    if not ffmpeg_path:
        raise RuntimeError("FFmpeg is not available. Install FFmpeg or run: pip install -r requirements.txt")
    if not input_video.exists() or not input_video.is_file():
        raise FileNotFoundError(f"Input video not found: {input_video}")
    if not srt_path.exists() or not srt_path.is_file():
        raise FileNotFoundError(f"Subtitle file not found: {srt_path}")
    if not srt_path.read_text(encoding="utf-8").strip():
        shutil.copyfile(input_video, output_video)
        return

    output_video.parent.mkdir(parents=True, exist_ok=True)
    subtitle_filter = (
        f"subtitles='{escape_ffmpeg_subtitle_path(srt_path)}':"
        f"force_style='FontName=Arial,FontSize={int(font_size)},Outline=1,Shadow=1,MarginV=60'"
    )
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_video),
        "-vf",
        subtitle_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        str(output_video),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode == 0 and video_has_readable_frame(ffmpeg_path, output_video):
        return

    with suppress(Exception):
        output_video.unlink()
    fallback = list(command)
    audio_codec_index = fallback.index("copy")
    fallback[audio_codec_index] = "aac"
    fallback[audio_codec_index + 1:audio_codec_index + 1] = ["-b:a", "192k"]
    result = subprocess.run(fallback, capture_output=True, text=True)
    if result.returncode != 0 or not video_has_readable_frame(ffmpeg_path, output_video):
        with suppress(Exception):
            output_video.unlink()
        error = (result.stderr or result.stdout or "FFmpeg subtitle burn failed.").strip()
        raise RuntimeError(error[-1600:])


def escape_ffmpeg_subtitle_path(path: Path) -> str:
    value = path.resolve().as_posix()
    value = value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return value


def overlay_xy(position: str, margin: int) -> tuple[str, str]:
    if position == "top-left":
        return str(margin), str(margin)
    if position == "bottom-left":
        return str(margin), f"H-h-{margin}"
    if position == "bottom-right":
        return f"W-w-{margin}", f"H-h-{margin}"
    return f"W-w-{margin}", str(margin)


def video_has_readable_frame(ffmpeg_path: str, video_path: Path) -> bool:
    if not video_path.exists() or video_path.stat().st_size <= 0:
        return False
    result = subprocess.run(
        [
            ffmpeg_path,
            "-v",
            "error",
            "-i",
            str(video_path),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0
