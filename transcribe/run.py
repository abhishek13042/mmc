#!/usr/bin/env python3
"""
MMC Transcript Tool
====================
Downloads every video from a YouTube playlist, extracts audio, and transcribes
each one via the HuggingFace free Inference API (Whisper large-v3 running on
their servers — no GPU needed on your machine).

Usage
-----
    python transcribe/run.py <playlist_url>
    python transcribe/run.py <playlist_url> --model medium    # faster, lower quality
    python transcribe/run.py <playlist_url> --skip-download   # transcribe only (audio already downloaded)

Setup (one-time)
----------------
    pip install -r transcribe/requirements.txt
    # ffmpeg must be in PATH (winget install ffmpeg  OR  choco install ffmpeg)
    # Add your free HF token(s) to transcribe/config.py
    # Get tokens free at: https://huggingface.co/settings/tokens

Output
------
    transcribe/downloads/    MP3 audio (kept, re-run skips already-downloaded)
    transcribe/transcripts/  One .txt per video, named after video title
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tqdm import tqdm

from transcribe.config import (
    CHUNK_SECONDS,
    FALLBACK_MODEL_URL,
    HF_TOKENS,
    MODEL_URL,
)
from transcribe.downloader import download_playlist
from transcribe.transcriber import Transcriber


# ─── helpers ──────────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def _banner(tokens: int, model: str, n_videos: int, url: str) -> None:
    w = 62
    print("=" * w)
    print("  MMC Transcript Tool")
    print(f"  Playlist : {url[:55]}{'…' if len(url) > 55 else ''}")
    print(f"  Videos   : {n_videos}")
    print(f"  Tokens   : {tokens}  (rotates automatically on rate-limit)")
    print(f"  Model    : {model}")
    print(f"  Chunks   : {CHUNK_SECONDS}s per API call")
    print("=" * w)


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__)
        sys.exit(1)

    playlist_url   = args[0]
    skip_download  = "--skip-download" in args
    model_url      = MODEL_URL
    if "--model" in args:
        idx = args.index("--model")
        if idx + 1 < len(args) and "medium" in args[idx + 1]:
            model_url = FALLBACK_MODEL_URL

    # ── tokens ───────────────────────────────────────────────────────────────
    env_tokens = [t.strip() for t in os.environ.get("HF_TOKENS", "").split(",") if t.strip()]
    tokens = env_tokens or HF_TOKENS
    if not tokens or "REPLACE" in tokens[0]:
        sys.exit(
            "ERROR: No HuggingFace token found.\n"
            "  → Edit transcribe/config.py  OR  set HF_TOKENS=hf_yourtoken\n"
            "  → Get a free token at https://huggingface.co/settings/tokens"
        )

    # ── download ─────────────────────────────────────────────────────────────
    audio_dir = Path("transcribe/downloads")
    out_dir   = Path("transcribe/transcripts")
    out_dir.mkdir(parents=True, exist_ok=True)

    if not skip_download:
        print(f"\nDownloading playlist …\n  {playlist_url}\n")
        audio_files = download_playlist(playlist_url, audio_dir)
    else:
        audio_files = sorted(audio_dir.glob("*.mp3"))

    if not audio_files:
        sys.exit("No audio files found. Check the playlist URL or run without --skip-download.")

    # ── transcribe ───────────────────────────────────────────────────────────
    _banner(len(tokens), model_url.split("/")[-1], len(audio_files), playlist_url)

    transcriber  = Transcriber(tokens, model_url, CHUNK_SECONDS)
    done = skipped = failed = 0
    wall_start   = time.time()

    for i, audio_path in enumerate(audio_files, 1):
        out_path = out_dir / (audio_path.stem + ".txt")
        tag      = f"[{i:02d}/{len(audio_files):02d}]"

        if out_path.exists():
            tqdm.write(f"{tag} SKIP  {audio_path.name}")
            skipped += 1
            continue

        size_mb = audio_path.stat().st_size / 1_048_576
        title   = audio_path.stem[:50]
        tqdm.write(f"\n{tag} {title}  ({size_mb:.1f} MB)")

        # progress bar for chunks
        pbar = tqdm(
            total=100,
            desc="       chunks",
            unit="%",
            ncols=62,
            leave=False,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}%  [{elapsed}]",
        )
        last_pct = [0]

        def on_chunk(done_n: int, total_n: int, _pbar=pbar, _last=last_pct) -> None:
            pct = int(done_n / total_n * 100)
            _pbar.update(pct - _last[0])
            _last[0] = pct

        t0 = time.time()
        try:
            text = transcriber.transcribe_file(audio_path, on_chunk=on_chunk)
            pbar.update(100 - last_pct[0])
            pbar.close()
            elapsed = time.time() - t0
            out_path.write_text(text, encoding="utf-8")
            tqdm.write(f"       → {out_path.name}  |  {len(text):,} chars  |  {_fmt_time(elapsed)}")
            done += 1
        except Exception as exc:
            pbar.close()
            tqdm.write(f"       ERROR: {exc}")
            failed += 1

    # ── summary ──────────────────────────────────────────────────────────────
    total_time = time.time() - wall_start
    w = 62
    print("\n" + "=" * w)
    print("  DONE")
    print(f"  Transcribed : {done}")
    print(f"  Skipped     : {skipped}  (already existed)")
    print(f"  Failed      : {failed}")
    print(f"  Total time  : {_fmt_time(total_time)}")
    print(f"  Output      : transcribe/transcripts/")
    print("=" * w)


if __name__ == "__main__":
    main()
