from __future__ import annotations

from pathlib import Path
import time

from .geometry import CameraIntrinsics, pixel_to_spatial
from .instrument import open_controller
from .tracking import CALIBRATION_GRID_VOLTAGES, build_calibration_model, save_calibration_model


CALIBRATION_PLANES = (
    ("near plane", "Place the target board at the near calibration depth."),
    ("working plane", "Place the target board at the hologram working depth."),
    ("far plane", "Place the target board at the far calibration depth."),
)
CALIBRATION_POINT_RETRIES = 3
CALIBRATION_SETTLE_SECONDS = 0.8
CALIBRATION_MIN_PEAK_INTENSITY = 30.0


def _measure_bright_spot(image, depth_image, intrinsics, voltage):
    """Convert the brightest valid depth-backed spot into one 3D sample."""
    import cv2
    import numpy as np

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grayscale, (5, 5), 0)
    _, peak, _, point = cv2.minMaxLoc(blurred)
    if peak < CALIBRATION_MIN_PEAK_INTENSITY:
        return None, "No bright calibration spot detected"
    x, y = point
    region = depth_image[
        max(0, y - 2) : min(depth_image.shape[0], y + 3),
        max(0, x - 2) : min(depth_image.shape[1], x + 3),
    ]
    valid = region[region > 0]
    if not len(valid):
        return None, "Calibration spot has no valid depth"
    spatial = pixel_to_spatial(
        x, y, float(np.mean(valid)), intrinsics
    )
    return {
        "voltage": [float(voltage[0]), float(voltage[1])],
        "coords_3d": list(spatial.xyz_mm),
    }, None


def _capture_calibration_point(controller, pipeline, align, voltage):
    import numpy as np

    controller.set_voltages(*voltage)
    time.sleep(CALIBRATION_SETTLE_SECONDS)
    frames = align.process(pipeline.wait_for_frames())
    color_frame = frames.get_color_frame()
    depth_frame = frames.get_depth_frame()
    if not color_frame or not depth_frame:
        return None, "Camera frame unavailable"
    image = np.asanyarray(color_frame.get_data())
    depth_image = np.asanyarray(depth_frame.get_data())
    raw = color_frame.profile.as_video_stream_profile().intrinsics
    intrinsics = CameraIntrinsics(raw.ppx, raw.ppy, raw.fx, raw.fy)
    return _measure_bright_spot(image, depth_image, intrinsics, voltage)


def _collect_calibration_layers(
    controller,
    pipeline,
    align,
    *,
    prompt=input,
    report=print,
    capture_point=_capture_calibration_point,
):
    layers = []
    voltages = [
        (float(voltage_x), float(voltage_y))
        for voltage_x in CALIBRATION_GRID_VOLTAGES
        for voltage_y in CALIBRATION_GRID_VOLTAGES
    ]
    for name, instruction in CALIBRATION_PLANES:
        prompt(f"{instruction} Press Enter to collect the 3 x 3 voltage grid...")
        samples = []
        for number, voltage in enumerate(voltages, start=1):
            last_error = "Unknown capture error"
            for attempt in range(1, CALIBRATION_POINT_RETRIES + 1):
                sample, error = capture_point(controller, pipeline, align, voltage)
                if sample is not None:
                    samples.append(sample)
                    report(
                        f"{name}: captured point {number}/9 at "
                        f"({voltage[0]:.1f}, {voltage[1]:.1f}) V"
                    )
                    break
                last_error = error or last_error
                report(
                    f"{name}: retry {attempt}/{CALIBRATION_POINT_RETRIES} "
                    f"for point {number}/9 ({last_error})"
                )
            else:
                raise RuntimeError(
                    f"{name}: could not capture point {number}/9 after "
                    f"{CALIBRATION_POINT_RETRIES} attempts ({last_error})"
                )
        layers.append(samples)
    return layers


def _save_collected_layers(layers, output_path: Path):
    model = build_calibration_model(layers)
    save_calibration_model(model, output_path)
    return model


def run_calibration(resource: str, output_path: Path) -> None:
    """Collect three nine-point planes and write a validated spatial model."""
    import pyrealsense2 as rs

    controller = open_controller(resource)
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 848, 480, rs.format.z16, 30)
    align = rs.align(rs.stream.color)
    started = False
    try:
        controller.enable()
        pipeline.start(config)
        started = True
        layers = _collect_calibration_layers(controller, pipeline, align)
    finally:
        if started:
            pipeline.stop()
        controller.close()
    _save_collected_layers(layers, output_path)
    print(f"Saved validated calibration model: {output_path}")
