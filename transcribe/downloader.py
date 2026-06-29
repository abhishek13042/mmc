"""Download every video in a YouTube playlist as MP3 audio using yt-dlp."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def download_playlist(url: str, out_dir: Path) -> list[Path]:
    """
    Download audio for every video in the playlist as MP3.
    Skips files that already exist. Returns sorted list of MP3 paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable, "-m", "yt_dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "--output", str(out_dir / "%(playlist_index)03d_%(title)s.%(ext)s"),
            "--yes-playlist",
            "--no-playlist-reverse",
            "--no-overwrites",
            "--ignore-errors",
            url,
        ],
        check=True,
    )
    return sorted(out_dir.glob("*.mp3"))
