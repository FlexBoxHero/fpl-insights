# Model evaluation (Phase 1)

## Team outcomes

- Walk-forward validation on finished fixtures using Poisson-derived W/D/L
- Track log loss and Brier score per gameweek on hold-out season (2024–25)
- Clean sheet probabilities calibrated with logistic regression on rolling team ratings

## Player points

- Regression target: next-gameweek `total_points`
- Baselines: last GW points, FPL `ep_next`, rolling mean
- Report MAE and RMSE on hold-out season

Re-run evaluation after retraining via the inference pipeline once ETL has loaded historical GW stats.
