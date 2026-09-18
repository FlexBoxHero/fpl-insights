"""Weekly FDR colour bands from a frozen score distribution."""

from __future__ import annotations

import math

import numpy as np

# Matches the Teams page max fixture window so slider changes reuse one scale.
FDR_SCALE_WINDOW = 8
DIFFICULTY_LABELS = {
    1: "very_easy",
    2: "easy",
    3: "neutral",
    4: "hard",
    5: "very_hard",
}


def raw_difficulty_from_lambdas(lam_for: float, lam_against: float) -> float:
    """Continuous 1–5 score from expected-goal share (steeper than linear)."""
    share = lam_for / (lam_for + lam_against + 1e-6)
    stretched = 1.0 / (1.0 + math.exp(-8.0 * (share - 0.5)))
    return float(1.0 + 4.0 * (1.0 - stretched))


def blend_with_fpl_fdr(model_score: float, fpl_fdr: float | None) -> float:
    if fpl_fdr is None:
        return model_score
    return 0.7 * model_score + 0.3 * float(fpl_fdr)


def quantile_breaks(scores: list[float]) -> tuple[float, float, float, float]:
    if not scores:
        return (2.2, 2.8, 3.2, 3.8)
    arr = np.asarray(scores, dtype=float)
    qs = np.quantile(arr, [0.2, 0.4, 0.6, 0.8])
    return (float(qs[0]), float(qs[1]), float(qs[2]), float(qs[3]))


def level_from_breaks(score: float, breaks: tuple[float, float, float, float]) -> int:
    """Map a raw score onto 1–5 using frozen weekly cuts.

    If the week's scores are a single point, keep them Neutral (3).
    """
    if breaks[0] == breaks[3]:
        return 3
    for i, cut in enumerate(breaks, start=1):
        if score <= cut:
            return i
    return 5


def label_for_level(level: int) -> str:
    return DIFFICULTY_LABELS[int(min(5, max(1, level)))]
