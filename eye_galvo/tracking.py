from pathlib import Path
import time

from .geometry import CameraIntrinsics, pixel_to_spatial
from .instrument import GalvoController, open_controller


def _depth_at(depth_image, x: int, y: int) -> float:
    import numpy as np

    height, width = depth_image.shape
    region = depth_image[max(0, y - 2) : min(height, y + 3), max(0, x - 2) : min(width, x + 3)]
    valid = region[region > 0]
    return float(np.mean(valid)) if len(valid) else 0.0


def run_tracking(
    *, model_path: Path, linked: bool = False, resource: str | None = None
) -> None:
    """Run real-time eye-center tracking, optionally sending bounded galvo output."""
    if not model_path.exists():
        raise FileNotFoundError(f"MediaPipe model not found: {model_path}")

    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    import numpy as np
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
                    spatial = pixel_to_spatial(target[0], target[1], _depth_at(depth, *target), intrinsics)
                    if controller is not None:
                        controller.update_angles(*spatial.angles_deg)
                    cv2.circle(image, target, 5, (0, 255, 255), -1)
                    status = (
                        f"Angles: {spatial.angles_deg[0]:.2f}, {spatial.angles_deg[1]:.2f} deg "
                        f"Distance: {spatial.distance_mm:.1f} mm"
                    )
                cv2.putText(image, status, (25, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                cv2.imshow("Eye-Galvo Control", image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                time.sleep(0.001)
    finally:
        if controller is not None:
            controller.close()
        pipeline.stop()
        cv2.destroyAllWindows()

