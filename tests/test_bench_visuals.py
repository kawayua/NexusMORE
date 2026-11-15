"""Geometry fidelity: rigid dimensions, rotation and invalid handle states."""
import numpy as np
import pytest
from modelcrew.bench_visuals import bench_geometry


def test_board_corners_preserve_dimensions_and_rotation():
    points = np.array([[0., 0.], [2.86, 0.], [2.86, 1.65]])
    corners = bench_geometry(points, .3, .275)
    np.testing.assert_allclose(np.linalg.norm(corners[:, 1] - corners[:, 0], axis=1), [3.41, 2.2])
    np.testing.assert_allclose(np.linalg.norm(corners[:, 2] - corners[:, 1], axis=1), [.3, .3])
    rotation = np.array([[0., -1.], [1., 0.]])
    translation = np.array([4., -3.])
    changed = bench_geometry(points @ rotation.T + translation, .3, .275)
    np.testing.assert_allclose(changed, corners @ rotation.T + translation)
    np.testing.assert_allclose(points, [[0., 0.], [2.86, 0.], [2.86, 1.65]])


@pytest.mark.parametrize('points,width,offset', [([[0, 0], [0, 0]], .3, .275), ([[0, 0], [1, 0]], 0, .275), ([[0, 0], [1, 0]], .3, -.1), ([[0, 0], [np.nan, 1]], .3, .275)])
def test_invalid_geometry_is_rejected(points, width, offset):
    with pytest.raises(ValueError):
        bench_geometry(points, width, offset)
