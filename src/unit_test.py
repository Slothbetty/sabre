import unittest
import math
import sabre  # assume your simulation code is in sabre.py

# A dummy ABR class to capture report_seek calls.
class DummyAbr:
    def __init__(self):
        self.last_seek = None

    def report_seek(self, where):
        self.last_seek = where

class TestMultipleSeekBehavior(unittest.TestCase):
    def setUp(self):
        # Initialize simulation globals.
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
        sabre.max_buffer_size = 25000  # e.g., 25 sec * 1000 ms/sec
        sabre.total_reaction_time = 0

        # Reset other globals.
        sabre.next_segment = 0
        sabre.buffer_contents = []
        sabre.buffer_fcc = 0
        sabre.seek_events = []
        sabre.network_total_time = 0

        # Create a dummy manifest with 10 segments (each 1000 ms long).
        sabre.manifest = sabre.ManifestInfo(
            segment_time=1000,            # 1000 ms per segment
            bitrates=[100, 200],          # two quality levels
            utilities=[0, math.log(2)],   # dummy utilities
            segments=[[100, 200]] * 10    # dummy segment sizes
        )

        # Replace the global ABR object with our dummy to record seek notifications.
        sabre.abr = DummyAbr()

    def simulate_seek_and_playout(self, initial_time, seek_events, delay=0):
        """
        Helper to simulate:
         - starting from a given play time,
         - processing provided seek events,
         - applying a delay (if any),
         - downloading one segment, and then playing out the buffer.
         
        Returns the final total_play_time.
        """
        sabre.total_play_time = initial_time
        sabre.seek_events = seek_events
        sabre.handle_seek()
        if delay:
            sabre.deplete_buffer(delay)
        # Simulate that one segment is downloaded after delay.
        sabre.buffer_contents = [0]  # dummy quality value for one segment
        sabre.buffer_fcc = 0
        sabre.playout_buffer()
        return sabre.total_play_time

    def test_single_seek(self):
        """
        When total_play_time exceeds the seek threshold,
        handle_seek() should update next_segment, clear the buffer,
        and call abr.report_seek() with the correct seek time.
        """
        sabre.total_play_time = 1500  # ms
        sabre.seek_events = [{"seek_when": 1.0, "seek_to": 5.0}]
        sabre.handle_seek()

        # Verify next_segment is computed correctly.
        self.assertEqual(sabre.next_segment, 5)
        # The playback buffer should be cleared.
        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)
        # Verify ABR is notified (seek time in ms).
        self.assertEqual(sabre.abr.last_seek, 5000)

    def test_multiple_seek(self):
        """
        With multiple seek events and sufficient total_play_time,
        the final next_segment should correspond to the last processed seek.
        """
        sabre.total_play_time = 3500  # 3.5 sec
        sabre.seek_events = [
            {"seek_when": 1.0, "seek_to": 4.0},
            {"seek_when": 3.0, "seek_to": 7.0}
        ]
        sabre.handle_seek()

        self.assertEqual(sabre.next_segment, 7)
        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)
        self.assertEqual(sabre.abr.last_seek, 7000)

    def test_total_play_time_after_seek(self):
        """
        Verify that after processing a seek and playing one segment,
        total_play_time equals time before seek + segment duration.
        """
        initial_time = 3000  # ms
        sabre.total_play_time = initial_time
        sabre.seek_events = [{"seek_when": 2.0, "seek_to": 8.0}]
        sabre.handle_seek()

        # Simulate downloading one segment.
        sabre.buffer_contents = [0]
        sabre.buffer_fcc = 0

        expected_time = initial_time + sabre.manifest.segment_time  # 3000 + 1000 = 4000 ms
        sabre.playout_buffer()

        self.assertEqual(sabre.total_play_time, expected_time)

    def test_total_play_time_after_seek_with_delay(self):
        """
        After a seek event, a delay, and playing one segment,
        total_play_time should be the sum of the pre-seek time, the delay, and the segment duration.
        """
        initial_time = 3000  # ms
        sabre.total_play_time = initial_time
        sabre.seek_events = [{"seek_when": 2.0, "seek_to": 8.0}]
        sabre.handle_seek()

        # Simulate a delay of 500 ms (e.g., rebuffering).
        sabre.deplete_buffer(500)
        # Simulate downloading one segment.
        sabre.buffer_contents = [0]
        sabre.buffer_fcc = 0

        expected_time = initial_time + 500 + sabre.manifest.segment_time  # 3000 + 500 + 1000 = 4500 ms
        sabre.playout_buffer()

        self.assertEqual(sabre.total_play_time, expected_time)

    def test_total_play_time_with_multiple_seeks_and_delay(self):
        """
        Test two scenarios for multiple seeks with delay:
         1. When the second seek’s condition is not met, only the first seek is processed.
         2. When both seek conditions are met, the final next_segment reflects the second seek.
         
        In both cases, after a delay and playing one segment,
        total_play_time should be initial_time + delay + segment duration.
        """
        test_cases = [
            {
                "name": "Only first seek triggered",
                "initial_time": 2500,
                "seek_events": [
                    {"seek_when": 1.5, "seek_to": 5.0},  # triggers when play_time >= 1500 ms
                    {"seek_when": 4.0, "seek_to": 7.0}    # would trigger when play_time >= 4000 ms
                ],
                "expected_next_segment": 5,
            },
            {
                "name": "Both seeks triggered",
                "initial_time": 2500,
                "seek_events": [
                    {"seek_when": 1.5, "seek_to": 5.0},  # triggers when play_time >= 1500 ms
                    {"seek_when": 2.5, "seek_to": 7.0}    # triggers when play_time >= 2500 ms
                ],
                "expected_next_segment": 7,
            }
        ]
        delay = 300  # ms delay
        expected_total = 2500 + delay + sabre.manifest.segment_time  # 2500 + 300 + 1000 = 3800 ms

        for tc in test_cases:
            with self.subTest(tc["name"]):
                sabre.total_play_time = tc["initial_time"]
                sabre.seek_events = tc["seek_events"]
                sabre.handle_seek()
                self.assertEqual(sabre.next_segment, tc["expected_next_segment"])
                self.assertEqual(sabre.buffer_contents, [])
                self.assertEqual(sabre.buffer_fcc, 0)
                sabre.deplete_buffer(delay)
                sabre.buffer_contents = [0]
                sabre.buffer_fcc = 0
                sabre.playout_buffer()
                self.assertEqual(sabre.total_play_time, expected_total)

    def test_total_network_time_multiple_seeks(self):
        """
        Ensure that network_total_time accumulates both delay and download times
        in a scenario with multiple seek events.
        """
        sabre.network_total_time = 0

        # Create a dummy network trace with one period.
        dummy_trace = [sabre.NetworkPeriod(time=1000, bandwidth=1000, latency=100)]
        network = sabre.NetworkModel(dummy_trace)

        sabre.total_play_time = 3500  # ms
        sabre.seek_events = [
            {"seek_when": 1.0, "seek_to": 4.0},
            {"seek_when": 3.0, "seek_to": 7.0}
        ]
        sabre.handle_seek()

        # Simulate a network delay of 300 ms.
        network.delay(300)
        # Simulate downloading one segment (using the first quality level).
        segment_size = sabre.manifest.segments[0][0]
        network.download(segment_size, idx=0, quality=0, buffer_level=0, check_abandon=None)

        # Verify that network_total_time is greater than the delay alone.
        self.assertGreater(sabre.network_total_time, 300,
                           "Total network time should exceed the delay time due to the download.")
        print("Total network time (ms):", sabre.network_total_time)

    def test_buffer_contents_cleared_with_multiple_seeks(self):
        """
        Verify that processing multiple seek events clears the playback buffer,
        resets buffer_fcc, updates next_segment, and notifies the ABR.
        """
        # Pre-populate the buffer.
        sabre.buffer_contents = [0, 1, 0, 1]
        sabre.buffer_fcc = 250  # e.g., partial consumption in ms
        sabre.total_play_time = 4000  # ms

        sabre.seek_events = [
            {"seek_when": 1.0, "seek_to": 5.0},
            {"seek_when": 3.0, "seek_to": 7.0}
        ]
        sabre.handle_seek()

        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)
        # For seek_to 7.0 sec with segment_time=1000 ms, next_segment should be 7.
        self.assertEqual(sabre.next_segment, 7)
        self.assertEqual(sabre.abr.last_seek, 7000)

    def test_rebuffer_time_with_multiple_seeks(self):
        """
        After processing multiple seek events (which clear the buffer),
        simulate two rebuffer events and verify that:
         - rebuffer_time equals the sum of delays,
         - rebuffer_event_count is updated,
         - total_play_time increases by the total rebuffer time.
        """
        sabre.total_play_time = 3000  # ms
        sabre.seek_events = [
            {"seek_when": 1.0, "seek_to": 5.0},
            {"seek_when": 2.0, "seek_to": 7.0}
        ]
        sabre.handle_seek()
        self.assertEqual(sabre.buffer_contents, [])
        self.assertEqual(sabre.buffer_fcc, 0)

        # Simulate two rebuffer events.
        sabre.deplete_buffer(500)
        sabre.deplete_buffer(300)

        expected_rebuffer_time = 500 + 300  # 800 ms
        expected_event_count = 2
        expected_total_play_time = 3000 + expected_rebuffer_time

        self.assertEqual(sabre.rebuffer_time, expected_rebuffer_time,
                         f"Expected rebuffer_time to be {expected_rebuffer_time} ms")
        self.assertEqual(sabre.rebuffer_event_count, expected_event_count,
                         f"Expected rebuffer_event_count to be {expected_event_count}")
        self.assertEqual(sabre.total_play_time, expected_total_play_time,
                         f"Expected total_play_time to be {expected_total_play_time} ms")

if __name__ == "__main__":
    unittest.main()
