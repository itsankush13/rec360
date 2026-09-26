# Demo video pipeline

Regenerates the recruiter demo video automatically instead of a human doing a live screen
recording: [Playwright](https://playwright.dev) drives each screen, [Sarvam](https://sarvam.ai)
TTS (voice `ritu`, English) narrates it, and `ffmpeg` (via `imageio-ffmpeg`, no separate install
needed) muxes and concatenates the result.

The script and timing this pipeline follows live in
[docs/plan/DEMO-VIDEO-SCRIPT-120S.md](../../docs/plan/DEMO-VIDEO-SCRIPT-120S.md) — edit that
file's timing table and `segments.py`'s `SEGMENTS` together; they're meant to match.

## What this fixes vs. the manual recording (`demoankfinl.mp4`)

- **Candidate 360 looping**: caused by a screen clip shorter than its voiceover, so playback
  looped it to fill the gap. `assemble.py` measures the narration's real duration first and
  pads the video (freezing the last frame) to match — it never loops.
- **Candidate 360 not ending cleanly**: the section now ends on a dedicated `candidate_close`
  segment holding on the verdict, narrated "And that's the AI assessment and the recommended
  decision for this candidate," before cutting to Compare.
- **Compare cutting away before the result**: split into three segments — the full candidate
  table, then selecting two candidates, then holding on the generated comparison table.
- **Decisions & Export rushed**: given its own longer `min_hold_seconds` and narration that
  covers both the decision buttons and scrolling down to "Send the report to the hiring
  manager."

## One-time setup

```bash
.\venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\venv\Scripts\python.exe -m playwright install chromium
```

Add your Sarvam key to `.env` (already gitignored — do not put it in `.env.example` or commit
it):

```
SARVAM_API_KEY=sk_...
SARVAM_SPEAKER=ritu
SARVAM_TARGET_LANGUAGE_CODE=en-IN
```

Copy the config template and fill in the live campaign/candidate ids for whichever demo
campaign you're using today (they're not hardcoded — they change per rehearsal per
`docs/SESSION-STATE.md`):

```bash
cp scripts/demo_video/config.example.json scripts/demo_video/config.json
```

`compare_candidate_ids` needs two candidate ids from that same campaign, for the Compare
segment.

## Before running

Both servers up per the repo's `CLAUDE.md` "How to run" section:

```
# Terminal 1
$env:QUEUE_BACKEND = "inline"; .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
# Terminal 2
cd web ; python -m http.server 8124
```

Confirm `config.json`'s campaign has an approved rubric and at least one scored, shortlist-able
candidate — don't discover a data problem mid-run.

## Run

Full video:

```bash
.\venv\Scripts\python.exe scripts\demo_video\main.py --config scripts\demo_video\config.json
```

Output lands at `config.json`'s `output_path` (default
`scripts/demo_video/output/demo-video.mp4`).

Rebuild just one or two sections instead of the whole thing (e.g. after tweaking a narration
line) with `--only`:

```bash
.\venv\Scripts\python.exe scripts\demo_video\main.py --only candidate_close compare_result
```

`--only` writes those segments' muxed `.mp4` files under `scripts/demo_video/_work/` but does
**not** re-concatenate the full output — splice them in manually or re-run without `--only`
once you're happy with the section.

## Files

- `segments.py` — the ordered list of segments: URL, narration text, and the Playwright
  actions (typing, clicking, scrolling) to perform on that page.
- `sarvam_tts.py` — thin Sarvam TTS client.
- `record.py` — records one Playwright video per segment.
- `assemble.py` — pads video/audio to the same length and mux; concatenates all segments.
- `main.py` — orchestrates the above; entry point.
- `config.example.json` / `config.json` — per-run settings (base URL, campaign/candidate ids,
  output path). `config.json` is gitignored (it holds environment-specific ids); copy it from
  the example.
