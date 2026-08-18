"""Frame sources: robot camera, webcam, or a directory of images.

Each source is a zero-arg callable returning (jpeg_or_png_bytes, media_type)
or None when no frame is available (dir source: exhausted).
"""

import os
import time
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def _media_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/jpeg"


def make_source(spec: str):
    """spec: 'robot' | 'webcam' | 'dir:<path>' -> callable() -> (bytes, media_type) | None"""
    if spec == "robot":
        return _robot_source()
    if spec == "webcam":
        return _webcam_source()
    if spec.startswith("dir:"):
        return _dir_source(spec[4:])
    raise ValueError(f"unknown source: {spec!r} (use robot, webcam, or dir:<path>)")


def _robot_source():
    # Daemon 1.8.3 reports its hotspot IP (10.42.0.1) as wlan_ip, so the SDK
    # dials WebRTC signalling on an unroutable address. Monkeypatch the
    # MediaManager to force the real host from REACHY_SIGNALLING_HOST
    # (exported by run.sh) BEFORE constructing ReachyMini.
    from reachy_mini.media import media_manager as _mm

    _real_init = _mm.MediaManager.__init__

    def _patched_init(self, *args, **kwargs):
        override = os.getenv("REACHY_SIGNALLING_HOST")
        if override and "signalling_host" in kwargs:
            kwargs["signalling_host"] = override
        _real_init(self, *args, **kwargs)

    _mm.MediaManager.__init__ = _patched_init

    from reachy_mini import ReachyMini

    robot = ReachyMini(connection_mode="network", timeout=30)

    def grab():
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                jpeg = robot.media.get_frame_jpeg()
            except Exception:
                jpeg = None
            if jpeg:
                return jpeg, "image/jpeg"
            time.sleep(0.5)
        return None

    return grab


def _webcam_source():
    import cv2

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("cannot open webcam device 0")

    def grab():
        ok, frame = cap.read()
        if not ok:
            return None
        ok, buf = cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return buf.tobytes(), "image/jpeg"

    return grab


def _dir_source(path: str):
    files = sorted(p for p in Path(path).iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        raise RuntimeError(f"no images in {path}")
    it = iter(files)

    def grab():
        try:
            data = next(it).read_bytes()
        except StopIteration:
            return None
        return data, _media_type(data)

    return grab
