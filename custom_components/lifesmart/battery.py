"""Validate percentages for battery channels whose raw values are voltage counts."""

import math

# LifeSmart Smart Device Specification v2.32, sections 2.6.3 and 2.6.4.
# V.val is raw voltage; V.v is the converted battery percentage.
VOLTAGE_BATTERY_TYPES = {"SL_SC_WA", "SL_SC_BE"}


def battery_percentage(value):
    """Accept only finite percentages; raw voltage counts are not percentages."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return value
