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
