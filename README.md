# Dyadic Conversation Preprocessing + Synchrony Analysis (Audio/TextGrid)

This repository contains a reproducible pipeline for **two-person conversational recordings** (two speakers recorded as separate streams, later combined), producing:

- **Processed WAVs** (per session × condition; optionally combined A+B reference audio)
- **Praat TextGrids** with consistent tiers for:
  - **Speech activity / diarisation** (per speaker stream)
  - **Transitional conditions/events** (gap / overlap / backchannel / between-event talk segments)
  - **Automatic syllable-nuclei annotations** (for syllable-based speech-rate estimation)
- **Analysis-ready data frames** (event-level and turn-pair / macro-turn level) for synchrony modelling in R.

---

## Pipeline overview (in order)
- Remember to specify their own local directory for processing.

### 0) Extract audio from BioSemi (optional, if starting from `.bdf`)
- **`0_1_extract_audio.py`**
  - Reads BioSemi BDF and extracts audio around task markers (e.g., start/end triggers).
  - Outputs WAV files for subsequent alignment/VAD steps.

### 1) Align multi-device offsets (when recordings come from multiple devices with delays)
- **`1_1_Align_multi_offsets.ipynb`**
  - Estimates and applies time offsets between streams (e.g., A recorder vs B recorder vs reference).
  - Produces aligned versions used by the later steps (VAD/diarisation/segmentation).

### 2) Voice activity detection (VAD) → TextGrid creation
- **`2_1_VAD_TextGrid_pyannote_FIX.ipynb`**
  - Runs VAD (pyannote) to detect speech segments.
  - Writes/updates TextGrids (praatio) for later tier merging and downstream segmentation.

### 3) Diarisation / speaker segmentation (pyannote-based)
- **`2_2_VAD_Diarisation_FIX.ipynb`**
  - Runs diarisation to obtain speaker-homogeneous intervals.
  - Outputs diarisation tiers that are later copied/merged into the combined/reference TextGrids.

### 4) Combine A/B audio into a reference 2-channel (and mirror tiers)
- **`3_Combine_Audio_Two_Channels.ipynb`**
  - Combines the two processed streams into a single reference audio file for session-level inspection.
  - Copies the relevant tiers into the combined/reference TextGrid so that the reference WAV and TextGrid stay aligned.

### 5) Transitional condition/event segmentation (gap/overlap/backchannel/BET)
- **`4_TRAN_Condition_segmentation.ipynb`**
  - Uses diarisation tiers (A/B) to derive **turn-transfer structure** and **transitional events**:
    - `Gap`, `Overlap`, `Backchannel_A/B`, and **between-event talk segments** (often called `BET`).
  - Produces a tier set suitable for turn-pair / macro-turn construction and Markov transition modelling.

### 6) Automatic syllable-nuclei annotation (speech-rate proxy)
- **`5_Anno_syllabic_nuclei.ipynb`**
  - Detects **syllable nuclei** using a Praat-style approach:
    - compute **Intensity** over time,
    - detect **local maxima** (peaks) under constraints (minimum dip, minimum peak distance),
    - optionally gate by **voicing/Pitch** to reduce false positives.
  - Writes two tiers back into the reference TextGrid (e.g., `Transcribe_A` and `Transcribe_B`), which are later counted per interval to get *syllables/second*.

> Important note: this provides a **syllable-nuclei rate** (a robust proxy for syllable rate), not a true phoneme rate and not guaranteed “true syllables” in a linguistic sense—especially in fast Swiss German speech with varied pronounciation bias. It’s designed for **consistent within-study comparisons** and recommended to be validated on a small hand-checked subset.

---

## Data products

One will typically end up with:
### A) Temporal infomation extraction table (**`6_0_Data_reStructure_Temporal.ipynb`**: `frame_df`)
- This process extracts the temporal info with every 2ms as a step from the processed auduo recordings for futher processing.
- It `temporal_processed_data_frames.csv` should contain at least the following columns:
[1] "id"        "cond"      "time"      "spk1"      "spk2"      "event"     "F0_A"      "RMS_A"     "F0_B"      "RMS_B"    
[11] "time_sec"  "dyad"      "condition" "F0_A_sp"   "F0_B_sp"   "RMS_A_sp"  "RMS_B_sp"

### B) Descriptive infomation extraction table (**`6_1_Data_reStructure_Descriptive.ipynb`**: `event_df`)
- This process extracts the core infomation of the events that we used for descriptive data analysis (turn-taking timing).
- It `descriptive_processed_event_data_with_pause.csv` should contain at least the following columns:
 [1] "i"          "c"          "speaker"    "event"      "duration"   "speechrate" "F0"         "RMS"        "time_sec" 

### C) Event-level table (**`6_2_Data_reStructure_TrE_BET_descriptive.ipynb`**: `tre_df`)
One row per event interval (speaker-specific for BET/BC; global for Gap/Overlap/Silence), with columns like:
- `i, c, dyad, condition`
- `speaker` (binary speaker id; **not** A/B identity)
- `event_type` (BET / BC / GAP / OVL / SIL …)
- `duration, time_sec`
- `speechrate` (syllable-nuclei/s)
- `F0, RMS` (prosody summaries per interval)
- It `descriptive_processed_TrE_BET_IPU_data.csv` should contain at least the following columns:
[1] "id"        "cond"      "etype"     "event"     "label"     "spk"       "spk1"      "spk2"      "n_syl_A"   "n_syl_B"   "sr_A"     
[12] "sr_B"      "sr"        "F0_A"      "RMS_A"     "F0_B"      "RMS_B"     "duration"  "time_sec"

### D) Turn / adjacent-turn-pair table (**`6_3_Data_synchrony_analysis.ipynb`**: `sync_df`)
One row per **adjacent macro-turn pair** (speaker switch enforced), with columns like:
- `macro_idx`, `speaker`, `start_time`, `end_time`
- `macro_idx_next`, `speaker_next`, `start_next`, `end_next`
- duration + counts: `D, N` and `D_next, N_next`
- mismatch measures: `F0_dev`, `M_rate` (absolute product of SR deviation), `F0_dev`, `RMS_dev`
- time normalisation: `t_rel_idx` (0–1 conversation progress)
- optional clustering outputs: `cluster`, `sync_level`
- It `turn_sync_pairs_with_F0_RMS.csv` should contain at least the following columns:

[1] "i"              "c"              "macro_idx"      "speaker"        "start_time"     "end_time"       "D"             
[8] "N"              "n_micro"        "F0_z_mean"      "RMS_z_mean"     "speaker_next"   "start_next"     "end_next"      
[15] "D_next"         "N_next"         "F0_next"        "RMS_next"       "macro_idx_next" "Delta_rate"     "M_rate"        
[22] "F0_dev"         "F0_rate"        "RMS_dev"        "RMS_rate"       "pair_idx"       "t_rel_idx" 

---

## Downstream analysis in R (what this pipeline enables)
All the analysis can be found in:
  - `1_descriptive_final.Rmd`: Descriptive analysis of turn-taking timing.
  - `2_prediction_analysis_turntaking.Rmd`: Descriptive analysis of turn-taking grammar (structure) with markov chain (1st and 2nd order).
  - `3_analysis_transevents_prob.Rmd`: Analysis of specific turn-taking behaviours regarding the structure.
  - `4_synchronicity_analysis_turns.Rmd`: Analysis of interpersonal acoustic synchrony with the synchrony indices built up in `sync_df`, and the interection with turn-taking events `tre_df`.

For example, typical analyses one can run once the above tables exist:

1) **Global synchrony per dyad × condition**
   - average mismatch indices (`M_rate`, `F0_dev`, `RMS_dev`) and their composites.
2) **Dynamic synchrony over conversation progress**
   - GAM/GAMM over `t_rel_idx`, with dyad random effects.
3) **Sliding-window entrainment**
   - time-resolved correlations (F0/RMS) per dyad, compared across conditions.
4) **CRQA on RMS envelopes (or derived series)**
   - compare RR/DET/Lmax across NC1 vs NC2.
5) **Time-weighted Markov transition landscape**
   - transition probabilities `P(next | current)` weighted by event duration.
   - conditional probabilities such as `P(disrupt_speech) = P((Gap ∪ Silence) | (Backchannel ∪ Overlap))`.

---

## Dependencies

**Python** (recommended: 3.10+):
- Jupyter (Notebook/Lab)
- Core scientific stack: `numpy`, `pandas`, `scipy`
- Audio I/O: `soundfile`, `librosa`
- **MNE** (for BioSemi `.bdf` extraction)
- **pyannote.audio** (VAD + diarisation; usually requires a HF token)
- **praatio** (TextGrid I/O via `tgio`)
- **parselmouth** (Praat pitch/intensity via Python)

**R**: 
- Packages in R will be installed automaticly by run.

---

## Notes on speaker labels (A/B vs spk1/spk2)

In this project, **A/B labels are treated as random recording assignments**, not stable identities.  
For modelling turn exchange, use **speaker-agnostic switching** (`spk1 → spk2`) rather than “A → B”.

---

## Useful documentation links

```text
MNE: reading BioSemi BDF
https://mne.tools/stable/generated/mne.io.read_raw_bdf.html

Praat manual: Sound → To Intensity
https://www.fon.hum.uva.nl/praat/manual/Sound__To_Intensity___.html

Praat manual: Sound → To Pitch
https://www.fon.hum.uva.nl/praat/manual/Sound__To_Pitch___.html

Parselmouth (Python–Praat bridge)
https://parselmouth.readthedocs.io/

praatio (TextGrid handling)
https://timmahrt.github.io/praatIO/

pyannote.audio tutorials
https://pyannote.github.io/pyannote-audio/

```

## Author
This repository was created for the Master's thesis study, originally by Moana J. Chen, depot on 21.01.2026.
