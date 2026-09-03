"""
tests/test_camera_integration.py — Integration tests with real hardware.

Phase 2 acceptance: works with the built-in camera. These tests are
skipped automatically when no V4L2 camera is present (CI, containers)
or when v4l-utils/OpenCV are missing.

Phase 11 (camera change during session) is covered by the start/stop
cycles; physical unplug is a manual step documented in docs/PHASE-2.md.
"""

import os
import shutil
import time

import pytest

pytest.importorskip("cv2")

pytestmark = pytest.mark.skipif(
    not os.path.exists("/dev/video0") or shutil.which("v4l2-ctl") is None,
    reason="requires /dev/video0 and v4l-utils",
)


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def service(qapp):
    from camera_service import CameraService
    svc = CameraService()
    yield svc
    svc.shutdown()


def _first_camera():
    from camera_service import list_devices
    devices = list_devices()
    assert devices, "no camera found"
    return devices[0]["device"]


class TestRealCamera:
    """Real capture on the machine's /dev/video0."""

    def test_enumeration_finds_camera(self):
        from camera_service import list_devices
        devices = list_devices()
        assert any(d["device"] == "/dev/video0" for d in devices)
        # Names are populated (not just /dev/videoN)
        assert all(d["name"] for d in devices)

    def test_device_reports_real_formats(self):
        from camera_service import device_formats
        formats = device_formats("/dev/video0")
        assert formats, "camera reported no formats"
        # Every reported mode is real: (w, h, fps) tuples
        for (w, h, fps), fmt in formats.items():
            assert w > 0 and h > 0 and fps > 0, (w, h, fps)
            assert fmt in ("MJPG", "YUYV", "H264", "RGB3", "BGR3")

    def test_capture_emits_frames(self, service, qapp):

        received = []
        errors = []
        service.frame_ready.connect(lambda f: received.append(f))
        service.error.connect(lambda m: errors.append(m))

        from camera_service import device_formats
        # Choose a small, fast mode for the test (real capability)
        formats = device_formats("/dev/video0")
        best = min(
            ((w, h, fps) for (w, h, fps) in formats),
            key=lambda whf: whf[0] * whf[1],
        )
        service.start("/dev/video0", best[0], best[1], best[2])

        # Spin the event loop briefly to let frames flow
        end = time.monotonic() + 5.0
        while time.monotonic() < end and len(received) < 5:
            qapp.processEvents()
            time.sleep(0.02)

        service.stop()
        assert not errors, errors
        assert len(received) >= 5, "fewer than 5 frames in 5 s"
        # Frames are BGR 3-channel arrays with the requested size
        frame = received[0]
        assert frame.ndim == 3 and frame.shape[2] == 3
        assert (frame.shape[1], frame.shape[0]) == (best[0], best[1])

    def test_stop_releases_device(self, service, qapp):
        """After stop(), another process can open the camera."""
        import subprocess
        service.start("/dev/video0", 640, 480, 30)
        end = time.monotonic() + 5.0
        while time.monotonic() < end and not service.is_active():
            qapp.processEvents()
            time.sleep(0.02)
        assert service.is_active()
        service.stop()

        # v4l2-ctl must be able to query the device again (not EBUSY)
        result = subprocess.run(
            ["v4l2-ctl", "-d", "/dev/video0", "--list-formats-ext"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        assert "Video Capture" in result.stdout

    def test_restart_after_stop(self, service, qapp):
        """Camera change / re-selection during the same session."""
        received = []
        service.frame_ready.connect(lambda f: received.append(f))
        service.start("/dev/video0", 640, 480, 30)
        end = time.monotonic() + 5.0
        while time.monotonic() < end and len(received) < 3:
            qapp.processEvents()
            time.sleep(0.02)
        first_count = len(received)
        service.stop()

        received.clear()
        service.start("/dev/video0", 640, 480, 30)  # restart same session
        end = time.monotonic() + 5.0
        while time.monotonic() < end and len(received) < 3:
            qapp.processEvents()
            time.sleep(0.02)
        service.stop()
        assert first_count >= 3 and len(received) >= 3
