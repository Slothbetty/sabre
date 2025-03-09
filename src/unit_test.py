import unittest
import math
import tempfile
import os
import json
import sys
import shutil
import sabre  # assume your simulation code is in sabre.py

# A dummy ABR class to capture report_seek calls.
class DummyAbr:
    def __init__(self):
        self.last_seek = None

    def report_seek(self, where):
        self.last_seek = where

class TestMultipleSeekBehavior(unittest.TestCase):
    def setUp(self):
        # Initialize globals that the simulation code uses.
        sabre.verbose = False
        sabre.played_utility = 0
        sabre.played_bitrate = 0
        sabre.total_play_time = 0
        sabre.total_bitrate_change = 0
        sabre.total_log_bitrate_change = 0
        sabre.last_played = None
        sabre.rebuffer_event_count = 0
        sabre.rebuffer_time = 0
        sabre.rampup_origin = 0
        sabre.rampup_time = None
        sabre.rampup_threshold = None
        sabre.sustainable_quality = 0
        sabre.segment_rebuffer_time = 0
        sabre.pending_quality_up = []
        
        # Initialize globals used by delay processing.
        sabre.max_buffer_size = 25000  # for example, 25 sec * 1000 ms/sec
        sabre.total_reaction_time = 0

        # Reset other globals.
        sabre.next_segment = 0
        sabre.buffer_contents = []
        sabre.buffer_fcc = 0
        sabre.seek_events = []
        
        # Reset network_total_time (used by the network model).
        sabre.network_total_time = 0

        # Create a dummy manifest with 10 segments.
        # For simplicity, each segment lasts 1000 ms.
        sabre.manifest = sabre.ManifestInfo(
            segment_time=1000,            # 1000 ms per segment
            bitrates=[100, 200],          # two quality levels (dummy bitrates)
            utilities=[0, math.log(2)],   # utilities computed relative to the first level
            segments=[[100, 200]] * 10    # dummy segment sizes for each quality level per segment
        )

        # Replace the global ABR object with our dummy to record seek notifications.
        sabre.abr = DummyAbr()

    def test_single_seek(self):
        """
        Test a single seek event:
          - When total_play_time (in ms) exceeds the seek threshold (seek_when in seconds),
            handle_seek() should update next_segment, clear the buffer, and call abr.report_seek().
          - For example, if total_play_time is 1500 ms and a seek event is scheduled at 1.0 sec
            with a target of 5.0 sec, then next_segment should become floor(5000/1000)=5.
        """
        sabre.total_play_time = 1500  
        sabre.seek_events = [{"seek_when": 1.0, "seek_to": 5.0}]
        
        sabre.handle_seek()
        
        # Verify that next_segment is updated correctly (5 = floor(5000/1000)).
        self.assertEqual(sabre.next_segment, 5)
        # The playback buffer should be cleared.
        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)
        # The ABR object should have been notified with a seek time of 5000 ms.
        self.assertEqual(sabre.abr.last_seek, 5000)

    def test_multiple_seek(self):
        """
        Test multiple seek events:
          - With multiple seek events scheduled (e.g., one at 1.0 sec and another at 3.0 sec)
            and total_play_time set high enough, all pending seeks should be processed.
          - The final next_segment should correspond to the last seek's target.
        """
        sabre.total_play_time = 3500  # 3.5 sec
        sabre.seek_events = [
            {"seek_when": 1.0, "seek_to": 4.0},
            {"seek_when": 3.0, "seek_to": 7.0}
        ]
        
        sabre.handle_seek()
        
        # The final seek should set next_segment = floor(7000/1000) = 7.
        self.assertEqual(sabre.next_segment, 7)
        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)
        self.assertEqual(sabre.abr.last_seek, 7000)
        self.assertEqual(sabre.total_play_time, 3500)

    def test_total_play_time_after_seek(self):
        """
        Test that after a seek, total_play_time includes only the time played before the seek 
        plus the durations of segments played after the seek, excluding any skipped segments.

        Scenario:
          - Set total_play_time to 3000 ms (time played before the seek).
          - Schedule a seek event that triggers when playback reaches 2.0 sec and seeks to 8.0 sec.
          - Process the seek event via handle_seek(), which clears the buffer.
          - Simulate playing one segment (1000 ms) after the seek by adding a segment to the buffer
            and calling playout_buffer().
          - Verify that total_play_time becomes 3000 ms + 1000 ms = 4000 ms.
        """
        initial_time = 3000
        sabre.total_play_time = initial_time

        sabre.seek_events = [{"seek_when": 2.0, "seek_to": 8.0}]
        sabre.handle_seek()

        # Simulate that one segment (1000 ms) is downloaded after the seek.
        sabre.buffer_contents = [0]  # dummy quality value for one segment
        sabre.buffer_fcc = 0

        expected_time_after_segment = initial_time + sabre.manifest.segment_time  # 3000 + 1000 = 4000

        sabre.playout_buffer()

        self.assertEqual(sabre.total_play_time, expected_time_after_segment)

    def test_total_play_time_after_seek_with_delay(self):
        """
        Test that after a seek event and a subsequent delay,
        total_play_time reflects the time before seek plus the delay plus the duration
        of the segment played after the seek.

        Scenario:
          - Set total_play_time to 3000 ms (before the seek).
          - Schedule a seek event to trigger when playback reaches 2.0 sec (seek_to 8.0 sec).
          - Process the seek event via handle_seek().
          - Simulate a delay of 500 ms (e.g., due to rebuffering) by calling deplete_buffer(500).
            (Since the buffer is empty, this adds 500 ms to total_play_time.)
          - Simulate downloading one segment (1000 ms) after the delay.
          - Call playout_buffer() to play the segment.
          - The expected total_play_time becomes 3000 + 500 + 1000 = 4500 ms.
        """
        initial_time = 3000
        sabre.total_play_time = initial_time

        sabre.seek_events = [{"seek_when": 2.0, "seek_to": 8.0}]
        sabre.handle_seek()

        # Simulate a delay of 500 ms.
        sabre.deplete_buffer(500)  # since buffer is empty, this adds 500 ms to total_play_time

        # Now, simulate that one segment is downloaded after the delay.
        sabre.buffer_contents = [0]  # one segment available
        sabre.buffer_fcc = 0

        # Expected total play time: 3000 (initial) + 500 (delay) + 1000 (one segment) = 4500 ms.
        expected_total_time = initial_time + 500 + sabre.manifest.segment_time

        sabre.playout_buffer()

        self.assertEqual(sabre.total_play_time, expected_total_time)

    def test_total_play_time_with_multiple_seeks_and_delay(self):
        """
        Test that total_play_time accounts correctly for multiple seek events and a delay.
        
        Scenario:
          - Set initial total_play_time to 2500 ms (before any seek processing).
          - Schedule two seek events:
              * First at 1.5 sec (seek_to 5.0 sec → next_segment becomes floor(5000/1000)=5)
              * Second at 2.5 sec (seek_to 7.0 sec → next_segment becomes floor(7000/1000)=7)
          - Process seek events via handle_seek(). After this, next_segment should be 7 and the buffer is cleared.
          - Simulate a delay of 300 ms (e.g. due to rebuffering) by calling deplete_buffer(300).
          - Then simulate downloading one segment (of duration 1000 ms) by setting the buffer.
          - Call playout_buffer() to play out that segment.
          - The expected final total_play_time should be:
                initial (2500 ms) + delay (300 ms) + segment duration (1000 ms) = 3800 ms.
        """
        # Set initial play time before seeks.
        sabre.total_play_time = 2500  

        # Schedule two seek events.
        sabre.seek_events = [
            {"seek_when": 1.5, "seek_to": 5.0},  # triggers when playback >= 1500 ms
            {"seek_when": 2.5, "seek_to": 7.0}   # triggers when playback >= 2500 ms
        ]
        
        # Process all seek events.
        sabre.handle_seek()
        
        # At this point, next_segment should be set to floor(7000/1000) = 7,
        # and the buffer should have been cleared.
        self.assertEqual(sabre.next_segment, 7)
        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)
        
        # Now, simulate a delay of 300 ms (e.g., rebuffering delay) when the buffer is empty.
        sabre.deplete_buffer(300)  # Since buffer_contents is empty, this will add 300 ms.
        
        # Then, simulate that one segment is downloaded after the delay.
        sabre.buffer_contents = [0]  # dummy quality value for one segment
        sabre.buffer_fcc = 0
        
        # Expected additional play time from the segment is 1000 ms.
        expected_total_play_time = 2500 + 300 + sabre.manifest.segment_time  # 2500 + 300 + 1000 = 3800
        
        # Play out the newly downloaded segment.
        sabre.playout_buffer()
        
        self.assertEqual(sabre.total_play_time, expected_total_play_time)

    def test_total_network_time_multiple_seeks(self):
        """
        Test that total network time accumulates correctly in a simulation with multiple seek events.
        
        Scenario:
          - Reset network_total_time to 0.
          - Create a dummy network trace with a single period:
                duration = 1000 ms, bandwidth = 1000, latency = 100.
          - Set initial total_play_time to 3500 ms and schedule two seek events.
          - Process the seek events via handle_seek().
          - Instantiate a NetworkModel using the dummy network trace.
          - Simulate a delay of 300 ms by calling network.delay(300).
          - Simulate downloading one segment (using the first quality level) after the delay.
          - Verify that network_total_time has increased (i.e. is greater than the delay alone).
        """
        # Reset network_total_time.
        sabre.network_total_time = 0

        # Create a dummy network trace.
        dummy_trace = [sabre.NetworkPeriod(time=1000, bandwidth=1000, latency=100)]
        network = sabre.NetworkModel(dummy_trace)

        # Set initial play time and schedule seek events.
        sabre.total_play_time = 3500  # 3.5 sec
        sabre.seek_events = [
            {"seek_when": 1.0, "seek_to": 4.0},
            {"seek_when": 3.0, "seek_to": 7.0}
        ]
        sabre.handle_seek()
        # At this point, next_segment should have been updated; we ignore it here.

        # Simulate a delay of 300 ms.
        delay_time = network.delay(300)  # network.delay() will update network_total_time
        # Simulate downloading one segment.
        # For quality 0, use the dummy segment size from manifest.
        segment_size = sabre.manifest.segments[0][0]
        dp = network.download(segment_size, idx=0, quality=0, buffer_level=0, check_abandon=None)

        # Check that network_total_time has accumulated both delay and download times.
        total_network_time = sabre.network_total_time
        # The delay was 300 ms; the download should add additional time.
        self.assertGreater(total_network_time, 300,
                           "Total network time should exceed the delay time due to the download.")
        # Optionally, print the network total time for manual inspection.
        print("Total network time (ms):", total_network_time)

    def test_buffer_contents_cleared_with_multiple_seeks(self):
        """
        Test that when multiple seek events are processed,
        the playback buffer is cleared.
        
        Scenario:
        - Pre-populate the buffer with some dummy segments and a nonzero buffer_fcc.
        - Set total_play_time high enough to trigger two seek events.
        - After processing seeks via handle_seek(), verify that:
            * buffer_contents is empty,
            * buffer_fcc is reset to 0,
            * next_segment is updated to the target corresponding to the last seek,
            * and the ABR object is notified with the correct seek time.
        """
        # Pre-populate the buffer with dummy quality values.
        sabre.buffer_contents = [0, 1, 0, 1]
        sabre.buffer_fcc = 250  # e.g., 250 ms of partial consumption

        # Set total_play_time high enough to trigger both seek events.
        sabre.total_play_time = 4000  # 4000 ms = 4 sec

        # Schedule two seek events:
        #   - The first seeks to 5.0 sec (should update next_segment to floor(5000/1000)=5).
        #   - The second seeks to 7.0 sec (should update next_segment to floor(7000/1000)=7).
        sabre.seek_events = [
            {"seek_when": 1.0, "seek_to": 5.0},
            {"seek_when": 3.0, "seek_to": 7.0}
        ]
        
        # Process the seek events.
        sabre.handle_seek()
        
        # Verify that the buffer has been cleared.
        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)
        
        # Verify that next_segment corresponds to the last seek target:
        # For seek_to 7.0 sec with segment_time=1000 ms, next_segment should be floor(7000/1000)=7.
        expected_segment = 7  # since floor(7000/1000) = 7
        self.assertEqual(sabre.next_segment, expected_segment)
        
        # Verify that the dummy ABR's report_seek was called with 7000 ms.
        self.assertEqual(sabre.abr.last_seek, 7000)

    def test_rebuffer_time_with_multiple_seeks(self):
        """
        Test that rebuffer_time accumulates correctly when multiple seek events occur and
        subsequent rebuffer events are triggered due to an empty buffer.
        
        Scenario:
        - Set total_play_time to 3000 ms.
        - Schedule two seek events; these will be processed via handle_seek(),
            which clears the playback buffer.
        - After processing, simulate a rebuffer event by calling deplete_buffer(500) (i.e., 500 ms delay).
        - Then simulate another rebuffer event by calling deplete_buffer(300) (i.e., 300 ms delay).
        - Verify that:
            * rebuffer_time equals 500 + 300 = 800 ms,
            * rebuffer_event_count equals 2,
            * total_play_time increased by 800 ms.
        """
        # Set initial play time and schedule two seek events.
        sabre.total_play_time = 3000
        sabre.seek_events = [
            {"seek_when": 1.0, "seek_to": 5.0},
            {"seek_when": 2.0, "seek_to": 7.0}
        ]
        
        # Process the seek events, which should clear the buffer.
        sabre.handle_seek()
        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)
        
        # Simulate a rebuffer event: 500 ms delay.
        sabre.deplete_buffer(500)
        # Simulate another rebuffer event: 300 ms delay.
        sabre.deplete_buffer(300)
        
        # Expected accumulated rebuffer time and event count.
        expected_rebuffer_time = 500 + 300  # 800 ms
        expected_rebuffer_event_count = 2
        
        self.assertEqual(sabre.rebuffer_time, expected_rebuffer_time,
                        f"Expected rebuffer_time to be {expected_rebuffer_time} ms")
        self.assertEqual(sabre.rebuffer_event_count, expected_rebuffer_event_count,
                        f"Expected rebuffer_event_count to be {expected_rebuffer_event_count}")
        
        # Verify that total_play_time has increased by 800 ms.
        expected_total_play_time = 3000 + 800
        self.assertEqual(sabre.total_play_time, expected_total_play_time,
                        f"Expected total_play_time to be {expected_total_play_time} ms")



    

if __name__ == "__main__":
    unittest.main()
