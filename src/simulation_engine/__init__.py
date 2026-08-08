"""simulation-engine — agent-driven discrete-event and Monte Carlo simulation.

A validated block DSL on SimPy, experiment machinery with confidence
intervals, and a self-contained web replay viewer. See THEORY.md for the
methodology this toolkit implements.
"""

from .blocks import (
    Assign,
    Block,
    Delay,
    Queue,
    Release,
    ResourcePool,
    Route,
    Seize,
    Service,
    Sink,
    Source,
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
)
from .model import Model, ModelValidationError, RunResult
from .units import TimeUnit

__version__ = "0.1.0"

__all__ = [
    "Assign", "Block", "Delay", "Queue", "Release", "ResourcePool", "Route",
    "Seize", "Service", "Sink", "Source",
    "Choice", "Constant", "Distribution", "Empirical", "Erlang", "Exponential",
    "Gamma", "Lognormal", "Normal", "Pert", "RateSchedule", "Triangular",
    "Uniform", "Weibull",
    "Model", "ModelValidationError", "RunResult", "TimeUnit",
]
