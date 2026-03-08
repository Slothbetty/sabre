"""
Prefetch module for SABRE dynamic buffering.

Decides *when* and *where* to prefetch based on:
- A JSON config that lists target segment indices
- A buffer-level threshold: prefetch only when the buffer is sufficiently full

Bitrate / quality selection is delegated to the ABR algorithm via the standard
``abr.get_quality_delay(segment_index)`` interface.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

# Dummy prefetch module that will be replaced with RL prefetch module.
class PrefetchModule:
    """Buffer-threshold-based prefetch scheduler.

    Parameters
    ----------
    config_path : str | Path
        Path to a JSON file with the format::

            {
              "prefetch": [
                {"segment": 5},
                {"segment": 10},
                {"segment": 15}
              ]
            }

    buffer_threshold_ms : float
        Minimum buffer level (in ms) required before a prefetch download is
        triggered.
    """

    def __init__(self, config_path: str | Path, buffer_threshold_ms: float) -> None:
        self.buffer_threshold_ms = buffer_threshold_ms

        with open(config_path) as f:
            data = json.load(f)

        entries = data.get("prefetch", [])
        self.pending_segments: list[int] = [e["segment"] for e in entries]
        self.completed_segments: set[int] = set()

    def should_prefetch(self, buffer_level_ms: float) -> bool:
        """Return True if conditions are met to start a prefetch download."""
        return (
            buffer_level_ms > self.buffer_threshold_ms
            and len(self.pending_segments) > 0
        )

    def get_next_prefetch_segment(self) -> Optional[int]:
        """Return the next segment to prefetch, or None if none remain."""
        if not self.pending_segments:
            return None
        return self.pending_segments[0]

    def mark_prefetched(self, segment_index: int) -> None:
        """Record that *segment_index* has been successfully prefetched."""
        if segment_index in self.pending_segments:
            self.pending_segments.remove(segment_index)
        self.completed_segments.add(segment_index)
