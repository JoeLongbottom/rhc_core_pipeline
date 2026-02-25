"""
Data Dictionary Definitions

Provides column metadata for auto-generating data dictionaries in Excel exports.
"""

# Complete column metadata for all pipeline outputs
# Format: {column_name: (type, unit, description, valid_values)}
COLUMN_DEFINITIONS = {
    # Core beat identifiers
    'global_sample_idx': (
        'int', 'samples',
        'Closing R-peak position in the recording (0-indexed)',
        '—'
    ),
    'timestamp': (
        'float', 's',
        'Closing R-peak time in seconds from recording start',
        '—'
    ),
    'period_start_sample_idx': (
        'int', 'samples',
        'Opening R-peak position (-1 for first beat with no predecessor)',
        '—'
    ),
    
    # ECG features
    'sqi_average_qrs': (
        'float', '—',
        'Template matching quality score (correlation with average QRS)',
        '—'
    ),
    'rr_interval': (
        'float', 'ms',
        'Time between opening and closing R-peaks',
        '—'
    ),
    'sqi_zhao_class': (
        'str', '—',
        'Zhao2018 categorical ECG quality classification',
        'Excellent / Barely acceptable / Unacceptable'
    ),
    
    # Pressure features
    'p_max': (
        'float', 'mmHg',
        'Maximum (systolic) pressure within the beat',
        '—'
    ),
    'p_min_onset': (
        'float', 'mmHg',
        'Minimum pressure at beat onset (opening R-peak)',
        '—'
    ),
    'p_min_decay': (
        'float', 'mmHg',
        'Minimum pressure after peak (diastolic nadir)',
        '—'
    ),
    'p_mean': (
        'float', 'mmHg',
        'Mean pressure over the beat interval',
        '—'
    ),
    'pulse_pressure': (
        'float', 'mmHg',
        'Difference between p_max and p_min_onset',
        '—'
    ),
    'dpdt_max': (
        'float', 'mmHg/s',
        'Maximum positive pressure derivative (contractility proxy)',
        '—'
    ),
    'dpdt_min': (
        'float', 'mmHg/s',
        'Maximum negative pressure derivative (relaxation proxy)',
        '—'
    ),
    't_zpoint': (
        'float', 's',
        'Time from beat onset to zero-crossing of dP/dt',
        '—'
    ),
    
    # Gating statuses
    'ecg_status': (
        'str', '—',
        'ECG quality gate result for this beat',
        'VALID / NOISE_ECG / ECTOPIC_PREMATURE'
    ),
    'prev_ecg_status': (
        'str', '—',
        'ECG quality gate result for the opening beat',
        'VALID / NOISE_ECG / NO_PREDECESSOR'
    ),
    'pressure_status': (
        'str', '—',
        'Pressure quality gate result',
        'VALID / OUTLIER_PHYSIO / OUTLIER_MEDIAN / WHIP_ARTIFACT / OUTLIER_JUMP'
    ),
    'interval_status': (
        'str', '—',
        'Combined gate result for the beat interval',
        'ACCEPTED / REJECT_ECG / REJECT_PRESSURE / REJECT_GAP'
    ),
    
    # Classification
    'anatomical_loc': (
        'str', '—',
        'Anatomical chamber classification based on pressure morphology',
        'RV / PA / UNCERTAIN'
    ),
    'epoch_id': (
        'int', '—',
        'Autonomic epoch identifier (-1 = not in any valid epoch)',
        '-1, 0, 1, 2, ...'
    ),
}

# Definitions for Clinical Indices (summary statistics)
CLINICAL_INDICES_DEFINITIONS = {
    # Waveform
    'sPAP': ('float', 'mmHg', 'Systolic Pulmonary Artery Pressure (mean of p_max)', '—'),
    'dPAP': ('float', 'mmHg', 'Diastolic Pulmonary Artery Pressure (mean of p_min_decay)', '—'),
    'mPAP': ('float', 'mmHg', 'Mean Pulmonary Artery Pressure (mean of p_mean)', '—'),
    'PP': ('float', 'mmHg', 'Pulse Pressure (mean of pulse_pressure)', '—'),
    'sRVP': ('float', 'mmHg', 'Systolic RV Pressure (mean of p_max)', '—'),
    'dRVP': ('float', 'mmHg', 'Diastolic RV Pressure (mean of p_min_onset)', '—'),
    'n_PA': ('int', '—', 'Number of accepted PA beats used for calculation', '—'),
    'n_RV': ('int', '—', 'Number of accepted RV beats used for calculation', '—'),

    # Variability
    'sPAP_SD': ('float', 'mmHg', 'Standard deviation of sPAP', '—'),
    'sPAP_CV': ('float', '%', 'Coefficient of variation of sPAP', '—'),
    'dPAP_SD': ('float', 'mmHg', 'Standard deviation of dPAP', '—'),
    'PP_SD': ('float', 'mmHg', 'Standard deviation of PP', '—'),

    # Derived
    'TPG': ('float', 'mmHg', 'Transpulmonary Gradient (mPAP - mPCWP)', '—'),
    'DPG': ('float', 'mmHg', 'Diastolic Pressure Gradient (dPAP - mPCWP)', '—'),
    'PVR': ('float', 'dyn·s·cm⁻⁵', 'Pulmonary Vascular Resistance', '—'),
    'PVR_WU': ('float', 'WU', 'Pulmonary Vascular Resistance (Wood Units)', '—'),
    
    # Dual PAC/RC Indices
    'PAC_ref': ('float', 'mL/mmHg', 'Pulmonary Arterial Compliance (using SV_ref)', '—'),
    'PAC_calc': ('float', 'mL/mmHg', 'Pulmonary Arterial Compliance (using SV_calc)', '—'),
    'RC_time_ref': ('float', 'ms', 'RC Time Constant (using PAC_ref)', '—'),
    'RC_time_calc': ('float', 'ms', 'RC Time Constant (using PAC_calc)', '—'),

    # Metadata Reference / Calculated
    'mCO_ref': ('float', 'L/min', 'Mean Cardiac Output (reference from metadata)', '—'),
    'CO_measurements': ('str', '—', 'Raw Cardiac Output measurements (comma-separated)', '—'),
    'HR_ref': ('float', 'bpm', 'Heart Rate (reference from metadata)', '—'),
    'HR_calc': ('float', 'bpm', 'Heart Rate (calculated from waveform RR)', '—'),
    'SV_ref': ('float', 'mL', 'Stroke Volume (derived from mCO_ref/HR_ref)', '—'),
    'SV_calc': ('float', 'mL', 'Stroke Volume (derived from mCO_ref/HR_calc)', '—'),
    'mPCWP_ref': ('float', 'mmHg', 'Mean Wedge Pressure (reference)', '—'),
}

# Definitions for Autonomic Indices (Spec 08, per-epoch)
AUTONOMIC_INDICES_DEFINITIONS = {
    # Epoch metadata
    'epoch_id': ('int', '—', 'Epoch identifier (or Mean for the summary row)', '-1, 0, 1, 2...'),
    'duration_sec': ('float', 's', 'Epoch duration in seconds', '—'),
    'n_beats': ('int', '—', 'Number of accepted beats in the epoch', '—'),

    # Time-Domain HRV
    'Mean_RR': ('float', 'ms', 'Mean RR interval', '—'),
    'SDNN': ('float', 'ms', 'Standard deviation of RR', '—'),
    'RMSSD': ('float', 'ms', 'Root mean square of successive differences', '—'),
    'pNN50': ('float', '%', 'Percentage of |ΔRR| > 50ms', '—'),
    
    # Time-Domain Pressure Variability
    'SDSBP': ('float', 'mmHg', 'Systolic BP variability (std of p_max)', '—'),
    'PP_CV': ('float', '%', 'Pulse pressure coefficient of variation', '—'),

    # Frequency-Domain (Welch)
    'Total_Power_RR': ('float', 'ms²', 'Integrated LF + HF power — Welch', '—'),
    'LF_Power_RR': ('float', 'ms²', 'Integrated LF power — Welch', '—'),
    'HF_Power_RR': ('float', 'ms²', 'Integrated HF power — Welch', '—'),
    'LF_HF_Ratio': ('float', '—', 'LF / HF ratio', '—'),
    'LF_Power_sPAP': ('float', 'mmHg²', 'Integrated LF power of sPAP — Welch', '—'),
    'HF_Power_sPAP': ('float', 'mmHg²', 'Integrated HF power of sPAP — Welch', '—'),

    # Coherence (Spec §5.4)
    'LF_Weighted_Coherence': ('float', '0–1', 'sPAP power-weighted mean coherence in LF band', '—'),
    'HF_Weighted_Coherence': ('float', '0–1', 'sPAP power-weighted mean coherence in HF band', '—'),
    'LF_Coh_Significant': ('int', '1/0', 'Is LF_Weighted_Coherence > mean-band significance threshold?', '0, 1'),
    'HF_Coh_Significant': ('int', '1/0', 'Is HF_Weighted_Coherence > mean-band significance threshold?', '0, 1'),

    # Baroreflex Sensitivity (BRS)
    'BRS_Up_Slope_lag0': ('float', 'ms/mmHg', 'Up-sequence BRS slope at lag 0', '—'),
    'BRS_Up_Slope_lag1': ('float', 'ms/mmHg', 'Up-sequence BRS slope at lag 1', '—'),
    'BRS_Up_Slope_lag2': ('float', 'ms/mmHg', 'Up-sequence BRS slope at lag 2', '—'),
    'BRS_Up_Slope_lag3': ('float', 'ms/mmHg', 'Up-sequence BRS slope at lag 3', '—'),
    'BRS_Down_Slope_lag0': ('float', 'ms/mmHg', 'Down-sequence BRS slope at lag 0', '—'),
    'BRS_Down_Slope_lag1': ('float', 'ms/mmHg', 'Down-sequence BRS slope at lag 1', '—'),
    'BRS_Down_Slope_lag2': ('float', 'ms/mmHg', 'Down-sequence BRS slope at lag 2', '—'),
    'BRS_Down_Slope_lag3': ('float', 'ms/mmHg', 'Down-sequence BRS slope at lag 3', '—'),
    'BRS_Up_Seq_lag0': ('int', '—', 'Valid up-sequence count at lag 0', '—'),
    'BRS_Up_Seq_lag1': ('int', '—', 'Valid up-sequence count at lag 1', '—'),
    'BRS_Up_Seq_lag2': ('int', '—', 'Valid up-sequence count at lag 2', '—'),
    'BRS_Up_Seq_lag3': ('int', '—', 'Valid up-sequence count at lag 3', '—'),
    'BRS_Down_Seq_lag0': ('int', '—', 'Valid down-sequence count at lag 0', '—'),
    'BRS_Down_Seq_lag1': ('int', '—', 'Valid down-sequence count at lag 1', '—'),
    'BRS_Down_Seq_lag2': ('int', '—', 'Valid down-sequence count at lag 2', '—'),
    'BRS_Down_Seq_lag3': ('int', '—', 'Valid down-sequence count at lag 3', '—'),

    # Frequency-Domain (Lomb-Scargle)
    'LF_Power_RR_LS': ('float', 'ms²', 'Integrated LF power — Lomb-Scargle', '—'),
    'HF_Power_RR_LS': ('float', 'ms²', 'Integrated HF power — Lomb-Scargle', '—'),
    'LF_HF_Ratio_LS': ('float', '—', 'LF / HF ratio — Lomb-Scargle', '—'),
}


def get_data_dictionary_df():
    """
    Generate a DataFrame containing the data dictionary.
    
    Returns:
        pd.DataFrame with columns: Column, Type, Unit, Description, Valid Values
    """
    import pandas as pd
    
    rows = []
    for col_name, (dtype, unit, desc, valid) in COLUMN_DEFINITIONS.items():
        rows.append({
            'Column': col_name,
            'Type': dtype,
            'Unit': unit,
            'Description': desc,
            'Valid Values': valid
        })
    
    return pd.DataFrame(rows)


def save_combined_excel(
    df,
    output_path,
    run_metadata: dict = None,
    pqrst_df=None,
    clinical_indices: dict = None,
    autonomic_results: dict = None
):
    """
    Save combined beats DataFrame to Excel with Data Dictionary and Clinical Indices sheets.
    
    Args:
        df: Combined beats DataFrame
        output_path: Path to save .xlsx file
        run_metadata: Optional dict with pipeline version, config hash, etc.
        pqrst_df: Optional PQRST delineation DataFrame
        clinical_indices: Optional dict of calculated clinical indices
        autonomic_results: Optional dict from calculate_autonomic_indices()
    """
    import pandas as pd
    from pathlib import Path
    
    output_path = Path(output_path)
    
    # Generate data dictionary for columns present in df
    dict_rows = []
    
    # 1. Beat metrics (columns in the dataframe)
    for col in df.columns:
        if col in COLUMN_DEFINITIONS:
            dtype, unit, desc, valid = COLUMN_DEFINITIONS[col]
        else:
            dtype, unit, desc, valid = 'unknown', '—', 'Undocumented column', '—'
        dict_rows.append({
            'Scope': 'Beat Features',
            'Name': col,
            'Type': dtype,
            'Unit': unit,
            'Description': desc,
            'Valid Values': valid
        })
        
    # 2. Clinical Indices (if present)
    if clinical_indices:
        for key, (dtype, unit, desc, valid) in CLINICAL_INDICES_DEFINITIONS.items():
            dict_rows.append({
                'Scope': 'Clinical Indices',
                'Name': key,
                'Type': dtype,
                'Unit': unit,
                'Description': desc,
                'Valid Values': valid
            })
            
    # 3. Autonomic Indices (if present)
    if autonomic_results:
        for key, (dtype, unit, desc, valid) in AUTONOMIC_INDICES_DEFINITIONS.items():
            dict_rows.append({
                'Scope': 'Autonomic Indices',
                'Name': key,
                'Type': dtype,
                'Unit': unit,
                'Description': desc,
                'Valid Values': valid
            })
            
    dict_df = pd.DataFrame(dict_rows)
    
    # Prepare Clinical Indices DataFrame if available
    clinical_df = None
    if clinical_indices:
        clinical_rows = []
        
        # Helper to add section rows
        def add_section(section_name, data_dict):
            for key, val in data_dict.items():
                unit = '—'
                # Infer unit based on key
                if '_CV' in key: unit = '%'
                elif 'PVR_WU' in key: unit = 'WU'
                elif 'PVR' in key: unit = 'dyn·s·cm⁻⁵'
                elif 'CO' in key: unit = 'L/min'
                elif 'SV' in key: unit = 'mL'
                elif 'HR' in key: unit = 'bpm'
                elif 'PAC' in key: unit = 'mL/mmHg'
                elif 'RC_time' in key: unit = 'ms'
                elif any(x in key for x in ['PAP', 'RVP', 'RAP', 'PCWP', 'TPG', 'DPG', 'PP', '_SD']): unit = 'mmHg'
                
                clinical_rows.append({
                    'Category': section_name,
                    'Index': key,
                    'Value': val,
                    'Unit': unit
                })

        if 'waveform' in clinical_indices: add_section('Waveform', clinical_indices['waveform'])
        if 'variability' in clinical_indices: add_section('Variability', clinical_indices['variability'])
        if 'derived' in clinical_indices: add_section('Derived', clinical_indices['derived'])
        if 'reference' in clinical_indices: add_section('Reference', clinical_indices['reference'])
        if 'quality' in clinical_indices: add_section('Quality', clinical_indices['quality'])
        
        clinical_df = pd.DataFrame(clinical_rows)
    
    # Write to Excel with multiple sheets
    # Order: Beats -> Clinical Indices -> PQRST Features -> Data Dictionary -> Metadata
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Beats', index=False)
        
        if clinical_df is not None:
            clinical_df.to_excel(writer, sheet_name='Clinical Indices', index=False)

        # Optional PQRST sheet (before Data Dictionary)
        if pqrst_df is not None and len(pqrst_df) > 0:
            pqrst_df.to_excel(writer, sheet_name='PQRST Features', index=False)
        
        # Autonomic Indices sheet (per-epoch summary + Mean row)
        try:
            if autonomic_results and 'epoch_results' in autonomic_results:
                epoch_df = autonomic_results['epoch_results']
                if len(epoch_df) > 0:
                    epoch_df.to_excel(writer, sheet_name='Autonomic Indices', index=False)
            
            # Epoch Data sheet (raw beats with NaN markers)
            if autonomic_results and 'epoch_data' in autonomic_results:
                ep_data = autonomic_results['epoch_data']
                if len(ep_data) > 0:
                    ep_data.to_excel(writer, sheet_name='Epoch Data', index=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Autonomic sheets could not be written (non-critical): {e}"
            )
            
        dict_df.to_excel(writer, sheet_name='Data Dictionary', index=False)
        
        # Optional metadata sheet
        if run_metadata:
            meta_df = pd.DataFrame([
                {'Key': k, 'Value': str(v)} 
                for k, v in run_metadata.items()
            ])
            meta_df.to_excel(writer, sheet_name='Metadata', index=False)

