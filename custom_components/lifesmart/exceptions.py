"""Exceptions raised by the LifeSmart integration."""


class LifeSmartError(Exception):
    """Base LifeSmart integration error."""


class LifeSmartCannotConnect(LifeSmartError):
    """Raised when the LifeSmart service cannot be reached."""


class LifeSmartInvalidAuth(LifeSmartError):
    """Raised when LifeSmart rejects the supplied credentials."""
