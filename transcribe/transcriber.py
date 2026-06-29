"""
HuggingFace Inference API transcription with automatic token rotation.

How key rotation works
----------------------
Every token gets a per-token cooldown timestamp.  On a 429 (rate-limit) the
token is frozen for however many seconds the server asks (Retry-After header,
default 60 s).  The next request automatically picks the first non-frozen token.
If ALL tokens are frozen at once the code waits for the earliest one to thaw.
No manual intervention needed — just add more tokens to config.py for higher
parallel throughput.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import requests
from pydub import AudioSegment


class Transcriber:
    def __init__(self, tokens: list[str], model_url: str, chunk_seconds: int = 30):
        if not tokens:
            raise ValueError("Need at least one HuggingFace token")
        self.tokens    = tokens
        self.model_url = model_url
        self.chunk_ms  = chunk_seconds * 1000
        self._cooldown: dict[int, float] = {}   # token-index -> epoch when usable again

    # -------------------------------------------------------------------------

    def _pick_token(self) -> tuple[int, str]:
        """Return (index, token) for the next available (non-rate-limited) key."""
        now = time.time()
        # Prefer any token with no active cooldown
        for i, tok in enumerate(self.tokens):
            if now >= self._cooldown.get(i, 0):
                return i, tok
        # All tokens cooling — wait for the soonest one to recover
        best = min(self._cooldown, key=self._cooldown.get)
        wait = self._cooldown[best] - now + 0.5
        print(f"  [keys] all {len(self.tokens)} token(s) rate-limited — waiting {wait:.0f}s for token {best+1}...")
        time.sleep(wait)
        return best, self.tokens[best]

    def _post(self, audio_bytes: bytes) -> str:
        """POST audio to HF API; rotate tokens on 429 / retry on 503 (model loading)."""
        max_attempts = len(self.tokens) * 4
        for attempt in range(max_attempts):
            idx, token = self._pick_token()
            try:
                resp = requests.post(
                    self.model_url,
                    headers={"Authorization": f"Bearer {token}"},
                    data=audio_bytes,
                    timeout=180,
                )
            except requests.Timeout:
                print(f"  [key {idx+1}] timeout, retrying...")
                continue

            if resp.status_code == 200:
                return resp.json().get("text", "").strip()

            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 60))
                print(f"  [key {idx+1}/{len(self.tokens)}] 429 rate-limited — cooling {retry}s, switching key...")
                self._cooldown[idx] = time.time() + retry

            elif resp.status_code == 503:
                # HF cold-start: model is loading on their server
                print(f"  [model] 503 loading on HF server — retrying in 20s...")
                time.sleep(20)

            elif resp.status_code == 401:
                raise RuntimeError(f"Token {idx+1} rejected (401 Unauthorized) — check token in config.py")

            else:
                raise RuntimeError(f"HF API error {resp.status_code}: {resp.text[:300]}")

        raise RuntimeError(f"Gave up after {max_attempts} attempts. Add more tokens to config.py.")

    # -------------------------------------------------------------------------

    def transcribe_file(self, audio_path: Path) -> str:
        """
        Transcribe a full audio file.
        Short files (≤ chunk_seconds) are sent in one shot.
        Longer files are split into chunks, transcribed individually, then joined.
        """
        audio    = AudioSegment.from_file(audio_path)
        total_ms = len(audio)

        if total_ms <= self.chunk_ms:
            return self._post(audio_path.read_bytes())

        parts: list[str] = []
        offset    = 0
        n_chunks  = -(-total_ms // self.chunk_ms)   # ceil
        chunk_idx = 0

        while offset < total_ms:
            chunk_idx += 1
            chunk = audio[offset : offset + self.chunk_ms]
            s0 = offset // 1000
            s1 = min((offset + self.chunk_ms) // 1000, total_ms // 1000)
            print(f"    chunk {chunk_idx}/{n_chunks}  ({s0}s–{s1}s)...", end=" ", flush=True)

            with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                chunk.export(tmp_path, format="flac")
                text = self._post(Path(tmp_path).read_bytes())
                print(text[:70] + ("…" if len(text) > 70 else ""))
                if text:
                    parts.append(text)
            finally:
                os.unlink(tmp_path)

            offset += self.chunk_ms

        return " ".join(parts)
