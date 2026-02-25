# Pressure Features Specification

## 1. Purpose

Extract haemodynamic features from Right Ventricular (RV) and Pulmonary Artery (PA) pressure waveforms. The algorithms are designed to be robust against respiratory baseline drift, catheter whip (ringing), and arrhythmia.

---

## 2. Signal Conditioning

| Stage | Filter Type | Parameters | Purpose |
|-------|-------------|------------|---------| 
| **Pressure** | Low-Pass Butterworth | Cutoff: 20 Hz, Order: 4 | Remove high-frequency noise while preserving waveform shape. |
| **Velocity ($dP/dt$)** | Savitzky-Golay | Window: 25ms (or dynamic 0.05 $\times$ RR)<br>Polyorder: 2, Deriv: 1 | Calculate smooth derivative. |

---

## 3. Beat Processing Logic (Per Beat)

### Anchor Concept ("Closing Index" Aligned)
All features for Beat $i$ are calculated within the specific interval defined by the **Previous R-peak ($i-1$)** and the **Current R-peak ($i$)**.

*   **Window Start**: $R\_peak_{i-1}$ (Exclusive)
*   **Window End**: $R\_peak_i$ (Inclusive)

> **Note**: Beat $i=0$ is skipping as it has no valid start pillar.

### Step 3.1: Global Maximum ($P_{max}$)
*   **Search Window**: $[R\_peak_{i-1}, R\_peak_i]$
*   **Method**: Find Global Maximum Pressure in window.
*   **Feature**: `p_max`

### Step 3.2: Maximum Upstroke Slope ($dP/dt_{max}$)
*   **Search Window**: Strictly the **Upstroke Window** $[R\_peak_{i-1}, P_{max\_idx}]$.
*   **Method**: Find the maximum value of the derivative ($dP/dt$) within this window.
*   **Feature**: `dpdt_max`

### Step 3.3: Upstroke Minimum ($P_{min\_onset}$)
*   **Search Window**: Same Upstroke Window $[R\_peak_{i-1}, P_{max\_idx}]$.
*   **Method**: Find the minimum value of the pressure within this window
*   **Feature**: `p_min_onset`

### Step 3.4: Z-Point Timing ($T_{zpoint}$)

* **Method**: $T_{zpoint} = T_{dp/dt\_max} - \left( \frac{P_{dp/dt\_max} - P_{min\_onset}}{ \frac{dP}{dt}_{max} } \right)$
* **Feature**: `t_zpoint`
* **Note**: accurately identifies the **start time** of ventricular contraction.
* **Context**: While we already know the onset *pressure* (Step 3.3), the onset *time* is often obscured by a-waves. This calculation ignores that and geometrically approximates the end diastolic time point.

### Step 3.5: Pulse Pressure ($P_{pulse}$)
*   **Formula**: $P_{pulse} = P_{max} - P_{min\_onset}.
*   **Feature**: `pulse_pressure`

### Step 3.6: Maximum Downstroke Slope ($dP/dt_{min}$)
* **Window Start**: $P_{max\_idx}$.
* **Window End**: $R\_peak_i$.
* **Method**: Find the minimum value (most negative) of the derivative ($dP/dt$) within this window.
* **Feature**: `dpdt_min`

### Step 3.7: Decay Minimum ($P_{min\_decay}$)
*   **Search Window**: $[P_{max\_idx}, R\_peak_i]$ (The Descent Phase).
*   **Method**: Find the minimum pressure value within this window.
*   **Feature**: `p_min_decay`
*   **Context**: In RV, this should drop near zero, PA will stay significantly raised. 

---

## 4. Additional Features

*   **Mean Pressure (`p_mean`)**: Mean of pressure between $R\_peak_{i-1}$ and $R\_peak_i$.

---

## 5. Output Schema

| Feature | Units | Description |
| :--- | :--- | :--- |
| `global_sample_idx` | int | Absolute index of closing R-peak ($i$). |
| `p_max` | mmHg | Maximum pressure in the cycle (Systolic Peak) |
| `dpdt_max` | mmHg/s | Maximum positive derivative in upstroke |
| `p_min_onset` | mmHg | Minimum pressure in the Upstroke Corridor |
| `period_start_sample_idx` | int | Absolute index of opening R-peak ($i-1$). |
| `t_zpoint` | s | Time of the back-projected tangent intersection (Z-Point) |
| `pulse_pressure` | mmHg | P_max minus P_min_onset |
| `dpdt_min` | mmHg/s | Minimum negative derivative in the descent |
| `p_min_decay` | mmHg | Minimum pressure in the descent phase ($P_{max} \to End$) |
| `p_mean` | mmHg | Mean Pressure over full cycle |
