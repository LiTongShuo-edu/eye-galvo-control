from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from .geometry import CameraIntrinsics, pixel_to_spatial
from .instrument import GalvoController, open_controller


CALIBRATION_FILE = Path("galvo_calibration.json")
VOLTAGE_CENTER = 5.0
COMMON_MODE_VOLTAGE = VOLTAGE_CENTER
CALIBRATION_VERSION = 3
CALIBRATION_WIRING = "CH1_PLUS=X_PLUS,CH2_PLUS=Y_PLUS,CH3_PLUS=X_MINUS_AND_Y_MINUS"
CALIBRATION_GRID_VOLTAGES = [4.0, 5.0, 6.0]
CALIBRATION_EXTRAPOLATION_MARGIN = 0.10
CALIBRATION_VOLTAGE_LIMITS = [3.8, 6.2]
ABSOLUTE_VOLTAGE_LIMITS = [0.0, 10.0]
HOLOGRAM_PLANE_DISTANCE_FROM_GALVO_MM = 70.0
CALIBRATION_MIN_LAYER_GAP_MM = 5.0
CALIBRATION_MIN_DEPTH_SPAN_MM = 10.0
CALIBRATION_MAX_RAY_RESIDUAL_MM = 10.0
CONTROL_DEADZONE_V = 0.02


def _finite_array(value, expected_shape, name):
    array = np.asarray(value, dtype=np.float64)
    if array.shape != expected_shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} 数据无效")
    return array


def fit_laser_ray(points_3d):
    """Fit one calibrated galvo ray to three measured spot positions."""
    points = _finite_array(points_3d, (3, 3), "射线采样点")
    origin = np.mean(points, axis=0)
    _, _, vh = np.linalg.svd(points - origin, full_matrices=False)
    direction = vh[0]
    if direction[2] < 0:
        direction = -direction
    direction = direction / float(np.linalg.norm(direction))
    projected = origin + np.outer((points - origin) @ direction, direction)
    residuals = np.linalg.norm(points - projected, axis=1)
    return {
        "origin": origin.tolist(),
        "direction": direction.tolist(),
        "max_residual_mm": float(np.max(residuals)),
    }


def intersect_ray_at_depth(ray, depth_mm):
    origin = np.asarray(ray["origin"], dtype=np.float64)
    direction = np.asarray(ray["direction"], dtype=np.float64)
    if abs(direction[2]) < 1e-8:
        raise ValueError("射线不能与深度平面求交")
    scale = (float(depth_mm) - origin[2]) / direction[2]
    return origin + direction * scale


def validate_calibration_model(model):
    """Normalize and validate a calibration file before it drives hardware."""
    if not isinstance(model, dict) or model.get("version") != CALIBRATION_VERSION:
        raise ValueError("标定文件版本不受支持")
    depths = np.sort(_finite_array(model.get("layer_depths_mm"), (3,), "标定层深度"))
    if (
        np.any(np.diff(depths) < CALIBRATION_MIN_LAYER_GAP_MM)
        or depths[2] - depths[0] < CALIBRATION_MIN_DEPTH_SPAN_MM
    ):
        raise ValueError("三个标定平面的深度间距不足")
    hologram_distance = float(
        model.get("hologram_plane_distance_from_galvo_mm", float("nan"))
    )
    if not math.isfinite(hologram_distance) or not math.isclose(
        hologram_distance, HOLOGRAM_PLANE_DISTANCE_FROM_GALVO_MM, abs_tol=1e-6
    ):
        raise ValueError("标定配置的全息工作面距离不匹配")
    working_depth = float(model.get("working_plane_depth_mm", float("nan")))
    if not math.isfinite(working_depth) or not math.isclose(
        working_depth, depths[1], abs_tol=1e-6
    ):
        raise ValueError("标定配置的全息工作面深度无效")
    common_mode = float(model.get("common_mode_voltage", float("nan")))
    if not math.isclose(common_mode, COMMON_MODE_VOLTAGE, abs_tol=1e-6):
        raise ValueError("标定配置的共模偏置电压不匹配")
    grid = _finite_array(model.get("grid_voltages"), (3,), "标定电压网格")
    if not np.all(np.diff(grid) > 0):
        raise ValueError("标定电压网格无效")
    if model.get("wiring") != CALIBRATION_WIRING:
        raise ValueError("标定接线定义与 DP832 映射不匹配")
    margin = float(model.get("extrapolation_margin", CALIBRATION_EXTRAPOLATION_MARGIN))
    if not 0 <= margin <= 0.5:
        raise ValueError("标定外推范围无效")
    voltage_limits = _finite_array(model.get("voltage_limits"), (2,), "电压限制")
    if (
        voltage_limits[0] >= voltage_limits[1]
        or voltage_limits[0] < ABSOLUTE_VOLTAGE_LIMITS[0]
        or voltage_limits[1] > ABSOLUTE_VOLTAGE_LIMITS[1]
    ):
        raise ValueError("标定电压限制无效")

    expected_voltages = {(float(vx), float(vy)) for vx in grid for vy in grid}
    rays = model.get("rays")
    if not isinstance(rays, list) or len(rays) != 9:
        raise ValueError("标定射线数量必须为 9")
    normalized_rays = []
    seen = set()
    for ray in rays:
        voltage = _finite_array(ray.get("voltage"), (2,), "射线电压")
        key = (float(voltage[0]), float(voltage[1]))
        if key not in expected_voltages or key in seen:
            raise ValueError("标定射线电压网格不完整")
        origin = _finite_array(ray.get("origin"), (3,), "射线起点")
        direction = _finite_array(ray.get("direction"), (3,), "射线方向")
        norm = float(np.linalg.norm(direction))
        if norm < 1e-12:
            raise ValueError("标定射线方向无效")
        direction = direction / norm
        if direction[2] < 0:
            direction = -direction
        if abs(direction[2]) < 1e-8:
            raise ValueError("标定射线与深度平面无法求交")
        residual = float(ray.get("max_residual_mm", float("inf")))
        if not math.isfinite(residual) or residual > CALIBRATION_MAX_RAY_RESIDUAL_MM:
            raise ValueError("射线拟合误差超出限制")
        normalized_rays.append(
            {
                "voltage": [key[0], key[1]],
                "origin": origin.tolist(),
                "direction": direction.tolist(),
                "max_residual_mm": residual,
            }
        )
        seen.add(key)
    if seen != expected_voltages:
        raise ValueError("标定射线电压网格不完整")

    normalized = dict(model)
    normalized["layer_depths_mm"] = depths.tolist()
    normalized["hologram_plane_distance_from_galvo_mm"] = hologram_distance
    normalized["working_plane_depth_mm"] = working_depth
    normalized["common_mode_voltage"] = common_mode
    normalized["wiring"] = CALIBRATION_WIRING
    normalized["grid_voltages"] = grid.tolist()
    normalized["extrapolation_margin"] = margin
    normalized["voltage_limits"] = voltage_limits.tolist()
    normalized["absolute_voltage_limits"] = list(ABSOLUTE_VOLTAGE_LIMITS)
    normalized["rays"] = normalized_rays
    return normalized


def build_calibration_model(layer_samples):
    """Create nine spatial rays from near, working and far plane samples."""
    if len(layer_samples) != 3:
        raise ValueError("必须采集近、中、远三个标定平面")
    grid_points = {
        (float(vx), float(vy))
        for vx in CALIBRATION_GRID_VOLTAGES
        for vy in CALIBRATION_GRID_VOLTAGES
    }
    layer_depths = []
    indexed_layers = []
    for layer in layer_samples:
        if len(layer) != 9:
            raise ValueError("每个标定平面必须包含完整九点")
        samples_by_voltage = {}
        depths = []
        for sample in layer:
            voltage = tuple(float(v) for v in sample["voltage"])
            coords = _finite_array(sample["coords_3d"], (3,), "光斑三维坐标")
            if voltage in samples_by_voltage:
                raise ValueError("标定平面存在重复电压点")
            samples_by_voltage[voltage] = coords
            depths.append(coords[2])
        if set(samples_by_voltage) != grid_points:
            raise ValueError("标定平面缺少电压网格点")
        indexed_layers.append(samples_by_voltage)
        layer_depths.append(float(np.median(depths)))
    if not (layer_depths[0] < layer_depths[1] < layer_depths[2]):
        raise ValueError("请按近、中、远顺序放置标定平面")

    rays = []
    residuals = []
    for voltage in sorted(grid_points):
        ray = fit_laser_ray([layer[voltage] for layer in indexed_layers])
        if ray["max_residual_mm"] > CALIBRATION_MAX_RAY_RESIDUAL_MM:
            raise ValueError(f"电压点 {voltage} 的射线拟合误差过大")
        ray["voltage"] = list(voltage)
        rays.append(ray)
        residuals.append(ray["max_residual_mm"])
    model = {
        "version": CALIBRATION_VERSION,
        "hologram_plane_distance_from_galvo_mm": HOLOGRAM_PLANE_DISTANCE_FROM_GALVO_MM,
        "working_plane_depth_mm": layer_depths[1],
        "layer_depths_mm": layer_depths,
        "common_mode_voltage": COMMON_MODE_VOLTAGE,
        "wiring": CALIBRATION_WIRING,
        "grid_voltages": list(CALIBRATION_GRID_VOLTAGES),
        "extrapolation_margin": CALIBRATION_EXTRAPOLATION_MARGIN,
        "voltage_limits": list(CALIBRATION_VOLTAGE_LIMITS),
        "absolute_voltage_limits": list(ABSOLUTE_VOLTAGE_LIMITS),
        "rays": rays,
        "max_ray_residual_mm": float(max(residuals)),
        "mean_ray_residual_mm": float(sum(residuals) / len(residuals)),
    }
    return validate_calibration_model(model)


def save_calibration_model(model, path=CALIBRATION_FILE):
    validated = validate_calibration_model(model)
    Path(path).write_text(
        json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_calibration_model(path=CALIBRATION_FILE):
    path = Path(path)
    if not path.exists():
        return None, None
    try:
        with path.open("r", encoding="utf-8") as stream:
            return validate_calibration_model(json.load(stream)), None
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return None, f"标定文件不可用: {exc}"


def _axis_samples_at_depth(calibration, depth, axis, voltage_axis):
    samples = []
    for voltage in calibration["grid_voltages"]:
        coordinates = [
            intersect_ray_at_depth(ray, depth)[axis]
            for ray in calibration["rays"]
            if float(ray["voltage"][voltage_axis]) == float(voltage)
        ]
        samples.append((float(np.mean(coordinates)), float(voltage)))
    samples.sort(key=lambda pair: pair[0])
    positions = np.asarray([position for position, _ in samples], dtype=np.float64)
    voltages = np.asarray([voltage for _, voltage in samples], dtype=np.float64)
    if not np.all(np.diff(positions) > 1e-9):
        raise ValueError("标定网格不能形成单调电压映射")
    return positions, voltages


def _interpolate_voltage(target, positions, voltages):
    if target < positions[0]:
        return float(
            voltages[0]
            + (target - positions[0])
            * (voltages[1] - voltages[0])
            / (positions[1] - positions[0])
        )
    if target > positions[-1]:
        return float(
            voltages[-2]
            + (target - positions[-2])
            * (voltages[-1] - voltages[-2])
            / (positions[-1] - positions[-2])
        )
    return float(np.interp(target, positions, voltages))


def calculate_dp832_voltages(target_3d, calibration):
    """Invert the calibrated ray grid into bounded X/Y output voltages."""
    if calibration is None:
        return False, None, "Outside Calibrated Volume / Holding"
    target = _finite_array(target_3d, (3,), "目标三维坐标")
    depth = float(target[2])
    depths = np.asarray(calibration["layer_depths_mm"], dtype=np.float64)
    lower, upper = depths[0], depths[2]
    span = upper - lower
    margin = float(calibration["extrapolation_margin"])
    if depth < lower - span * margin or depth > upper + span * margin:
        return False, None, "Outside Calibrated Volume / Holding"
    try:
        x_positions, x_voltages = _axis_samples_at_depth(calibration, depth, 0, 0)
        y_positions, y_voltages = _axis_samples_at_depth(calibration, depth, 1, 1)
    except ValueError:
        return False, None, "Outside Calibrated Volume / Holding"
    voltage_x = _interpolate_voltage(target[0], x_positions, x_voltages)
    voltage_y = _interpolate_voltage(target[1], y_positions, y_voltages)
    low, high = calibration["voltage_limits"]
    if not low <= voltage_x <= high or not low <= voltage_y <= high:
        return False, None, "Outside Calibrated Volume / Holding"
    if (
        depth < lower
        or depth > upper
        or math.isclose(voltage_x, low, abs_tol=1e-9)
        or math.isclose(voltage_x, high, abs_tol=1e-9)
        or math.isclose(voltage_y, low, abs_tol=1e-9)
        or math.isclose(voltage_y, high, abs_tol=1e-9)
    ):
        return True, (voltage_x, voltage_y), "Limited Extrapolation"
    return True, (voltage_x, voltage_y), "Tracking"


def run_tracking(*, model_path: Path, linked: bool = False, resource: str | None = None) -> None:
    """Run real-time eye-center tracking, optionally sending galvo output."""
    if not model_path.exists():
        raise FileNotFoundError(f"MediaPipe model not found: {model_path}")
    calibration = None
    if linked:
        calibration, error = load_calibration_model()
        if error is not None:
            raise RuntimeError(f"Cannot start linked tracking: {error}")

    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    import pyrealsense2 as rs

    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 848, 480, rs.format.z16, 30)
    align = rs.align(rs.stream.color)
    controller: GalvoController | None = open_controller(resource or "") if linked else None
    options = vision.FaceLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
    )
    try:
        pipeline.start(config)
        if controller is not None:
            identity = controller.enable()
            print(f"Connected instrument: {identity}")
        with vision.FaceLandmarker.create_from_options(options) as detector:
            timestamp_ms = 0
            while True:
                frames = align.process(pipeline.wait_for_frames())
                color_frame = frames.get_color_frame()
                depth_frame = frames.get_depth_frame()
                if not color_frame or not depth_frame:
                    continue
                image = np.asanyarray(color_frame.get_data())
                depth = np.asanyarray(depth_frame.get_data())
                timestamp_ms += 33
                mp_image = mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB),
                )
                detected = detector.detect_for_video(mp_image, timestamp_ms)
                status = "No target"
                if detected.face_landmarks:
                    landmarks = detected.face_landmarks[0]
                    height, width, _ = image.shape
                    left = (
                        int((landmarks[33].x + landmarks[133].x) / 2 * width),
                        int((landmarks[33].y + landmarks[133].y) / 2 * height),
                    )
                    right = (
                        int((landmarks[362].x + landmarks[263].x) / 2 * width),
                        int((landmarks[362].y + landmarks[263].y) / 2 * height),
                    )
                    target = ((left[0] + right[0]) // 2, (left[1] + right[1]) // 2)
                    raw = color_frame.profile.as_video_stream_profile().intrinsics
                    intrinsics = CameraIntrinsics(raw.ppx, raw.ppy, raw.fx, raw.fy)
                    spatial = pixel_to_spatial(
                        target[0], target[1], _depth_at(depth, *target), intrinsics
                    )
                    control_status = "Preview only"
                    if controller is not None and calibration is not None:
                        can_update, voltages, control_status = calculate_dp832_voltages(
                            spatial.xyz_mm, calibration
                        )
                        if can_update and voltages is not None:
                            controller.set_voltages(*voltages)
                    elif controller is not None:
                        controller.update_angles(
                            *spatial.angles_deg, deadzone=CONTROL_DEADZONE_V
                        )
                        control_status = "Uncalibrated angle mapping"
                    cv2.circle(image, target, 5, (0, 255, 255), -1)
                    status = (
                        f"{control_status} | Angles: {spatial.angles_deg[0]:.2f}, "
                        f"{spatial.angles_deg[1]:.2f} deg Distance: "
                        f"{spatial.distance_mm:.1f} mm"
                    )
                cv2.putText(
                    image, status, (25, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
                )
                cv2.imshow("Eye-Galvo Control", image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                time.sleep(0.001)
    finally:
        if controller is not None:
            controller.close()
        pipeline.stop()
        cv2.destroyAllWindows()


def _depth_at(depth_image, x: int, y: int) -> float:
    height, width = depth_image.shape
    region = depth_image[
        max(0, y - 2) : min(height, y + 3), max(0, x - 2) : min(width, x + 3)
    ]
    valid = region[region > 0]
    return float(np.mean(valid)) if len(valid) else 0.0
