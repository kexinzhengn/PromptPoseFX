"""Vectorized One Euro filtering for pose landmark sequences."""

from time import perf_counter

import numpy as np
from numpy.typing import NDArray


def _smoothing_factor(delta_time: float, cutoff: NDArray[np.float64]) -> NDArray[np.float64]:
    rate = 2.0 * np.pi * cutoff * delta_time
    return rate / (rate + 1.0)


class OneEuroFilter:
    """Smooth a sequence while retaining fast intentional motion.

    Input arrays use ``(frames, joints, coordinates)``. Frames are treated as
    evenly spaced samples because the pose pipeline extracts video at 30 FPS.
    """

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.0,
        derivative_cutoff: float = 1.0,
    ) -> None:
        if min_cutoff <= 0 or derivative_cutoff <= 0 or beta < 0:
            raise ValueError("One Euro filter parameters must be positive")
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.derivative_cutoff = float(derivative_cutoff)

    def __call__(
        self,
        poses: NDArray[np.floating],
    ) -> tuple[NDArray[np.float64], float]:
        """Return the smoothed sequence and elapsed processing time."""
        values = np.asarray(poses, dtype=np.float64)
        if values.ndim != 3:
            raise ValueError("Pose data must have shape (frames, joints, coordinates)")
        if values.shape[0] == 0:
            return values.copy(), 0.0

        started_at = perf_counter()
        result = np.empty_like(values)
        result[0] = values[0]

        previous_value = values[0].copy()
        previous_derivative = np.zeros_like(previous_value)
        derivative_alpha = _smoothing_factor(
            1.0,
            np.full_like(previous_value, self.derivative_cutoff),
        )

        for frame_index in range(1, values.shape[0]):
            current_value = values[frame_index]
            derivative = current_value - previous_value
            filtered_derivative = (
                derivative_alpha * derivative
                + (1.0 - derivative_alpha) * previous_derivative
            )
            cutoff = self.min_cutoff + self.beta * np.abs(filtered_derivative)
            value_alpha = _smoothing_factor(1.0, cutoff)
            filtered_value = (
                value_alpha * current_value
                + (1.0 - value_alpha) * previous_value
            )

            result[frame_index] = filtered_value
            previous_value = filtered_value
            previous_derivative = filtered_derivative

        return result, perf_counter() - started_at
