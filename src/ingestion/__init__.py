# Ingestion Module
"""
Data ingestion from LabChart files.

Main entry points:
- ingest_waveform: Load .mat file, extract ECG/Pressure, output CSV/JSON
- extract_clinical_metadata: Extract hemodynamics from .adicht binary
"""

from .waveform_ingestion import ingest_waveform
from .clinical_extraction import extract_clinical_metadata, merge_with_metadata

__all__ = ['ingest_waveform', 'extract_clinical_metadata', 'merge_with_metadata']
