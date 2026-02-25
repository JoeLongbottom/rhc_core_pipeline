# Specification 01: Waveform Ingestion

## 1. Overview

This module handles the extraction of raw waveform data (ECG and Pressure) from LabChart exports and converts them into CSV format for downstream processing.

**NOTE**: The ADInstruments SDK (required to read `.adicht` files programmatically) is Windows-only. Therefore, waveform extraction relies on a pre-exported MATLAB (`.mat`) file.

---

## 2. Input Requirements

### 2.1 Required Files

For each recording session, the ingestion process requires **two files**:

| File | Format | Purpose |
|------|--------|---------|
| Waveform Export | `.mat` | Contains ECG and Pressure arrays, sampling rate, record structure.|
| Original Recording | `.adicht` | Required for clinical measurement extraction (see [Spec 02](./02_clinical_metadata_extraction.md)) |

### 2.2 File Preparation (Windows)

On Windows with ADInstruments SDK:

1. Run the provided MATLAB export script (`export_to_mat.m`).
2. Select input folder (containing `.adicht`) and output folder.

### 2.3 Expected `.mat` Structure

LabChart exports typically contain:

```
data_block1 (or datastart/dataend arrays)
├── data          # n_samples × n_channels array (or transposed in HDF5)
├── tickrate      # Samples per second
├── titles        # Channel names (cell array)
├── unittext      # Channel units (cell array)
├── blocktimes    # Start time of each block
└── com           # Comment metadata (if comments exist)
```

> [!NOTE]
> The ingestion script automatically handles the differences between MATLAB v7 and v7.3 (HDF5) file structures, including array transposition.

---

## 3. Processing Steps

### 3.1 Load MAT File

The script attempts to load using `scipy.io.loadmat`. If that fails (due to v7.3 format), it checks for HDF5 signature and transparently loads using `h5py`.

### 3.2 Channel Identification

The ingestion script requires **exactly two channels**: `ECG` and `Pressure`.

**Identification Strategy**:
1.  **Name Matching**: Searches `titles` metadata for "ECG" and "Pressure" (case-insensitive substring match).
2.  **Fallback**: If channel names cannot be read or matched, defaults to **Index 0 = ECG** and **Index 1 = Pressure** (matching the export script's default order).

### 3.3 Multi-Block Handling

LabChart files may contain multiple "blocks" (recording segments).

**Export Requirement**:
The `.mat` export (via the provided MATLAB script) MUST:
1. **Concatenate** keys blocks into a single continuous `data` matrix.
2. **Fill gaps** between blocks with `NaN` values.
3. Provide `datastart` and `dataend` indices for each block.

**Ingestion Logic**:
The Python ingestion script uses the `datastart`/`dataend` indices to:
1. Identify block boundaries within the continuous array.
2. Create metadata entries for each recording block.
3. Identify gap blocks in the metadata where `datastart[i] > dataend[i-1]`.

### 3.4 Unit Conversion

> [!IMPORTANT]
> LabChart exports Pressure in **mmHg/100**. The ingestion script **multiplies by 100** to convert to standard mmHg. All downstream modules receive Pressure in true mmHg.

| Channel | Raw Unit | Output Unit | Conversion |
|---------|----------|-------------|------------|
| ECG | mV | mV | None |
| Pressure | mmHg/100 | mmHg | × 100 |

---

## 4. Usage (CLI)

The `run_ingestion.py` script supports batch processing of directories.

```bash
python scripts/run_ingestion.py \
    --mat-dir /path/to/exported_mats \
    --adicht-dir /path/to/raw_adicht \
    --output-dir output \
    --verbose
```

**Arguments**:
- `--mat-dir`: Directory containing `.mat` files.
- `--adicht-dir`: Directory containing corresponding `.adicht` files.
- `--output-dir`: Root output directory. Each recording creates a subdirectory.
- `--skip-clinical`: (Optional) Skip metadata extraction from `.adicht` files.

---

## 5. Output

Each recording is saved to its own directory: `output/{recording_id}/`

### 5.1 Waveform CSV

**Filename**: `waveform.csv`
**Format**: Comma-separated values, UTF-8 encoding.

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `ECG` | float | mV | Electrocardiogram signal |
| `Pressure` | float | mmHg | Invasive pressure signal (scaled from mmHg/100) |

**Time Reconstruction**: Time for any row can be calculated as `row_index / sample_rate_hz` using metadata.

> [!NOTE]
> Gaps between blocks are filled with `NaN` for both ECG and Pressure channels.

### 5.2 Metadata JSON

**Filename**: `[recording_id].json`

The JSON file is populated by this module and augmented by [Spec 02](./02_clinical_metadata_extraction.md).

#### Block Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `block_id` | int \| null | Sequential block number (1, 2, 3...). `null` for gaps. |
| `start_sample` | int | First sample index (0-indexed, inclusive). |
| `end_sample` | int | Last sample index (0-indexed, **exclusive**). Use `data[start:end]`. |
| `n_samples` | int | Number of samples in this block (`end_sample - start_sample`). |
| `start_datetime` | string \| null | ISO 8601 timestamp when this block started. `null` for gaps. |
| `duration_seconds` | float | Duration of this block in seconds. |
| `is_gap` | bool | `true` if this represents a gap (no valid data), `false` for real data. |

#### Example

```json
{
  "recording_id": "study001",
  "start_datetime": "2026-01-27T14:30:00.000Z",
  "provenance": {
    "source_mat": "study001.mat",
    "source_adicht": "study001.adicht",
    "ingestion_timestamp": "2026-01-27T17:00:00Z",
    "git_commit": "fb38742..."
  },
  "waveform": {
    "sample_rate_hz": 1000.0,
    "duration_seconds": 300.5,
    "total_samples": 300500,
    "channels": {
      "ECG": {"unit": "mV"},
      "Pressure": {"unit": "mmHg", "note": "Scaled from mmHg/100"}
    }
  },
  "blocks": [
    {
      "block_id": 1,
      "start_sample": 0,
      "end_sample": 150000,
      "n_samples": 150000,
      "start_datetime": "2026-01-27T14:30:00.000Z",
      "duration_seconds": 150.0,
      "is_gap": false
    },
    {
      "block_id": null,
      "start_sample": 150000,
      "end_sample": 151000,
      "n_samples": 1000,
      "start_datetime": null,
      "duration_seconds": 1.0,
      "is_gap": true
    },
    {
      "block_id": 2,
      "start_sample": 151000,
      "end_sample": 300500,
      "n_samples": 149500,
      "start_datetime": "2026-01-27T14:32:31.000Z",
      "duration_seconds": 149.5,
      "is_gap": false
    }
  ],
  "hemodynamics": {},
  "extraction": {}
}
```

**Key Design Decisions**:

| Field | Convention | Rationale |
|-------|------------|-----------|
| `start_sample` | 0-indexed, inclusive | Python array indexing |
| `end_sample` | 0-indexed, **exclusive** | Slice notation: `data[start:end]` |
| `n_samples` | `end_sample - start_sample` | Explicit for convenience |
| `blocks` | Renamed from `record_structure` | Clearer terminology |
| `sample_rate_hz` | Explicit unit suffix | Avoids ambiguity |
| `provenance.git_commit` | Commit Hash | Ensures traceability of analysis code used |

The `hemodynamics` field is populated by [Spec 02](./02_clinical_metadata_extraction.md).

---

## 6. Validation

The ingestion script performs the following checks:

| Check | Condition | Action |
|-------|-----------|--------|
| Channel Presence | Required channels (ECG, Pressure) found | Fallback to Index Assumed if failed |
| Sample Rate Consistency | All blocks have same sample rate | Error if inconsistent |
| Duration Match | `total_samples / sample_rate ≈ duration_seconds` | Warning if mismatch > 1% |

---

## 7. Error Handling

| Status | Condition | Action |
|--------|-----------|--------|
| `SUCCESS` | All checks passed | Proceed to clinical extraction |
| `WARNING` | Non-critical checks failed | Proceed but log warnings |
| `FILE_ERROR` | Cannot read `.mat` file | Skip file, log error |
| `CHANNEL_ERROR` | Required channels missing | Skip file, log error |

---

## 8. Related Documents

- [02_clinical_metadata_extraction.md](./02_clinical_metadata_extraction.md) — Extracts clinical measurements from `.adicht` Notebook
- [02_architecture.md](../02_architecture.md) — Overall pipeline architecture
