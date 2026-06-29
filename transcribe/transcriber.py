"""
HuggingFace Inference API transcription with:
  - ffmpeg-based audio chunking (no pydub needed)
  - automatic token rotation on 429 rate-limit
  - progress callback for tqdm integration
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import requests


def _ffprobe_duration(audio_path: Path) -> float:
    """Return audio duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _ffmpeg_chunk(audio_path: Path, start_s: float, duration_s: float, out_path: Path) -> None:
    """Extract a time slice from audio, resample to 16 kHz mono FLAC (Whisper-optimal)."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start_s),
            "-t",  str(duration_s),
            "-i",  str(audio_path),
            "-ar", "16000",   # 16 kHz sample rate (Whisper default)
            "-ac", "1",       # mono
            "-f",  "flac",
            str(out_path),
        ],
        capture_output=True, check=True,
    )


class Transcriber:
    """Transcribe audio files via HF Inference API, rotating tokens on rate-limit."""

    def __init__(self, tokens: list[str], model_url: str, chunk_seconds: int = 30):
        if not tokens:
            raise ValueError("Need at least one HuggingFace token")
        self.tokens       = tokens
        self.model_url    = model_url
        self.chunk_seconds = chunk_seconds
        self._cooldown: dict[int, float] = {}   # token-index → usable-after epoch

    # -------------------------------------------------------------------------
    #  Token rotation
    # -------------------------------------------------------------------------

    def _pick_token(self) -> tuple[int, str]:
        """Return (index, token) for the next non-rate-limited key."""
        now = time.time()
        for i, tok in enumerate(self.tokens):
            if now >= self._cooldown.get(i, 0):
                return i, tok
        # All cooling — wait for the earliest one to recover
        best = min(self._cooldown, key=self._cooldown.get)
        wait = self._cooldown[best] - now + 0.5
        print(f"\n  [keys] all {len(self.tokens)} token(s) cooling — waiting {wait:.0f}s...")
        time.sleep(wait)
        return best, self.tokens[best]

    def _post(self, audio_bytes: bytes) -> str:
        """POST audio to HF API; rotate tokens on 429, retry on 503."""
        for _ in range(len(self.tokens) * 4):
            idx, token = self._pick_token()
            try:
                resp = requests.post(
                    self.model_url,
                    headers={"Authorization": f"Bearer {token}"},
                    data=audio_bytes,
                    timeout=180,
                )
            except requests.Timeout:
                print(f"\n  [key {idx+1}] timeout, retrying...")
                continue

            if resp.status_code == 200:
                return resp.json().get("text", "").strip()

            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 60))
                print(f"\n  [key {idx+1}/{len(self.tokens)}] rate-limited — cooling {retry}s, switching key...")
                self._cooldown[idx] = time.time() + retry

            elif resp.status_code == 503:
                print("\n  [model] HF server loading — retrying in 20s...")
                time.sleep(20)

            elif resp.status_code == 401:
                raise RuntimeError(f"Token {idx+1} rejected (401) — check config.py")

            else:
                raise RuntimeError(f"HF API {resp.status_code}: {resp.text[:300]}")

        raise RuntimeError("All tokens exhausted. Add more tokens to config.py.")

    # -------------------------------------------------------------------------
    #  Public
    # -------------------------------------------------------------------------

    def transcribe_file(
        self,
        audio_path: Path,
        on_chunk: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """
        Transcribe a full audio file.
        Short files (≤ chunk_seconds) are sent in one shot.
        Longer files are split via ffmpeg, sent chunk by chunk, then joined.

        on_chunk(done, total) is called after each chunk completes (for progress bars).
        """
        duration = _ffprobe_duration(audio_path)

        if duration <= self.chunk_seconds:
            text = self._post(audio_path.read_bytes())
            if on_chunk:
                on_chunk(1, 1)
            return text

        n_chunks = int(duration // self.chunk_seconds) + (1 if duration % self.chunk_seconds else 0)
        parts: list[str] = []

        for i in range(n_chunks):
            start     = i * self.chunk_seconds
            chunk_dur = min(self.chunk_seconds, duration - start)

            with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                _ffmpeg_chunk(audio_path, start, chunk_dur, tmp_path)
                text = self._post(tmp_path.read_bytes())
                if text:
                    parts.append(text)
            finally:
                tmp_path.unlink(missing_ok=True)

            if on_chunk:
                on_chunk(i + 1, n_chunks)

        return " ".join(parts)
