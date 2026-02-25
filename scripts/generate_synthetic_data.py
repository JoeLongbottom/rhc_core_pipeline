#!/usr/bin/env python3
"""
Generate synthetic ECG and pressure data for testing the plotting pipeline.
"""

import numpy as np
import pandas as pd
from pathlib import Path

def generate_synthetic_ecg(duration_sec=10.0, fs=1000.0, heart_rate=75):
    """Generate synthetic ECG with clear R-peaks."""
    n_samples = int(duration_sec * fs)
    t = np.arange(n_samples) / fs
    
    # Heart rate in Hz
    hr_hz = heart_rate / 60.0
    rr_interval = 1.0 / hr_hz
    
    # Generate ECG-like signal
    ecg = np.zeros(n_samples)
    
    # Add R-peaks at regular intervals
    beat_times = np.arange(0, duration_sec, rr_interval)
    
    for beat_t in beat_times:
        # Find sample index
        beat_idx = int(beat_t * fs)
        if beat_idx >= n_samples:
            break
            
        # Create QRS complex (simplified)
        for offset in range(-10, 30):
            idx = beat_idx + offset
            if 0 <= idx < n_samples:
                if offset == 0:
                    ecg[idx] = 1.0  # R-peak
                elif -5 <= offset <= -1:
                    ecg[idx] = -0.1 + 0.02 * (offset + 5)  # Q-wave
                elif 1 <= offset <= 5:
                    ecg[idx] = 0.8 - 0.16 * offset  # S-wave descent
                elif 20 <= offset <= 28:
                    ecg[idx] = 0.2 * np.sin(np.pi * (offset - 20) / 8)  # T-wave
    
    # Add some noise
    ecg += np.random.normal(0, 0.02, n_samples)
    
    return ecg


def generate_synthetic_pressure(duration_sec=10.0, fs=1000.0, heart_rate=75, 
                                systolic=45, diastolic=15):
    """Generate synthetic RV pressure waveform."""
    n_samples = int(duration_sec * fs)
    t = np.arange(n_samples) / fs
    
    hr_hz = heart_rate / 60.0
    rr_interval = 1.0 / hr_hz
    
    pressure = np.ones(n_samples) * diastolic
    
    beat_times = np.arange(0, duration_sec, rr_interval)
    samples_per_beat = int(rr_interval * fs)
    
    for beat_t in beat_times:
        beat_idx = int(beat_t * fs)
        if beat_idx >= n_samples:
            break
        
        # Create pressure waveform for this beat
        systolic_duration = int(0.35 * samples_per_beat)
        diastolic_duration = samples_per_beat - systolic_duration
        
        for i in range(systolic_duration):
            idx = beat_idx + i
            if idx >= n_samples:
                break
            # Systolic rise and fall
            phase = i / systolic_duration
            if phase < 0.3:
                # Rapid upstroke
                pressure[idx] = diastolic + (systolic - diastolic) * (phase / 0.3)
            else:
                # Gradual fall
                pressure[idx] = systolic - (systolic - diastolic) * ((phase - 0.3) / 0.7) * 0.6
    
    # Add some noise
    pressure += np.random.normal(0, 0.5, n_samples)
    
    return pressure


def main():
    print("Generating synthetic waveform data...")
    
    fs = 1000.0
    duration = 300.0
    
    ecg = generate_synthetic_ecg(duration, fs, heart_rate=72)
    pressure = generate_synthetic_pressure(duration, fs, heart_rate=72, systolic=40, diastolic=8)
    
    # Create DataFrame
    df = pd.DataFrame({
        'ecg': ecg,
        'pressure': pressure
    })
    
    # Save to output/ingested
    output_dir = Path('output/ingested')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = output_dir / 'synthetic_test.csv'
    df.to_csv(csv_path, index=False)
    print(f"Saved: {csv_path}")
    
    # Save metadata
    import json
    metadata = {
        'recording_id': 'synthetic_test',
        'waveform': {
            'sample_rate_hz': fs,
            'total_samples': len(df),
            'duration_seconds': duration
        }
    }
    
    json_path = output_dir / 'synthetic_test.json'
    with open(json_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved: {json_path}")
    
    print(f"\nGenerated {duration}s of synthetic data at {fs}Hz")
    print(f"ECG range: [{ecg.min():.2f}, {ecg.max():.2f}]")
    print(f"Pressure range: [{pressure.min():.1f}, {pressure.max():.1f}] mmHg")


if __name__ == '__main__':
    main()
