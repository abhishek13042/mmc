"""
Audio transcription via HuggingFace or Groq Inference APIs with:
  - ffmpeg-based audio chunking (no pydub needed)
  - automatic token rotation on 429 rate-limit
  - progress callback for tqdm integration
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
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

    _chunk_delay: float = 0  # seconds to sleep between chunks (subclasses can override)

    def __init__(self, tokens: list[str], model_url: str, chunk_seconds: int = 30):
        if not tokens:
            raise ValueError("Need at least one token")
        self.tokens        = tokens
        self.model_url     = model_url
        self.chunk_seconds = chunk_seconds
        self._cooldown: dict[int, float] = {}   # token-index → usable-after epoch
        self._lock = threading.Lock()            # protects _cooldown across parallel workers

    # -------------------------------------------------------------------------
    #  Token rotation
    # -------------------------------------------------------------------------

    def _pick_token(self) -> tuple[int, str]:
        """Return (index, token) for the next non-rate-limited key. Thread-safe."""
        while True:
            with self._lock:
                now = time.time()
                for i, tok in enumerate(self.tokens):
                    if now >= self._cooldown.get(i, 0):
                        return i, tok
                # All cooling — find earliest recovery time
                best = min(self._cooldown, key=self._cooldown.get)
                wait = self._cooldown[best] - now + 0.5
            print(f"\n  [keys] all {len(self.tokens)} token(s) cooling — waiting {wait:.0f}s...")
            time.sleep(wait)

    def _post(self, audio_bytes: bytes) -> str:
        """POST raw FLAC audio to HF API; rotate tokens on 429, retry on 503."""
        for _ in range(len(self.tokens) * 4):
            idx, token = self._pick_token()
            try:
                resp = requests.post(
                    self.model_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "audio/flac",
                    },
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
                with self._lock:
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
            # Always convert to FLAC so Content-Type: audio/flac is correct
            with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                _ffmpeg_chunk(audio_path, 0, duration, tmp_path)
                text = self._post(tmp_path.read_bytes())
            finally:
                tmp_path.unlink(missing_ok=True)
            if on_chunk:
                on_chunk(1, 1)
            return text

        n_chunks = int(duration // self.chunk_seconds) + (1 if duration % self.chunk_seconds else 0)
        parts: list[str] = []

        for i in range(n_chunks):
            start     = i * self.chunk_seconds
            chunk_dur = min(self.chunk_seconds, duration - start)

            if i > 0:
                time.sleep(self._chunk_delay)  # pace requests to stay under RPM limit

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


class GroqTranscriber(Transcriber):
    """
    Transcribe via Groq's OpenAI-compatible API.
    Free tier: ~7,200 audio-seconds/day per key at console.groq.com.
    ~189x real-time speed — much faster than HuggingFace.
    """

    GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    _chunk_delay: float = 3.1  # Groq free tier: 20 req/min → 1 req per 3s

    def __init__(self, tokens: list[str], model: str = "whisper-large-v3-turbo", chunk_seconds: int = 30):
        super().__init__(tokens, model, chunk_seconds)

    def _post(self, audio_bytes: bytes) -> str:
        """POST FLAC chunk to Groq via multipart/form-data."""
        for _ in range(len(self.tokens) * 4):
            idx, token = self._pick_token()
            try:
                resp = requests.post(
                    self.GROQ_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": ("audio.flac", audio_bytes, "audio/flac")},
                    data={"model": self.model_url, "response_format": "text"},
                    timeout=120,
                )
            except requests.Timeout:
                print(f"\n  [key {idx+1}] timeout, retrying...")
                continue

            if resp.status_code == 200:
                return resp.text.strip()

            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 60))
                print(f"\n  [key {idx+1}/{len(self.tokens)}] rate-limited — cooling {retry}s, switching key...")
                with self._lock:
                    self._cooldown[idx] = time.time() + retry

            elif resp.status_code == 401:
                raise RuntimeError(f"Groq key {idx+1} rejected (401) — check GROQ_TOKENS in config.py")

            elif resp.status_code == 413:
                raise RuntimeError("Chunk too large for Groq (reduce CHUNK_SECONDS)")

            else:
                raise RuntimeError(f"Groq API {resp.status_code}: {resp.text[:300]}")

        raise RuntimeError("All Groq tokens exhausted. Add more keys to config.py.")
