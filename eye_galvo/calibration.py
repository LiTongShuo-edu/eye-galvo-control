import json
from pathlib import Path
import time

from .geometry import CameraIntrinsics, pixel_to_spatial
from .instrument import open_controller


def run_calibration(resource: str, output_path: Path) -> None:
    """Collect a nine-point bright-spot calibration against real hardware."""
    import cv2
    import numpy as np
    import pyrealsense2 as rs

    controller = open_controller(resource)
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 848, 480, rs.format.z16, 30)
    align = rs.align(rs.stream.color)
    measurements: list[dict[str, object]] = []

    try:
        controller.enable()
        pipeline.start(config)
        for voltage_x in (4.0, 5.0, 6.0):
            for voltage_y in (4.0, 5.0, 6.0):
                controller.set_voltages(voltage_x, voltage_y)
                time.sleep(0.8)
                frame = align.process(pipeline.wait_for_frames())
                color_frame = frame.get_color_frame()
                depth_frame = frame.get_depth_frame()
                image = np.asanyarray(color_frame.get_data())
                depth = np.asanyarray(depth_frame.get_data())
                _, _, _, point = cv2.minMaxLoc(cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (5, 5), 0))
                x, y = point
                region = depth[max(0, y - 2) : y + 3, max(0, x - 2) : x + 3]
                valid = region[region > 0]
                if not len(valid):
                    continue
                raw = color_frame.profile.as_video_stream_profile().intrinsics
                spatial = pixel_to_spatial(
                    x, y, float(np.mean(valid)), CameraIntrinsics(raw.ppx, raw.ppy, raw.fx, raw.fy)
                )
                measurements.append(
                    {"voltages": [voltage_x, voltage_y], "xyz_mm": list(spatial.xyz_mm)}
                )
    finally:
        pipeline.stop()
        controller.close()

    if len(measurements) < 4:
        raise RuntimeError("Calibration requires at least four valid measured points.")
    output_path.write_text(
        json.dumps({"measurements": measurements}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
