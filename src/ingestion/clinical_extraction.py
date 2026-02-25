"""
Clinical Metadata Extraction Module (Spec 02)

Extracts clinical measurements (RA, RV, PA, Wedge, CO, HR) from LabChart
.adicht files by reading embedded Notebook text.

See: docs/specs/02_clinical_metadata_extraction.md
"""

from pathlib import Path
import re
from typing import Optional


def extract_text_from_adicht(adicht_path: Path) -> str:
    """
    Extract readable text from a .adicht binary file.
    
    Opens the file in binary mode, decodes as UTF-8 (ignoring errors),
    and filters to printable characters.
    
    Args:
        adicht_path: Path to the .adicht file
        
    Returns:
        Extracted text as a string
        
    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    adicht_path = Path(adicht_path)
    if not adicht_path.exists():
        raise FileNotFoundError(f"ADICHT file not found: {adicht_path}")
    
    with open(adicht_path, 'rb') as f:
        raw_bytes = f.read()
    
    # Decode as UTF-8, ignoring errors
    text = raw_bytes.decode('utf-8', errors='ignore')
    
    # Filter to printable characters plus newlines
    text = ''.join(c for c in text if c.isprintable() or c in '\n\r')
    
    return text


def _line_matches_label(line: str, label: str) -> bool:
    """
    Check if a line matches a pressure label using word boundary logic.
    
    Matches patterns like 'RA ', 'RA-', 'RA:', or line starts with label.
    Also applies exclusion rules for certain labels.
    
    Args:
        line: The line to check (will be uppercased)
        label: The label to match ('RA', 'RV', 'PA')
        
    Returns:
        True if the line matches the label
    """
    line_upper = line.upper()
    label_upper = label.upper()
    
    # Check for word boundary patterns
    patterns = [
        f'{label_upper} ',
        f'{label_upper}-',
        f'{label_upper}:',
    ]
    
    has_match = any(p in line_upper for p in patterns) or line_upper.startswith(label_upper)
    
    if not has_match:
        return False
    
    # Apply exclusions
    if label_upper == 'RA':
        if 'CARDIAC' in line_upper or 'SYSTEMIC' in line_upper:
            return False
    elif label_upper == 'PA':
        if 'WEDGE' in line_upper or 'PCW' in line_upper:
            return False
    
    return True


def extract_pressure(lines: list[str], label: str) -> Optional[dict]:
    """
    Extract systolic/diastolic/mean pressure for a given label.
    
    Searches for patterns like "40/20 (30)" or "40/20, 30".
    
    Args:
        lines: List of text lines to search
        label: Pressure label ('RA', 'RV', 'PA')
        
    Returns:
        Dictionary with 'systolic', 'diastolic', 'mean' keys, or None if not found
    """
    # Pattern: digits/digits followed by optional (digits) or , digits
    pressure_pattern = re.compile(r'(\d+)\s*/\s*(\d+)\s*[,\s]*\(?\s*(\d+)\s*\)?')
    
    for line in lines:
        match = pressure_pattern.search(line)
        if match and _line_matches_label(line, label):
            return {
                'systolic': int(match.group(1)),
                'diastolic': int(match.group(2)),
                'mean': int(match.group(3))
            }
    
    return None


def extract_wedge(lines: list[str]) -> Optional[dict]:
    """
    Extract Wedge pressure (PCWP, PCW, WPA, WEDGE, PA WEDGE).
    
    Args:
        lines: List of text lines to search
        
    Returns:
        Dictionary with 'systolic', 'diastolic', 'mean' keys, or None if not found
    """
    wedge_patterns = ['PCWP', 'PCW', 'WPA', 'WEDGE', 'PA WEDGE']
    pressure_pattern = re.compile(r'(\d+)\s*/\s*(\d+)\s*[,\s]*\(?\s*(\d+)\s*\)?')
    
    for line in lines:
        line_upper = line.upper()
        match = pressure_pattern.search(line)
        
        if match and any(p in line_upper for p in wedge_patterns):
            return {
                'systolic': int(match.group(1)),
                'diastolic': int(match.group(2)),
                'mean': int(match.group(3))
            }
    
    return None


def extract_co(text: str, co_range: tuple[float, float] = (2.0, 20.0)) -> list[float]:
    """
    Extract cardiac output trial values.
    
    Finds the CO section, then extracts up to 3 numeric values
    in the valid range, skipping list item numbers.
    
    Args:
        text: Full text to search
        co_range: Valid range for CO values (min, max)
        
    Returns:
        List of up to 3 CO values
    """
    # Find CO section using word boundaries
    co_match = re.search(r'cardiac output|(?<![a-z])CO(?![a-z])|C\.O', text, re.IGNORECASE)
    
    if not co_match:
        return []
    
    # Extract next ~500 characters as CO section
    start = co_match.start()
    co_section = text[start:start + 500]
    
    # Find all numbers
    all_numbers = re.findall(r'(\d+\.?\d*)', co_section)
    
    co_values = []
    min_co, max_co = co_range
    
    for i, num_str in enumerate(all_numbers):
        num = float(num_str)
        
        # Skip integers 1-4 that look like list items
        if 1 <= num <= 4 and num == int(num):
            # Check if it looks like a list item (e.g., "1." or "1 ")
            # Simple heuristic: if it's at the start or after newline
            pos = co_section.find(num_str)
            if pos > 0:
                before = co_section[max(0, pos-3):pos]
                if re.match(r'^\s*$|[\n\r]', before):
                    continue
        
        # Accept values in valid range
        if min_co <= num <= max_co:
            co_values.append(num)
            if len(co_values) >= 3:
                break
    
    return co_values


def extract_hr(text: str, hr_range: tuple[int, int] = (40, 200)) -> Optional[int]:
    """
    Extract heart rate value.
    
    Searches for HR keyword with word boundaries, then extracts
    the next integer in the valid range.
    
    Args:
        text: Full text to search
        hr_range: Valid range for HR values (min, max)
        
    Returns:
        Heart rate as integer, or None if not found
    """
    # Find CO section first (HR is usually near CO)
    co_match = re.search(r'cardiac output|(?<![a-z])CO(?![a-z])|C\.O', text, re.IGNORECASE)
    
    if co_match:
        search_text = text[co_match.start():co_match.start() + 500]
    else:
        search_text = text
    
    # Find HR with word boundaries
    hr_match = re.search(r'(?<![a-z])HR(?![a-z])', search_text, re.IGNORECASE)
    
    if not hr_match:
        return None
    
    # Extract next 100 characters
    hr_region = search_text[hr_match.start():hr_match.start() + 100]
    
    # Find first number after HR
    num_match = re.search(r'HR[^0-9]*?(\d+)', hr_region, re.IGNORECASE)
    
    if not num_match:
        return None
    
    hr_value = int(num_match.group(1))
    min_hr, max_hr = hr_range
    
    if min_hr <= hr_value <= max_hr:
        return hr_value
    
    return None


def validate_physiology(hemodynamics: dict) -> list[str]:
    """
    Apply physiological cross-checks to extracted values.
    
    Checks:
    - RA mean < RV mean
    - RA systolic < RV systolic
    - RV systolic ≈ PA systolic (within 15 mmHg)
    - Wedge mean < RV mean
    - Wedge mean < PA mean
    
    Args:
        hemodynamics: Dictionary of extracted measurements
        
    Returns:
        List of warning messages for failed checks
    """
    warnings = []
    
    ra = hemodynamics.get('RA')
    rv = hemodynamics.get('RV')
    pa = hemodynamics.get('PA')
    wedge = hemodynamics.get('Wedge')
    
    # RA vs RV (mean)
    if ra and rv:
        if ra['mean'] >= rv['mean']:
            warnings.append(f"RA mean ({ra['mean']}) >= RV mean ({rv['mean']})")
        if ra['systolic'] >= rv['systolic']:
            warnings.append(f"RA systolic ({ra['systolic']}) >= RV systolic ({rv['systolic']})")
    
    # RV vs PA (systolic)
    if rv and pa:
        diff = abs(rv['systolic'] - pa['systolic'])
        if diff > 15:
            warnings.append(
                f"RV systolic ({rv['systolic']}) and PA systolic ({pa['systolic']}) "
                f"differ by {diff} mmHg"
            )
    
    # Wedge vs RV (mean)
    if wedge and rv:
        if wedge['mean'] >= rv['mean']:
            warnings.append(f"Wedge mean ({wedge['mean']}) >= RV mean ({rv['mean']})")
    
    # Wedge vs PA (mean)
    if wedge and pa:
        if wedge['mean'] >= pa['mean']:
            warnings.append(f"Wedge mean ({wedge['mean']}) >= PA mean ({pa['mean']})")
    
    return warnings


def determine_status(hemodynamics: dict) -> str:
    """
    Determine extraction status based on what was found.
    
    Args:
        hemodynamics: Dictionary of extracted measurements
        
    Returns:
        'OK' if all critical values found, 'PARTIAL' if some missing, 'FAILED' if none
    """
    critical = ['RA', 'RV', 'PA']
    found = sum(1 for c in critical if hemodynamics.get(c) is not None)
    
    if found == len(critical):
        return 'OK'
    elif found > 0:
        return 'PARTIAL'
    else:
        return 'FAILED'


def extract_clinical_metadata(
    adicht_path: Path,
    config: dict | None = None
) -> tuple[dict, dict]:
    """
    Main entry point for clinical metadata extraction.
    
    Extracts hemodynamic measurements from a .adicht file's embedded
    Notebook text using regex pattern matching.
    
    Args:
        adicht_path: Path to the .adicht file
        config: Optional configuration dictionary
        
    Returns:
        Tuple of (hemodynamics_dict, extraction_dict)
        
    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    adicht_path = Path(adicht_path)
    
    # Default config
    if config is None:
        config = {
            'co_range': (2.0, 20.0),
            'hr_range': (40, 200)
        }
    
    # Extract text from binary
    text = extract_text_from_adicht(adicht_path)
    lines = text.split('\n')
    
    # Extract measurements
    hemodynamics = {}
    
    # Pressures
    ra = extract_pressure(lines, 'RA')
    if ra:
        hemodynamics['RA'] = ra
    
    rv = extract_pressure(lines, 'RV')
    if rv:
        hemodynamics['RV'] = rv
    
    pa = extract_pressure(lines, 'PA')
    if pa:
        hemodynamics['PA'] = pa
    
    wedge = extract_wedge(lines)
    if wedge:
        hemodynamics['Wedge'] = wedge
    
    # CO
    co_range = config.get('co_range', (2.0, 20.0))
    co_values = extract_co(text, co_range)
    if co_values:
        hemodynamics['CO'] = co_values
    
    # HR
    hr_range = config.get('hr_range', (40, 200))
    hr_value = extract_hr(text, hr_range)
    if hr_value:
        hemodynamics['HR'] = hr_value
    
    # Validate
    warnings = validate_physiology(hemodynamics)
    
    # Determine status
    status = determine_status(hemodynamics)
    
    extraction = {
        'status': status,
        'warnings': warnings
    }
    
    return hemodynamics, extraction


def merge_with_metadata(
    metadata: dict,
    hemodynamics: dict,
    extraction: dict
) -> dict:
    """
    Merge clinical extraction results into existing metadata.
    
    Args:
        metadata: Existing metadata dictionary (from waveform ingestion)
        hemodynamics: Extracted hemodynamic measurements
        extraction: Extraction status and warnings
        
    Returns:
        Updated metadata dictionary
    """
    metadata['hemodynamics'] = hemodynamics
    metadata['extraction'] = extraction
    return metadata
