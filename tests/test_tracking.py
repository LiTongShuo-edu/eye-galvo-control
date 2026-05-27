import copy

import pytest

import eye_galvo.tracking as tracking


def synthetic_point(voltage_x, voltage_y, depth_mm):
    return [
        (voltage_x - 5.0) * depth_mm * 0.2,
        (voltage_y - 5.0) * depth_mm * 0.2,
        depth_mm,
    ]


def synthetic_layers(depths=(400.0, 600.0, 800.0)):
    return [
        [
            {
                "voltage": [voltage_x, voltage_y],
                "coords_3d": synthetic_point(voltage_x, voltage_y, depth),
            }
            for voltage_x in tracking.CALIBRATION_GRID_VOLTAGES
            for voltage_y in tracking.CALIBRATION_GRID_VOLTAGES
        ]
        for depth in depths
    ]


class TestCalibrationMath:
    def setup_method(self):
        self.model = tracking.build_calibration_model(synthetic_layers())

    def test_build_model_and_recover_voltage_inside_volume(self):
        can_update, voltages, status = tracking.calculate_dp832_voltages(
            synthetic_point(4.5, 5.5, 600.0), self.model
        )

        assert can_update is True
        assert status == "Tracking"
        assert voltages[0] == pytest.approx(4.5)
        assert voltages[1] == pytest.approx(5.5)

    def test_limited_extrapolation_uses_voltage_boundaries(self):
        can_update, voltages, status = tracking.calculate_dp832_voltages(
            synthetic_point(3.8, 6.2, 820.0), self.model
        )

        assert can_update is True
        assert status == "Limited Extrapolation"
        assert voltages == (3.8, 6.2)

    def test_outside_permitted_volume_holds_output(self):
        can_update, voltages, status = tracking.calculate_dp832_voltages(
            synthetic_point(5.0, 5.0, 850.0), self.model
        )

        assert can_update is False
        assert voltages is None
        assert status == "Outside Calibrated Volume / Holding"

    def test_target_requiring_voltage_beyond_limit_holds_output(self):
        can_update, voltages, status = tracking.calculate_dp832_voltages(
            synthetic_point(3.7, 5.0, 600.0), self.model
        )

        assert can_update is False
        assert voltages is None
        assert status == "Outside Calibrated Volume / Holding"

    def test_rejects_effectively_coincident_depth_layers(self):
        with pytest.raises(ValueError):
            tracking.build_calibration_model(synthetic_layers((500.0, 503.0, 512.0)))

    def test_rejects_ray_residual_over_limit(self):
        damaged = copy.deepcopy(self.model)
        damaged["rays"][0]["max_residual_mm"] = (
            tracking.CALIBRATION_MAX_RAY_RESIDUAL_MM + 1
        )

        with pytest.raises(ValueError):
            tracking.validate_calibration_model(damaged)

    def test_save_then_load_validated_configuration(self, tmp_path):
        path = tmp_path / "calibration.json"

        tracking.save_calibration_model(self.model, path)
        loaded, error = tracking.load_calibration_model(path)

        assert error is None
        assert len(loaded["rays"]) == 9


def test_missing_calibration_file_allows_uncalibrated_fallback(tmp_path):
    model, error = tracking.load_calibration_model(tmp_path / "missing.json")

    assert model is None
    assert error is None


def test_invalid_calibration_file_is_reported(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{}", encoding="utf-8")

    model, error = tracking.load_calibration_model(path)

    assert model is None
    assert "标定文件不可用" in error


def test_link_rejects_invalid_model_before_opening_device(tmp_path, monkeypatch):
    model_path = tmp_path / "face_landmarker.task"
    model_path.write_bytes(b"placeholder")
    (tmp_path / tracking.CALIBRATION_FILE).write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="Cannot start linked tracking"):
        tracking.run_tracking(model_path=model_path, linked=True, resource="unused")
