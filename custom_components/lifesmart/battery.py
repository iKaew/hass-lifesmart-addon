"""Validate percentages for battery channels whose raw values are voltage counts."""

import math

# LifeSmart Local Interfaces (2023-09-26), sections 6.6.1–6.6.4.
# These V channels document v as the percentage. Raw val is not a substitute.
VOLTAGE_BATTERY_TYPES = {
    "SL_SC_WA",
    "SL_SC_BE",
    "SL_SC_G",
    "SL_SC_BG",
    "SL_SC_MHW",
    "SL_SC_BM",
    "SL_SC_CM",
}


def battery_percentage(value):
    """Accept only finite percentages; raw voltage counts are not percentages."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return value
