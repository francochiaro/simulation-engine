"""Random-number streams.

One independent generator per *named stochastic source* per replication.
Stream identity depends only on ``(base_seed, replication, name)`` — never on
creation order or process — which is what makes runs reproducible and makes
common random numbers (CRN) work across scenarios: replication *i* of scenario
A and replication *i* of scenario B draw identical streams for every source
whose name is unchanged.
"""

from __future__ import annotations

import zlib

import numpy as np


def _name_key(name: str) -> int:
    # Stable across processes and Python versions (unlike built-in hash()).
    return zlib.crc32(name.encode("utf-8"))


class StreamRegistry:
    """Named, independently seeded ``numpy.random.Generator`` streams."""

    def __init__(self, base_seed: int = 12345, replication: int = 0):
        self.base_seed = int(base_seed)
        self.replication = int(replication)
        self._streams: dict[str, np.random.Generator] = {}

    def stream(self, name: str) -> np.random.Generator:
        """Return the generator for ``name``, creating it deterministically."""
        gen = self._streams.get(name)
        if gen is None:
            seq = np.random.SeedSequence(
                [self.base_seed, self.replication, _name_key(name)]
            )
            gen = np.random.Generator(np.random.PCG64(seq))
            self._streams[name] = gen
        return gen

    def __repr__(self) -> str:
        return (
            f"StreamRegistry(base_seed={self.base_seed}, "
            f"replication={self.replication}, streams={sorted(self._streams)})"
        )
