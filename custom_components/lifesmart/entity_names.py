"""Resolve device-relative channel names reported by LifeSmart."""


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


def resolve_sensor_channel_name(name: str | None, channel: str) -> str | None:
    """Return a custom sensor name, or None to use its translated function.

    Only the default template for this channel is treated as a function name.
    Unknown template suffixes retain the channel ID as a safe fallback.
    """
    if name in (None, "", "none", channel):
        return None
    if isinstance(name, str) and name.startswith("{$EPN}"):
        suffix = name.removeprefix("{$EPN}").strip()
        if suffix in ("", channel, "{" + channel + "}"):
            return None
    return resolve_channel_name(name, channel)
