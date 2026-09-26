"""Regenerates the recruiter demo video: narration (Sarvam TTS) + screen capture (Playwright)
+ assembly (ffmpeg), per docs/plan/DEMO-VIDEO-SCRIPT-120S.md.

Usage (from repo root, with the app's API server on :8000 and the static web server on :8124
already running per CLAUDE.md's "How to run" section):

    .\\venv\\Scripts\\python.exe scripts\\demo_video\\main.py --config scripts\\demo_video\\config.json

Requires SARVAM_API_KEY set (via .env, loaded automatically) and `playwright install chromium`
already run once. See scripts/demo_video/README.md.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

from assemble import concatenate, mux_segment, wav_duration_seconds
from record import record_segment
from sarvam_tts import SarvamTTS
from segments import build_segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "config.json"),
        help="Path to config.json (copy config.example.json and fill in live ids).",
    )
    parser.add_argument(
        "--only", nargs="*", default=None,
        help="Only (re)build these segment keys, e.g. --only candidate_close compare_result. "
             "Useful for fixing one section without re-recording everything.",
    )
    args = parser.parse_args()

    load_dotenv()

    if not os.path.isfile(args.config):
        example = os.path.join(os.path.dirname(__file__), "config.example.json")
        sys.exit(
            f"Config not found: {args.config}\n"
            f"Copy {example} to {args.config} and fill in the live campaign/candidate ids."
        )
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    work_dir = os.path.join(os.path.dirname(__file__), "_work")
    os.makedirs(work_dir, exist_ok=True)
    out_dir = os.path.dirname(cfg["output_path"]) or "."
    os.makedirs(out_dir, exist_ok=True)

    tts = SarvamTTS()
    all_segments = build_segments(cfg)
    segments = all_segments
    if args.only:
        wanted = set(args.only)
        segments = [s for s in all_segments if s.key in wanted]
        if not segments:
            sys.exit(f"No segment matched --only {args.only}")

    muxed_paths = []
    for i, seg in enumerate(segments, start=1):
        print(f"[{i}/{len(segments)}] {seg.key}")

        wav_path = os.path.join(work_dir, f"{seg.key}.wav")
        print("  narrating...")
        tts.synthesize(seg.narration, wav_path)
        narration_dur = wav_duration_seconds(wav_path)
        print(f"  narration duration: {narration_dur:.1f}s")

        print("  recording...")
        video_path = record_segment(seg, cfg, work_dir)

        print("  muxing...")
        mp4_path = os.path.join(work_dir, f"{seg.key}.mp4")
        mux_segment(video_path, wav_path, mp4_path, seg.min_hold_seconds)
        muxed_paths.append(mp4_path)

    if args.only:
        print(
            f"--only was set: rebuilt {len(muxed_paths)} segment mp4(s) under {work_dir}, "
            "did not re-concatenate the full video. Re-run without --only for a full build, "
            "or splice these files into the existing output manually."
        )
        return

    print(f"Concatenating {len(muxed_paths)} segments -> {cfg['output_path']}")
    concatenate(muxed_paths, cfg["output_path"])
    print("Done:", cfg["output_path"])


if __name__ == "__main__":
    main()
