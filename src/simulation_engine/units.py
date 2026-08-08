"""Time units.

Every model declares a base time unit (e.g. ``"minutes"``). All durations
inside the engine are plain floats expressed in that base unit; these helpers
exist so model code can say ``m.hours(2)`` instead of ``120``.
"""

from __future__ import annotations

# Conversion factors to seconds.
_SECONDS_PER: dict[str, float] = {
    "milliseconds": 1e-3,
    "seconds": 1.0,
    "minutes": 60.0,
    "hours": 3600.0,
    "days": 86400.0,
    "weeks": 604800.0,
}

ALIASES: dict[str, str] = {
    "ms": "milliseconds",
    "millisecond": "milliseconds",
    "s": "seconds",
    "sec": "seconds",
    "second": "seconds",
    "min": "minutes",
    "minute": "minutes",
    "h": "hours",
    "hr": "hours",
    "hour": "hours",
    "d": "days",
    "day": "days",
    "w": "weeks",
    "week": "weeks",
}


def canonical(unit: str) -> str:
    u = unit.strip().lower()
    u = ALIASES.get(u, u)
    if u not in _SECONDS_PER:
        raise ValueError(
            f"Unknown time unit {unit!r}. Known units: {sorted(_SECONDS_PER)}"
        )
    return u


def convert(value: float, from_unit: str, to_unit: str) -> float:
    """Convert ``value`` between two time units."""
    return value * _SECONDS_PER[canonical(from_unit)] / _SECONDS_PER[canonical(to_unit)]


class TimeUnit:
    """A declared base time unit with conversion helpers.

    >>> tu = TimeUnit("minutes")
    >>> tu.hours(2)
    120.0
    >>> tu.seconds(30)
    0.5
    """

    def __init__(self, base: str):
        self.base = canonical(base)

    def __call__(self, value: float, unit: str) -> float:
        return convert(value, unit, self.base)

    def milliseconds(self, v: float) -> float:
        return convert(v, "milliseconds", self.base)

    def seconds(self, v: float) -> float:
        return convert(v, "seconds", self.base)

    def minutes(self, v: float) -> float:
        return convert(v, "minutes", self.base)

    def hours(self, v: float) -> float:
        return convert(v, "hours", self.base)

    def days(self, v: float) -> float:
        return convert(v, "days", self.base)

    def weeks(self, v: float) -> float:
        return convert(v, "weeks", self.base)

    def __repr__(self) -> str:
        return f"TimeUnit({self.base!r})"
