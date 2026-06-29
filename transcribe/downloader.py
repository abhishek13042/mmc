"""Download every video in a YouTube playlist as MP3 audio using yt-dlp."""

from __future__ import annotations
import subprocess
from pathlib import Path


def download_playlist(url: str, out_dir: Path) -> list[Path]:
    """
    Download audio for every video in the playlist.
    Skips files that already exist (yt-dlp --no-overwrites).
    Returns sorted list of downloaded MP3 paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "0",          # best quality
            "--output", str(out_dir / "%(playlist_index)03d_%(title)s.%(ext)s"),
            "--yes-playlist",
            "--no-playlist-reverse",
            "--no-overwrites",               # skip already-downloaded files
            "--ignore-errors",               # skip unavailable videos, don't abort
            url,
        ],
        check=True,
    )
    return sorted(out_dir.glob("*.mp3"))
