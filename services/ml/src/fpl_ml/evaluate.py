"""Optional backtest metrics for documentation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error


def team_metrics(y_true: pd.Series, proba: pd.DataFrame) -> dict[str, float]:
    """y_true: 0=home, 1=draw, 2=away; proba columns home, draw, away."""
    y = y_true.astype(int)
    p = proba[["home", "draw", "away"]].values
    p = np.clip(p, 1e-9, 1 - 1e-9)
    p = p / p.sum(axis=1, keepdims=True)
    return {
        "log_loss": float(log_loss(y, p)),
        "brier_home": float(brier_score_loss((y == 0).astype(int), proba["home"])),
    }


def player_mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float(mean_absolute_error(y_true, y_pred))
