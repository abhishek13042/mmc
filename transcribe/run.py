#!/usr/bin/env python3
"""
MMC Transcript Tool
====================
Downloads every video from a YouTube playlist, extracts audio, and transcribes
each one via free cloud Whisper (HuggingFace or Groq — no GPU needed locally).

Usage
-----
    python transcribe/run.py <playlist_url>
    python transcribe/run.py <playlist_url> --provider groq        # use Groq (recommended)
    python transcribe/run.py <playlist_url> --skip-download        # skip yt-dlp, transcribe only
    python transcribe/run.py <playlist_url> --model medium         # HF only: use whisper-medium

Providers
---------
    groq  (default when GROQ_TOKENS are set)
          Free at console.groq.com → API Keys. ~189x real-time speed.
          7,200 audio-seconds/day per key. Rotate multiple keys automatically.

    huggingface
          Free at huggingface.co/settings/tokens. Monthly quota; reset on 1st.
          Add tokens to HF_TOKENS in transcribe/config.py.

Output
------
    transcribe/downloads/    MP3 audio (kept, re-run skips already-downloaded)
    transcribe/transcripts/  One .txt per video, named after video title
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from tqdm import tqdm

from transcribe.config import (
    CHUNK_SECONDS,
    FALLBACK_MODEL_URL,
    GROQ_MODEL,
    GROQ_TOKENS,
    HF_TOKENS,
    MODEL_URL,
)
from transcribe.downloader import download_playlist
from transcribe.transcriber import GroqTranscriber, Transcriber


# ─── helpers ──────────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def _banner(provider: str, tokens: int, model: str, n_videos: int, url: str) -> None:
    w = 62
    print("=" * w)
    print("  MMC Transcript Tool")
    print(f"  Playlist : {url[:55]}{'…' if len(url) > 55 else ''}")
    print(f"  Videos   : {n_videos}")
    print(f"  Provider : {provider}  ({tokens} token(s), auto-rotate on rate-limit)")
    print(f"  Model    : {model}")
    print(f"  Chunks   : {CHUNK_SECONDS}s per API call")
    print("=" * w)


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__)
        sys.exit(1)

    playlist_url  = args[0]
    skip_download = "--skip-download" in args

    # ── pick provider ─────────────────────────────────────────────────────────
    use_groq = "--provider" in args and args[args.index("--provider") + 1] == "groq"
    # auto-select Groq if tokens are configured and provider not forced
    if not use_groq and "--provider" not in args:
        use_groq = bool(GROQ_TOKENS and not GROQ_TOKENS[0].startswith("#"))

    if use_groq:
        groq_env = [t.strip() for t in os.environ.get("GROQ_TOKENS", "").split(",") if t.strip()]
        tokens   = groq_env or GROQ_TOKENS
        if not tokens or tokens[0].startswith("#"):
            sys.exit(
                "ERROR: No Groq token found.\n"
                "  → Edit transcribe/config.py  →  add key(s) to GROQ_TOKENS\n"
                "  → Get a free key at https://console.groq.com"
            )
        provider    = "groq"
        model_label = GROQ_MODEL
        transcriber = GroqTranscriber(tokens, GROQ_MODEL, CHUNK_SECONDS)
    else:
        model_url = MODEL_URL
        if "--model" in args:
            idx = args.index("--model")
            if idx + 1 < len(args) and "medium" in args[idx + 1]:
                model_url = FALLBACK_MODEL_URL
        hf_env  = [t.strip() for t in os.environ.get("HF_TOKENS", "").split(",") if t.strip()]
        tokens  = hf_env or HF_TOKENS
        if not tokens or "REPLACE" in tokens[0]:
            sys.exit(
                "ERROR: No HuggingFace token found.\n"
                "  → Edit transcribe/config.py  OR  set HF_TOKENS=hf_yourtoken\n"
                "  → Get a free token at https://huggingface.co/settings/tokens\n"
                "  → Or use Groq: add GROQ_TOKENS to config.py (console.groq.com)"
            )
        provider    = "huggingface"
        model_label = model_url.split("/")[-1]
        transcriber = Transcriber(tokens, model_url, CHUNK_SECONDS)

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
    _banner(provider, len(tokens), model_label, len(audio_files), playlist_url)

    workers = max(1, len(tokens))
    done = skipped = failed = 0
    wall_start = time.time()

    pending = []
    for i, audio_path in enumerate(audio_files, 1):
        out_path = out_dir / (audio_path.stem + ".txt")
        if out_path.exists():
            tqdm.write(f"[{i:02d}/{len(audio_files):02d}] SKIP  {audio_path.name}")
            skipped += 1
        else:
            pending.append((i, audio_path))

    tqdm.write(f"\n{len(pending)} to transcribe  |  {workers} parallel worker(s)\n")

    overall = tqdm(total=len(pending), desc="Overall", unit="video", ncols=62, position=0)

    def _transcribe_one(item):
        i, audio_path = item
        out_path = out_dir / (audio_path.stem + ".txt")
        tag      = f"[{i:02d}/{len(audio_files):02d}]"
        size_mb  = audio_path.stat().st_size / 1_048_576
        title    = audio_path.stem[:45]
        tqdm.write(f"{tag} START  {title}  ({size_mb:.1f} MB)")
        t0 = time.time()
        try:
            text = transcriber.transcribe_file(audio_path)
            out_path.write_text(text, encoding="utf-8")
            elapsed = time.time() - t0
            tqdm.write(f"{tag} DONE   {title}  |  {len(text):,} chars  |  {_fmt_time(elapsed)}")
            return "done"
        except Exception as exc:
            tqdm.write(f"{tag} ERROR  {title}  |  {exc}")
            return "failed"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_transcribe_one, item): item for item in pending}
        for fut in as_completed(futures):
            result = fut.result()
            if result == "done":
                done += 1
            else:
                failed += 1
            overall.update(1)

    overall.close()

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
