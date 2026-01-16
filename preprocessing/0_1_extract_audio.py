import mne
import numpy as np
from scipy.io.wavfile import write
from pathlib import Path
import re
from fractions import Fraction

# ---------- Configuration ----------
EEG_ROOT = Path('/Users/moanason/Downloads/Data_EEG')    # /s01, /s02, ...
OUT_ROOT = Path('/Users/moanason/Downloads/Data_REF')    # rec_s##_NC#.wav will be written here

TARGET_CHANNEL   = 'Erg1'     # audio channel in BDF
START_EVENT_ID   = 63         # event ID for conversation start
END_EVENT_ID     = 63         # event ID for conversation end (last occurrence)
TARGET_SAMPLE_RATE = 48000    

# channels for sti
STIM_CANDIDATES = ['STI 014', 'Status', 'STATUS', 'Stim', 'STI101']

NC_RX = re.compile(r'NC(?P<nc>\d+)\.bdf$', re.IGNORECASE)
SESSION_RX = re.compile(r'^s(?P<sess>\d+)$', re.IGNORECASE)

# -----------------------------------

def pick_stim_channel(raw) -> str | None:
    """Pick a reasonable stimulus channel present in the Raw, or None."""
    for cand in STIM_CANDIDATES:
        if cand in raw.ch_names:
            return cand
    return None

def find_events(raw, stim_name: str | None):
    """Find events either from the stim channel or from annotations."""
    events = None
    if stim_name:
        try:
            events = mne.find_events(raw, stim_channel=stim_name,
                                     shortest_event=1, initial_event=True, verbose=False)
        except Exception:
            events = None
    if events is None or len(events) == 0:
        # fallback to annotations
        try:
            events, _ = mne.events_from_annotations(raw, verbose=False)
        except Exception:
            events = None
    return events

def resample_1d_mne(x: np.ndarray, orig_sfreq: float, target_sfreq: int) -> np.ndarray:
    if int(round(orig_sfreq)) == int(target_sfreq):
        return x
    info = mne.create_info(['AUDIO'], sfreq=orig_sfreq, ch_types='misc')
    raw = mne.io.RawArray(x[np.newaxis, :], info, verbose=False)
    raw.resample(target_sfreq, npad='auto', verbose=False)
    return raw.get_data()[0]

def extract_and_write(bdf_path: Path, out_path: Path,
                      channel_name: str = TARGET_CHANNEL,
                      start_id: int = START_EVENT_ID,
                      end_id: int = END_EVENT_ID,
                      target_sr: int = TARGET_SAMPLE_RATE) -> bool:
    try:
        raw = mne.io.read_raw_bdf(bdf_path, preload=True, verbose=False)
        sfreq = float(raw.info['sfreq'])

        # check channel
        if channel_name not in raw.ch_names:
            print(f"[SKIP] {bdf_path.name}: channel '{channel_name}' not found. "
                  f"Available: {', '.join(raw.ch_names[:10])} ...")
            return False

        # find events
        stim = pick_stim_channel(raw)
        events = find_events(raw, stim)
        if events is None or len(events) == 0:
            print(f"[SKIP] {bdf_path.name}: no events found (stim='{stim}').")
            return False

        # start and end events by ID
        start_ev = events[events[:, 2] == start_id]
        end_ev   = events[events[:, 2] == end_id]

        if start_ev.size == 0 or end_ev.size == 0:
            print(f"[SKIP] {bdf_path.name}: could not find both start({start_id}) and end({end_id}) events. "
                  f"IDs present: {np.unique(events[:,2])}")
            return False

        start_sample = int(start_ev[0, 0])         # first occurrence
        end_sample   = int(end_ev[-1, 0])          # last occurrence

        if end_sample <= start_sample:
            print(f"[SKIP] {bdf_path.name}: end <= start (start={start_sample}, end={end_sample}).")
            return False

        # Crop to [start, end]
        tmin = start_sample / sfreq
        tmax = end_sample   / sfreq
        raw_crop = raw.copy().crop(tmin=tmin, tmax=tmax)

        # extract audio channel
        audio = raw_crop.get_data(picks=[channel_name])[0]  # shape (n,)

        audio_out = resample_1d_mne(audio, sfreq, target_sr)

        # Normalize to int16 safely
        peak = np.max(np.abs(audio_out)) if audio_out.size else 0.0
        if peak > 0:
            audio_norm = audio_out / peak
        else:
            audio_norm = audio_out  # all zeros

        audio_int16 = np.int16(np.clip(audio_norm, -1.0, 1.0) * 32767)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        write(out_path.as_posix(), int(target_sr), audio_int16)

        print(f"[OK]  {bdf_path.name}  ->  {out_path.name}  "
              f"(dur {len(audio_int16)/target_sr:.2f}s, sr={target_sr})")
        return True

    except FileNotFoundError:
        print(f"[ERR] File not found: {bdf_path}")
        return False
    except Exception as e:
        print(f"[ERR] {bdf_path.name}: {e}")
        return False

def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    total = 0
    ok = 0
    skipped = 0

    for sess_dir in sorted(EEG_ROOT.glob("s*")):
        m = SESSION_RX.match(sess_dir.name)
        if not (sess_dir.is_dir() and m):
            continue
        sess_num = int(m.group('sess'))  # e.g., '06' -> 6

        for bdf_path in sorted(sess_dir.glob("p*_NC*.bdf")):
            total += 1
            mnc = NC_RX.search(bdf_path.name)
            if not mnc:
                print(f"[SKIP] {bdf_path.name}: cannot parse NC number.")
                skipped += 1
                continue

            nc_num = int(mnc.group('nc'))
            out_name = f"rec_s{sess_num:02d}_NC{nc_num}.wav"
            out_path = OUT_ROOT / out_name

            success = extract_and_write(
                bdf_path=bdf_path,
                out_path=out_path,
                channel_name=TARGET_CHANNEL,
                start_id=START_EVENT_ID,
                end_id=END_EVENT_ID,
                target_sr=TARGET_SAMPLE_RATE,
            )
            if success:
                ok += 1
            else:
                skipped += 1

    print("\n summary ")
    print(f"total bdf files matched: {total}")
    print(f"exported: {ok}")
    print(f"skipped/failed:       {skipped}")
    print(f"save to:        {OUT_ROOT}")

if __name__ == "__main__":
    main()












# import mne
# import numpy as np
# from scipy.io.wavfile import write

# # --- Configuration ---
# FILE_PATH = '/Users/moanason/Downloads/Data_EEG/s06/p11_NC1.bdf' # Change this to your actual file path
# TARGET_CHANNEL = 'Erg1' # Make sure this channel name is correct
# START_EVENT_ID = 63 # The integer ID for your start event
# END_EVENT_ID = 63 # The integer ID for your end event
# OUTPUT_WAV_FILE = 'audio_s06_NC1.wav'
# TARGET_SAMPLE_RATE = 48000 # Resample to 16kHz for better quality
# # FILTER_RANGE = (100, 1024) # Band-pass filter from 100 Hz to 7.5 kHz

# def extract_channel_between_events(file_path, channel_name, start_desc, end_desc, output_file):
#     """
#     Loads a data file, finds start/end events, and extracts the specified 
#     channel data between them, saving it as a WAV file.

#     Args:
#         file_path (str): Path to the data file (e.g., .edf).
#         channel_name (str): The name of the channel to extract.
#         start_desc (str): The description/name of the start event annotation.
#         end_desc (str): The description/name of the end event annotation.
#         output_file (str): Path to save the output .wav file.
#     """
#     try:
#         # 1. Load the raw data file. Preload=True loads data into memory.
#         print(f"Loading data from '{file_path}'...")
#         raw = mne.io.read_raw_bdf(file_path, preload=True, verbose=False)
#         sfreq = raw.info['sfreq']

#         # --- Optional Preprocessing from your example ---
#         # raw.resample(2048)
#         # raw.set_eeg_reference('average', projection=False)
#         # print("Applied resampling and re-referencing.")

#         # --- Find events from the stimulus channel ---
#         # This is the correct method when annotations are empty.
#         events = mne.find_events(raw, stim_channel=None, initial_event=True)

#         # --- Inspection Step for Events ---
#         # Let's print all available event IDs to help find the right ones.
#         print("\n--- Inspecting Events from Stimulus Channel ---")
#         print(f"Found {len(events)} events in total.")
#         # The third column in the events array is the event ID
#         print(f"Unique event IDs found: {np.unique(events[:, 2])}")
#         print("---------------------------------------------\n")

#         # Check if the target channel exists
#         if channel_name not in raw.ch_names:
#             print(f"Error: Channel '{channel_name}' not found in the file.")
#             print(f"Available channels are: {raw.ch_names}")
#             return

#         # 2. Find the start and end times from annotations
#         start_time = None
#         end_time = None

#         # Find all events that match the start and end IDs
#         # Event array columns are: [sample, previous_id, new_id]
#         start_events = events[events[:, 2] == start_desc]
#         end_events = events[events[:, 2] == end_desc]

#         if start_events.size > 0:
#             # Use the first occurrence for the start time
#             # Convert from sample number to seconds
#             start_time = start_events[0, 0] / sfreq
#             print(f"Found start event ID '{start_desc}' at sample {start_events[0, 0]} ({start_time:.2f} seconds).")

#         if end_events.size > 0:
#             # Use the last occurrence for the end time
#             end_time = end_events[-1, 0] / sfreq
#             print(f"Found end event ID '{end_desc}' at sample {end_events[-1, 0]} ({end_time:.2f} seconds).")
        
#         if start_time is None or end_time is None:
#             print("Error: Could not find both start and end event markers.")
#             print(f"Looked for event IDs '{start_desc}' and '{end_desc}'.")
#             return
            
#         # 3. Get the sampling frequency
#         sfreq = raw.info['sfreq']
#         print(f"Sampling frequency: {sfreq} Hz")
#         # If original sfreq is not 16000, we will resample later
#         # but for extraction, we keep the original sfreq
#         # 4. Select the specific channel and crop the time window
#         # The copy() is important to avoid modifying the original raw object
#         raw_cropped = raw.copy().crop(tmin=start_time, tmax=end_time)
        
#         # 5. Get the data from the cropped segment for the target channel
#         # It returns a 2D numpy array (channels x samples)
#         channel_data, _ = raw_cropped.get_data(picks=[channel_name], return_times=True)
        
#         # The result is a 2D array, so we take the first (and only) row
#         audio_segment = channel_data[0]

#         print(f"Successfully extracted {len(audio_segment)} samples for channel '{channel_name}' at {sfreq} Hz.")

#         # 6. Resample the audio for better quality
#         # We are skipping the filtering step as requested.
#         print(f"Resampling audio from {sfreq} Hz to {TARGET_SAMPLE_RATE} Hz...")
#         # MNE's resample function is efficient for this
#         audio_resampled = mne.filter.resample(audio_segment, up=TARGET_SAMPLE_RATE/sfreq, down=1, npad='auto', verbose=False)
#         final_sr = TARGET_SAMPLE_RATE

#         # 7. Save the extracted audio segment as a WAV file
#         # Note: WAV files require integer data. We scale and convert it.
#         # Assuming the data is in Volts, we scale it to fit into a 16-bit integer range.
#         print("Normalizing and converting data to 16-bit integer for WAV format...")
#         # Use the resampled audio now
#         audio_normalized = audio_resampled / np.max(np.abs(audio_resampled))
#         audio_int16 = np.int16(audio_normalized * 32767)
        
#         write(output_file, int(final_sr), audio_int16)
#         print(f"Successfully saved extracted audio to '{output_file}'.")

#     except FileNotFoundError:
#         print(f"Error: The file '{file_path}' was not found.")
#     except Exception as e:
#         print(f"An unexpected error occurred: {e}")

# # --- Run the extraction ---
# if __name__ == '__main__':
#     extract_channel_between_events(
#         file_path=FILE_PATH,
#         channel_name=TARGET_CHANNEL,
#         start_desc=START_EVENT_ID,
#         end_desc=END_EVENT_ID,
#         output_file=OUTPUT_WAV_FILE
#     )


