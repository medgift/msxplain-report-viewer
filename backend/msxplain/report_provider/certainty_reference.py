"""Test-set reference distributions used to express certainty as a percentile.

Shared by the report API (app.py) and the DCM-SEG label builder
(msxplain_report.py) so the percentile shown in OHIF matches the report.

  PSU_data.csv – patient-level: column 'PSC' (certainty = 1 − PSU)
  LLU_data.csv – lesion-level: column 'LLU' (uncertainty); certainty = 1 − LLU
"""
import logging
import math
import os
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

_CONFIGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs")
PSU_DATA_FILEPATH = os.path.join(_CONFIGS_DIR, "PSU_data.csv")
LLU_DATA_FILEPATH = os.path.join(_CONFIGS_DIR, "LLU_data.csv")


@lru_cache(maxsize=8)
def load_reference_certainties(filepath: str, value_col: str, invert: bool) -> Optional[np.ndarray]:
    """Load a pooled reference distribution of certainty values from the test set.

    The result is cached per (filepath, value_col, invert): reference
    distributions are static deployment artifacts, so this avoids re-parsing the
    CSV on every call. A missing file caches as None for the process lifetime —
    provision the CSV before startup, or restart after adding.

    Args:
        filepath: Path to the reference CSV.
        value_col: Column to read (e.g. 'PSC' for patient-level, 'LLU' for lesion-level).
        invert: If True, the column holds uncertainty and certainty = 1 − value.

    Returns:
        np.ndarray of certainty values (0–1), or None if unavailable.
    """
    try:
        if not os.path.exists(filepath):
            logger.warning(f"Reference distribution not found: {filepath}")
            return None
        ref_df = pd.read_csv(filepath)
        if value_col not in ref_df.columns:
            logger.warning(f"Column '{value_col}' missing in {filepath}")
            return None
        values = pd.to_numeric(ref_df[value_col], errors='coerce').dropna().to_numpy()
        if values.size == 0:
            return None
        return 1.0 - values if invert else values
    except Exception as e:
        logger.warning(f"Could not load reference distribution {filepath}: {e}")
        return None


def patient_certainty_reference() -> Optional[np.ndarray]:
    return load_reference_certainties(PSU_DATA_FILEPATH, "PSC", invert=False)


def lesion_certainty_reference() -> Optional[np.ndarray]:
    return load_reference_certainties(LLU_DATA_FILEPATH, "LLU", invert=True)


def percentile_of(certainty: Optional[float], reference: Optional[np.ndarray]) -> Optional[float]:
    """Return the percentile (0–100) of a certainty value within a reference distribution.

    Higher certainty → higher percentile (i.e. "X % of the population scored lower").
    Returns None when the value or reference data is unavailable.
    """
    if certainty is None or reference is None or reference.size == 0:
        return None
    try:
        if pd.isna(certainty):
            return None
        return round(float(stats.percentileofscore(reference, certainty, kind='mean')), 1)
    except Exception as e:
        logger.warning(f"Could not compute percentile: {e}")
        return None


def format_percentile(p: float) -> str:
    """Percentile (0–100) → rounded ordinal label, e.g. 72.6 → "73rd".

    Mirrors ``formatPercentile`` in frontend/src/components/CertaintyGaussian.js.
    """
    n = int(math.floor(p + 0.5))  # JS Math.round semantics (Python round() is banker's)
    if 11 <= n % 100 <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"
