"""
tests/test_branding_model.py — Tests for branding_model (Phase 8).

Pure-Python: aspect ratio math, kit validation, persistence.
"""

import pytest

from branding_model import (
    AspectRatio,
    BrandingError,
    BrandKit,
    SubtitleStyle,
)


class TestAspectRatio:
    def test_valid_names(self):
        for name in ("16:9", "9:16", "1:1", "4:5"):
            assert AspectRatio.is_valid(name)
        assert not AspectRatio.is_valid("21:9")

    def test_resolution(self):
        assert AspectRatio.resolution("16:9") == (1920, 1080)
        assert AspectRatio.resolution("9:16") == (1080, 1920)

    def test_unknown_resolution_raises(self):
        with pytest.raises(BrandingError, match="Available"):
            AspectRatio.resolution("21:9")

    def test_ratio_value(self):
        assert abs(AspectRatio.ratio_value("16:9") - 16 / 9) < 0.01
        assert abs(AspectRatio.ratio_value("1:1") - 1.0) < 0.01

    def test_letterbox_horizontal_source(self):
        # 1920x1080 into 9:16 → pillarboxed: fits 1080 wide, 606 tall
        sw, sh, x, y = AspectRatio.fit_letterbox(1920, 1080, "9:16")
        assert sw == 1080 and sh == 606
        assert x == 0
        assert y == (1920 - 606) // 2

    def test_letterbox_vertical_source(self):
        # 1080x1920 into 16:9 → letterboxed: fits 606 wide, 1080 tall
        sw, sh, x, y = AspectRatio.fit_letterbox(1080, 1920, "16:9")
        assert sw == 606 and sh == 1080
        assert x == (1920 - 606) // 2
        assert y == 0

    def test_letterbox_same_ratio(self):
        sw, sh, x, y = AspectRatio.fit_letterbox(1920, 1080, "16:9")
        assert (sw, sh) == (1920, 1080)
        assert (x, y) == (0, 0)

    def test_crop_wide_source(self):
        # 1920x1080 into 1:1 → crop sides to 1080x1080
        cw, ch, tw, th = AspectRatio.fit_crop(1920, 1080, "1:1")
        assert (cw, ch) == (1080, 1080)
        assert (tw, th) == (1080, 1080)

    def test_crop_tall_source(self):
        # 1080x1920 into 9:16 is already matching
        cw, ch, _tw, _th = AspectRatio.fit_crop(1080, 1920, "9:16")
        assert (cw, ch) == (1080, 1920)

    def test_crop_partial(self):
        # 320x240 (4:3) into 9:16 → crop width to 135
        cw, ch, _tw, _th = AspectRatio.fit_crop(320, 240, "9:16")
        assert ch == 240
        assert abs(cw - 135) < 2


class TestBrandKit:
    def _root(self, tmp_path, with_files=True):
        if with_files:
            assets = tmp_path / "media" / "assets"
            assets.mkdir(parents=True)
            (assets / "logo.png").write_bytes(b"png")
            (assets / "theme.mp3").write_bytes(b"mp3")
        return str(tmp_path)

    def test_default_kit_is_clean(self, tmp_path):
        kit = BrandKit()
        assert kit.validate(self._root(tmp_path, with_files=False)) == []

    def test_valid_full_kit(self, tmp_path):
        kit = BrandKit(
            logo_path="media/assets/logo.png",
            music_path="media/assets/theme.mp3",
        )
        assert kit.validate(self._root(tmp_path)) == []

    def test_missing_asset_flagged(self, tmp_path):
        kit = BrandKit(logo_path="media/assets/ghost.png")
        problems = kit.validate(self._root(tmp_path))
        assert any("not found" in p for p in problems)

    def test_absolute_path_rejected(self, tmp_path):
        kit = BrandKit(logo_path="/etc/passwd")
        problems = kit.validate(self._root(tmp_path))
        assert any("relative" in p for p in problems)

    def test_bad_logo_position(self, tmp_path):
        kit = BrandKit(logo_position="middle")
        problems = kit.validate(self._root(tmp_path, with_files=False))
        assert any("position" in p for p in problems)

    def test_opacity_bounds(self, tmp_path):
        kit = BrandKit(logo_opacity=1.5)
        problems = kit.validate(self._root(tmp_path, with_files=False))
        assert any("opacity" in p for p in problems)

    def test_music_volume_bounds(self, tmp_path):
        kit = BrandKit(music_volume=-0.1)
        problems = kit.validate(self._root(tmp_path, with_files=False))
        assert any("volume" in p for p in problems)

    def test_bad_color(self, tmp_path):
        kit = BrandKit(primary_color="gold")
        problems = kit.validate(self._root(tmp_path, with_files=False))
        assert any("#RRGGBB" in p for p in problems)

    def test_bad_ratio(self, tmp_path):
        kit = BrandKit(aspect_ratio="21:9")
        problems = kit.validate(self._root(tmp_path, with_files=False))
        assert any("Aspect ratio" in p for p in problems)

    def test_bad_fit_mode(self, tmp_path):
        kit = BrandKit(fit_mode="stretch")
        problems = kit.validate(self._root(tmp_path, with_files=False))
        assert any("letterbox" in p for p in problems)

    def test_unknown_option_raises(self):
        with pytest.raises(BrandingError, match="Unknown brand option"):
            BrandKit(hologram=True)

    def test_round_trip(self, tmp_path):
        kit = BrandKit(
            logo_path="media/assets/logo.png",
            music_path="media/assets/theme.mp3",
            music_volume=0.5,
            aspect_ratio="9:16",
        )
        kit.subtitle_style.enabled = True
        kit.subtitle_style.font_size = 36
        data = kit.to_dict()
        clone = BrandKit.from_dict(data)
        assert clone.logo_path == kit.logo_path
        assert clone.music_volume == 0.5
        assert clone.aspect_ratio == "9:16"
        assert clone.subtitle_style.enabled is True
        assert clone.subtitle_style.font_size == 36

    def test_from_dict_ignores_unknown(self):
        clone = BrandKit.from_dict({
            "logo_path": None, "quantum": 1,
        })
        assert not hasattr(clone, "quantum")


class TestSubtitleStyle:
    def test_defaults_off(self):
        style = SubtitleStyle()
        assert style.enabled is False
        assert style.validate() == []

    def test_bad_position(self):
        style = SubtitleStyle(position="middle-left")
        assert any("position" in p for p in style.validate())

    def test_bad_color(self):
        style = SubtitleStyle(primary_color="white")
        assert any("#RRGGBB" in p for p in style.validate())

    def test_background_formats(self):
        ok = SubtitleStyle(background="#000000@80")
        assert ok.validate() == []
        bad = SubtitleStyle(background="#00000080")  # missing @AA
        assert any("background" in p for p in bad.validate())

    def test_negative_font(self):
        style = SubtitleStyle(font_size=0)
        assert any("font size" in p for p in style.validate())

    def test_unknown_option(self):
        with pytest.raises(BrandingError, match="Unknown subtitle"):
            SubtitleStyle(glow=True)
