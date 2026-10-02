"""Tests for the project-owned One Euro pose smoother."""

import numpy as np
import pytest

from video_process.smooth import OneEuroFilter


def test_smoother_preserves_shape_and_constant_signals() -> None:
    poses = np.full((8, 3, 2), 0.25, dtype=np.float64)

    smoothed, elapsed = OneEuroFilter(min_cutoff=0.2, beta=0.005)(poses)

    assert smoothed.shape == poses.shape
    assert np.allclose(smoothed, poses)
    assert elapsed >= 0


def test_smoother_reduces_a_single_frame_jump() -> None:
    poses = np.zeros((4, 1, 1), dtype=np.float64)
    poses[2:] = 1.0

    smoothed, _ = OneEuroFilter(min_cutoff=0.2, beta=0.0)(poses)

    assert smoothed[2, 0, 0] > 0
    assert smoothed[2, 0, 0] < poses[2, 0, 0]
    assert smoothed[3, 0, 0] > smoothed[2, 0, 0]


def test_smoother_rejects_non_pose_arrays() -> None:
    with pytest.raises(ValueError, match="frames, joints, coordinates"):
        OneEuroFilter()(np.zeros((4, 3)))
