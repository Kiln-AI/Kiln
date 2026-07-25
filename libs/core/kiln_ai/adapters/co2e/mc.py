"""Monte Carlo primitives for the CO2e factor builder.

Uncertain inputs are [P5, P50, P95] triples sampled as two-piece lognormals
(separate lower/upper sigma, preserving the median and both stated quantiles
for asymmetric triples). Mixes of regions/hardware are sampled categorically —
a request is served from ONE region on ONE hardware class, so mixes are
mixture distributions, not weighted averages.
"""

import math
import random
from collections.abc import Callable, Sequence

Z95 = 1.6449  # one-sided z-score for P5/P95

Sampler = Callable[[], float]


def make_sampler(triple: Sequence[float], rng: random.Random) -> Sampler:
    lo, mid, hi = float(triple[0]), float(triple[1]), float(triple[2])
    if lo <= 0 or hi <= 0 or (lo == mid == hi):
        return lambda: mid
    mu = math.log(mid)
    sig_lo = max(0.0, (mu - math.log(lo)) / Z95)
    sig_hi = max(0.0, (math.log(hi) - mu) / Z95)

    def sample() -> float:
        z = rng.gauss(0.0, 1.0)
        return math.exp(mu + z * (sig_hi if z >= 0 else sig_lo))

    return sample


def make_categorical(
    weighted_samplers: Sequence[tuple[float, Sampler]], rng: random.Random
) -> Sampler:
    """Pick ONE (weight, sampler) branch per draw — mixture, not average."""
    cum: list[tuple[float, Sampler]] = []
    total = 0.0
    for weight, sampler in weighted_samplers:
        total += weight
        cum.append((total, sampler))

    def sample() -> float:
        r = rng.random() * total
        for edge, sampler in cum:
            if r <= edge:
                return sampler()
        return cum[-1][1]()

    return sample


def percentiles(
    values: list[float], ps: Sequence[int] = (5, 50, 95)
) -> dict[str, float]:
    xs = sorted(values)
    return {
        f"p{p}": xs[min(len(xs) - 1, max(0, round(p / 100 * (len(xs) - 1))))]
        for p in ps
    }


def round_sig(stats: dict[str, float], sig: int = 3) -> dict[str, float]:
    def r(v: float) -> float:
        if v == 0:
            return 0.0
        return round(v, max(0, sig - 1 - math.floor(math.log10(abs(v)))))

    return {k: r(v) for k, v in stats.items()}
