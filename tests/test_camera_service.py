"""
tests/test_camera_service.py — Tests for camera_service.py (Phase 2).

Unit tests parse v4l2-ctl output and exercise error diagnostics with
mocks (no hardware needed). Integration tests with the real camera
live in test_camera_integration.py and are skipped automatically when
no /dev/video0 exists.
"""

import pytest

from camera_service import (
    CameraError,
    _open_failure_reason,
    _parse_formats,
    grouped_modes,
)

SAMPLE_LIST_DEVICES = """Integrated_Webcam_HD: Integrate (usb-0000:00:14.0-5):
\t/dev/video0
\t/dev/video1
\t/dev/media0

External Cam: USB (usb-0000:00:14.0-3):
\t/dev/video2

"""

SAMPLE_FORMATS = """ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[1]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.100s (10.000 fps)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
"""


class TestParseListDevices:
    """v4l2-ctl --list-devices parsing."""

    def test_parses_names_and_devices(self):
        # list_devices runs v4l2-ctl; on this machine it works. For a
        # pure unit test we patch _run_v4l2.
        import camera_service
        from camera_service import list_devices
        original = camera_service._run_v4l2
        camera_service._run_v4l2 = lambda args: (
            SAMPLE_LIST_DEVICES if args == ["--list-devices"] else None
        )
        try:
            devices = list_devices()
        finally:
            camera_service._run_v4l2 = original
        by_dev = {d["device"]: d["name"] for d in devices}
        assert by_dev["/dev/video0"] == "Integrated_Webcam_HD"
        assert by_dev["/dev/video1"] == "Integrated_Webcam_HD"
        assert "/dev/media0" not in by_dev
        assert by_dev["/dev/video2"] == "External Cam"


class TestParseFormats:
    """v4l2-ctl --list-formats-ext parsing (the machine's real format)."""

    def test_parses_mjpg_and_yuyv(self):
        formats = _parse_formats(SAMPLE_FORMATS)
        assert formats[(1280, 720, 30.0)] == "MJPG"
        assert formats[(640, 480, 30.0)] == "MJPG"
        assert formats[(1280, 720, 10.0)] == "YUYV"
        assert formats[(640, 480, 30.0)] == "MJPG"

    def test_empty_output(self):
        assert _parse_formats("") == {}

    def test_no_capture_section(self):
        # Output with only metadata sections yields no formats
        assert _parse_formats("ioctl: VIDIOC_ENUM_FMT\n\tType: Metadata Capture\n") == {}


class TestGroupedModes:
    """Format grouping for the UI selector."""

    def test_groups_by_size(self):
        formats = _parse_formats(SAMPLE_FORMATS)
        modes = grouped_modes(formats)
        by_size = {(m["width"], m["height"]): m for m in modes}
        m720 = by_size[(1280, 720)]
        assert m720["fps"] == [30.0, 10.0]
        assert m720["format"] == "MJPG"  # MJPG preferred

    def test_sorted_largest_first(self):
        modes = grouped_modes(_parse_formats(SAMPLE_FORMATS))
        areas = [m["width"] * m["height"] for m in modes]
        assert areas == sorted(areas, reverse=True)

    def test_prefers_mjpg(self):
        formats = {
            (640, 480, 30.0): "YUYV",
            (640, 480, 15.0): "MJPG",
        }
        modes = grouped_modes(formats)
        assert modes[0]["format"] == "MJPG"

    def test_non_mjpg_uses_first_format(self):
        modes = grouped_modes({(320, 240, 30.0): "YUYV"})
        assert modes[0]["format"] == "YUYV"


class TestOpenFailureReason:
    """Actionable error messages for open() failures."""

    def test_missing_device(self):
        msg = _open_failure_reason("/dev/video99")
        assert "not found" in msg

    def test_permission_denied(self, monkeypatch, tmp_path):
        # A file that raises PermissionError on open
        target = tmp_path / "video0"
        target.write_bytes(b"")

        def fake_open(path, mode="r"):
            if str(path) == str(target):
                raise PermissionError(13, "Permission denied")
            raise FileNotFoundError

        monkeypatch.setattr("builtins.open", fake_open)
        monkeypatch.setattr("os.path.exists", lambda p: str(p) == str(target))
        msg = _open_failure_reason(str(target))
        assert "Permission denied" in msg
        assert "usermod" in msg  # corrective hint present

    def test_busy_device(self, monkeypatch, tmp_path):
        target = tmp_path / "video0"
        target.write_bytes(b"")

        def fake_open(path, mode="r"):
            if str(path) == str(target):
                raise OSError(16, "Device or resource busy")
            raise FileNotFoundError

        monkeypatch.setattr("builtins.open", fake_open)
        monkeypatch.setattr("os.path.exists", lambda p: str(p) == str(target))
        msg = _open_failure_reason(str(target))
        assert "busy" in msg

    def test_unsupported_device(self, monkeypatch, tmp_path):
        """Readable device that reports no formats → clear message."""
        target = tmp_path / "video0"
        target.write_bytes(b"")

        import camera_service
        monkeypatch.setattr(
            "os.path.exists", lambda p: str(p) == str(target)
        )
        monkeypatch.setattr(camera_service, "_run_v4l2", lambda args: None)
        msg = _open_failure_reason(str(target))
        assert "does not support" in msg or "busy" in msg


class TestCameraErrorMessages:
    """device_formats raises CameraError with actionable text."""

    def test_v4l2ctl_unavailable(self, monkeypatch):
        import camera_service
        monkeypatch.setattr(camera_service, "_run_v4l2", lambda args: None)
        with pytest.raises(CameraError, match="v4l-utils"):
            camera_service.device_formats("/dev/video0")

    def test_metadata_only_node(self, monkeypatch):
        import camera_service
        monkeypatch.setattr(
            camera_service, "_run_v4l2",
            lambda args: "ioctl: VIDIOC_ENUM_FMT\n\tType: Metadata Capture\n",
        )
        with pytest.raises(CameraError, match="metadata-only"):
            camera_service.device_formats("/dev/video1")
