"""Factor introspection: the make_model(**factors) signature becomes a UI
schema, and JSON edits coerce back into kwargs (distributions included)."""

import json

import pytest

from simulation_engine.distributions import Exponential, RateSchedule, Triangular
from simulation_engine.factors import (
    coerce_factors,
    describe_factors,
    distribution_catalog,
)


def factory(
    n_counters: int = 2,
    arrival_rate: float = 0.5,
    priority_lane: bool = False,
    discipline: str = "fifo",
    service_time=Exponential(mean=4.0),
    day=RateSchedule([(0, 0.5), (180, 1.2)], cycle=480),
    on_create=lambda e: e,
):
    return None


def test_kinds_inferred_from_defaults():
    schema = describe_factors(factory)
    kinds = {f["name"]: f["kind"] for f in schema}
    assert kinds == {
        "n_counters": "int",
        "arrival_rate": "float",
        "priority_lane": "bool",  # bool checked before int
        "discipline": "str",
        "service_time": "distribution",
        "day": "schedule",
        "on_create": "fixed",
    }
    by_name = {f["name"]: f for f in schema}
    assert by_name["service_time"]["default"] == {
        "type": "Exponential",
        "args": {"mean": 4.0},
    }
    assert by_name["day"]["default"]["type"] == "RateSchedule"


def test_overrides_merge_and_options_flip_to_choice():
    schema = describe_factors(
        factory,
        {
            "n_counters": {"label": "Counters", "min": 1, "max": 5, "step": 1},
            "discipline": {"options": ["fifo", "lifo"]},
        },
    )
    by_name = {f["name"]: f for f in schema}
    assert by_name["n_counters"]["label"] == "Counters"
    assert by_name["n_counters"]["max"] == 5
    assert by_name["discipline"]["kind"] == "choice"


def test_overrides_reject_unknown_factor_and_key():
    with pytest.raises(ValueError, match="unknown factor"):
        describe_factors(factory, {"nope": {"min": 0}})
    with pytest.raises(ValueError, match="unknown key"):
        describe_factors(factory, {"n_counters": {"colour": "red"}})


def test_missing_default_raises():
    def bad(x):
        return None

    with pytest.raises(ValueError, match="no default"):
        describe_factors(bad)


def test_coerce_round_trips_through_json():
    schema = describe_factors(factory, {"discipline": {"options": ["fifo", "lifo"]}})
    raw = json.loads(
        json.dumps(
            {
                "n_counters": 3,
                "arrival_rate": 0.8,
                "priority_lane": True,
                "discipline": "lifo",
                "service_time": {"type": "Triangular", "args": {"low": 2, "mode": 4, "high": 9}},
            }
        )
    )
    kwargs = coerce_factors(raw, schema)
    assert kwargs["n_counters"] == 3 and isinstance(kwargs["n_counters"], int)
    assert kwargs["arrival_rate"] == 0.8 and isinstance(kwargs["arrival_rate"], float)
    assert kwargs["priority_lane"] is True
    assert kwargs["discipline"] == "lifo"
    assert isinstance(kwargs["service_time"], Triangular)
    assert kwargs["service_time"].mode == 4.0


def test_coerce_rejections():
    schema = describe_factors(factory, {"discipline": {"options": ["fifo", "lifo"]}})
    with pytest.raises(ValueError, match="unknown factor"):
        coerce_factors({"ghost": 1}, schema)
    with pytest.raises(ValueError, match="must be an integer"):
        coerce_factors({"n_counters": 2.5}, schema)
    with pytest.raises(ValueError, match="must be one of"):
        coerce_factors({"discipline": "random"}, schema)
    with pytest.raises(ValueError, match="not editable"):
        coerce_factors({"on_create": 1}, schema)
    with pytest.raises(ValueError, match="unknown distribution type"):
        coerce_factors({"service_time": {"type": "Nope"}}, schema)
    with pytest.raises(ValueError, match="must be a bool"):
        coerce_factors({"priority_lane": 1}, schema)


def test_int_kind_accepts_integral_float_from_json():
    schema = describe_factors(factory)
    assert coerce_factors({"n_counters": 3.0}, schema)["n_counters"] == 3


def test_distribution_catalog_shape():
    cat = distribution_catalog()
    types = [e["type"] for e in cat]
    assert "Exponential" in types and "Empirical" not in types
    exp = next(e for e in cat if e["type"] == "Exponential")
    assert [a["name"] for a in exp["args"]] == ["mean"]
    # Returned structure is a copy — mutating it must not corrupt the catalog.
    exp["args"].append({"name": "hacked"})
    assert [a["name"] for a in distribution_catalog()[2]["args"]] == ["mean"]
