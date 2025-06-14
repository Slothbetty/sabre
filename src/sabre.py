# Copyright (c) 2018, Kevin Spiteri
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import argparse
import json
import math
import sys
import string
import os
from importlib.machinery import SourceFileLoader
from collections import namedtuple
from enum import Enum

# Units used throughout:
#     size     : bits
#     time     : ms
#     size/time: bits/ms = kbit/s


# global variables:
#     video manifest
#     buffer contents
#     buffer first segment consumed
#     throughput estimate
#     latency estimate
#     rebuffer event count
#     rebuffer total time
#     session info


def load_json(path):
    with open(path) as file:
        obj = json.load(file)
    return obj


ManifestInfo = namedtuple("ManifestInfo", "segment_time bitrates utilities segments")
NetworkPeriod = namedtuple("NetworkPeriod", "time bandwidth latency")

DownloadProgress = namedtuple(
    "DownloadProgress",
    "index quality " "size downloaded " "time time_to_first_bit " "abandon_to_quality",
)


def get_buffer_level():
    global manifest
    global buffer_contents
    global buffer_fcc # Note: buffer first content chunk: use to track remaining portion of the first segment in the playback buffer.

    return manifest.segment_time * len(buffer_contents) - buffer_fcc


def interrupted_by_seek(delta):
    global next_segment, buffer_contents, buffer_fcc, total_play_time
    global rampup_origin, rampup_time, abr, verbose, seek_events, last_seek_time

    # Check for a pending seek event.
    if seek_events:
        # Convert the next scheduled seek time to milliseconds.
        seek_when_ms = seek_events[0]["seek_when"] * 1000
        # If adding delta would cross the seek event time, process the seek.
        if total_play_time < seek_when_ms and total_play_time + delta >= seek_when_ms:
            # Directly update the play time to the scheduled seek time.
            total_play_time = seek_when_ms

            # Get the seek event and convert seek_to into milliseconds.
            event = seek_events.pop(0)
            seek_to = event["seek_to"]
            seek_to_ms = seek_to * 1000
            # Determine the segment index nearest to the requested seek time (seek_to_ms).
            # We split each segment in half: if seek_to_ms is in the first half, round down;
            # if it’s in the second half, round up.
            seg_time = manifest.segment_time  # duration of each segment in milliseconds

            # Compute the zero‐based index by flooring the division.
            floor_idx = math.floor(seek_to_ms / seg_time)

            # Calculate the timestamp of the start of the floor_idx segment.
            prev_boundary = floor_idx * seg_time

            # How many milliseconds past the start of that segment the seek target is.
            delta = seek_to_ms - prev_boundary

            if delta < (seg_time / 2):
                # If target is in the first half of the segment, stay on floor_idx.
                new_segment = floor_idx
            else:
                # If target is in the second half, advance to the next segment.
                new_segment = floor_idx + 1

            last_seek_time = total_play_time

            if verbose:
                print("[Seek] At playback time %d ms: seeking to %d seconds (segment index %d)" %
                      (total_play_time, seek_to, new_segment))

            # Compute the segment index corresponding to the first element in the buffer.
            # next_segment always equals: buffer_base + len(buffer_contents)
            buffer_base = next_segment - len(buffer_contents)

            # If the current buffered segments span content past the new playback position,
            # keep the segments that are beyond 'new_segment'.
            if buffer_contents and new_segment >= buffer_base and new_segment < next_segment:
                # Calculate how many segments to drop.
                skip_count = new_segment - buffer_base
                buffer_contents = buffer_contents[skip_count:]
            else:
                # Otherwise, if no buffered segment is relevant, clear the buffer.
                buffer_contents.clear()
                next_segment = new_segment

            # At this point, calculate how much of the first segment is already “used up”:
            # If `new_segment` equals `floor_idx`, the seek landed partway into that segment.
            # Otherwise, we jumped to the very start of a segment.
            if new_segment == floor_idx:
                # Seek landed inside the same segment: set buffer_fcc to the elapsed ms within it.
                buffer_fcc = seek_to_ms - (floor_idx * seg_time)
            else:
                # Seek landed at a segment boundary: no partial chunk has been consumed.
                buffer_fcc = 0
            # Notify ABR of the seek event (using seek time in milliseconds).
            abr.report_seek(seek_to_ms)
            # Reset rampup variables.
            rampup_origin = total_play_time
            rampup_time = None
            return True  # Indicate that a seek was processed.

    # If no seek event occurs in this delta, simply increment total_play_time.
    total_play_time += delta
    return False

def deplete_buffer(time):
    """
    Process the playback buffer for the given amount of time.
    Returns True if depleting the buffer completes normally, or False if a seek event is detected and processed.
    """
    global manifest, buffer_contents, buffer_fcc, rebuffer_event_count, rebuffer_time
    global played_utility, played_bitrate, total_bitrate_change, total_log_bitrate_change, last_played
    global rampup_origin, rampup_time, rampup_threshold, sustainable_quality, segment_rebuffer_time
    global pending_quality_up, seek_events

    if len(buffer_contents) == 0:
        rebuffer_time += time
        if interrupted_by_seek(time):
            return False  # Seek event triggered: abort depleting further.
        rebuffer_event_count += 1
        segment_rebuffer_time = time
        return True

    if buffer_fcc > 0:
        # Play the remaining fraction of the first chunk.
        if time + buffer_fcc < manifest.segment_time:
            buffer_fcc += time
            if interrupted_by_seek(time):
                return False
            return True
        dt = manifest.segment_time - buffer_fcc
        time -= dt
        if interrupted_by_seek(dt):
            return False
        buffer_contents.pop(0)
        buffer_fcc = 0

    # Process full segments.
    while time > 0 and len(buffer_contents) > 0:
        (_seg_idx, quality) = buffer_contents[0]
        played_utility += manifest.utilities[quality]
        played_bitrate += manifest.bitrates[quality]
        if last_played is not None and quality != last_played:
            total_bitrate_change += abs(manifest.bitrates[quality] - manifest.bitrates[last_played])
            total_log_bitrate_change += abs(math.log(manifest.bitrates[quality] / manifest.bitrates[last_played]))
        last_played = quality

        if rampup_time is None:
            rt = sustainable_quality if rampup_threshold is None else rampup_threshold
            if quality >= rt:
                rampup_time = total_play_time - rampup_origin

        # Process pending quality-up events.
        for p in pending_quality_up:
            if len(p) == 2 and quality >= p[1]:
                p.append(total_play_time)

        if time >= manifest.segment_time:
            buffer_contents.pop(0)
            if interrupted_by_seek(manifest.segment_time):
                return False
            time -= manifest.segment_time
        else:
            buffer_fcc = time
            if interrupted_by_seek(time):
                return False
            time = 0

    if time > 0:
        rebuffer_time += time
        if interrupted_by_seek(time):
            return False
        rebuffer_event_count += 1
        segment_rebuffer_time = time

    process_quality_up(total_play_time)
    return True  # Completed without interruption.

def playout_buffer():
    global buffer_contents
    global buffer_fcc

    deplete_buffer(get_buffer_level())

    # make sure no rounding error
    del buffer_contents[:]
    buffer_fcc = 0


# The process_quality_up function processes pending quality upgrade requests that are older than a certain cutoff time.
# It calculates the reaction time for each processed request and accumulates this time in a global counter.
# The reaction time is either the maximum buffer size or a calculated value based on the request details.
def process_quality_up(now):
    global max_buffer_size
    global pending_quality_up
    global total_reaction_time

    # check which switches can be processed

    # print("now=%d, max_buffer_size=%d" % (now, max_buffer_size))
    cutoff = now - max_buffer_size
    # print("cutoff=%d" % cutoff)
    # print("pending_quality_up=%s" % pending_quality_up)
    while len(pending_quality_up) > 0 and pending_quality_up[0][0] < cutoff:
        p = pending_quality_up.pop(0)
        if len(p) == 2:
            reaction = max_buffer_size
        else:
            reaction = min(max_buffer_size, p[2] - p[0])
        # print('\n[%d] reaction time: %d' % (now, reaction))
        # print(p)
        total_reaction_time += reaction


def advertize_new_network_quality(quality, previous_quality):
    global max_buffer_size
    global network_total_time
    global pending_quality_up
    global buffer_contents

    # bookkeeping to track reaction time to increased bandwidth

    # process any previous quality up switches that have "matured"
    process_quality_up(network_total_time)

    # mark any pending switch up done if new quality switches back below its quality
    for p in pending_quality_up:
        if len(p) == 2 and p[1] > quality:
            p.append(network_total_time)
    # pending_quality_up = [p for p in pending_quality_up if p[1] >= quality]

    # filter out switches which are not upwards (three separate checks)
    if quality <= previous_quality:
        return
    for (_idx, q) in buffer_contents:
        if quality <= q:
            return
    for p in pending_quality_up:
        if quality <= p[1]:
            return

    # valid quality up switch
    pending_quality_up.append([network_total_time, quality])

def process_download_loop():
    global next_segment, abandoned_to_quality, buffer_contents, total_play_time
    global segment_rebuffer_time, throughput, overestimate_count, overestimate_average
    global goodestimate_count, goodestimate_average, estimate_average, throughput_history
    global manifest, buffer_size, network, abr, replacer, args, is_bola, verbose, graph

    while next_segment < len(manifest.segments):
        # Check if there is extra content in the buffer.
        full_delay = get_buffer_level() + manifest.segment_time - buffer_size
        if full_delay > 0:
            if not deplete_buffer(full_delay):
                continue  # A seek event was triggered; restart loop.
            network.delay(full_delay)
            abr.report_delay(full_delay)
            if verbose:
                print("full buffer delay %d bl=%d" % (full_delay, get_buffer_level()))

        # Determine quality and delay; handle potential replacement.
        if abandoned_to_quality is None:
            quality, delay = abr.get_quality_delay(next_segment)
            replace = replacer.check_replace(quality)
        else:
            quality, delay = abandoned_to_quality, 0
            replace = None
            abandoned_to_quality = None

        if replace is not None:
            delay = 0
            current_segment = next_segment + replace
            check_abandon = replacer.check_abandon
        else:
            current_segment = next_segment
            check_abandon = abr.check_abandon
        if args.no_abandon:
            check_abandon = None

        size = manifest.segments[current_segment][quality]

        if delay > 0:
            if not deplete_buffer(delay):
                continue  # Seek occurred, restart the loop.
            network.delay(delay)
            if verbose:
                print("abr delay %d bl=%d" % (delay, get_buffer_level()))

        download_metric = network.download(size, current_segment, quality, get_buffer_level(), check_abandon)

        start_time = round(total_play_time)
        success = deplete_buffer(download_metric.time)
        end_time = round(total_play_time)
        if not success:
            # A seek occurred during depleting the buffer.
            effective_end = last_seek_time
            effective_download_time = effective_end - start_time
            if download_metric.time > 0:
                effective_downloaded = int(download_metric.downloaded * effective_download_time / download_metric.time)
            if verbose:
                print(
                    "[%d-%d]  %d: quality=%d download_size=%d/%d download_time=%d=%d+%d "
                    % (
                        start_time,
                        effective_end,
                        current_segment,
                        download_metric.quality,
                        effective_downloaded,
                        download_metric.size,
                        effective_download_time,
                        download_metric.time_to_first_bit,
                        effective_download_time - download_metric.time_to_first_bit,
                    ),
                    end="",
                )
                # Append extra logging details.
                if replace is None:
                    if download_metric.abandon_to_quality is None:
                        print("buffer_level=%d" % get_buffer_level())
                    else:
                        print(
                            " ABANDONED to %d - %d/%d bits in %d=%d+%d ttfb+ttdl  bl=%d"
                            % (
                                download_metric.abandon_to_quality,
                                download_metric.downloaded,
                                download_metric.size,
                                download_metric.time,
                                download_metric.time_to_first_bit,
                                download_metric.time - download_metric.time_to_first_bit,
                                get_buffer_level(),
                            ),
                            end="",
                        )
                else:
                    if download_metric.abandon_to_quality is None:
                        print(" REPLACEMENT  bl=%d" % get_buffer_level())
                    else:
                        print(
                            " REPLACMENT ABANDONED after %d=%d+%d ttfb+ttdl  bl=%d"
                            % (
                                download_metric.time,
                                download_metric.time_to_first_bit,
                                download_metric.time - download_metric.time_to_first_bit,
                                get_buffer_level(),
                            ),
                            end="",
                        )
            if graph:
                print(
                    "%d time=%d network_bandwidth=%d network_latency=%d quality=%d bitrate=%d download_size=%d download_time=%d buffer_level=%d rebuffer_time=%d is_bola=%s"
                    % (
                        current_segment,
                        effective_end,
                        network.trace[network.index].bandwidth,
                        network.trace[network.index].latency,
                        download_metric.quality,
                        manifest.bitrates[download_metric.quality],
                        effective_downloaded,
                        effective_download_time,
                        get_buffer_level(),
                        0,
                        is_bola
                    )
                )
            continue  # After a seek, restart the loop.
        else:
            if verbose:
                print(
                    "[%d-%d]  %d: quality=%d download_size=%d/%d download_time=%d=%d+%d "
                    % (
                        start_time,
                        end_time,
                        current_segment,
                        download_metric.quality,
                        download_metric.downloaded,
                        download_metric.size,
                        download_metric.time,
                        download_metric.time_to_first_bit,
                        download_metric.time - download_metric.time_to_first_bit,
                    ),
                    end="",
                )
                # Append extra logging details.
                if replace is None:
                    if download_metric.abandon_to_quality is None:
                        print("buffer_level=%d" % get_buffer_level(), end="")
                    else:
                        print(
                            " ABANDONED to %d - %d/%d bits in %d=%d+%d ttfb+ttdl  bl=%d"
                            % (
                                download_metric.abandon_to_quality,
                                download_metric.downloaded,
                                download_metric.size,
                                download_metric.time,
                                download_metric.time_to_first_bit,
                                download_metric.time - download_metric.time_to_first_bit,
                                get_buffer_level(),
                            ),
                            end="",
                        )
                else:
                    if download_metric.abandon_to_quality is None:
                        print(" REPLACEMENT  bl=%d" % get_buffer_level(), end="")
                    else:
                        print(
                            " REPLACMENT ABANDONED after %d=%d+%d ttfb+ttdl  bl=%d"
                            % (
                                download_metric.time,
                                download_metric.time_to_first_bit,
                                download_metric.time - download_metric.time_to_first_bit,
                                get_buffer_level(),
                            ),
                            end="",
                        )
            if graph:
                print(
                    "%d time=%d network_bandwidth=%d network_latency=%d quality=%d bitrate=%d download_size=%d download_time=%d "
                    % (
                        current_segment,
                        end_time,
                        network.trace[network.index].bandwidth,
                        network.trace[network.index].latency,
                        download_metric.quality,
                        manifest.bitrates[download_metric.quality],
                        download_metric.downloaded,
                        download_metric.time,
                    ),
                    end="",
                )
        if verbose:
            print("->%d" % get_buffer_level(), end="")

        # Update buffer with new download.
        if replace is None:
            if download_metric.abandon_to_quality is None:
                buffer_contents.append((next_segment, quality))
                next_segment += 1
            else:
                abandoned_to_quality = download_metric.abandon_to_quality
        else:
            if download_metric.abandon_to_quality is None:
                if get_buffer_level() + manifest.segment_time * replace >= 0:
                    old_seg_idx, _ = buffer_contents[replace]
                    buffer_contents[replace] = (old_seg_idx, quality)
                else:
                    print("WARNING: too late to replace")
            else:
                pass

        if verbose:
            print("->%d" % get_buffer_level())
        if graph:
            if segment_rebuffer_time > 0:
                print(
                    "buffer_level=%d rebuffer_time=%d is_bola=%s"
                    % (get_buffer_level(), segment_rebuffer_time, is_bola)
                )
                segment_rebuffer_time = 0
            else:
                print("buffer_level=%d rebuffer_time=%d is_bola=%s" % (get_buffer_level(), 0, is_bola))

        abr.report_download(download_metric, replace is not None)

        # Calculate throughput and latency.
        download_time = download_metric.time - download_metric.time_to_first_bit
        t = download_metric.downloaded / download_time
        l = download_metric.time_to_first_bit

        if throughput > t:
            overestimate_count += 1
            overestimate_average += (throughput - t - overestimate_average) / overestimate_count
        else:
            goodestimate_count += 1
            goodestimate_average += (t - throughput - goodestimate_average) / goodestimate_count
        estimate_average += (throughput - t - estimate_average) / (overestimate_count + goodestimate_count)

        if download_metric.abandon_to_quality is None:
            throughput_history.push(download_time, t, l)

class NetworkModel:

    # Question: these variables are hardcoded, should they be configurable?
    min_progress_size = 12000
    min_progress_time = 50

    def __init__(self, network_trace):
        # Purpose: sustainable_quality represents the highest quality level of video that can be sustained given the current network conditions.
        # Initialization: It is initially set to None and then reset to 0 at the beginning of each network period calculation.
        # Calculation: It is determined by iterating through the available bitrates and comparing them to the effective_bandwidth.
        global sustainable_quality
        global network_total_time

        sustainable_quality = 0
        network_total_time = 0
        self.trace = network_trace
        self.index = -1
        self.time_to_next = 0
        self.next_network_period()

    def next_network_period(self):
        global manifest
        global sustainable_quality
        global network_total_time

        self.index += 1
        if self.index == len(self.trace):
            self.index = 0
        self.time_to_next = self.trace[self.index].time

        # calculate effective bandwidth by removing the latency factor from the current bandwidth
        latency_factor = 1 - self.trace[self.index].latency / manifest.segment_time
        effective_bandwidth = self.trace[self.index].bandwidth * latency_factor

        previous_sustainable_quality = sustainable_quality
        sustainable_quality = 0
        for i in range(1, len(manifest.bitrates)):
            if manifest.bitrates[i] > effective_bandwidth:
                break
            # sustainable_quality is the highest quality level that can be sustained given the current network conditions
            # it is the index of the bitrate in the manifest.bitrates list
            sustainable_quality = i
        if (
            sustainable_quality != previous_sustainable_quality
            and previous_sustainable_quality != None
        ):
            advertize_new_network_quality(
                sustainable_quality, previous_sustainable_quality
            )

        if verbose:
            print(
                "[%d] Network: bandwidth->%d, lantency->%d (sustainable_quality=%d: bitrate=%d)"
                % (
                    network_total_time,
                    self.trace[self.index].bandwidth,
                    self.trace[self.index].latency,
                    sustainable_quality,
                    manifest.bitrates[sustainable_quality],
                )
            )

    # apply latency delay for the given number of units and return delay time
    def do_latency_delay(self, delay_units):
        global network_total_time

        total_delay = 0
        while delay_units > 0:
            current_latency = self.trace[self.index].latency
            time = delay_units * current_latency
            # print("%d, %d" % (time, self.time_to_next), end="\n")
            if time <= self.time_to_next:
                total_delay += time
                network_total_time += time
                self.time_to_next -= time
                delay_units = 0
            else:
                # time > self.time_to_next implies current_latency > 0
                total_delay += self.time_to_next
                network_total_time += self.time_to_next
                delay_units -= self.time_to_next / current_latency
                self.next_network_period()
        return total_delay

    # return download time
    def do_download(self, size):
        global network_total_time
        total_download_time = 0
        while size > 0:
            current_bandwidth = self.trace[self.index].bandwidth
            if size <= self.time_to_next * current_bandwidth:
                # current_bandwidth > 0
                time = size / current_bandwidth
                total_download_time += time
                network_total_time += time
                self.time_to_next -= time
                size = 0
            else:
                total_download_time += self.time_to_next
                network_total_time += self.time_to_next
                size -= self.time_to_next * current_bandwidth
                self.next_network_period()
        return total_download_time

    def do_minimal_latency_delay(self, delay_units, min_time):
        global network_total_time
        total_delay_units = 0
        total_delay_time = 0
        while delay_units > 0 and min_time > 0:
            current_latency = self.trace[self.index].latency
            time = delay_units * current_latency
            if time <= min_time and time <= self.time_to_next:
                units = delay_units
                self.time_to_next -= time
                network_total_time += time
            elif min_time <= self.time_to_next:
                # time > 0 implies current_latency > 0
                time = min_time
                units = time / current_latency
                self.time_to_next -= time
                network_total_time += time
            else:
                time = self.time_to_next
                units = time / current_latency
                network_total_time += time
                self.next_network_period()
            total_delay_units += units
            total_delay_time += time
            delay_units -= units
            min_time -= time
        return (total_delay_units, total_delay_time)

    def do_minimal_download(self, size, min_size, min_time):
        global network_total_time
        total_size = 0
        total_time = 0
        while size > 0 and (min_size > 0 or min_time > 0):
            current_bandwidth = self.trace[self.index].bandwidth
            if current_bandwidth > 0:
                min_bits = max(min_size, min_time * current_bandwidth)
                bits_to_next = self.time_to_next * current_bandwidth
                if size <= min_bits and size <= bits_to_next:
                    bits = size
                    time = bits / current_bandwidth
                    self.time_to_next -= time
                    network_total_time += time
                elif min_bits <= bits_to_next:
                    bits = min_bits
                    time = bits / current_bandwidth
                    # make sure rounding error does not push while loop into endless loop
                    min_size = 0
                    min_time = 0
                    self.time_to_next -= time
                    network_total_time += time
                else:
                    bits = bits_to_next
                    time = self.time_to_next
                    network_total_time += time
                    self.next_network_period()
            else:  # current_bandwidth == 0
                bits = 0
                if min_size > 0 or min_time > self.time_to_next:
                    time = self.time_to_next
                    network_total_time += time
                    self.next_network_period()
                else:
                    time = min_time
                    self.time_to_next -= time
                    network_total_time += time
            total_size += bits
            total_time += time
            size -= bits
            min_size -= bits
            min_time -= time
        return (total_size, total_time)

    def delay(self, time):
        global network_total_time
        while time > self.time_to_next:
            time -= self.time_to_next
            network_total_time += self.time_to_next
            self.next_network_period()
        self.time_to_next -= time
        network_total_time += time

    # The download method simulates the downloading of a video segment, handling latency, download progress,
    # and potential abandonment based on buffer levels and a provided callback function.
    # It returns a DownloadProgress object with the details of the download process.
    def download(self, size, idx, quality, buffer_level, check_abandon=None):
        if size <= 0:
            return DownloadProgress(
                index=idx,
                quality=quality,
                size=0,
                downloaded=0,
                time=0,
                time_to_first_bit=0,
                abandon_to_quality=None,
            )

        # print("check_abandon=%s" % check_abandon)
        if not check_abandon or (
            NetworkModel.min_progress_time <= 0 and NetworkModel.min_progress_size <= 0
        ):
            latency = self.do_latency_delay(1)
            time = latency + self.do_download(size)
            # print("time=%d" % time)
            return DownloadProgress(
                index=idx,
                quality=quality,
                size=size,
                downloaded=size,
                time=time,
                time_to_first_bit=latency,
                abandon_to_quality=None,
            )

        total_download_time = 0
        total_download_size = 0
        min_time_to_progress = NetworkModel.min_progress_time
        min_size_to_progress = NetworkModel.min_progress_size
        # print("min_time_to_progress=%d, min_size_to_progress=%d" % (min_time_to_progress, min_size_to_progress))
        if NetworkModel.min_progress_size > 0:
            latency = self.do_latency_delay(1)
            total_download_time += latency
            min_time_to_progress -= total_download_time
            delay_units = 0
        else:
            latency = None
            delay_units = 1

        abandon_quality = None
        while total_download_size < size and abandon_quality == None:

            if delay_units > 0:
                # NetworkModel.min_progress_size <= 0
                (units, time) = self.do_minimal_latency_delay(
                    delay_units, min_time_to_progress
                )
                total_download_time += time
                delay_units -= units
                min_time_to_progress -= time
                if delay_units <= 0:
                    latency = total_download_time

            if delay_units <= 0:
                # don't use else to allow fall through
                (bits, time) = self.do_minimal_download(
                    size - total_download_size,
                    min_size_to_progress,
                    min_time_to_progress,
                )
                total_download_time += time
                total_download_size += bits
                # no need to upldate min_[time|size]_to_progress - reset below

            dp = DownloadProgress(
                index=idx,
                quality=quality,
                size=size,
                downloaded=total_download_size,
                time=total_download_time,
                time_to_first_bit=latency,
                abandon_to_quality=None,
            )
            if total_download_size < size:
                abandon_quality = check_abandon(
                    dp, max(0, buffer_level - total_download_time)
                )
                if abandon_quality != None:
                    if verbose:
                        print(
                            "[%d] abandoning: quality=%d->abandon_quality=%d"
                            % (idx, quality, abandon_quality)
                        )
                        print(
                            "%d/%d %d(%d)"
                            % (dp.downloaded, dp.size, dp.time, dp.time_to_first_bit)
                        )
                min_time_to_progress = NetworkModel.min_progress_time
                min_size_to_progress = NetworkModel.min_progress_size

        return DownloadProgress(
            index=idx,
            quality=quality,
            size=size,
            downloaded=total_download_size,
            time=total_download_time,
            time_to_first_bit=latency,
            abandon_to_quality=abandon_quality,
        )


class ThroughputHistory:
    def __init__(self, config):
        pass

    def push(self, time, tput, lat):
        raise NotImplementedError


class SessionInfo:

    def __init__(self):
        pass

    def get_throughput(self):
        global throughput
        return throughput

    def get_buffer_contents(self):
        global buffer_contents
        return buffer_contents[:]


session_info = SessionInfo()


class Abr:

    session = session_info

    def __init__(self, config):
        pass

    def get_quality_delay(self, segment_index):
        raise NotImplementedError

    def get_first_quality(self):
        return 0

    def report_delay(self, delay):
        pass

    def report_download(self, metrics, is_replacment):
        pass

    def report_seek(self, where):
        pass

    def check_abandon(self, progress, buffer_level):
        return None

    def quality_from_throughput(self, tput): # Note: This function calculates the quality level based on the throughput.
        global manifest
        global throughput
        global latency

        p = manifest.segment_time

        quality = 0
        while (
            quality + 1 < len(manifest.bitrates)
            and latency + p * manifest.bitrates[quality + 1] / tput <= p
        ):
            quality += 1
        return quality


class Replacement:

    session = session_info

    def check_replace(self, quality):
        return None

    def check_abandon(self, progress, buffer_level):
        return None


average_list = {}
abr_list = {}


class SlidingWindow(ThroughputHistory):

    default_window_size = [3]
    max_store = 20

    def __init__(self, config):
        global throughput
        global latency

        if "window_size" in config and config["window_size"] != None:
            self.window_size = config["window_size"]
        else:
            self.window_size = SlidingWindow.default_window_size

        # TODO: init somewhere else?
        throughput = None
        latency = None

        self.last_throughputs = []
        self.last_latencies = []

    def push(self, time, tput, lat):
        global throughput
        global latency

        self.last_throughputs += [tput]
        self.last_throughputs = self.last_throughputs[-SlidingWindow.max_store :]

        self.last_latencies += [lat]
        self.last_latencies = self.last_latencies[-SlidingWindow.max_store :]

        tput = None
        lat = None
        for ws in self.window_size:
            sample = self.last_throughputs[-ws:]
            t = sum(sample) / len(sample)
            tput = t if tput == None else min(tput, t)  # conservative min
            sample = self.last_latencies[-ws:]
            l = sum(sample) / len(sample)
            lat = l if lat == None else max(lat, l)  # conservative max
        throughput = tput
        latency = lat


average_list["sliding"] = SlidingWindow


class Ewma(ThroughputHistory):

    # for throughput:
    default_half_life = [8000, 3000]

    def __init__(self, config):
        global throughput
        global latency

        # TODO: init somewhere else?
        throughput = None
        latency = None

        if "half_life" in config and config["half_life"] != None:
            self.half_life = [h * 1000 for h in config["half_life"]]
        else:
            self.half_life = Ewma.default_half_life

        self.latency_half_life = [h / manifest.segment_time for h in self.half_life]

        self.throughput = [0] * len(self.half_life)
        self.weight_throughput = 0
        self.latency = [0] * len(self.half_life)
        self.weight_latency = 0

    def push(self, time, tput, lat):
        global throughput
        global latency

        for i in range(len(self.half_life)):
            alpha = math.pow(0.5, time / self.half_life[i])
            self.throughput[i] = alpha * self.throughput[i] + (1 - alpha) * tput
            alpha = math.pow(0.5, 1 / self.latency_half_life[i])
            self.latency[i] = alpha * self.latency[i] + (1 - alpha) * lat

        self.weight_throughput += time
        self.weight_latency += 1

        tput = None
        lat = None
        for i in range(len(self.half_life)):
            zero_factor = 1 - math.pow(0.5, self.weight_throughput / self.half_life[i])
            t = self.throughput[i] / zero_factor
            tput = t if tput == None else min(tput, t)  # conservative case is min
            zero_factor = 1 - math.pow(
                0.5, self.weight_latency / self.latency_half_life[i]
            )
            l = self.latency[i] / zero_factor
            lat = l if lat == None else max(lat, l)  # conservative case is max
        throughput = tput
        latency = lat


average_list["ewma"] = Ewma
average_default = "ewma"


class Bola(Abr):

    def __init__(self, config):
        global verbose
        global manifest

        utility_offset = -math.log(manifest.bitrates[0])  # so utilities[0] = 0
        self.utilities = [math.log(b) + utility_offset for b in manifest.bitrates]

        self.gp = config["gp"]
        self.buffer_size = config["buffer_size"]
        self.abr_osc = config["abr_osc"]
        self.abr_basic = config["abr_basic"]
        self.Vp = (self.buffer_size - manifest.segment_time) / (
            self.utilities[-1] + self.gp
        )

        self.last_seek_index = 0  # TODO: need to update when multiple seeks
        self.last_quality = 0

        if verbose:
            for q in range(len(manifest.bitrates)):
                b = manifest.bitrates[q]
                u = self.utilities[q]
                l = self.Vp * (self.gp + u)
                if q == 0:
                    print("%d %d" % (q, l))
                else:
                    qq = q - 1
                    bb = manifest.bitrates[qq]
                    uu = self.utilities[qq]
                    ll = self.Vp * (self.gp + (b * uu - bb * u) / (b - bb))
                    print("%d %d    <- %d %d" % (q, l, qq, ll))

    def quality_from_buffer(self): # Note: This function calculates the quality level based on the buffer level.
        level = get_buffer_level()
        quality = 0
        score = None
        for q in range(len(manifest.bitrates)):
            s = (self.Vp * (self.utilities[q] + self.gp) - level) / manifest.bitrates[q]
            if score == None or s > score:
                quality = q
                score = s
        return quality

    def get_quality_delay(self, segment_index):
        global manifest
        global throughput

        if not self.abr_basic:
            t = min(
                segment_index - self.last_seek_index,
                len(manifest.segments) - segment_index,
            )
            t = max(t / 2, 3)
            t = t * manifest.segment_time
            buffer_size = min(self.buffer_size, t)
            self.Vp = (buffer_size - manifest.segment_time) / (
                self.utilities[-1] + self.gp
            )

        quality = self.quality_from_buffer()
        delay = 0

        if quality > self.last_quality:
            quality_t = self.quality_from_throughput(throughput)
            if quality <= quality_t:
                delay = 0
            elif self.last_quality > quality_t:
                quality = self.last_quality
                delay = 0
            else:
                if not self.abr_osc:
                    quality = quality_t + 1 # Note: Without oscillation control, the algorithm prioritizes a higher quality level, assuming the buffer can handle the extra risk.
                    delay = 0
                else:
                    quality = quality_t
                    # now need to calculate delay
                    b = manifest.bitrates[quality]
                    u = self.utilities[quality]
                    # bb = manifest.bitrates[quality + 1]
                    # uu = self.utilities[quality + 1]
                    # l = self.Vp * (self.gp + (bb * u - b * uu) / (bb - b))
                    l = self.Vp * (self.gp + u)  ##########
                    delay = max(0, get_buffer_level() - l)
                    if quality == len(manifest.bitrates) - 1:
                        delay = 0
                    # delay = 0 ###########

        self.last_quality = quality
        return (quality, delay)

    def report_seek(self, where):
        global manifest
        # Compute the segment index corresponding to the new playback position.
        self.last_seek_index = math.floor(where / manifest.segment_time)
        # Seek Update Note:
        # Reset the last chosen quality to a safe starting point.
        # Doesn't affect the simluation result, due to the buffer level is cleaned up.
        # The quality_from_buffer() in get_quality_delay() will re-calculate the quality level and update the self.last_quality into 0.
        self.last_quality = self.get_first_quality()

    def check_abandon(self, progress, buffer_level):
        global manifest

        if self.abr_basic:
            return None

        remain = progress.size - progress.downloaded
        if progress.downloaded <= 0 or remain <= 0:
            return None

        abandon_to = None
        score = (
            self.Vp * (self.gp + self.utilities[progress.quality]) - buffer_level
        ) / remain
        if score < 0:
            return  # TODO: check

        for q in range(progress.quality):
            other_size = (
                progress.size
                * manifest.bitrates[q]
                / manifest.bitrates[progress.quality]
            )
            other_score = (
                self.Vp * (self.gp + self.utilities[q]) - buffer_level
            ) / other_size
            if other_size < remain and other_score > score:
                # check size: see comment in BolaEnh.check_abandon()
                score = other_score
                abandon_to = q

        if abandon_to != None:
            self.last_quality = abandon_to

        return abandon_to


abr_list["bola"] = Bola


class BolaEnh(Abr):

    minimum_buffer = 10000
    minimum_buffer_per_level = 2000
    low_buffer_safety_factor = 0.5
    low_buffer_safety_factor_init = 0.9

    class State(Enum):
        STARTUP = 1
        STEADY = 2

    def __init__(self, config):
        global verbose
        global manifest

        config_buffer_size = config["buffer_size"]
        self.abr_osc = config["abr_osc"]
        self.no_ibr = config["no_ibr"]

        utility_offset = 1 - math.log(manifest.bitrates[0])  # so utilities[0] = 1
        self.utilities = [math.log(b) + utility_offset for b in manifest.bitrates]

        if self.no_ibr:
            self.gp = config["gp"] - 1  # to match BOLA Basic
            buffer = config["buffer_size"]
            self.Vp = (buffer - manifest.segment_time) / (self.utilities[-1] + self.gp)
        else:
            buffer = BolaEnh.minimum_buffer
            buffer += BolaEnh.minimum_buffer_per_level * len(manifest.bitrates)
            buffer = max(buffer, config_buffer_size)
            self.gp = (self.utilities[-1] - 1) / (buffer / BolaEnh.minimum_buffer - 1)
            self.Vp = BolaEnh.minimum_buffer / self.gp
            # equivalently:
            # self.Vp = (buffer - BolaEnh.minimum_buffer) / (math.log(manifest.bitrates[-1] / manifest.bitrates[0]))
            # self.gp = BolaEnh.minimum_buffer / self.Vp

        self.state = BolaEnh.State.STARTUP
        self.placeholder = 0
        self.last_quality = 0

        if verbose:
            for q in range(len(manifest.bitrates)):
                b = manifest.bitrates[q]
                u = self.utilities[q]
                l = self.Vp * (self.gp + u)
                if q == 0:
                    print("%d %d" % (q, l))
                else:
                    qq = q - 1
                    bb = manifest.bitrates[qq]
                    uu = self.utilities[qq]
                    ll = self.Vp * (self.gp + (b * uu - bb * u) / (b - bb))
                    print("%d %d    <- %d %d" % (q, l, qq, ll))

    def quality_from_buffer(self, level):
        if level == None:
            level = get_buffer_level()
        quality = 0
        score = None
        for q in range(len(manifest.bitrates)):
            s = (self.Vp * (self.utilities[q] + self.gp) - level) / manifest.bitrates[q]
            if score == None or s > score:
                quality = q
                score = s
        return quality

    def quality_from_buffer_placeholder(self):
        return self.quality_from_buffer(get_buffer_level() + self.placeholder)

    def min_buffer_for_quality(self, quality):
        global manifest

        bitrate = manifest.bitrates[quality]
        utility = self.utilities[quality]

        level = 0
        for q in range(quality):
            # for each bitrates[q] less than bitrates[quality],
            # BOLA should prefer bitrates[quality]
            # (unless bitrates[q] has higher utility)
            if self.utilities[q] < self.utilities[quality]:
                b = manifest.bitrates[q]
                u = self.utilities[q]
                l = self.Vp * (self.gp + (bitrate * u - b * utility) / (bitrate - b))
                level = max(level, l)
        return level

    def max_buffer_for_quality(self, quality):
        return self.Vp * (self.utilities[quality] + self.gp)

    def get_quality_delay(self, segment_index):
        global buffer_contents
        global buffer_fcc
        global throughput

        buffer_level = get_buffer_level()

        if self.state == BolaEnh.State.STARTUP:
            if throughput == None:
                return (self.last_quality, 0)
            self.state = BolaEnh.State.STEADY
            self.ibr_safety = BolaEnh.low_buffer_safety_factor_init
            quality = self.quality_from_throughput(throughput)
            self.placeholder = self.min_buffer_for_quality(quality) - buffer_level
            self.placeholder = max(0, self.placeholder)
            return (quality, 0)

        quality = self.quality_from_buffer_placeholder()
        quality_t = self.quality_from_throughput(throughput)
        if quality > self.last_quality and quality > quality_t:
            quality = max(self.last_quality, quality_t)
            if not self.abr_osc:
                quality += 1

        max_level = self.max_buffer_for_quality(quality)

        if quality > 0:
            q = quality
            b = manifest.bitrates[q]
            u = self.utilities[q]
            qq = q - 1
            bb = manifest.bitrates[qq]
            uu = self.utilities[qq]
            # max_level = self.Vp * (self.gp + (b * uu - bb * u) / (b - bb))

        delay = buffer_level + self.placeholder - max_level
        if delay > 0:
            if delay <= self.placeholder:
                self.placeholder -= delay
                delay = 0
            else:
                delay -= self.placeholder
                self.placeholder = 0
        else:
            delay = 0

        if quality == len(manifest.bitrates) - 1:
            delay = 0

        # insufficient buffer rule
        if not self.no_ibr:
            safe_size = self.ibr_safety * (buffer_level - latency) * throughput
            self.ibr_safety *= BolaEnh.low_buffer_safety_factor_init
            self.ibr_safety = max(self.ibr_safety, BolaEnh.low_buffer_safety_factor)
            for q in range(quality):
                if manifest.bitrates[q + 1] * manifest.segment_time > safe_size:
                    # print('InsufficientBufferRule %d -> %d' % (quality, q))
                    quality = q
                    delay = 0
                    min_level = self.min_buffer_for_quality(quality)
                    max_placeholder = max(0, min_level - buffer_level)
                    self.placeholder = min(max_placeholder, self.placeholder)
                    break

        # print('ph=%d' % self.placeholder)
        return (quality, delay)

    def report_delay(self, delay):
        self.placeholder += delay

    def report_download(self, metrics, is_replacment):
        global manifest
        self.last_quality = metrics.quality
        level = get_buffer_level()

        if metrics.abandon_to_quality == None:

            if is_replacment:
                self.placeholder += manifest.segment_time
            else:
                # make sure placeholder is not too large relative to download
                level_was = level + metrics.time
                max_effective_level = self.max_buffer_for_quality(metrics.quality)
                max_placeholder = max(0, max_effective_level - level_was)
                self.placeholder = min(self.placeholder, max_placeholder)

                # make sure placeholder not too small (can happen when decision not taken by BOLA)
                if level > 0:
                    # we don't want to inflate placeholder when rebuffering
                    min_effective_level = self.min_buffer_for_quality(metrics.quality)
                    # min_effective_level < max_effective_level
                    min_placeholder = min_effective_level - level_was
                    self.placeholder = max(self.placeholder, min_placeholder)
                # else: no need to deflate placeholder for 0 buffer - empty buffer handled

        elif not is_replacment:  # do nothing if we abandoned a replacement
            # abandonment indicates something went wrong - lower placeholder to conservative level
            if metrics.abandon_to_quality > 0:
                want_level = self.min_buffer_for_quality(metrics.abandon_to_quality)
            else:
                want_level = BolaEnh.minimum_buffer
            max_placeholder = max(0, want_level - level)
            self.placeholder = min(self.placeholder, max_placeholder)

    def report_seek(self, where):
        self.state = BolaEnh.State.STARTUP
        # Clear any accumulated placeholder since the buffer state is effectively reset.
        self.placeholder = 0
        # Reset the last chosen quality to a safe starting quality.
        self.last_quality = self.get_first_quality()
        # Record the new playback segment index (assuming segment_time is in ms).
        self.last_seek_index = math.floor(where / manifest.segment_time)

    def check_abandon(self, progress, buffer_level):
        global manifest

        remain = progress.size - progress.downloaded
        if progress.downloaded <= 0 or remain <= 0:
            return None

        # abandon leads to new latency, so estimate what current status is after latency
        bl = max(0, buffer_level + self.placeholder - progress.time_to_first_bit)
        tp = progress.downloaded / (progress.time - progress.time_to_first_bit)
        sz = remain - progress.time_to_first_bit * tp
        if sz <= 0:
            return None

        abandon_to = None
        score = (self.Vp * (self.gp + self.utilities[progress.quality]) - bl) / sz

        for q in range(progress.quality):
            other_size = (
                progress.size
                * manifest.bitrates[q]
                / manifest.bitrates[progress.quality]
            )
            other_score = (self.Vp * (self.gp + self.utilities[q]) - bl) / other_size
            if other_size < sz and other_score > score:
                # check size:
                # if remaining bits in this download are less than new download, why switch?
                # IMPORTANT: this check is NOT subsumed in score check:
                # if sz < other_size and bl is large, original score suffers larger penalty
                # print('abandon bl=%d=%d+%d-%d %d->%d score:%d->%s' % (progress.quality, bl, buffer_level, self.placeholder, progress.time_to_first_bit, q, score, other_score))
                score = other_score
                abandon_to = q

        return abandon_to


abr_list["bolae"] = BolaEnh
abr_default = "bolae"


class ThroughputRule(Abr):

    safety_factor = 0.9
    low_buffer_safety_factor = 0.5
    low_buffer_safety_factor_init = 0.9
    abandon_multiplier = 1.8
    abandon_grace_time = 500

    def __init__(self, config):
        self.ibr_safety = ThroughputRule.low_buffer_safety_factor_init
        self.no_ibr = config["no_ibr"]

    def get_quality_delay(self, segment_index):
        global manifest

        quality = self.quality_from_throughput(
            throughput * ThroughputRule.safety_factor
        )

        if not self.no_ibr:
            # insufficient buffer rule
            safe_size = self.ibr_safety * (get_buffer_level() - latency) * throughput
            self.ibr_safety *= ThroughputRule.low_buffer_safety_factor_init
            self.ibr_safety = max(
                self.ibr_safety, ThroughputRule.low_buffer_safety_factor
            )
            for q in range(quality):
                if manifest.bitrates[q + 1] * manifest.segment_time > safe_size:
                    quality = q
                    break

        return (quality, 0)

    def check_abandon(self, progress, buffer_level):
        global manifest

        quality = None  # no abandon

        dl_time = progress.time - progress.time_to_first_bit
        if progress.time >= ThroughputRule.abandon_grace_time and dl_time > 0:
            tput = progress.downloaded / dl_time
            size_left = progress.size - progress.downloaded
            estimate_time_left = size_left / tput
            if (
                progress.time + estimate_time_left
                > ThroughputRule.abandon_multiplier * manifest.segment_time
            ):
                quality = self.quality_from_throughput(
                    tput * ThroughputRule.safety_factor
                )
                estimate_size = (
                    progress.size
                    * manifest.bitrates[quality]
                    / manifest.bitrates[progress.quality]
                )
                if quality >= progress.quality or estimate_size >= size_left:
                    quality = None

        return quality
    
    def report_seek(self, where):
        # Reset internal throughput-specific state.
        self.ibr_safety = ThroughputRule.low_buffer_safety_factor_init


abr_list["throughput"] = ThroughputRule


class Dynamic(Abr):

    low_buffer_threshold = 10000

    def __init__(self, config):
        global manifest
        global is_bola

        self.bola = Bola(config)
        self.tput = ThroughputRule(config)

        is_bola = False
        # self.is_bola = False

    def get_quality_delay(self, segment_index):
        global is_bola
        level = get_buffer_level()

        b = self.bola.get_quality_delay(segment_index)
        t = self.tput.get_quality_delay(segment_index)

        if is_bola:
            if level < Dynamic.low_buffer_threshold and b[0] < t[0]:
                is_bola = False
        else:
            if level > Dynamic.low_buffer_threshold and b[0] >= t[0]:
                is_bola = True

        return b if is_bola else t

    def get_first_quality(self):
        if is_bola:
            return self.bola.get_first_quality()
        else:
            return self.tput.get_first_quality()

    def report_delay(self, delay):
        self.bola.report_delay(delay)
        self.tput.report_delay(delay)

    def report_download(self, metrics, is_replacment):
        self.bola.report_download(metrics, is_replacment)
        self.tput.report_download(metrics, is_replacment)
        if is_replacment:
            is_bola = False

    def check_abandon(self, progress, buffer_level):
        if False and is_bola:
            return self.bola.check_abandon(progress, buffer_level)
        else:
            return self.tput.check_abandon(progress, buffer_level)
        
    def report_seek(self, where):
        # Delegate the seek notification to both underlying strategies.
        self.bola.report_seek(where)
        self.tput.report_seek(where)   


abr_list["dynamic"] = Dynamic


class DynamicDash(Abr):

    def __init__(self, config):
        global manifest

        self.bola = BolaEnh(config)
        self.tput = ThroughputRule(config)

        buffer_size = config["buffer_size"]
        self.low_threshold = (buffer_size - manifest.segment_time) / 2
        self.high_threshold = (buffer_size - manifest.segment_time) - 100
        self.low_threshold = 5000
        self.high_threshold = 10000
        ######################## TODO
        self.is_bola = False

    def get_quality_delay(self, segment_index):
        level = get_buffer_level()
        if self.is_bola and level < self.low_threshold:
            self.is_bola = False
        elif not self.is_bola and level > self.high_threshold:
            self.is_bola = True

        if self.is_bola:
            return self.bola.get_quality_delay(segment_index)
        else:
            return self.tput.get_quality_delay(segment_index)

    def get_first_quality(self):
        if self.is_bola:
            return self.bola.get_first_quality()
        else:
            return self.tput.get_first_quality()

    def report_delay(self, delay):
        self.bola.report_delay(delay)
        self.tput.report_delay(delay)

    def report_download(self, metrics, is_replacment):
        self.bola.report_download(metrics, is_replacment)
        self.tput.report_download(metrics, is_replacment)

    def check_abandon(self, progress, buffer_level):
        if self.is_bola:
            return self.bola.check_abandon(progress, buffer_level)
        else:
            return self.tput.check_abandon(progress, buffer_level)
        
    def report_seek(self, where):
        # Notify both strategies of the seek event.
        self.bola.report_seek(where)
        self.tput.report_seek(where)


abr_list["dynamicdash"] = DynamicDash


class Bba(Abr):

    def __init__(self, config):
        pass

    def get_quality_delay(self, segment_index):
        raise NotImplementedError

    def report_delay(self, delay):
        pass

    def report_download(self, metrics, is_replacment):
        pass

    def report_seek(self, where):
        pass


abr_list["bba"] = Bba


class NoReplace(Replacement):
    pass


# TODO: different classes instead of strategy
class Replace(Replacement):

    def __init__(self, strategy):
        self.strategy = strategy
        self.replacing = None
        # self.replacing is either None or -ve index to buffer_contents

    def check_replace(self, quality):
        global manifest
        global buffer_contents
        global buffer_fcc

        self.replacing = None

        if self.strategy == 0:

            skip = math.ceil(1.5 + buffer_fcc / manifest.segment_time)
            # print('skip = %d  fcc = %d' % (skip, buffer_fcc))
            for i in range(skip, len(buffer_contents)):
                (_seg_idx, q_i) = buffer_contents[i]
                if q_i < quality:
                    self.replacing = i - len(buffer_contents)
                    break

            # if self.replacing == None:
            #    print('no repl:  0/%d' % len(buffer_contents))
            # else:
            #    print('replace: %d/%d' % (self.replacing, len(buffer_contents)))

        elif self.strategy == 1:

            skip = math.ceil(1.5 + buffer_fcc / manifest.segment_time)
            # print('skip = %d  fcc = %d' % (skip, buffer_fcc))
            for i in range(len(buffer_contents) - 1, skip - 1, -1):
                (_seg_idx, q_i) = buffer_contents[i]
                if q_i < quality:
                    self.replacing = i - len(buffer_contents)
                    break

            # if self.replacing == None:
            #    print('no repl:  0/%d' % len(buffer_contents))
            # else:
            #    print('replace: %d/%d' % (self.replacing, len(buffer_contents)))

        else:
            pass

        return self.replacing

    def check_abandon(self, progress, buffer_level):
        global manifest
        global buffer_contents
        global buffer_fcc

        if self.replacing == None:
            return None
        if buffer_level + manifest.segment_time * self.replacing <= 0:
            return -1
        return None


class AbrInput(Abr):

    def __init__(self, path, config):
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.abr_module = SourceFileLoader(self.name, path).load_module()
        self.abr_class = getattr(self.abr_module, self.name)
        self.abr_class.session = session_info
        self.abr = self.abr_class(config)

    def get_quality_delay(self, segment_index):
        return self.abr.get_quality_delay(segment_index)

    def get_first_quality(self):
        return self.abr.get_first_quality()

    def report_delay(self, delay):
        self.abr.report_delay(delay)

    def report_download(self, metrics, is_replacment):
        self.abr.report_download(metrics, is_replacment)

    def report_seek(self, where):
        self.abr.report_seek(where)

    def check_abandon(self, progress, buffer_level):
        return self.abr.check_abandon(progress, buffer_level)


class ReplacementInput(Replacement):

    def __init__(self, path):
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.replacement_module = SourceFileLoader(self.name, path).load_module()
        self.replacement_class = getattr(self.replacement_module, self.name)
        self.replacement_class.session = session_info
        self.replacement = self.replacement_class()

    def check_replace(self, quality):
        return self.replacement.check_replace(quality)

    def check_abandon(self, progress, buffer_level):
        return self.replacement.check_abandon(progress, buffer_level)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Simulate an ABR session.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-n",
        "--network",
        metavar="NETWORK",
        default="network.json",
        help="Specify the .json file describing the network trace.",
    )
    parser.add_argument(
        "-nm",
        "--network-multiplier",
        metavar="MULTIPLIER",
        type=float,
        default=1,
        help="Multiply throughput by MULTIPLIER.",
    )
    parser.add_argument(
        "-m",
        "--movie",
        metavar="MOVIE",
        default="movie.json",
        help="Specify the .json file describing the movie chunks.",
    )
    parser.add_argument(
        "-ml",
        "--movie-length",
        metavar="LEN",
        type=float,
        default=None,
        help="Specify the movie length in seconds (use MOVIE length if None).",
    )
    parser.add_argument(
        "-a",
        "--abr",
        metavar="ABR",
        choices=abr_list.keys(),
        default=abr_default,
        help="Choose ABR algorithm from predefined list (%s), or specify .py module to import."
        % ", ".join(abr_list.keys()),
    )
    parser.add_argument(
        "-ab",
        "--abr-basic",
        action="store_true",
        help="Set ABR to BASIC (ABR strategy dependant).",
    )
    parser.add_argument(
        "-ao",
        "--abr-osc",
        action="store_true",
        help="Set ABR to minimize oscillations.",
    )
    parser.add_argument(
        "-gp",
        "--gamma-p",
        metavar="GAMMAP",
        type=float,
        default=5,
        help="Specify the (gamma p) product in seconds.",
    )
    parser.add_argument(
        "-noibr",
        "--no-insufficient-buffer-rule",
        action="store_true",
        help="Disable Insufficient Buffer Rule.",
    )
    parser.add_argument(
        "-ma",
        "--moving-average",
        metavar="AVERAGE",
        choices=average_list.keys(),
        default=average_default,
        help="Specify the moving average strategy (%s)."
        % ", ".join(average_list.keys()),
    )
    parser.add_argument(
        "-ws",
        "--window-size",
        metavar="WINDOW_SIZE",
        nargs="+",
        type=int,
        default=[3],
        help="Specify sliding window size.",
    )
    parser.add_argument(
        "-hl",
        "--half-life",
        metavar="HALF_LIFE",
        nargs="+",
        type=float,
        default=[3, 8],
        help="Specify EWMA half life.",
    )
    # Our seek will need to read from the config file to support multiple seek strategies.
    parser.add_argument(
        "-s",
        "--seek",
        nargs=2,
        metavar=("WHEN", "SEEK"),
        type=float,
        default=None,
        help="Specify when to seek in seconds and where to seek in seconds.",
    )
    choices = ["none", "left", "right"]
    parser.add_argument(
        "-r",
        "--replace",
        metavar="REPLACEMENT",
        # choices = choices,
        default="none",
        help="Set replacement strategy from predefined list (%s), or specify .py module to import."
        % ", ".join(choices),
    )
    parser.add_argument(
        "-b",
        "--max-buffer",
        metavar="MAXBUFFER",
        type=float,
        default=25,
        help="Specify the maximum buffer size in seconds.",
    )
    parser.add_argument(
        "-noa", "--no-abandon", action="store_true", help="Disable abandonment."
    )

    parser.add_argument(
        "-rmp",
        "--rampup-threshold",
        metavar="THRESHOLD",
        type=int,
        default=None,
        help="Specify at what quality index we are ramped up (None matches network).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Run in verbose mode."
    )
    parser.add_argument("-g", "--graph", action="store_true", help="Run in graph mode.")
    parser.add_argument(
    "-sc",
    "--seek-config",
    metavar="SEEK_CONFIG",
    help="Specify the JSON file containing multiple seek events."
)
    args = parser.parse_args()

    verbose = args.verbose
    graph = args.graph

    buffer_contents = []
    buffer_fcc = 0
    pending_quality_up = []
    reaction_metrics = []

    rebuffer_event_count = 0
    rebuffer_time = 0
    segment_rebuffer_time = 0
    played_utility = 0
    played_bitrate = 0
    total_play_time = 0
    total_bitrate_change = 0
    total_log_bitrate_change = 0
    total_reaction_time = 0
    last_played = None

    overestimate_count = 0
    overestimate_average = 0
    goodestimate_count = 0
    goodestimate_average = 0
    estimate_average = 0

    rampup_origin = 0
    rampup_time = None
    rampup_threshold = args.rampup_threshold

    max_buffer_size = args.max_buffer * 1000

    manifest = load_json(args.movie)
    bitrates = manifest["bitrates_kbps"]

    utility_offset = 0 - math.log(bitrates[0])
    utilities = [math.log(b) + utility_offset for b in bitrates]
    # If a seek configuration file is provided, load it.
    seek_events = []
    if args.seek_config:
        with open(args.seek_config) as f:
            seek_config = json.load(f)
        # Expecting a key "seeks" which is a list of { "seek_when": <seconds>, "seek_to": <seconds> }
        if "seeks" in seek_config:
            # Global list of pending seeks, sorted by seek_when
            seek_events = sorted(seek_config["seeks"], key=lambda x: x["seek_when"])

    if args.movie_length != None:
        l1 = len(manifest["segment_sizes_bits"])
        l2 = math.ceil(args.movie_length * 1000 / manifest["segment_duration_ms"])
        manifest["segment_sizes_bits"] *= math.ceil(l2 / l1)
        manifest["segment_sizes_bits"] = manifest["segment_sizes_bits"][0:l2]
    manifest = ManifestInfo(
        segment_time=manifest["segment_duration_ms"],
        bitrates=bitrates,
        utilities=utilities,
        segments=manifest["segment_sizes_bits"],
    )
    SessionInfo.manifest = manifest
    is_bola = False

    network_trace = load_json(args.network)
    network_trace = [
        NetworkPeriod(
            time=p["duration_ms"],
            bandwidth=p["bandwidth_kbps"] * args.network_multiplier,
            latency=p["latency_ms"],
        )
        for p in network_trace
    ]

    # default max buffer size is 25 seconds
    buffer_size = args.max_buffer * 1000
    gamma_p = args.gamma_p

    config = {
        "buffer_size": buffer_size,
        "gp": gamma_p,
        "abr_osc": args.abr_osc,
        "abr_basic": args.abr_basic,
        "no_ibr": args.no_insufficient_buffer_rule,
    }

    if args.abr[-3:] == ".py":
        abr = AbrInput(args.abr, config)
    else:
        abr_list[args.abr].use_abr_o = args.abr_osc
        abr_list[args.abr].use_abr_u = not args.abr_osc
        abr = abr_list[args.abr](config)
    network = NetworkModel(network_trace)
    if args.replace[-3:] == ".py":
        replacer = ReplacementInput(args.replace)
    if args.replace == "left":
        replacer = Replace(0)
    elif args.replace == "right":
        replacer = Replace(1)
    else:
        replacer = NoReplace()

    config = {"window_size": args.window_size, "half_life": args.half_life}
    throughput_history = average_list[args.moving_average](config)

    # download first segment
    quality = abr.get_first_quality()
    size = manifest.segments[0][quality]
    download_metric = network.download(size, 0, quality, 0)
    download_time = download_metric.time - download_metric.time_to_first_bit
    startup_time = download_time
    buffer_contents.append((0, download_metric.quality))
    t = download_metric.size / download_time
    l = download_metric.time_to_first_bit
    throughput_history.push(download_time, t, l)
    total_play_time += download_metric.time

    if verbose:
        print(
            "[%d-%d]  %d: quality=%d download_size=%d/%d download_time=%d=%d+%d buffer_level=0->0->%d"
            % (
                0,
                round(download_metric.time),
                0,
                download_metric.quality,
                download_metric.downloaded,
                download_metric.size,
                download_metric.time,
                download_metric.time_to_first_bit,
                download_metric.time - download_metric.time_to_first_bit,
                get_buffer_level(),
            )
        )
    if graph:
        print(
            "%d time=%d network_bandwidth=%d network_latency=%d quality=%d bitrate=%d download_size=%d download_time=%d buffer_level=%d rebuffer_time=%d is_bola=%s"
            % (
                0,
                0,
                network.trace[network.index].bandwidth,
                network.trace[network.index].latency,
                download_metric.quality,
                manifest.bitrates[download_metric.quality],
                0,
                0,
                0,
                0,
                is_bola,
            )
        )
        print(
            "%d time=%d network_bandwidth=%d network_latency=%d quality=%d bitrate=%d download_size=%d download_time=%d buffer_level=%d rebuffer_time=%d is_bola=%s"
            % (
                0,
                download_metric.time,
                network.trace[network.index].bandwidth,
                network.trace[network.index].latency,
                download_metric.quality,
                manifest.bitrates[download_metric.quality],
                download_metric.downloaded,
                download_metric.time,
                get_buffer_level(),
                0,
                is_bola,
            )
        )

    # download rest of segments
    next_segment = 1
    abandoned_to_quality = None
    while next_segment < len(manifest.segments):
        process_download_loop()

    playout_buffer()

    if verbose:
        # multiply by to_time_average to get per/chunk average
        to_time_average = 1 / (total_play_time / manifest.segment_time)
        count = len(manifest.segments)
        time = count * manifest.segment_time + rebuffer_time + startup_time
        print("buffer size: %d" % buffer_size)
        print("total played utility: %f" % played_utility)
        print("time average played utility: %f" % (played_utility * to_time_average))
        print("total played bitrate: %f" % played_bitrate)
        print("time average played bitrate: %f" % (played_bitrate * to_time_average))
        print("total play time: %f" % (total_play_time / 1000))
        print("total play time chunks: %f" % (total_play_time / manifest.segment_time))
        print("total rebuffer: %f" % (rebuffer_time / 1000))
        print("rebuffer ratio: %f" % (rebuffer_time / total_play_time))
        print("time average rebuffer: %f" % (rebuffer_time / 1000 * to_time_average))
        print("total rebuffer events: %f" % rebuffer_event_count)
        print(
            "time average rebuffer events: %f"
            % (rebuffer_event_count * to_time_average)
        )
        print("total bitrate change: %f" % total_bitrate_change)
        print(
            "time average bitrate change: %f" % (total_bitrate_change * to_time_average)
        )
        print("total log bitrate change: %f" % total_log_bitrate_change)
        print(
            "time average log bitrate change: %f"
            % (total_log_bitrate_change * to_time_average)
        )
        print(
            "time average score: %f"
            % (
                to_time_average
                * (
                    played_utility
                    - args.gamma_p * rebuffer_time / manifest.segment_time
                )
            )
        )
        if overestimate_count == 0:
            print("over estimate count: 0")
            print("over estimate: 0")
        else:
            print("over estimate count: %d" % overestimate_count)
            print("over estimate: %f" % overestimate_average)
        if goodestimate_count == 0:
            print("leq estimate count: 0")
            print("leq estimate: 0")
        else:
            print("leq estimate count: %d" % goodestimate_count)
            print("leq estimate: %f" % goodestimate_average)
        print("estimate: %f" % estimate_average)
        if rampup_time == None:
            print(
                "rampup time: %f"
                % (len(manifest.segments) * manifest.segment_time / 1000)
            )
        else:
            print("rampup time: %f" % (rampup_time / 1000))
        print("total reaction time: %f" % (total_reaction_time / 1000))
        print("network total time: %f" % (network_total_time/1000))
