# Specification 02: Clinical Metadata Extraction

## 1. Overview

This module extracts clinical reference measurements (RA, RV, PA, Wedge, Cardiac Output, Heart Rate) from LabChart recordings. These values are typed by clinicians into the **Notebook** panel during the procedure and serve as reference data for downstream clinical indices calculations.

**Key Constraint**: The Notebook content is **not** exported via LabChart's MATLAB export. It must be extracted by reading the raw `.adicht` file as binary and searching for embedded text strings.

---

## 2. Input Requirements

| File | Format | Purpose |
|------|--------|---------|
| Original Recording | `.adicht` | Contains embedded Notebook text |

The waveform data is handled separately by [Spec 01](./01_waveform_ingestion.md).

---

## 3. Extraction Method

### 3.1 Binary Text Extraction

The `.adicht` file is a proprietary binary format. However, the Notebook text is stored as embedded UTF-8 strings. We extract readable text by:

1. Opening the file in binary mode.
2. Decoding as UTF-8 (ignoring errors).
3. Filtering to printable characters.

```python
with open(adicht_path, 'rb') as f:
    raw_bytes = f.read()

text = raw_bytes.decode('utf-8', errors='ignore')
text = ''.join(c for c in text if c.isprintable() or c in '\n\r')
lines = text.split('\n')
```

### 3.2 Known Limitations

| Risk | Mitigation |
|------|------------|
| Encoding changes in future LabChart versions | Monitor for failures; update decoder if needed |
| Binary data matching pressure patterns | Context validation (require label prefix) |
| Inconsistent clinician formatting | Flexible regex patterns |

---

## 4. Measurement Patterns

### 4.1 Pressure Measurements (RA, RV, PA, Wedge)

**Target Format**: `LABEL: Systolic/Diastolic (Mean)` or `LABEL: Systolic/Diastolic, Mean`

**Primary Regex** (extracts three integers):
```regex
(\d+)\s*/\s*(\d+)\s*[,\s]*\(?\s*(\d+)\s*\)?
```

**Label Detection** (case-insensitive):

For each line containing the pressure pattern, check if it matches a label. Labels must appear as **word boundaries** to avoid false matches (e.g., "EXTRA" should not match "RA").

| Measurement | Match Conditions | 
|-------------|------------------|
| RA | Line contains `RA `, `RA-`, `RA:`, or starts with `RA` | 
| RV | Line contains `RV `, `RV-`, `RV:`, or starts with `RV` |
| PA | Line contains `PA `, `PA-`, `PA:`, or starts with `PA` | 
| Wedge | Line contains any of: `PCWP`, `PCW`, `WPA`, `WEDGE`, `PA WEDGE` |

### 4.2 Cardiac Output (CO)

**Step 1: Find CO Section**

Search for the CO keyword using word boundaries to avoid false matches (e.g., "PROTOCOL"):
```regex
cardiac output|(?<![a-z])CO(?![a-z])|C\.O
```

Extract the next ~500 characters as the "CO section" for further parsing.

**Step 2: Extract CO Values**

Find all numbers in the CO section matching `(\d+\.?\d*)`. For each number:

1. **Skip list item numbers**: If the number is 1–4 (integer) AND appears in a list context (e.g., `1.`, `1-`, `1 ` at line start), skip it.
2. **Accept valid CO range**: If the number is 2.0–20.0, add it to the trials list.
3. **Stop at 3 trials**: Maximum of 3 CO values.

### 4.3 Heart Rate (HR)

**Step 1: Find HR Keyword**

Within the CO section, search for `HR` using word boundaries:
```regex
(?<![a-z])HR(?![a-z])
```

**Step 2: Extract HR Value**

From the HR position, extract the next 100 characters. Find the first integer:
```regex
HR[^0-9]*?(\d+)
```

**Step 3: Validate**

Accept only if the value is in the physiological range 40–200 bpm.

---

## 5. Physiological Validation

After extraction, apply cross-checks based on expected blood flow through the right heart. Failed checks generate warnings but do not prevent extraction—the values may still be correct if the patient has unusual physiology.

### 5.1 Expected Pressure Relationships

Blood flows through the right heart in this order:

```
RA → RV → PA → (Lungs) → Wedge ≈ LA
```

Therefore, under normal physiology:
- RA pressures should be **lower** than RV pressures
- RV and PA **systolic** pressures should be **similar** (same ventricle ejection)
- Wedge (reflecting left atrial pressure) should be **lower** than PA and RV

### 5.2 Validation Rules

| Check | Expected | Warning If |
|-------|----------|------------|
| RA vs RV (mean) | RA < RV | RA mean ≥ RV mean |
| RA vs RV (systolic) | RA < RV | RA systolic ≥ RV systolic |
| RV vs PA (systolic) | RV ≈ PA | Differ by > 15 mmHg |
| Wedge vs RV (mean) | Wedge < RV | Wedge mean ≥ RV mean |
| Wedge vs PA (mean) | Wedge < PA | Wedge mean ≥ PA mean |

### 5.3 Output

Warnings are added to `extraction.warnings` array:

```json
{
  "extraction": {
    "status": "OK",
    "warnings": ["RA mean (12) >= RV mean (10)"]
  }
}
```

---

## 6. Extraction Status

A single status summarises the extraction outcome:

| Status | Condition |
|--------|-----------|
| `OK` | All critical measurements (RA, RV, PA) found |
| `PARTIAL` | Some measurements missing (e.g., Wedge not found) |
| `FAILED` | No measurements could be extracted |

---

## 7. Manual Override Mechanism

For files requiring manual intervention, a sidecar override file can be created:

**Filename**: `[recording_id]_override.json`

```json
{
  "RA": {"systolic": 10, "diastolic": 5, "mean": 7},
  "Wedge": {"systolic": 12, "diastolic": 8, "mean": 10},
  "notes": "Wedge extracted manually from LabChart screenshot."
}
```

The ingestion script:
1. Checks for the existence of an override file.
2. Merges override values into the extracted metadata.
3. Sets `source` to `"manual"` for overridden values.

---

## 8. Output

The extracted measurements are added to the metadata JSON (created by [Spec 01](./01_waveform_ingestion.md)).

```json
{
  "hemodynamics": {
    "RA": {"systolic": 10, "diastolic": 5, "mean": 7},
    "RV": {"systolic": 25, "diastolic": 2, "mean": 15},
    "PA": {"systolic": 40, "diastolic": 20, "mean": 30},
    "Wedge": {"systolic": 12, "diastolic": 8, "mean": 10},
    "CO": [5.2, 5.4, 5.1],
    "HR": 72
  },
  "extraction": {
    "status": "OK",
    "warnings": []
  }
}
```

### Field Reference

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `RA`, `RV`, `PA`, `Wedge` | object | mmHg | Pressure with `systolic`, `diastolic`, `mean` |
| `CO` | array | L/min | Up to 3 cardiac output trials |
| `HR` | int | bpm | Heart rate |
| `extraction.status` | string | — | `OK`, `PARTIAL`, or `FAILED` |
| `extraction.warnings` | array | — | List of validation warnings |

> [!NOTE]
> Stroke Volume (SV), mean CO, and other derived values are calculated downstream in the Clinical Indices module ([Spec 07](./07_clinical_indices.md)), not during extraction.

---

## 9. Related Documents

- [01_waveform_ingestion.md](./01_waveform_ingestion.md) — Extracts waveforms from `.mat` export
- [07_clinical_indices.md](./07_clinical_indices.md) — Calculates derived values (SV, PVR, etc.)
- [02_architecture.md](../02_architecture.md) — Overall pipeline architecture
