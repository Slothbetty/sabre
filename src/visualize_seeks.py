import math
import matplotlib.pyplot as plt
import sabre  # assume your simulation code is in sabre.py

def run_simulation_and_collect_data():
    """
    Run a simplified simulation with multiple seek events.
    Record total_play_time, buffer level, and the times when seek events occur.
    """
    # Initialize simulation globals.
    sabre.verbose = False
    sabre.total_play_time = 0
    sabre.buffer_contents = []
    sabre.buffer_fcc = 0
    sabre.rebuffer_time = 0             # Initialize rebuffer_time
    sabre.rebuffer_event_count = 0      # Initialize rebuffer_event_count
    sabre.seek_events = [
        {"seek_when": 1.0, "seek_to": 5.0},
        {"seek_when": 3.0, "seek_to": 7.0}
    ]
    
    # For visualization, install a dummy ABR to record seek notifications.
    sabre.abr = type("DummyAbr", (), {
        "last_seek": None, 
        "report_seek": lambda self, where: setattr(self, "last_seek", where)
    })()
    
    # Create a dummy manifest: 10 segments, each 1000 ms in duration.
    sabre.manifest = sabre.ManifestInfo(
        segment_time=1000,
        bitrates=[100, 200],
        utilities=[0, math.log(2)],
        segments=[[100, 200]] * 10
    )
    
    time_series = []       # Record total_play_time (ms)
    buffer_series = []     # Record computed buffer level (ms)
    seek_event_times = []  # Record times when seek events are processed

    # Helper: compute the current buffer level.
    def get_buffer_level():
        return sabre.manifest.segment_time * len(sabre.buffer_contents) - sabre.buffer_fcc

    # Record initial state.
    time_series.append(sabre.total_play_time)
    buffer_series.append(get_buffer_level())

    # --- Step 1: Download first segment (simulate startup) ---
    sabre.buffer_contents.append(0)  # dummy quality value
    sabre.total_play_time += sabre.manifest.segment_time
    time_series.append(sabre.total_play_time)
    buffer_series.append(get_buffer_level())

    # --- Step 2: Process a seek event ---
    # Set total_play_time high enough to trigger the seek events.
    sabre.total_play_time = 2500  
    sabre.handle_seek()  # This call should clear the buffer and update next_segment.
    seek_event_times.append(sabre.total_play_time)
    time_series.append(sabre.total_play_time)
    buffer_series.append(get_buffer_level())

    # --- Step 3: Simulate a rebuffering delay after seek ---
    sabre.deplete_buffer(500)  # Simulate 500 ms rebuffer delay (buffer empty -> delay is added)
    time_series.append(sabre.total_play_time)
    buffer_series.append(get_buffer_level())

    # --- Step 4: Download a new segment after delay ---
    sabre.buffer_contents.append(0)  # add a segment to the buffer
    sabre.total_play_time += sabre.manifest.segment_time
    time_series.append(sabre.total_play_time)
    buffer_series.append(get_buffer_level())

    # --- Step 5: Process another seek event (if any remain) ---
    sabre.total_play_time = 4000  # set play time so that another seek is triggered
    sabre.handle_seek()           # process any pending seeks
    if sabre.abr.last_seek is not None:
        seek_event_times.append(sabre.total_play_time)
    time_series.append(sabre.total_play_time)
    buffer_series.append(get_buffer_level())

    # --- Step 6: Final delay and segment download ---
    sabre.deplete_buffer(300)  # simulate a 300 ms delay (e.g. rebuffering)
    time_series.append(sabre.total_play_time)
    buffer_series.append(get_buffer_level())

    sabre.buffer_contents.append(0)  # download another segment
    sabre.total_play_time += sabre.manifest.segment_time
    time_series.append(sabre.total_play_time)
    buffer_series.append(get_buffer_level())

    return time_series, buffer_series, seek_event_times

def plot_simulation_data():
    times, buffers, seek_times = run_simulation_and_collect_data()

    plt.figure(figsize=(10, 6))
    plt.plot(times, buffers, marker='o', label='Buffer Level (ms)')
    plt.xlabel("Total Play Time (ms)")
    plt.ylabel("Buffer Level (ms)")
    plt.title("Visualization of Multiple Seeks Behavior")

    # Mark seek events on the timeline.
    for st in seek_times:
        plt.axvline(x=st, color='red', linestyle='--', label='Seek Event' if st == seek_times[0] else "")
        plt.text(st, max(buffers)*0.8, f"Seek @ {st} ms", rotation=90, verticalalignment='center')
        
    plt.legend()
    plt.tight_layout()
    plt.show()

if __name__ == '__main__':
    plot_simulation_data()
