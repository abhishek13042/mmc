#!/usr/bin/env python3
"""
MMC Transcript Tool
====================
Downloads every video from a YouTube playlist, extracts audio, and transcribes
each one via the HuggingFace free Inference API (Whisper large-v3 running on
their servers — no GPU or heavy libraries needed on your machine).

Usage
-----
    python transcribe/run.py <playlist_url>
    python transcribe/run.py <playlist_url> --model medium   # faster, lower quality

    # Use env-var instead of editing config.py:
    set HF_TOKENS=hf_tok1,hf_tok2,hf_tok3
    python transcribe/run.py <url>

Setup (one-time)
----------------
    pip install yt-dlp pydub requests
    # ffmpeg is required by yt-dlp (audio extraction) and pydub (chunking):
    #   Windows: winget install ffmpeg   OR  choco install ffmpeg
    # Add free HF token(s) to transcribe/config.py
    # Get tokens: https://huggingface.co/settings/tokens  (read-only is fine)
    # Create multiple free HF accounts for more tokens = higher throughput.

Output
------
    transcribe/downloads/   — downloaded MP3 files (kept for re-runs)
    transcribe/transcripts/ — one .txt per video, named after the video title

Re-runs skip already-transcribed files automatically.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transcribe.config import HF_TOKENS, MODEL_URL, FALLBACK_MODEL_URL, CHUNK_SECONDS
from transcribe.downloader import download_playlist
from transcribe.transcriber import Transcriber


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__)
        sys.exit(1)

    playlist_url = args[0]

    # --model medium  switches to the faster fallback model
    model_url = MODEL_URL
    if "--model" in args:
        m = args[args.index("--model") + 1]
        if "medium" in m or m == "medium":
            model_url = FALLBACK_MODEL_URL
            print("[config] Using whisper-medium (faster, lower quality)")

    # Tokens: env var overrides config.py
    env_tokens = [t.strip() for t in os.environ.get("HF_TOKENS", "").split(",") if t.strip()]
    tokens = env_tokens or HF_TOKENS
    if not tokens or "REPLACE" in tokens[0]:
        sys.exit(
            "ERROR: Add at least one HuggingFace token.\n"
            "  → Edit transcribe/config.py  OR  set env var  HF_TOKENS=hf_yourtoken\n"
            "  → Get a free token at https://huggingface.co/settings/tokens"
        )

    print(f"{'='*60}")
    print(f"  MMC Transcript Tool")
    print(f"  Tokens loaded  : {len(tokens)}")
    print(f"  Model          : {model_url.split('/')[-1]}")
    print(f"  Chunk size     : {CHUNK_SECONDS}s")
    print(f"{'='*60}\n")

    # ---- 1. Download --------------------------------------------------------
    audio_dir = Path("transcribe/downloads")
    print(f"Downloading playlist:\n  {playlist_url}\n")
    audio_files = download_playlist(playlist_url, audio_dir)
    if not audio_files:
        sys.exit("No audio files downloaded — check the URL or yt-dlp install.")
    print(f"\n{len(audio_files)} file(s) ready for transcription\n")

    # ---- 2. Transcribe ------------------------------------------------------
    out_dir = Path("transcribe/transcripts")
    out_dir.mkdir(parents=True, exist_ok=True)

    transcriber = Transcriber(tokens, model_url, CHUNK_SECONDS)
    done = skipped = failed = 0

    for i, audio_path in enumerate(audio_files, 1):
        out_path = out_dir / (audio_path.stem + ".txt")
        tag = f"[{i:02d}/{len(audio_files):02d}]"

        if out_path.exists():
            print(f"{tag} SKIP (already done): {audio_path.name}")
            skipped += 1
            continue

        size_mb = audio_path.stat().st_size / 1_048_576
        print(f"{tag} Transcribing: {audio_path.name}  ({size_mb:.1f} MB)")

        try:
            text = transcriber.transcribe_file(audio_path)
            out_path.write_text(text, encoding="utf-8")
            print(f"  → saved: {out_path.name}  ({len(text):,} chars)\n")
            done += 1
        except Exception as exc:
            print(f"  ERROR: {exc}\n")
            failed += 1

    # ---- 3. Summary ---------------------------------------------------------
    print(f"{'='*60}")
    print(f"  Done   : {done}")
    print(f"  Skipped: {skipped} (already existed)")
    print(f"  Failed : {failed}")
    print(f"  Output : transcribe/transcripts/")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
