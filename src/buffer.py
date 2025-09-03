import math
import typing
from bisect import bisect_right
from enum import Enum
from __future__ import annotations


class BufferRegion:
    """Buffer region: a continuous region of chunks.
    """
    def __init__(self, start: float, chunk_duration: float) -> None:
        self.start = start      # start position of the first chunk
        self.end = None         # end position of the last chunk
        self.chunk_duration = chunk_duration
        self.chunks = []       # Chunks [quality_1, quality_2, ...]

    def add_chunk(self, quality: float) -> None:
        """Adds one chunk of given quality to the region.
        This is to be used during download. """
        if self.end is None:
            self.end = self.start + self.chunk_duration
        else:
            self.end += self.chunk_duration
        self.chunks.append(quality)

    def pop_chunk(self, pos: float) -> None:
        """Pops all chunks before `pos` for user seek.
        This is to be used during seek, assuming no back seek allowed. """
        n_chunk_to_pop = pos // self.chunk_duration
        self.start += n_chunk_to_pop * self.chunk_duration
        self.chunks = self.chunks[n_chunk_to_pop : ]

    def _pop_back_chunk(self, pos: float) -> None:
        """Pops all chunks after `pos`. Used in merge. """
        n_chunk_to_pop = (self.end - pos) // self.chunk_duration
        self.end -= n_chunk_to_pop * self.chunk_duration
        self.chunks = self.chunks[ : -n_chunk_to_pop]

    def exists(self, pos: float) -> bool:
        """Returns if chunk at `pos` exists in this region. """
        return pos >= self.start and pos < self.end

    def try_merge(self, region: BufferRegion) -> bool:
        """Try merging this region with another buffer region.

        If the given region can be merged, then current region is updated with
        the new chunks; otherwise if region and current region are not
        overlapped, nothing is changed. Returns if the merge is successful.
        """
        if self.end < region.start or self.start > region.end:
            return False
        assert abs(region.start - self.start) // self.chunk_duration == \
            abs(region.start - self.start) / self.chunk_duration, \
            f'Boundary difference must be the multiple of chunk duration.'

        # TODO: logging w/ various levels is preferred here
        if self.start < region.start:
            # self <- region case
            if self.end > region.start:
                print(f'Warning: positive overlap between regions: '
                    f'self.end: {self.end} > region.start: {region.start}')
            region.pop_chunk(self.end)
            self.end = region.end
            self.chunks.extend(region.chunks)
        else:
            # region -> self case
            if self.start < region.end:
                print(f'Warning: positive overlap between regions: '
                    f'self.start: {self.start} > region.end: {region.end}')
            region._pop_back_chunk(self.start)
            self.start = region.start
            self.chunks = region.chunks + self.chunks


class MultiRegionBuffer:
    """Multi-Region-Buffer: buffer with multiple regions for dynamic buffering.
    TODO:
    - Interaction with the decision module.
    - Testing.
    """
    def __init__(self, chunk_duration) -> None:
        self.region_starts = []     # start pos of regions for bisect
        # Reason for not using list: regions can be merged, and i will be moved
        # for all the regions afterwards
        self.region_map = {}        # region map {t: region}
        self.chunk_duration = chunk_duration

    def buffer_by_pos(self, pos: float, quality: float):
        """Buffers a chunk for `pos`. There are three cases:
        1. Hit the existing buffer -> buffer after the region or ignore?
        2. Miss, then register a new region;
        TODO: polish this after finalizing the usage in sabre.py
        below is a tentative implementation.
        """
        region = self._find_region_of(pos)
        if region:
            region.add_chunk(quality)
            i_region = bisect_right(self.region_starts, pos) - 1
            assert 0 <= i_region < len(self.region_starts)
            if i_region < len(self.region_starts) - 1:
                next_start = self.region_starts[i_region + 1]
                next_region = self.region_map[next_start]
                region.try_merge(next_region)
            print(f'Add into existing region: {region.start} - {region.end} s')

        else:
            # TODO: double check the chunk boundary remainder
            start = pos // self.chunk_duration * self.chunk_duration
            region = BufferRegion(start, self.chunk_duration)
            self.region_starts.append(start)
            self.region_starts.sort()
            self.region_map[start] = region
            print(f'Start a new region: {region.start} - {region.end} s')

    def buffer_by_region(self, i_region: int, quality: float):
        """Buffers a chunk after i-th existing region.
        New buffer region is not supported here on purpose.
        """
        assert 0 <= i_region < len(self.region_map)
        region_start = self.region_starts[i_region]
        region = self.region_map[region_start]
        region.add_chunk(quality)
        if i_region < len(self.region_map) - 1:
            next_start = self.region_starts[i_region + 1]
            next_region = self.region_map[next_start]
            region.try_merge(next_region)
        print(f'Add into existing region: {region.start} - {region.end} s')

    def _find_region_of(self, pos: float):
        """Finds the region of given `pos`. """
        if not self.region_starts:
            return None
        i_region = bisect_right(self.region_starts, pos) - 1
        assert 0 <= i_region < len(self.region_starts)
        start = self.region_starts[i_region]
        region = self.region_map[start]
        if not region.exists(pos):
            return None
        return region

    def is_buffered(self, pos: float):
        """Returns if the closest chunk to `pos` is buffered.
        """
        return self._find_region_of(pos) is not None

