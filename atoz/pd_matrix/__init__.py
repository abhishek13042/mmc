"""A-Z Guide PD-array-matrix layer (ep 9)."""

from .matrix import PriceActionLag, find_price_action_lags

# Alias: find_pd_matrix is the public-facing name used by the test harness
find_pd_matrix = find_price_action_lags

__all__ = ["PriceActionLag", "find_price_action_lags", "find_pd_matrix"]
