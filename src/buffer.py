from __future__ import annotations
import math
import typing
from bisect import bisect_right
from enum import Enum

# Import gs for compatibility methods
try:
    from global_state import gs
except ImportError:
    # Handle case where gs is not available (e.g., during import)
    gs = None


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
        if self.end is None:
            return False  # Region has no chunks yet
        return pos >= self.start and pos < self.end

    def try_merge(self, region: BufferRegion) -> bool:
        """Try merging this region with another buffer region.

        If the given region can be merged, then current region is updated with
        the new chunks; otherwise if region and current region are not
        overlapped, nothing is changed. Returns if the merge is successful.
        """
        # Handle None end values
        if self.end is None or region.end is None:
            return False
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
            # Filter valid starts before checking next region
            valid_starts = [s for s in self.region_starts if s in self.region_map]
            i_region = bisect_right(valid_starts, pos) - 1
            if 0 <= i_region < len(valid_starts) and i_region < len(valid_starts) - 1:
                next_start = valid_starts[i_region + 1]
                if next_start in self.region_map:
                    next_region = self.region_map[next_start]
                    region.try_merge(next_region)
            print(f'Add into existing region: {region.start} - {region.end} s')

        else:
            # Check if there's a region that ends exactly at this position (adjacent)
            # This handles sequential downloads
            valid_starts = [s for s in self.region_starts if s in self.region_map]
            found_adjacent = False
            for start in valid_starts:
                adj_region = self.region_map[start]
                print(f'adj_region.end:{adj_region.end},pos:{pos}, boundary difference: {abs(adj_region.end - pos)}')
                if adj_region.end is not None and abs(adj_region.end - pos) < 0.001:
                    # Found adjacent region - extend it
                    adj_region.add_chunk(quality)
                    found_adjacent = True
                    # Try to merge with next region if exists
                    valid_starts_sorted = sorted(valid_starts)
                    if start in valid_starts_sorted:
                        idx = valid_starts_sorted.index(start)
                        if idx + 1 < len(valid_starts_sorted):
                            next_start = valid_starts_sorted[idx + 1]
                            if next_start in self.region_map:
                                next_region = self.region_map[next_start]
                                adj_region.try_merge(next_region)
                    print(f'Extend adjacent region: {adj_region.start} - {adj_region.end} s')
                    break
            
            if not found_adjacent:
                # TODO: double check the chunk boundary remainder
                start = pos // self.chunk_duration * self.chunk_duration
                region = BufferRegion(start, self.chunk_duration)
                region.add_chunk(quality)  # Add the chunk to set end
                self.region_starts.append(start)
                self.region_starts.sort()
                self.region_map[start] = region
                print(f'Start a new region: {region.start} - {region.end} s')

    def buffer_by_region(self, i_region: int, quality: float):
        """Buffers a chunk after i-th existing region.
        New buffer region is not supported here on purpose.
        """
        # Filter valid starts
        valid_starts = [s for s in self.region_starts if s in self.region_map]
        assert 0 <= i_region < len(valid_starts)
        region_start = valid_starts[i_region]
        region = self.region_map[region_start]
        region.add_chunk(quality)
        if i_region < len(valid_starts) - 1:
            next_start = valid_starts[i_region + 1]
            if next_start in self.region_map:
                next_region = self.region_map[next_start]
                region.try_merge(next_region)
        print(f'Add into existing region: {region.start} - {region.end} s')

    def _find_region_of(self, pos: float):
        """Finds the region of given `pos`. """
        if not self.region_starts:
            return None
        
        # Filter out starts that don't exist in region_map (due to merging)
        valid_starts = [s for s in self.region_starts if s in self.region_map]
        if not valid_starts:
            return None
        
        i_region = bisect_right(valid_starts, pos) - 1
        if i_region < 0 or i_region >= len(valid_starts):
            return None
        
        start = valid_starts[i_region]
        if start not in self.region_map:
            return None
            
        region = self.region_map[start]
        if not region.exists(pos):
            return None
        return region

    def is_buffered(self, pos: float):
        """Returns if the closest chunk to `pos` is buffered.
        """
        return self._find_region_of(pos) is not None
    
    # Compatibility methods (previously in BufferWrapper)
    
    def get_buffer_level(self):
        """Only count contiguous playable content - CRITICAL for ABR compatibility."""
        if gs is None:
            return 0
        playable_chunks = self.get_contiguous_chunks_from_current_position()
        return self.chunk_duration * len(playable_chunks) - gs.buffer_fcc
    
    def get_contiguous_chunks_from_current_position(self):
        """Find region containing current playback position, return contiguous chunks forward.
        Also includes chunks from adjacent contiguous regions."""
        if gs is None:
            return []
        
        # Find the region containing current playback position
        region = self._find_region_of(gs.current_playback_pos)
        if not region:
            # If no region at exact position, try to find the closest region after current position
            valid_starts = [s for s in self.region_starts if s in self.region_map]
            valid_starts = sorted([s for s in valid_starts if s >= gs.current_playback_pos])
            if valid_starts:
                region = self.region_map[valid_starts[0]]
            else:
                return []
        
        # Calculate start index within the region
        if gs.current_playback_pos < region.start:
            start_idx = 0
        else:
            start_idx = int((gs.current_playback_pos - region.start) / self.chunk_duration)
        
        # Collect chunks from this region
        chunks = region.chunks[start_idx:] if start_idx < len(region.chunks) else []
        
        # Collect chunks from adjacent contiguous regions
        valid_starts = sorted([s for s in self.region_starts if s in self.region_map])
        current_start = region.start
        
        # Find this region's index
        if current_start in valid_starts:
            idx = valid_starts.index(current_start)
            # Check subsequent regions for contiguous chunks
            for i in range(idx + 1, len(valid_starts)):
                next_start = valid_starts[i]
                next_region = self.region_map[next_start]
                
                # Check if regions are contiguous (current ends where next starts)
                if region.end is not None and abs(region.end - next_start) < 0.001:
                    chunks.extend(next_region.chunks)
                    region = next_region  # Update for next iteration
                else:
                    # Not contiguous, stop
                    break
        
        return chunks
    
    def add_chunk(self, segment_index, quality):
        """Add chunk, convert segment_index to ms position."""
        pos_ms = segment_index * self.chunk_duration
        self.buffer_by_pos(pos_ms, quality)
        self.cleanup_and_merge()
        # Rebuild buffer_contents from all regions for compatibility
        # This ensures replacement logic works correctly
        self._sync_buffer_contents()
    
    def _sync_buffer_contents(self):
        """Sync buffer_contents with MultiRegionBuffer regions for compatibility."""
        if gs is None or not hasattr(gs, 'buffer_contents'):
            return
        
        # Update buffer_contents - keep only sequential chunks from current position forward
        # This matches the playable chunks logic
        playable_chunks = self.get_contiguous_chunks_from_current_position()
        if playable_chunks:
            # Find the starting segment index from current playback position
            region = self._find_region_of(gs.current_playback_pos)
            if region:
                start_idx = int((gs.current_playback_pos - region.start) / self.chunk_duration)
                start_seg_idx = int(region.start / self.chunk_duration) + start_idx
                gs.buffer_contents = [(start_seg_idx + i, q) for i, q in enumerate(playable_chunks)]
            else:
                gs.buffer_contents = []
        else:
            gs.buffer_contents = []
    
    def cleanup_and_merge(self):
        """Maintain buffer health by merging adjacent regions when they become contiguous."""
        self.merge_adjacent_regions()
    
    def merge_adjacent_regions(self):
        """Merge regions that are adjacent (no gap between them)."""
        if len(self.region_starts) < 2:
            return
        
        # Filter out any starts that don't have corresponding regions in the map
        valid_starts = [start for start in self.region_starts if start in self.region_map]
        
        if len(valid_starts) < 2:
            # Update region_starts to match valid regions
            self.region_starts = valid_starts
            return
        
        # Sort regions by start position
        sorted_starts = sorted(valid_starts)
        merged_starts = []
        merged_map = {}
        
        i = 0
        while i < len(sorted_starts):
            current_start = sorted_starts[i]
            if current_start not in self.region_map:
                i += 1
                continue
                
            current_region = self.region_map[current_start]
            
            # Check if we can merge with next region
            if i + 1 < len(sorted_starts):
                next_start = sorted_starts[i + 1]
                if next_start not in self.region_map:
                    # Next region doesn't exist, keep current and move on
                    merged_starts.append(current_start)
                    merged_map[current_start] = current_region
                    i += 1
                    continue
                    
                next_region = self.region_map[next_start]
                
                # Check if regions are adjacent (end of current == start of next)
                if current_region.end is not None and abs(current_region.end - next_start) < 0.001:
                    # Merge: extend current region with next region's chunks
                    if current_region.try_merge(next_region):
                        # Successfully merged, remove next region from map
                        if next_start in self.region_map:
                            del self.region_map[next_start]
                        # Successfully merged, skip next region
                        i += 2
                        continue
            
            # Keep current region as-is
            merged_starts.append(current_start)
            merged_map[current_start] = current_region
            i += 1
        
        # Update MultiRegionBuffer with merged regions
        self.region_starts = merged_starts
        self.region_map = merged_map
    
    def pop_chunk(self):
        """Remove first chunk from current playback position."""
        if gs is None:
            return
        region = self._find_region_of(gs.current_playback_pos)
        if not region or not region.chunks:
            return
        
        # Calculate chunk index within region
        start_idx = int((gs.current_playback_pos - region.start) / self.chunk_duration)
        
        if start_idx < len(region.chunks):
            # Remove the chunk
            old_start = region.start
            region.chunks.pop(start_idx)
            
            # Update region start if we removed the first chunk
            if start_idx == 0:
                new_start = region.start + self.chunk_duration
                # Update region_map key if start changed
                if old_start in self.region_map:
                    del self.region_map[old_start]
                if old_start in self.region_starts:
                    self.region_starts.remove(old_start)
                region.start = new_start
                self.region_starts.append(new_start)
                self.region_starts.sort()
                self.region_map[new_start] = region
            
            # Update region end
            if region.end is not None:
                region.end -= self.chunk_duration
                if region.end <= region.start or len(region.chunks) == 0:
                    # Region is empty, remove it
                    if region.start in self.region_starts:
                        self.region_starts.remove(region.start)
                    if region.start in self.region_map:
                        del self.region_map[region.start]
            
            # Update buffer_fcc
            gs.buffer_fcc = 0
            
            # Sync buffer_contents after popping
            self._sync_buffer_contents()

