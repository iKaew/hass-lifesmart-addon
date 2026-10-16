"""Resolve device-relative channel names reported by LifeSmart."""

# LifeSmart Smart Device Specification v2.32, sections 2.6.3–2.6.6.
# Device classes alone cannot distinguish multiple inputs or measurements.
SENSOR_FUNCTION_CHANNELS = {
    "SL_SC_BE": ("T", "H", "Z", "V"),
    "SL_SC_WA": ("WA", "V"),
    "SL_SC_CP": ("P1", "P2", "P3"),
    "SL_SC_CH": ("P1", "P2", "P3"),
}


def resolve_channel_name(name: str | None, channel: str) -> str | None:
    """Remove the device-name template prefix without repeating the HA device name."""
    if not isinstance(name, str) or not name.startswith("{$EPN}"):
        return name

    channel_name = name.removeprefix("{$EPN}").strip()
    if not channel_name:
        # O is the outlet's main control; other ports must remain distinguishable.
        return None if channel == "O" else channel
    if "{" in channel_name or "}" in channel_name:
        # Unknown template tokens must not become literal entity names.
        return channel
    return channel_name


def resolve_sensor_channel_name(
    name: str | None, channel: str, device_type: str
) -> str | None:
    """Preserve channel names unless a documented function can be translated.

    None opts into a translated function for an explicitly mapped model/channel.
    Other default names and unknown templates fall back to the channel ID.
    """
    default_name: str | None = channel
    if channel in SENSOR_FUNCTION_CHANNELS.get(device_type, ()):
        default_name = None

    if name in (None, "", "none", channel):
        return default_name
    if isinstance(name, str) and name.startswith("{$EPN}"):
        suffix = name.removeprefix("{$EPN}").strip()
        if suffix in ("", channel, "{" + channel + "}"):
            return default_name
    return resolve_channel_name(name, channel)
