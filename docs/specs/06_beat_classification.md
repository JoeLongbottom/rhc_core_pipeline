# Beat Classification Specification

## 1. Purpose

Classify each validated beat by anatomical location based on haemodynamic pressure features.

> [!NOTE]
> **Current Scope: PA-Only**
> 
> This module positively identifies **Pulmonary Artery (PA)** beats only. All other beats are marked as **UNCERTAIN**. Future work will extend classification to RV, RA, and Wedge.

---

## 2. Input

This module runs **after** beat gating.

| Source | Fields Used |
|--------|-------------|
| `pressure_features` | `p_max`, `p_min_decay` |
| `beat_gating` | `pressure_status` (filter: `VALID` only) |

---

## 3. Classification Logic

### Phase A: Active Beat Check

Determine if the beat has sufficient pressure generation to classify reliably.

1. **Reference Population**: Beats where `p_max > sys_hard_floor` (default: 25 mmHg)
2. **Operating Pressure**: $P_{ref} = \text{Percentile}_{75}(P_{max})$
3. **Active Threshold**: $P_{active} = P_{ref} \times (1 - \text{tolerance})$
4. **Pulse Pressure Threshold**: $PP_{min} = P_{active} \times \text{pp\_fraction}$

Beats are marked **UNCERTAIN** if:
- `p_max < P_active` OR
- `pulse_pressure < PP_min`

### Phase B: PA Identification (Diastolic Check)

For beats passing Phase A, check if diastolic pressure is maintained:

**Adaptive Threshold**:
$$P_{dia\_thresh} = \max(P_{active} \times \text{dia\_factor}, \text{dia\_floor})$$

| Result | Condition |
|--------|-----------|
| **PA** | `p_min_decay >= P_dia_thresh` |
| **UNCERTAIN** | Otherwise |

**Rationale**: In PA, the pulmonic valve closes after systole, maintaining diastolic pressure. This distinguishes PA from RV (where pressure drops to near-zero).

---

## 4. Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `sys_hard_floor` | 25 | Minimum p_max for reference population (mmHg) |
| `sys_ref_percentile` | 75 | Percentile for operating pressure |
| `sys_tolerance` | 0.25 | Tolerance below operating pressure (25%) |
| `pp_fraction` | 0.30 | Min Pulse Pressure as fraction of P_active |
| `dia_factor` | 0.25 | Fraction of P_active for diastolic threshold |
| `dia_floor` | 8.0 | Absolute minimum diastolic threshold (mmHg) |

---

## 5. Output

| Column | Type | Values | Description |
|--------|------|--------|-------------|
| `anatomical_loc` | string | `PA`, `UNCERTAIN` | Classified location |

---

## 6. Adjacency Check

To prevent noisy "active" beats from being misclassified as PA, we enforce a **continuity rule**:

> **A PA beat must be adjacent to at least one other PA beat.**

Isolated PA beats (sequences of length 1) are reclassified as **UNCERTAIN**. This aligns with the physical reality that the catheter cannot instantly jump into the PA for a single beat and then immediately exit.

---

## 7. Future Work

- **RV Classification**: Identify beats where `p_min_decay` drops to near-zero
- **RA/Wedge Classification**: Low mean pressure, low pulse pressure patterns
