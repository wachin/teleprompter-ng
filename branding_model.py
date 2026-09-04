"""
branding_model.py — Brand kit and aspect ratios (Phase 8).

Pure Python data + validation (no Qt, no ffmpeg): everything lives
in project.json under `branding` so any export re-uses the same kit.

The kit: logo (project-relative path + position + opacity), colors,
intro/outro (project-relative media), music (file + volume + fade in
/out), subtitle style (position, colors, size), and the target
aspect ratio. Files are referenced RELATIVELY (Rule 12) and copied
into the project's media/assets when the UI imports them.
"""

import os
import re
from typing import ClassVar

from logging_setup import get_logger

log = get_logger("Branding")


class BrandingError(Exception):
    """Invalid branding data with a user-facing message."""


# ─────────────────────────────────────────────────────────────
# Aspect ratios
# ─────────────────────────────────────────────────────────────

class AspectRatio:
    """Named social-media ratios with canonical resolutions."""

    RATIOS: ClassVar[dict] = {
        "16:9":  (1920, 1080),
        "9:16":  (1080, 1920),
        "1:1":   (1080, 1080),
        "4:5":   (1080, 1350),
    }

    @classmethod
    def is_valid(cls, name):
        return name in cls.RATIOS

    @classmethod
    def resolution(cls, name):
        """(w, h) canonical for the ratio; raises for unknown names."""
        if name not in cls.RATIOS:
            raise BrandingError(
                "Unknown aspect ratio '{0}'. Available: {1}".format(
                    name, ", ".join(sorted(cls.RATIOS))
                )
            )
        return cls.RATIOS[name]

    @classmethod
    def ratio_value(cls, name):
        """w/h as float (1.777… for 16:9)."""
        w, h = cls.resolution(name)
        return w / h

    @classmethod
    def fit_letterbox(cls, source_w, source_h, target):
        """
        Letterbox geometry: the source scaled to fit inside the
        target ratio, centered, with black bars.

        Returns (scaled_w, scaled_h, x, y) in target pixels —
        used by render_pipeline to build the pad filter.
        """
        tw, th = cls.resolution(target)
        scale = min(tw / source_w, th / source_h)
        sw, sh = int(source_w * scale) // 2 * 2, int(source_h * scale) // 2 * 2
        x = (tw - sw) // 2
        y = (th - sh) // 2
        return sw, sh, x, y

    @classmethod
    def fit_crop(cls, source_w, source_h, target):
        """
        Crop geometry: the source center-cropped to the target
        ratio then scaled to fill (no bars, edges lost).

        Returns (crop_w, crop_h, scaled_w, scaled_h) in source
        pixels — the crop happens BEFORE scaling.
        """
        target_ratio = cls.ratio_value(target)
        source_ratio = source_w / source_h
        if source_ratio > target_ratio:
            # Source too wide: crop the sides
            crop_h = source_h
            crop_w = int(source_h * target_ratio)
        else:
            crop_w = source_w
            crop_h = int(source_w / target_ratio)
        tw, th = cls.resolution(target)
        return crop_w, crop_h, tw, th


# ─────────────────────────────────────────────────────────────
# Brand kit
# ─────────────────────────────────────────────────────────────

_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right")
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class BrandKit:
    """
    Serializable brand configuration.

    All paths are project-relative (validated on load); None means
    the feature is off. Defaults keep everything disabled so an
    empty kit renders exactly the trimmed timeline.
    """

    def __init__(self, **kwargs):
        # Logo
        self.logo_path = None           # project-relative
        self.logo_position = "top-right"
        self.logo_opacity = 0.85          # 0..1
        self.logo_scale = 0.15            # fraction of output width

        # Colors (brand identity, used by future lower-thirds)
        self.primary_color = "#FFD700"
        self.secondary_color = "#1a1a2e"

        # Intro / outro clips (project-relative)
        self.intro_path = None
        self.outro_path = None

        # Music
        self.music_path = None
        self.music_volume = 0.35          # 0..1 relative to original
        self.music_fade_in = 1.0          # seconds
        self.music_fade_out = 2.0         # seconds

        # Subtitles burn-in style
        self.subtitle_style = SubtitleStyle()

        # Output
        self.aspect_ratio = "16:9"
        self.fit_mode = "letterbox"        # letterbox | crop

        for key, value in kwargs.items():
            if not hasattr(self, key):
                raise BrandingError(f"Unknown brand option: {key}")
            setattr(self, key, value)

    # ── Validation ───────────────────────────────────────────

    def validate(self, project_root):
        """
        Checks every configured asset exists (project-relative).

        Returns a list of problems; empty = ready.
        """
        problems = []
        for attr in ("logo_path", "intro_path", "outro_path", "music_path"):
            path = getattr(self, attr)
            if path is None:
                continue
            if os.path.isabs(path):
                problems.append(
                    f"{attr} must be a project-relative path"
                )
                continue
            full = os.path.join(project_root, path)
            if not os.path.isfile(full):
                problems.append(
                    f"{attr} not found in the project: {path}"
                )
        if self.logo_position not in _POSITIONS:
            problems.append(
                "Logo position must be one of: {0}".format(
                    ", ".join(_POSITIONS)
                )
            )
        if not 0.0 <= self.logo_opacity <= 1.0:
            problems.append("Logo opacity must be between 0 and 1")
        if not 0.0 < self.logo_scale <= 0.5:
            problems.append("Logo scale must be between 0 and 0.5")
        if not 0.0 <= self.music_volume <= 1.0:
            problems.append("Music volume must be between 0 and 1")
        if self.music_fade_in < 0 or self.music_fade_out < 0:
            problems.append("Music fades cannot be negative")
        for color in (self.primary_color, self.secondary_color):
            if not _HEX_COLOR.match(color):
                problems.append(
                    f"Colors must look like #RRGGBB (got {color})"
                )
        if not AspectRatio.is_valid(self.aspect_ratio):
            problems.append(
                "Aspect ratio must be one of: {0}".format(
                    ", ".join(sorted(AspectRatio.RATIOS))
                )
            )
        if self.fit_mode not in ("letterbox", "crop"):
            problems.append("Fit mode must be letterbox or crop")
        problems.extend(self.subtitle_style.validate())
        return problems

    # ── Persistence ──────────────────────────────────────────

    def to_dict(self):
        data = {k: v for k, v in self.__dict__.items()
                if k != "subtitle_style"}
        data["subtitle_style"] = self.subtitle_style.to_dict()
        return data

    @classmethod
    def from_dict(cls, data):
        """Builds a kit from project.json, ignoring unknown keys."""
        clean = {k: v for k, v in (data or {}).items()
                 if k in cls().__dict__ or k == "subtitle_style"}
        style = clean.pop("subtitle_style", None)
        kit = cls(**clean)
        if style:
            kit.subtitle_style = SubtitleStyle.from_dict(style)
        return kit

    def copy(self):
        return BrandKit.from_dict(self.to_dict())


class SubtitleStyle:
    """Burn-in appearance for subtitles (Phase 8)."""

    POSITIONS = ("bottom-center", "top-center", "bottom-left", "bottom-right")

    def __init__(self, **kwargs):
        self.enabled = False
        self.position = "bottom-center"
        self.font_size = 28               # relative to 1080p height
        self.primary_color = "#FFFFFF"
        self.outline_color = "#000000"
        self.background = None            # None | "#RRGGBB@alpha"

        for key, value in kwargs.items():
            if not hasattr(self, key):
                raise BrandingError(f"Unknown subtitle option: {key}")
            setattr(self, key, value)

    def validate(self):
        problems = []
        if self.position not in self.POSITIONS:
            problems.append(
                "Subtitle position must be one of: {0}".format(
                    ", ".join(self.POSITIONS)
                )
            )
        if self.font_size <= 0:
            problems.append("Subtitle font size must be positive")
        for color in (self.primary_color, self.outline_color):
            if not _HEX_COLOR.match(color):
                problems.append(
                    f"Subtitle colors must look like #RRGGBB (got {color})"

                )
        if self.background is not None and not re.match(
            r"^#[0-9a-fA-F]{6}@\d{2}$", self.background
        ):
            problems.append(
                "Subtitle background must look like #RRGGBB@AA or empty"
            )
        return problems

    def to_dict(self):
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data):
        clean = {k: v for k, v in (data or {}).items()
                 if k in cls().__dict__}
        return cls(**clean)
