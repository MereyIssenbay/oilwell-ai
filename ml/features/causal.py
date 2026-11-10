"""Observed-value summaries for complete trailing windows; no future fill."""
from __future__ import annotations

import numpy as np

from .constants import FEATURES


def feature_names(sensor_names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{sensor}__{feature}" for sensor in sensor_names for feature in FEATURES)


def summarize_windows(values: np.ndarray, endpoints: np.ndarray,
                      window_rows: int, cadence_seconds: float) -> tuple[np.ndarray, np.ndarray]:
    """Return (n windows x 6 features/sensor, observed counts/sensor).

    All windows have a validated uniform cadence. Missing samples remain missing;
    rates use first/last *observed* timestamps within that same window. Trend is
    least-squares slope over observed values at their relative source times.
    """
    columns = values.shape[1]
    result = np.empty((len(endpoints), columns * len(FEATURES)), dtype=float)
    observed = np.empty((len(endpoints), columns), dtype=np.int64)
    relative = np.arange(window_rows, dtype=float) * cadence_seconds
    offsets = np.arange(window_rows, dtype=np.int64)
    for start in range(0, len(endpoints), 512):
        stop = min(start + 512, len(endpoints))
        positions = endpoints[start:stop, None] - window_rows + 1 + offsets
        windows = values[positions]
        valid = np.isfinite(windows)
        count = valid.sum(axis=1)
        count_safe = np.maximum(count, 1)
        y = np.where(valid, windows, 0)
        mean = y.sum(axis=1) / count_safe
        centered_y = np.where(valid, windows - mean[:, None, :], 0)
        std = np.sqrt(np.square(centered_y).sum(axis=1) / count_safe)
        minimum = np.where(valid, windows, np.inf).min(axis=1)
        maximum = np.where(valid, windows, -np.inf).max(axis=1)
        first = valid.argmax(axis=1)
        last = window_rows - 1 - valid[:, ::-1, :].argmax(axis=1)
        first_values = np.take_along_axis(windows, first[:, None, :], axis=1)[:, 0, :]
        last_values = np.take_along_axis(windows, last[:, None, :], axis=1)[:, 0, :]
        elapsed = (last - first) * cadence_seconds
        rate = np.divide(last_values - first_values, elapsed,
                         out=np.full(count.shape, np.nan), where=count >= 2)
        mean_x = (valid * relative[None, :, None]).sum(axis=1) / count_safe
        centered_x = np.where(valid, relative[None, :, None] - mean_x[:, None, :], 0)
        denominator = np.square(centered_x).sum(axis=1)
        trend = np.divide((centered_x * centered_y).sum(axis=1), denominator,
                          out=np.full(count.shape, np.nan), where=denominator > 0)
        for array in (mean, std, minimum, maximum):
            array[count == 0] = np.nan
        result[start:stop] = np.stack((mean, std, minimum, maximum, rate, trend), axis=2).reshape(stop - start, -1)
        observed[start:stop] = count
    if np.isinf(result).any():
        raise ValueError("Feature arithmetic overflow; inputs cannot be represented safely")
    return result, observed
