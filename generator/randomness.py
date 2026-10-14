"""Seeded randomness helpers.

Two kinds of randomness keep the output reproducible:

1. **Per-day random streams.** Everything that happens on simulated day `t` draws from
   `day_rng(seed, stream, t)`. Extending the simulation by one day (simulate-day mode)
   therefore never changes what happened on earlier days.
2. **Stable hashes.** Planted data-quality issues are chosen by hashing a record's ID, so the
   same record gets the same issue whether it is written by the backfill or by a later
   simulated day.
"""

from __future__ import annotations

import hashlib

import numpy as np

_STREAMS = {
    "reference": 0,
    "prices": 1,
    "customer_changes": 2,
    "demand": 3,
    "purchasing": 4,
    "counts": 5,
    "setup": 6,
}


def reference_rng(seed: int, stream: str = "reference") -> np.random.Generator:
    """Random stream for one-off setup work (reference data, calibration noise)."""
    return np.random.default_rng([seed, _STREAMS[stream]])


def day_rng(seed: int, stream: str, day_index: int) -> np.random.Generator:
    """Random stream for one simulated day. Independent of the simulation horizon."""
    return np.random.default_rng([seed, _STREAMS[stream], day_index])


def stable_uniform(seed: int, key: str) -> float:
    """Deterministic pseudo-random number in [0, 1) derived from a string key."""
    digest = hashlib.blake2b(f"{seed}|{key}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


def stable_uniform_array(seed: int, prefix: str, keys) -> np.ndarray:
    """Vector version of `stable_uniform` for a sequence of record IDs."""
    return np.fromiter((stable_uniform(seed, f"{prefix}|{k}") for k in keys), dtype=float)
