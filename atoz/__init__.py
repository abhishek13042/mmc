"""atoz — the A-Z Guide trading library.

A self-contained implementation built faithfully from the raw A-Z Guide video
transcripts (transcribe/transcripts/00x). Kept separate from the ``mmc`` package
(which was built from a different, distilled transcript set).

Layers (by episode):
    atoz.core    — Direction/Swing/Zone/FVG primitives        (ep 1 foundation)
    atoz.blocks  — Order/Mitigation/Breaker/Rejection/Reclaimed (ep 2-6)
    [next]       — liquidity pools (ep 7), imbalances (ep 8),
                   FLOD/PD matrix (ep 9), market structure (ep 10)

Quick start:
    from atoz.blocks import find_all_blocks, strongest
    from mmc.data import load            # reuse mmc's CSV loader (infra only)
    from mmc.core.types import Timeframe

    df = load("EURUSD", Timeframe.H1)
    blocks = find_all_blocks(df)
    best = strongest(blocks, min_overlaps=2)   # most-confluent setups
"""

from atoz.core import Direction, FVG, Swing, SwingType, Zone, find_fvgs, find_swings

__all__ = ["Direction", "SwingType", "Swing", "Zone", "FVG", "find_swings", "find_fvgs"]
