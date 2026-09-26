"""Records one Playwright video per segment.

Uses Playwright's native video recording (a real screen-equivalent capture of the rendered
page, not a screenshot loop) so what ends up in the mp4 is exactly what a recruiter would see
in the browser. Each segment gets its own browser context so its video is a separate file we
can pad to the narration's duration independently, in assemble.py.
"""
from __future__ import annotations

import os
import shutil

from playwright.sync_api import sync_playwright

from segments import Segment


def record_segment(segment: Segment, cfg: dict, out_dir: str) -> str:
    """Records `segment` and returns the path to its .webm video file."""
    os.makedirs(out_dir, exist_ok=True)
    viewport = cfg.get("viewport", {"width": 1600, "height": 900})
    base_url = cfg["base_url"].rstrip("/")
    url = f"{base_url}/{segment.url_path}"

    video_dir = os.path.join(out_dir, f"_raw_{segment.key}")
    if os.path.isdir(video_dir):
        shutil.rmtree(video_dir)
    os.makedirs(video_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=viewport,
            record_video_dir=video_dir,
            record_video_size=viewport,
        )
        page = context.new_page()
        page.goto(url, wait_until="load", timeout=30000)
        segment.actions(page, cfg)
        page.close()
        context.close()  # flushes the video file to disk
        browser.close()

    recorded = [f for f in os.listdir(video_dir) if f.endswith(".webm")]
    if not recorded:
        raise RuntimeError(f"Playwright produced no video for segment '{segment.key}'")
    src = os.path.join(video_dir, recorded[0])
    dest = os.path.join(out_dir, f"{segment.key}.webm")
    shutil.move(src, dest)
    shutil.rmtree(video_dir, ignore_errors=True)
    return dest
