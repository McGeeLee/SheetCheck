"""Encode genuine browser screenshots with a separate Chinese caption strip.

frames.json: [{"file": "frame-000001.png", "captured_at_ms": 1234567890000}, ...]
captions.json: [{"start": 0, "end": 12, "text": "检查字段映射"}, ...]
Optional segments.json: [{"source_start_ms": 1234567890000,
                          "source_end_ms": 1234567902000, "label": "映射"}, ...]

Timestamps are not sped up. Segments explicitly select and concatenate original
recording intervals. The UI image is only scaled and padded, never reconstructed
or cropped. Captions are generated below it and also saved as WebVTT. All media
commands use argument lists, not shell strings. FFmpeg is a recording tool only.
Screenshot bytes may be PNG or JPEG regardless of their filename suffix; the
detected encoding is verified and recorded without rewriting the source image.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont


DEFAULT_FONT = Path("/System/Library/Fonts/STHeiti Medium.ttc")
DEFAULT_TOOLS = Path("/private/tmp/sheetcheck-m4-ffmpeg")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_array(path: Path) -> list:
    result = json.loads(path.read_text())
    if not isinstance(result, list):
        raise ValueError(f"Expected a JSON array: {path.name}")
    return result


def finite_number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return value


def read_frames(path: Path) -> list[dict]:
    root = path.resolve().parent
    frames = []
    dimensions = None
    for item in read_array(path):
        name = item["file"]
        source = (root / name).resolve()
        if not source.is_relative_to(root) or source.suffix.lower() not in {".png", ".jpg", ".jpeg"} or not source.is_file():
            raise ValueError("Frames must be screenshot image files inside the manifest directory")
        timestamp = finite_number(item["captured_at_ms"], "captured_at_ms")
        if not isinstance(timestamp, int):
            raise ValueError("Frame timestamps must be integer milliseconds")
        if frames and timestamp <= frames[-1]["captured_at_ms"]:
            raise ValueError("Frame timestamps must be strictly increasing")
        with Image.open(source) as frame:
            image_format = frame.format
            if image_format not in {"PNG", "JPEG"}:
                raise ValueError("Screenshot image encoding must be PNG or JPEG")
            if frames and image_format != frames[0]["image_format"]:
                raise ValueError("Keep the screenshot image encoding unchanged during recording")
            frame.verify()
        with Image.open(source) as frame:
            if dimensions is None:
                dimensions = frame.size
            if frame.size != dimensions:
                raise ValueError("Keep the browser viewport size unchanged during recording")
        frames.append({"file": name, "path": source, "captured_at_ms": timestamp,
                       "sha256": digest(source), "width": dimensions[0], "height": dimensions[1],
                       "image_format": image_format})
    if len(frames) < 2:
        raise ValueError("At least two recorded frames are required")
    return frames


def build_timeline(frames: list[dict], selections: list | None, tail_ms: int) -> tuple[list, list]:
    times = [frame["captured_at_ms"] for frame in frames]
    recording_end = times[-1] + tail_ms
    if selections is None:
        selections = [{"source_start_ms": times[0], "source_end_ms": recording_end,
                       "label": "完整录制"}]
    if not selections:
        raise ValueError("At least one recording segment must be selected")
    intervals, mapping = [], []
    output_ms = 0
    last_source_end = times[0]
    for item in selections:
        start = finite_number(item["source_start_ms"], "source_start_ms")
        end = finite_number(item["source_end_ms"], "source_end_ms")
        if not isinstance(start, int) or not isinstance(end, int):
            raise ValueError("Segment timestamps must be integer milliseconds")
        if start < times[0] or end > recording_end or start >= end:
            raise ValueError("Segment is outside the recorded interval")
        if start < last_source_end:
            raise ValueError("Segments must preserve recording order without repeating intervals")
        last_source_end = end
        mapping.append({"source_start_ms": start, "source_end_ms": end,
                        "output_start_ms": output_ms, "output_end_ms": output_ms + end - start,
                        "label": str(item.get("label", ""))})
        index = bisect_right(times, start) - 1
        cursor = start
        while cursor < end:
            next_time = times[index + 1] if index + 1 < len(times) else recording_end
            stop = min(next_time, end)
            intervals.append({"frame_index": index, "duration_ms": stop - cursor,
                              "source_start_ms": cursor, "source_end_ms": stop,
                              "output_start_ms": output_ms, "output_end_ms": output_ms + stop - cursor})
            output_ms += stop - cursor
            cursor = stop
            index += 1
    return intervals, mapping


def read_captions(path: Path, duration: float) -> list[dict]:
    captions = []
    for item in read_array(path):
        start = finite_number(item["start"], "caption start")
        end = finite_number(item["end"], "caption end")
        text = item["text"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Each caption requires nonempty text")
        if start < 0 or start >= end or end > duration + 0.001:
            raise ValueError("Caption is outside the output timeline")
        if captions and start < captions[-1]["end"]:
            raise ValueError("Captions must be sorted and must not overlap")
        captions.append({"start": start, "end": end, "text": text})
    return captions


def vtt_time(seconds: float) -> str:
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    seconds, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{millis:03}"


def write_vtt(path: Path, captions: list[dict]) -> None:
    lines = ["WEBVTT", "", "NOTE Captions describe real recorded UI; added outside the original UI image.", ""]
    for index, caption in enumerate(captions, 1):
        lines += [str(index), f"{vtt_time(caption['start'])} --> {vtt_time(caption['end'])}",
                  caption["text"].replace("-->", "→"), ""]
    path.write_text("\n".join(lines))


def caption_image(text: str, width: int, height: int, font_path: Path) -> Image.Image:
    """Draw annotations only; the original UI pixels never enter Pillow."""
    image = Image.new("RGB", (width, height), "#10232B")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 3), fill="#31C5B0")
    if not text:
        return image
    for size in range(29, 17, -1):
        font = ImageFont.truetype(str(font_path), size=size)
        lines = []
        for paragraph in text.splitlines():
            line = ""
            for char in paragraph:
                if line and draw.textlength(line + char, font=font) > width - 80:
                    lines.append(line)
                    line = char
                else:
                    line += char
            lines.append(line)
        line_height = size + 9
        if len(lines) * line_height <= height - 18:
            y = (height - len(lines) * line_height) // 2
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                draw.text(((width - draw.textlength(line, font=font)) / 2, y - bbox[1]),
                          line, font=font, fill="#F5FAFC")
                y += line_height
            return image
    raise ValueError("Caption is too long for the separate bottom strip; shorten it")


def concat_file(path: Path, rows: list[tuple[str, float]]) -> None:
    # Filenames are generated internally and relative to the temporary directory.
    lines = ["ffconcat version 1.0"]
    for filename, duration in rows:
        lines += [f"file '{filename}'", f"duration {duration:.6f}"]
    lines.append(f"file '{rows[-1][0]}'")
    path.write_text("\n".join(lines) + "\n")


def execute(args: argparse.Namespace) -> dict:
    if args.width % 2 or args.height % 2 or args.caption_height % 2:
        raise ValueError("Video and caption dimensions must be even for yuv420p")
    if args.width < 640 or args.height < 480 or not 64 <= args.caption_height <= args.height // 3:
        raise ValueError("Use a readable video size and a separate caption strip")
    if not 2 <= args.fps <= 30 or not 0 < args.tail_ms <= 1000:
        raise ValueError("Output fps must be 2–30; final captured frame hold must be 1–1000 ms")
    if not args.font.is_file():
        raise ValueError("Choose an installed Chinese font file with --font")
    frames = read_frames(args.frames)
    intervals, mapping = build_timeline(frames, read_array(args.segments) if args.segments else None, args.tail_ms)
    duration = intervals[-1]["output_end_ms"] / 1000
    if args.expected_duration and abs(duration - args.expected_duration) > args.duration_tolerance:
        raise ValueError(f"Selected recording lasts {duration:.3f}s; select real intervals near {args.expected_duration}s")
    captions = read_captions(args.captions, duration)
    output = args.output.resolve()
    if output.exists() and not args.overwrite:
        raise ValueError("Output exists; use a new path or explicitly provide --overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    vtt = output.with_suffix(".vtt")
    if vtt.exists() and not args.overwrite:
        raise ValueError("Caption output exists; use a new path or explicitly provide --overwrite")
    write_vtt(vtt, captions)
    source_duration_ms = frames[-1]["captured_at_ms"] - frames[0]["captured_at_ms"]
    capture_gaps = [right["captured_at_ms"] - left["captured_at_ms"] for left, right in zip(frames, frames[1:])]
    record = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "plan_only" if args.plan_only else "encoded",
        "source_kind": "actual UI screenshots supplied by recording operator",
        "frame_manifest": str(args.frames.resolve()), "frame_manifest_sha256": digest(args.frames),
        "caption_source": str(args.captions.resolve()), "caption_source_sha256": digest(args.captions),
        "segment_source": str(args.segments.resolve()) if args.segments else None,
        "segment_source_sha256": digest(args.segments) if args.segments else None,
        "source_frame_count": len(frames), "source_width": frames[0]["width"], "source_height": frames[0]["height"],
        "capture_average_fps": (len(frames) - 1) * 1000 / source_duration_ms,
        "capture_median_gap_ms": statistics.median(capture_gaps), "capture_max_gap_ms": max(capture_gaps),
        "timeline_duration_seconds": duration, "source_to_output_segments": mapping,
        "frame_intervals": intervals, "captions": captions,
        "recording_boundary": "Original capture timing preserved within selected intervals; no playback acceleration. Last captured frame may be held for explicitly recorded tail_ms. Screenshot recording does not contain motion between captures.",
        "tail_ms": args.tail_ms, "output_fps": args.fps,
        "ui_processing": "Aspect-preserving scale and letterbox; color range converted to limited-range video; no crop or reconstructed UI",
        "caption_processing": "Pillow creates a separate bottom strip; not part of the captured UI",
        "caption_font": str(args.font), "caption_font_sha256": digest(args.font),
        "caption_strip_pixels": args.caption_height,
        "output_width": args.width, "output_height": args.height, "audio": "none",
        "vtt": str(vtt), "vtt_sha256": digest(vtt),
        "source_frames": [{key: value for key, value in frame.items() if key != "path"} for frame in frames],
    }
    if args.plan_only:
        plan = output.with_suffix(".plan.json")
        plan.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        return record
    for tool in (args.ffmpeg, args.ffprobe):
        subprocess.run([str(tool), "-version"], capture_output=True, text=True, check=True)
    record["encoding_tools"] = {tool.name: {"path": str(tool), "sha256": digest(tool)}
                                for tool in (args.ffmpeg, args.ffprobe)}
    with tempfile.TemporaryDirectory(prefix="sheetcheck-demo-") as temporary:
        temporary = Path(temporary)
        for index in {interval["frame_index"] for interval in intervals}:
            (temporary / f"source-{index:06d}.png").symlink_to(frames[index]["path"])
        concat_file(temporary / "ui.ffconcat", [(f"source-{item['frame_index']:06d}.png", item["duration_ms"] / 1000)
                                               for item in intervals])
        caption_image("", args.width, args.caption_height, args.font).save(temporary / "caption-empty.png")
        caption_rows, cursor = [], 0
        for index, caption in enumerate(captions):
            if caption["start"] > cursor:
                caption_rows.append(("caption-empty.png", caption["start"] - cursor))
            filename = f"caption-{index:06d}.png"
            caption_image(caption["text"], args.width, args.caption_height, args.font).save(temporary / filename)
            caption_rows.append((filename, caption["end"] - caption["start"]))
            cursor = caption["end"]
        if cursor < duration:
            caption_rows.append(("caption-empty.png", duration - cursor))
        concat_file(temporary / "captions.ffconcat", caption_rows)
        ui_height = args.height - args.caption_height
        filters = (f"[0:v]scale={args.width}:{ui_height}:force_original_aspect_ratio=decrease:force_divisible_by=2:in_range=auto:out_range=tv,"
                   f"pad={args.width}:{ui_height}:(ow-iw)/2:(oh-ih)/2:color=0x0B1320,"
                   f"pad={args.width}:{args.height}:0:0:color=0x0B1320,setsar=1[ui];"
                   f"[ui][1:v]overlay=0:{ui_height}:shortest=1,format=yuv420p,setparams=range=limited[v]")
        command = [str(args.ffmpeg), "-hide_banner", "-nostdin", "-y" if args.overwrite else "-n",
                   "-f", "concat", "-safe", "1", "-i", str(temporary / "ui.ffconcat"),
                   "-f", "concat", "-safe", "1", "-i", str(temporary / "captions.ffconcat"),
                   "-filter_complex", filters, "-map", "[v]", "-an", "-t", f"{duration:.6f}",
                   "-r", str(args.fps), "-c:v", "libopenh264", "-b:v", "3000k", "-pix_fmt", "yuv420p", "-color_range", "tv",
                   "-movflags", "+faststart", str(output)]
        log = output.with_suffix(".encode.log")
        with log.open("w") as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
        record["encoder_command_argv"] = command
    probe_command = [str(args.ffprobe), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(output)]
    probe = json.loads(subprocess.run(probe_command, capture_output=True, text=True, check=True).stdout)
    streams = probe["streams"]
    if len(streams) != 1:
        raise RuntimeError("Expected one video stream and no audio")
    video = streams[0]
    expected = {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "color_range": "tv", "width": args.width, "height": args.height}
    if any(video.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Encoded video format differs from the requested format")
    if abs(float(probe["format"]["duration"]) - duration) > max(0.25, 2 / args.fps):
        raise RuntimeError("Encoded duration differs from the source timeline")
    keyframe_dir = output.parent / (output.stem + "-keyframes")
    keyframe_dir.mkdir(exist_ok=True)
    keyframes = []
    for index, fraction in enumerate((0.03, 0.18, 0.33, 0.48, 0.63, 0.78, 0.93), 1):
        timestamp = min(duration - 1 / args.fps, duration * fraction)
        path = keyframe_dir / f"frame-{index:02d}.png"
        subprocess.run([str(args.ffmpeg), "-v", "error", "-nostdin", "-y", "-ss", f"{timestamp:.3f}",
                        "-i", str(output), "-frames:v", "1", str(path)], capture_output=True, text=True, check=True)
        keyframes.append({"time_seconds": timestamp, "path": str(path), "sha256": digest(path)})
    record.update({"validation": "PASS", "ffprobe": probe, "keyframes": keyframes,
                   "output": str(output), "output_sha256": digest(output), "output_bytes": output.stat().st_size})
    output.with_suffix(".video.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--captions", type=Path, required=True)
    parser.add_argument("--segments", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg", type=Path, default=DEFAULT_TOOLS / "ffmpeg")
    parser.add_argument("--ffprobe", type=Path, default=DEFAULT_TOOLS / "ffprobe")
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--caption-height", type=int, default=96)
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--tail-ms", type=int, default=500)
    parser.add_argument("--expected-duration", type=float, default=120, help="Use 0 only for tool smoke tests")
    parser.add_argument("--duration-tolerance", type=float, default=10)
    parser.add_argument("--plan-only", action="store_true", help="Validate timeline and write VTT/plan without encoding")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except (ValueError, KeyError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Demo encoding failed: {error}\n")
    print(json.dumps({"mode": result["mode"], "duration_seconds": result["timeline_duration_seconds"],
                      "capture_average_fps": result["capture_average_fps"],
                      "output": result.get("output"), "validation": result.get("validation", "PLAN ONLY")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
