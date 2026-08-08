"""Transporters — moving resources on a 1-D track (elevators, shuttles, AGVs
on a fixed run, forklifts on an aisle).

A :class:`Fleet` owns cars with *positions*; a :class:`Ride` block carries an
entity from ``from_pos`` to ``to_pos``: request a car → car deadheads to the
pickup → load → travel → unload. One entity per trip in v1 (shared-direction
batching is on the backlog — this is a cargo lift, not a metro).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import simpy

from .. import trace as ev
from ..distributions import Distribution
from ..entity import Entity
from ..monitors import LevelMonitor, TallyMonitor
from .base import Block, resolve_amount

if TYPE_CHECKING:
    from ..model import Model


class _Car:
    __slots__ = ("uid", "pos")

    def __init__(self, uid: str, pos: float):
        self.uid = uid
        self.pos = pos


class Fleet:
    """``n_cars`` transporters moving at ``speed`` (distance per time unit).
    Registered beside resource pools; reports utilization and wait stats.
    Dispatch is FIFO (nearest-car dispatch: backlog)."""

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        n_cars: int = 1,
        speed: float = 1.0,
        load_time: float = 0.0,
        unload_time: float = 0.0,
        home: float = 0.0,
    ):
        if n_cars < 1:
            raise ValueError(f"Fleet {name!r}: n_cars must be >= 1")
        if speed <= 0:
            raise ValueError(f"Fleet {name!r}: speed must be > 0")
        self.m = model
        self.name = name
        self.n_cars = n_cars
        self.capacity = n_cars  # pool-compatible alias
        self.speed = speed
        self.load_time = load_time
        self.unload_time = unload_time
        self.home = home
        self.busy = LevelMonitor(f"{name}.busy")
        self.wait = TallyMonitor(f"{name}.wait")
        model._register_pool(self)

    def bind(self) -> None:
        env = self.m.env
        self._store = simpy.Store(env)
        for i in range(self.n_cars):
            self._store.put(_Car(f"{self.name}#{i + 1}", self.home))
        self.busy = LevelMonitor(f"{self.name}.busy")
        self.wait = TallyMonitor(f"{self.name}.wait")
        self._waiting = 0

    def reset_stats(self, t: float) -> None:
        self.busy.reset(t)
        self.wait.reset(t)

    def finalize_stats(self, t: float) -> None:
        self.busy.finalize(t)

    def utilization(self) -> float:
        return self.busy.mean() / self.n_cars

    def stats(self) -> dict:
        return {
            "busy": self.busy.summary(),
            "wait": self.wait.summary(),
            "utilization": self.utilization(),
            "capacity": self.n_cars,
        }

    def describe(self) -> dict:
        return {
            "name": self.name,
            "capacity": self.n_cars,
            "kind": "fleet",
            "speed": self.speed,
        }


class Ride(Block):
    """Carry the entity from ``from_pos`` to ``to_pos`` (constants,
    Distributions, or callables of the entity) using a car of ``fleet``."""

    def __init__(
        self,
        model: Model,
        name: str,
        *,
        fleet: Fleet,
        from_pos: float | Callable[[Entity], float] | Distribution,
        to_pos: float | Callable[[Entity], float] | Distribution,
        **hooks,
    ):
        super().__init__(model, name, **hooks)
        self.fleet = fleet
        self.from_pos = from_pos
        self.to_pos = to_pos

    def bind(self) -> None:
        pass

    def occupancy(self) -> int:
        return self.fleet._waiting + int(self.fleet.busy.value)

    def process(self, entity: Entity):
        env, m = self.m.env, self.m
        f = self.fleet
        self._fire("on_enter", entity)
        rng = m.streams.stream(f"ride.{self.name}")
        src = resolve_amount(self.from_pos, entity, rng)
        dst = resolve_amount(self.to_pos, entity, rng)

        t0 = env.now
        f._waiting += 1
        car = yield f._store.get()
        f._waiting -= 1
        f.wait.observe(env.now - t0)
        f.busy.increment(+1, env.now)

        deadhead = abs(car.pos - src) / f.speed
        if deadhead > 0:
            m.trace.emit(
                env.now, ev.MOVE, entity, block=self.name, resource=f.name,
                resource_unit=car.uid, note="deadhead",
                t_start=env.now, t_end=env.now + deadhead,
                from_pos=car.pos, to_pos=src,
            )
            yield env.timeout(deadhead)
        if f.load_time > 0:
            yield env.timeout(f.load_time)

        travel = abs(dst - src) / f.speed
        m.trace.emit(
            env.now, ev.MOVE, entity, block=self.name, resource=f.name,
            resource_unit=car.uid,
            t_start=env.now, t_end=env.now + travel,
            from_pos=src, to_pos=dst,
        )
        yield env.timeout(travel)
        if f.unload_time > 0:
            yield env.timeout(f.unload_time)

        car.pos = dst
        f.busy.increment(-1, env.now)
        yield f._store.put(car)
        self._fire("on_exit", entity)
        return self.outputs["out"]

    def params(self) -> dict:
        return {
            "fleet": self.fleet.name,
            "from_pos": self._describe_value(self.from_pos),
            "to_pos": self._describe_value(self.to_pos),
        }
