# RHC Core Pipeline

Core analysis pipeline for Right Heart Catheterisation (RHC) pressure waveforms and ECG data, extracting beat-by-beat haemodynamic features and clinical indices.

## Quick Start

### Prerequisites

- Python 3.12+

### Installation

```bash
# Clone repository
git clone https://github.com/JoeLongbottom/rhc_core_pipeline.git

# Install dependencies
pip install -r requirements.txt
````

### Running the Pipeline

**Option 1 — `.mat` and `.adicht` files in the same directory:**

```bash
python scripts/run_pipeline.py \
    --input-dir data/raw \
    --output-dir output \
    --workers -1
```

**Option 2 — `.mat` and `.adicht` files in separate directories:**

```bash
python scripts/run_pipeline.py \
    --mat-dir data/mat_exports \
    --adicht-dir data/labchart_originals \
    --output-dir output \
    --workers -1
```

Runs the **full pipeline** (ingestion → analysis → plotting).

**Running specific stages**:

```bash
# Re-run only analysis on all recordings
python scripts/run_pipeline.py \
    --input-dir output \
    --output-dir output \
    --steps analysis \
    --workers -1

# Re-run only plotting
python scripts/run_pipeline.py \
    --input-dir output \
    --output-dir output \
    --steps plotting \
    --workers -1
```

### CLI Reference

| Flag | Required | Default | Description |
|---|---|---|---|
| `--input-dir` | Yes* | — | Directory containing co-located `.mat` and `.adicht` files |
| `--mat-dir` | Yes* | — | Directory containing `.mat` files (use with `--adicht-dir`) |
| `--adicht-dir` | Yes* | — | Directory containing `.adicht` files (use with `--mat-dir`) |
| `--output-dir` | Yes | — | Root output directory |
| `--steps` | No | `all` | Pipeline stages to run: `all`, `ingestion`, `analysis`, `plotting` |
| `--workers` | No | `4` | Number of parallel workers (`-1` = all available CPU cores) |
| `--config` | No | `config/pipeline_config.yaml` | Path to pipeline configuration file |
| `--plotting-config` | No | `config/plotting_config.yaml` | Path to plotting configuration file |
| `--sampling-rate` | No | auto-detected | Override the sampling rate (Hz) during analysis |
| `--skip-clinical` | No | `false` | Skip clinical metadata extraction during ingestion |
| `--show` | No | `false` | Show plots interactively (forces single worker) |

*Either `--input-dir` **or** both `--mat-dir` and `--adicht-dir` must be provided.



## Input Requirements

### Data Preparation (Windows with LabChart)

1. Export `.mat` files using the MATLAB script:
   - Run `matlab/export_to_mat.m` (or call `export_to_mat()` from the command window)
   - Select the input folder containing `.adicht` files when prompted
   - Select the output folder for `.mat` exports when prompted

2. Transfer both `.mat` and `.adicht` files to the processing environment

## Output Structure

Each recording generates a dedicated folder:

```
output/{recording_id}/
├── waveform.csv              # Ingested ECG + Pressure data
├── metadata.json             # Recording metadata + clinical measurements
├── beats.xlsx                # Primary output (beat-by-beat metrics)
├── analysis.pkl              # Full pipeline data (for reprocessing)
├── intermediates/
│   ├── ecg_features.csv
│   ├── pressure_features.csv
│   ├── gated_beats.csv
│   └── classified_beats.csv
└── plots/
    ├── ecg_features.png
    ├── pressure_features.png
    ├── beat_gating.png
    └── beat_classification.png
```

### Primary Output: `beats.xlsx`

| Sheet | Contents |
|---|---|
| **Beats** | Beat-by-beat haemodynamic features: pressure waveform morphology (systolic, diastolic, mean, upstroke, area), beat location, quality flags, and classification |
| **Clinical Indices** | Per-recording summary: mPAP, mRAP, PVR, TPG, DPG, PAC, RC time, cardiac output/index, heart rate, stroke volume |
| **PQRST Features** | Beat-by-beat ECG features: P, Q, R, S, T wave amplitudes and intervals (where ECG is available) |
| **Data Dictionary** | Definitions, units, and descriptions for every column across all sheets |
| **Metadata** | Recording information: patient ID, date, clinical measurements from lab notes, pipeline version |


## Configuration

Pipeline behaviour controlled via YAML files:

```
config/
├── ingestion_config.yaml   # Ingestion parameters
├── pipeline_config.yaml    # Processing parameters
└── plotting_config.yaml    # Plot generation settings
```

Key parameters:
- **ECG**: Peak detection method, quality thresholds
- **Pressure**: Filtering, search windows, slew rate limits  
- **Gating**: Arrhythmia detection, outlier filters
- **Classification**: PA vs UNCERTAIN thresholds

## Processing Pipeline

```
MAT/ADICHT → Ingestion → ECG Features → Pressure Features 
                ↓            ↓               ↓
           metadata.json    ↓               ↓
                          Beat Gating → Beat Classification 
                                ↓               ↓
                        Clinical Indices ← ─────┘
                                ↓
                          beats.xlsx + plots/
```

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/architecture.md`](docs/architecture.md) | Module structure and data flow |
| [`docs/specs/`](docs/specs/) | Detailed specifications for each module |
