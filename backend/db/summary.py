"""Shared derivation of report-summary metrics from ``report.csv``.

Used by BOTH the live pipeline (on session completion) and the backfill script,
so the two never disagree. Percentiles are intentionally left out — they depend
on reference-population files and are computed on demand in ``get_report``.
"""
import os
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_LESION_TYPE_TO_COLUMN = {
    "Periventricular": "count_periventricular",
    "Juxtacortical": "count_juxtacortical",
    "Infratentorial": "count_infratentorial",
    "Deep White Matter": "count_deep_white_matter",
    "False Positive": "count_false_positive",
}


def compute_report_summary(session_path: str) -> Optional[dict]:
    """Return summary metrics for a processed session, or None if no report."""
    report_path = os.path.join(session_path, "report.csv")
    if not os.path.exists(report_path):
        return None

    try:
        df = pd.read_csv(report_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read report.csv at %s: %s", report_path, exc)
        return None

    counts = (
        df["Lesion Type"].value_counts().to_dict()
        if "Lesion Type" in df.columns
        else {}
    )
    summary = {
        col: int(counts.get(name, 0))
        for name, col in _LESION_TYPE_TO_COLUMN.items()
    }

    if "Lesion Volume" in df.columns and "Lesion Type" in df.columns:
        vol = df.loc[df["Lesion Type"] != "False Positive", "Lesion Volume"].sum()
        summary["total_lesion_volume"] = float(vol)
    else:
        summary["total_lesion_volume"] = 0.0

    # McDonald dissemination in space: ≥2 of the 4 true-lesion regions involved.
    regions = [
        summary["count_periventricular"],
        summary["count_juxtacortical"],
        summary["count_infratentorial"],
        summary["count_deep_white_matter"],
    ]
    affected = sum(1 for r in regions if r > 0)
    summary["dissemination_space"] = (
        "Fulfilled" if affected >= 2 else "Not fulfilled"
    )

    # Patient-level certainty = 1 − PSU (from the first row).
    patient_certainty = None
    if "PSU" in df.columns and not df.empty:
        psu = df["PSU"].iloc[0]
        if pd.notna(psu):
            patient_certainty = round(1.0 - float(psu), 6)
    summary["patient_certainty"] = patient_certainty

    return summary
