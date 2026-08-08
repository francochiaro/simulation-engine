"""Source — generates entities."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from .. import trace as ev
from ..distributions import Distribution, Exponential, RateSchedule
from .base import Block

if TYPE_CHECKING:
    from ..model import Model


class Source(Block):
    """Generates entities on one of four arrival modes (exactly one):

    - ``interarrival=`` a Distribution (or constant float) between arrivals
    - ``rate=`` a Poisson stream at rate λ (sugar for Exponential(rate=λ))
    - ``schedule=`` a RateSchedule — nonstationary Poisson, sampled by thinning
    - ``arrival_times=`` explicit absolute times

    Options: ``entities_per_arrival``, ``max_arrivals`` (total entities),
    ``first_arrival_at``, ``entity_type``, ``on_create(entity, rng)``.
    """

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        interarrival: Distribution | float | None = None,
        rate: float | None = None,
        schedule: RateSchedule | None = None,
        arrival_times: Sequence[float] | None = None,
        entity_type: str = "entity",
        entities_per_arrival: int = 1,
        max_arrivals: int | None = None,
        first_arrival_at: float | None = None,
        on_create: Callable | None = None,
        **hooks,
    ):
        super().__init__(model, name, **hooks)
        modes = [interarrival is not None, rate is not None, schedule is not None,
                 arrival_times is not None]
        if sum(modes) != 1:
            raise ValueError(
                f"Source {name!r}: specify exactly one of interarrival=, rate=, "
                f"schedule=, arrival_times="
            )
        if rate is not None:
            if rate <= 0:
                raise ValueError(f"Source {name!r}: rate must be > 0, got {rate}")
            interarrival = Exponential(rate=rate)
        if isinstance(interarrival, (int, float)):
            if interarrival <= 0:
                raise ValueError(
                    f"Source {name!r}: constant interarrival must be > 0"
                )
        if entities_per_arrival < 1:
            raise ValueError(f"Source {name!r}: entities_per_arrival must be >= 1")
        if max_arrivals is not None and max_arrivals < 1:
            raise ValueError(f"Source {name!r}: max_arrivals must be >= 1")
        if arrival_times is not None:
            ts = list(arrival_times)
            if ts != sorted(ts) or any(t < 0 for t in ts):
                raise ValueError(
                    f"Source {name!r}: arrival_times must be sorted and >= 0"
                )
        self.interarrival = interarrival
        self.schedule = schedule
        self.arrival_times = list(arrival_times) if arrival_times is not None else None
        self.entity_type = entity_type
        self.entities_per_arrival = entities_per_arrival
        self.max_arrivals = max_arrivals
        self.first_arrival_at = first_arrival_at
        self.on_create = on_create
        self.created = 0

    @property
    def bounded(self) -> bool:
        return self.max_arrivals is not None or self.arrival_times is not None

    def bind(self) -> None:
        self.created = 0
        self.m.env.process(self._generate())

    def _emit_batch(self) -> bool:
        """Create one arrival batch; returns False when max_arrivals is hit."""
        env, m = self.m.env, self.m
        rng = m.streams.stream(f"source.{self.name}")
        for _ in range(self.entities_per_arrival):
            if self.max_arrivals is not None and self.created >= self.max_arrivals:
                return False
            e = m._new_entity(self.entity_type)
            self.created += 1
            if self.on_create is not None:
                self.on_create(e, rng)
            self._fire("on_exit", e)
            m.trace.emit(env.now, ev.ARRIVAL, e, block=self.name)
            m._entity_entered(env.now)
            target = self.outputs["out"]
            if target is not None:
                env.process(m._drive(e, target))
        return not (self.max_arrivals is not None and self.created >= self.max_arrivals)

    def _generate(self):
        env = self.m.env
        rng = self.m.streams.stream(f"source.{self.name}.arrivals")

        if self.arrival_times is not None:
            for t in self.arrival_times:
                if t > env.now:
                    yield env.timeout(t - env.now)
                if not self._emit_batch():
                    return
            return

        if self.first_arrival_at is not None:
            yield env.timeout(self.first_arrival_at)
        elif self.schedule is not None:
            t = self.schedule.next_arrival(env.now, rng)
            yield env.timeout(t - env.now)
        else:
            assert self.interarrival is not None
            d = (
                self.interarrival.sample(rng)
                if isinstance(self.interarrival, Distribution)
                else float(self.interarrival)
            )
            yield env.timeout(d)

        while True:
            if not self._emit_batch():
                return
            if self.schedule is not None:
                t = self.schedule.next_arrival(env.now, rng)
                yield env.timeout(t - env.now)
            else:
                assert self.interarrival is not None
                d = (
                    self.interarrival.sample(rng)
                    if isinstance(self.interarrival, Distribution)
                    else float(self.interarrival)
                )
                yield env.timeout(d)

    def process(self, entity):
        raise RuntimeError("Source generates entities; nothing flows into it")

    def params(self) -> dict:
        p: dict = {
            "entity_type": self.entity_type,
            "entities_per_arrival": self.entities_per_arrival,
            "max_arrivals": self.max_arrivals,
        }
        if self.schedule is not None:
            p["schedule"] = self.schedule.describe()
        elif self.arrival_times is not None:
            p["arrival_times"] = {"n": len(self.arrival_times)}
        else:
            p["interarrival"] = self._describe_value(self.interarrival)
        return p
