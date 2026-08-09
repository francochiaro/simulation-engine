"""simulation-engine — agent-driven discrete-event and Monte Carlo simulation.

A validated block DSL on SimPy, experiment machinery with confidence
intervals, and a self-contained web replay viewer. See THEORY.md for the
methodology this toolkit implements.
"""

from .blocks import (
    Assign,
    Batch,
    Block,
    Delay,
    Fleet,
    Gate,
    Move,
    Queue,
    Release,
    ResourcePool,
    Ride,
    Route,
    Seize,
    Service,
    Sink,
    Source,
    TimeMeasureEnd,
    TimeMeasureStart,
    Unbatch,
)
from .distributions import (
    Choice,
    Constant,
    Distribution,
    Empirical,
    Erlang,
    Exponential,
    Gamma,
    Lognormal,
    Normal,
    Pert,
    RateSchedule,
    Triangular,
    Uniform,
    Weibull,
    from_dict,
)
from .model import Model, ModelValidationError, RunResult
from .units import TimeUnit

__version__ = "0.1.0"

__all__ = [
    "Assign", "Batch", "Block", "Delay", "Fleet", "Gate", "Move", "Queue",
    "Release", "ResourcePool", "Ride", "Route", "Seize", "Service", "Sink",
    "Source", "TimeMeasureEnd", "TimeMeasureStart", "Unbatch",
    "Choice", "Constant", "Distribution", "Empirical", "Erlang", "Exponential",
    "Gamma", "Lognormal", "Normal", "Pert", "RateSchedule", "Triangular",
    "Uniform", "Weibull", "from_dict",
    "Model", "ModelValidationError", "RunResult", "TimeUnit",
]
