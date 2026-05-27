from dataclasses import dataclass
import math


@dataclass(frozen=True)
class CameraIntrinsics:
    """Minimal pinhole camera parameters used by the coordinate conversion."""

    ppx: float
    ppy: float
    fx: float
    fy: float


@dataclass(frozen=True)
class SpatialResult:
    xyz_mm: tuple[float, float, float]
    distance_mm: float
    angles_deg: tuple[float, float]


def pixel_to_spatial(
    x: float, y: float, depth_mm: float, intrinsics: CameraIntrinsics
) -> SpatialResult:
    """Convert one aligned depth pixel into 3D coordinates and view angles."""
    if depth_mm <= 0:
        return SpatialResult((0.0, 0.0, 0.0), 0.0, (0.0, 0.0))
    if intrinsics.fx <= 0 or intrinsics.fy <= 0:
        raise ValueError("Focal lengths must be positive.")

    rx = (x - intrinsics.ppx) / intrinsics.fx
    ry = (y - intrinsics.ppy) / intrinsics.fy
    xyz = (rx * depth_mm, ry * depth_mm, float(depth_mm))
    distance = math.sqrt(sum(value * value for value in xyz))
    angles = (math.degrees(math.atan(rx)), math.degrees(math.atan(ry)))
    return SpatialResult(xyz, distance, angles)


def angles_to_voltages(
    angle_x: float,
    angle_y: float,
    *,
    center_voltage: float = 5.0,
    voltage_span: float = 5.0,
    max_optical_angle: float = 22.5,
) -> tuple[float, float]:
    """Map optical angles to two clamped unipolar control voltages."""
    if max_optical_angle <= 0:
        raise ValueError("Maximum optical angle must be positive.")

    gain = voltage_span / max_optical_angle
    low = center_voltage - voltage_span
    high = center_voltage + voltage_span

    def clamp(value: float) -> float:
        return max(low, min(high, value))

    return (
        clamp(center_voltage + angle_x * gain),
        clamp(center_voltage + angle_y * gain),
    )

