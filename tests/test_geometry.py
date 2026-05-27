import math

import pytest

from eye_galvo.geometry import CameraIntrinsics, angles_to_voltages, pixel_to_spatial


def test_pixel_at_principal_point_is_forward_only():
    result = pixel_to_spatial(320, 240, 1000, CameraIntrinsics(320, 240, 500, 500))

    assert result.xyz_mm == (0.0, 0.0, 1000.0)
    assert result.distance_mm == 1000.0
    assert result.angles_deg == (0.0, 0.0)


def test_pixel_to_spatial_uses_pinhole_geometry():
    result = pixel_to_spatial(370, 190, 1000, CameraIntrinsics(320, 240, 500, 500))

    assert result.xyz_mm == (100.0, -100.0, 1000.0)
    assert result.distance_mm == pytest.approx(math.sqrt(1_020_000))
    assert result.angles_deg == pytest.approx((math.degrees(math.atan(0.1)), -math.degrees(math.atan(0.1))))


def test_zero_depth_is_safe_empty_result():
    result = pixel_to_spatial(370, 190, 0, CameraIntrinsics(320, 240, 500, 500))

    assert result.distance_mm == 0
    assert result.xyz_mm == (0.0, 0.0, 0.0)


def test_voltage_mapping_clamps_to_output_range():
    assert angles_to_voltages(0, 0) == (5.0, 5.0)
    assert angles_to_voltages(30, -30) == (10.0, 0.0)

