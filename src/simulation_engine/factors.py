"""Experimental-factor introspection: turn a ``make_model(**factors)``
factory into a UI-ready schema, and coerce JSON edits back into kwargs.

The factory's keyword arguments *are* the model's declared factors — the same
contract ``sweep()`` varies. This module reads them via ``inspect.signature``
so a viewer (or the sidecar server) can render controls without any parallel
declaration, and rebuilds Python values (including distributions, via
``from_dict``) from what the UI posts back.

Anything that is not a factor — literals inside the factory body, lambdas —
is invisible here by design: it can be *displayed* from ``model.describe()``
but never edited.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

from .distributions import Distribution, RateSchedule, from_dict

#: FACTORS metadata keys a model.py may declare per factor.
_META_KEYS = ("label", "min", "max", "step", "options", "help")

#: Distributions offered in the UI dropdown, with ordered arg specs.
#: Empirical/Choice/RateSchedule stay deserializable via from_dict but are
#: not offered for editing — their args aren't a flat list of numbers.
_CATALOG: list[dict] = [
    {"type": "Constant", "args": [{"name": "value", "min": 0}]},
    {"type": "Uniform", "args": [{"name": "low", "min": 0}, {"name": "high", "min": 0}]},
    {"type": "Exponential", "args": [{"name": "mean", "min": 0}]},
    {"type": "Triangular", "args": [{"name": "low", "min": 0}, {"name": "mode", "min": 0}, {"name": "high", "min": 0}]},
    {"type": "Normal", "args": [{"name": "mean", "min": 0}, {"name": "sd", "min": 0}]},
    {"type": "Lognormal", "args": [{"name": "mean", "min": 0}, {"name": "sd", "min": 0}]},
    {"type": "Gamma", "args": [{"name": "shape", "min": 0}, {"name": "scale", "min": 0}]},
    {"type": "Erlang", "args": [{"name": "k", "min": 1, "integer": True}, {"name": "mean", "min": 0}]},
    {"type": "Weibull", "args": [{"name": "shape", "min": 0}, {"name": "scale", "min": 0}]},
    {"type": "Pert", "args": [{"name": "low", "min": 0}, {"name": "mode", "min": 0}, {"name": "high", "min": 0}, {"name": "lam", "min": 0}]},
]


def distribution_catalog() -> list[dict]:
    """Distribution types (and their ordered args) the UI may offer in the
    dist-type dropdown."""
    return [dict(entry, args=[dict(a) for a in entry["args"]]) for entry in _CATALOG]


def describe_factors(
    factory: Callable, overrides: dict[str, dict] | None = None
) -> list[dict]:
    """UI-ready schema for the factory's keyword arguments.

    Each entry: ``{name, kind, default}`` plus any of ``label/min/max/step/
    options/help`` declared in ``overrides`` (a model.py's optional
    module-level ``FACTORS`` dict). ``kind`` is one of ``bool | int | float |
    str | choice | distribution | schedule | fixed`` — ``fixed`` marks
    defaults this module can't rebuild from JSON (callables, arbitrary
    objects); they are shown but not editable.

    Raises ``ValueError`` for positional-only or default-less parameters —
    the factory contract is keyword args with defaults (that is what
    ``sweep()`` varies too).
    """
    overrides = overrides or {}
    unknown = set(overrides) - {
        p.name for p in inspect.signature(factory).parameters.values()
    }
    if unknown:
        raise ValueError(f"FACTORS metadata for unknown factor(s): {sorted(unknown)}")

    schema: list[dict] = []
    for p in inspect.signature(factory).parameters.values():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if p.default is inspect.Parameter.empty:
            raise ValueError(
                f"factor {p.name!r} has no default — make_model factors must be "
                f"keyword arguments with defaults"
            )
        default = p.default
        # bool before int: bool subclasses int.
        if isinstance(default, bool):
            kind, default_json = "bool", default
        elif isinstance(default, int):
            kind, default_json = "int", default
        elif isinstance(default, float):
            kind, default_json = "float", default
        elif isinstance(default, str):
            kind, default_json = "str", default
        elif isinstance(default, Distribution):
            kind, default_json = "distribution", default.to_dict()
        elif isinstance(default, RateSchedule):
            kind, default_json = "schedule", default.to_dict()
        else:
            kind, default_json = "fixed", repr(default)

        entry: dict = {"name": p.name, "kind": kind, "default": default_json}
        meta = overrides.get(p.name, {})
        bad = set(meta) - set(_META_KEYS)
        if bad:
            raise ValueError(
                f"FACTORS[{p.name!r}] has unknown key(s) {sorted(bad)}; "
                f"allowed: {list(_META_KEYS)}"
            )
        entry.update({k: meta[k] for k in _META_KEYS if k in meta})
        if "options" in entry and kind in ("bool", "int", "float", "str"):
            entry["kind"] = "choice"
        schema.append(entry)
    return schema


def coerce_factors(raw: dict, schema: list[dict]) -> dict:
    """JSON factor values from the UI -> kwargs ready for ``factory(**kwargs)``.

    Raises ``ValueError`` on unknown names, non-integral ints, values outside
    a choice's options, attempts to set a ``fixed`` factor, or a distribution
    spec ``from_dict`` rejects.
    """
    by_name = {f["name"]: f for f in schema}
    out: dict = {}
    for name, value in raw.items():
        f = by_name.get(name)
        if f is None:
            raise ValueError(
                f"unknown factor {name!r}; declared factors: {sorted(by_name)}"
            )
        kind = f["kind"]
        if kind == "fixed":
            raise ValueError(f"factor {name!r} is not editable (non-JSON default)")
        if kind == "choice":
            if value not in f["options"]:
                raise ValueError(
                    f"factor {name!r} must be one of {f['options']}, got {value!r}"
                )
            out[name] = value
        elif kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"factor {name!r} must be a bool, got {value!r}")
            out[name] = value
        elif kind == "int":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"factor {name!r} must be an integer, got {value!r}")
            if float(value) != int(value):
                raise ValueError(f"factor {name!r} must be an integer, got {value!r}")
            out[name] = int(value)
        elif kind == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"factor {name!r} must be a number, got {value!r}")
            out[name] = float(value)
        elif kind == "str":
            if not isinstance(value, str):
                raise ValueError(f"factor {name!r} must be a string, got {value!r}")
            out[name] = value
        elif kind in ("distribution", "schedule"):
            out[name] = from_dict(value)  # ValueError propagates with its message
        else:  # pragma: no cover - schema kinds are produced above
            raise ValueError(f"factor {name!r} has unhandled kind {kind!r}")
    return out
