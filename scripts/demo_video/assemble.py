"""Mux each segment's video to its own narration audio and concatenate the final mp4.

The rule that fixes the original "video plays again and again" bug: a segment's video is
never allowed to be shorter than its narration. We measure both, take the longer of
(narration duration, recorded video duration, segment.min_hold_seconds), and pad whichever
is shorter — video by freezing its last frame (`tpad`), audio by appending silence
(`apad`) — so a media player has no gap to fill by looping.
"""
from __future__ import annotations

import contextlib
import os
import re
import subprocess
import wave

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def wav_duration_seconds(path: str) -> float:
    with contextlib.closing(wave.open(path, "rb")) as w:
        return w.getnframes() / float(w.getframerate())


def probe_duration_seconds(path: str) -> float:
    """Reads a media file's duration from ffmpeg's stderr banner (no ffprobe binary needed)."""
    proc = subprocess.run(
        [FFMPEG, "-i", path], capture_output=True, text=True, timeout=30
    )
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not match:
        raise RuntimeError(f"Could not read duration for {path}:\n{proc.stderr[-500:]}")
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def mux_segment(video_path: str, audio_path: str, out_path: str, min_hold_seconds: float) -> str:
    video_dur = probe_duration_seconds(video_path)
    audio_dur = wav_duration_seconds(audio_path)
    target = max(video_dur, audio_dur, min_hold_seconds) + 0.3  # small trailing buffer

    video_pad = max(0.0, target - video_dur)
    audio_pad_ms = int(max(0.0, target - audio_dur) * 1000)

    filter_complex = (
        f"[0:v]tpad=stop_mode=clone:stop_duration={video_pad:.3f},setpts=PTS-STARTPTS[v];"
        f"[1:a]apad=pad_dur={audio_pad_ms / 1000:.3f}[a]"
    )
    cmd = [
        FFMPEG, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{target:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        out_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return out_path


def concatenate(segment_mp4_paths: list[str], out_path: str) -> str:
    list_file = os.path.join(os.path.dirname(out_path) or ".", "_concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for p in segment_mp4_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out_path]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    os.remove(list_file)
    return out_path
