"""Plan-view board geometry reconstructed from frozen handle centers, not collision analysis."""
import numpy as np

def bench_geometry(positions, width_m, hole_offset_m):
    points = np.asarray(positions, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or points.shape[0] < 2 or not np.isfinite(points).all():
        raise ValueError('Expected finite 2D handle positions')
    if not np.isfinite([width_m, hole_offset_m]).all() or width_m <= 0 or hole_offset_m < 0:
        raise ValueError('Invalid physical board dimensions')
    delta = np.diff(points, axis=0)
    distances = np.linalg.norm(delta, axis=1)
    if np.any(distances <= 0):
        raise ValueError('Coincident handles cannot define board orientation')
    along = delta / distances[:, None]
    normal = np.column_stack((-along[:, 1], along[:, 0])) * (width_m / 2)
    start = points[:-1] - hole_offset_m * along
    end = points[1:] + hole_offset_m * along
    return np.stack((start + normal, end + normal, end - normal, start - normal), axis=1)
