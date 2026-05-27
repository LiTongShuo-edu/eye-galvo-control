import numpy as np
import pytest

from eye_galvo.calibration import (
    CALIBRATION_POINT_RETRIES,
    _collect_calibration_layers,
    _measure_bright_spot,
    _save_collected_layers,
)
from eye_galvo.geometry import CameraIntrinsics
from eye_galvo.tracking import CALIBRATION_GRID_VOLTAGES


def synthetic_sample(voltage, depth):
    voltage_x, voltage_y = voltage
    return {
        "voltage": [voltage_x, voltage_y],
        "coords_3d": [
            (voltage_x - 5.0) * depth * 0.2,
            (voltage_y - 5.0) * depth * 0.2,
            depth,
        ],
    }


def synthetic_layers(depths=(400.0, 600.0, 800.0)):
    return [
        [
            synthetic_sample((voltage_x, voltage_y), depth)
            for voltage_x in CALIBRATION_GRID_VOLTAGES
            for voltage_y in CALIBRATION_GRID_VOLTAGES
        ]
        for depth in depths
    ]


def test_bright_spot_measurement_returns_three_dimensional_sample():
    image = np.zeros((40, 40, 3), dtype=np.uint8)
    image[15:21, 18:24] = 255
    depth = np.full((40, 40), 600, dtype=np.uint16)

    sample, error = _measure_bright_spot(
        image,
        depth,
        CameraIntrinsics(ppx=20.0, ppy=20.0, fx=100.0, fy=100.0),
        (4.0, 6.0),
    )

    assert error is None
    assert sample["voltage"] == [4.0, 6.0]
    assert sample["coords_3d"][2] == 600.0


def test_collects_three_complete_voltage_grids():
    depths = iter((400.0, 600.0, 800.0))
    state = {"depth": None}
    captures = []

    def prompt(_message):
        state["depth"] = next(depths)
        return ""

    def capture_point(_controller, _pipeline, _align, voltage):
        captures.append((state["depth"], voltage))
        return synthetic_sample(voltage, state["depth"]), None

    layers = _collect_calibration_layers(
        None,
        None,
        None,
        prompt=prompt,
        report=lambda _message: None,
        capture_point=capture_point,
    )

    assert [len(layer) for layer in layers] == [9, 9, 9]
    assert len(captures) == 27
    assert [layer[0]["coords_3d"][2] for layer in layers] == [400.0, 600.0, 800.0]


def test_capture_retries_abort_incomplete_layer():
    attempts = 0

    def capture_point(_controller, _pipeline, _align, _voltage):
        nonlocal attempts
        attempts += 1
        return None, "missing spot"

    with pytest.raises(RuntimeError, match="could not capture point"):
        _collect_calibration_layers(
            None,
            None,
            None,
            prompt=lambda _message: "",
            report=lambda _message: None,
            capture_point=capture_point,
        )

    assert attempts == CALIBRATION_POINT_RETRIES


def test_invalid_layers_do_not_create_output_file(tmp_path):
    output = tmp_path / "galvo_calibration.json"
    layers = synthetic_layers()
    layers[-1].pop()

    with pytest.raises(ValueError):
        _save_collected_layers(layers, output)

    assert not output.exists()
