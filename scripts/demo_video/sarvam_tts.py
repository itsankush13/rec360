"""Sarvam text-to-speech client for the demo video narration track.

Only used by scripts/demo_video/ — not part of the FastAPI app. Requires
SARVAM_API_KEY (see .env.example). Speaker/model were validated by hand on
2026-09-16: bare "ritu" is only accepted by bulbul:v3 and bulbul:v3-beta,
not v2 or v4 (v4 renamed it to task-specific variants like ritu_en_edtech).
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass

import requests

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
DEFAULT_MODEL = "bulbul:v3"


@dataclass
class NarrationClip:
    text: str
    wav_path: str
    duration_seconds: float


class SarvamTTSError(RuntimeError):
    pass


class SarvamTTS:
    def __init__(self, api_key: str | None = None, speaker: str | None = None,
                 target_language_code: str | None = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("SARVAM_API_KEY")
        if not self.api_key:
            raise SarvamTTSError(
                "SARVAM_API_KEY is not set. Add it to .env (gitignored) or export it "
                "in the shell before running this pipeline."
            )
        self.speaker = speaker or os.environ.get("SARVAM_SPEAKER", "ritu")
        self.target_language_code = target_language_code or os.environ.get(
            "SARVAM_TARGET_LANGUAGE_CODE", "en-IN"
        )
        self.model = model

    def synthesize(self, text: str, out_wav_path: str) -> str:
        """Calls Sarvam TTS and writes the returned audio as a WAV file. Returns the path."""
        resp = requests.post(
            SARVAM_TTS_URL,
            headers={
                "api-subscription-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "target_language_code": self.target_language_code,
                "speaker": self.speaker,
                "model": self.model,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            raise SarvamTTSError(f"Sarvam TTS {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        audios = data.get("audios") or []
        if not audios:
            raise SarvamTTSError(f"Sarvam TTS returned no audio: {resp.text[:500]}")
        os.makedirs(os.path.dirname(out_wav_path) or ".", exist_ok=True)
        with open(out_wav_path, "wb") as f:
            f.write(base64.b64decode(audios[0]))
        return out_wav_path
