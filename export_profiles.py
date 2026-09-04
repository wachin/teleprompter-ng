"""
export_profiles.py — Social export profiles (Phase 10).

Pure data (no Qt, no ffmpeg): every profile documents its ffmpeg
parameters and target, per the Roadmap ("Use FFmpeg with documented
parameters").

Choosing a profile means choosing (a) the aspect ratio (already in
the BrandKit) and (b) the codec ladder: fast draft vs balanced vs
high-quality master. Container/codec/fps/bitrate come from here;
geometry comes from the kit.
"""

from branding_model import AspectRatio

# Rough bytes/second at 1080p for each codec tier — used for the size
# estimate shown BEFORE a long export (Roadmap: "Show a size estimate
# when possible"). Video+audio combined, conservative.
_SIZE_HINTS_BPS = {
    "draft": 1_200_000,     # ~1.2 MB/s at 1080p
    "balanced": 2_500_000,  # ~2.5 MB/s
    "master": 5_000_000,   # ~5 MB/s
}


class ProfileError(Exception):
    """Invalid profile configuration with a user-facing message."""


class ExportProfile:
    """One named social target with its documented ffmpeg ladder."""

    def __init__(self, key, name, aspect_ratio, tier, description,
                 video_codec="libx264", audio_codec="aac",
                 container="mp4", fps=30):
        if tier not in _SIZE_HINTS_BPS:
            raise ProfileError(
                f"Unknown quality tier '{tier}'. Available: draft, "
                "balanced, master"
            )
        if not AspectRatio.is_valid(aspect_ratio):
            raise ProfileError(
                f"Unknown aspect ratio '{aspect_ratio}'"
            )
        self.key = key
        self.name = name
        self.aspect_ratio = aspect_ratio
        self.tier = tier
        self.description = description
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.container = container
        self.fps = fps

    # ── ffmpeg parameters (documented per Roadmap) ───────────

    def video_args(self):
        """
        -c:v ladder.

        draft:     veryfast preset, CRF 26 — smallest, quickest checks
        balanced:  medium preset,  CRF 21 — the social default
        master:    slow preset,    CRF 18 — archival/best quality
        """
        tiers = {
            "draft": ["-c:v", self.video_codec, "-preset", "veryfast",
                      "-crf", "26"],
            "balanced": ["-c:v", self.video_codec, "-preset", "medium",
                         "-crf", "21"],
            "master": ["-c:v", self.video_codec, "-preset", "slow",
                       "-crf", "18"],
        }
        return list(tiers[self.tier])

    def audio_args(self):
        """-c:a: AAC; bitrate by tier (draft 128k, balanced 192k,
        master 256k)."""
        bitrates = {"draft": "128k", "balanced": "192k", "master": "256k"}
        return ["-c:a", self.audio_codec, "-b:a", bitrates[self.tier]]

    def container_args(self, output):
        """Container flags: mp4 gets +faststart (web upload)."""
        args = ["-f", self.container]
        if self.container == "mp4":
            args += ["-movflags", "+faststart"]
        return [*args, output]

    # ── Estimate ─────────────────────────────────────────────

    def estimate_size_bytes(self, duration_s, output_height=1080):
        """
        Rough output size for the tier, scaled by resolution.

        A 720p vertical video holds fewer pixels than 1080p; the
        hint scales by (height/1080)^2, clamped to [0.4, 1.0] —
        good enough to warn the user before a long export.
        """
        scale = min(1.0, max(0.4, (output_height / 1080.0) ** 2))
        return int(_SIZE_HINTS_BPS[self.tier] * max(0.1, duration_s) * scale)

    def __repr__(self):  # pragma: no cover
        return f"Profile({self.key}/{self.tier})"


# ─────────────────────────────────────────────────────────────
# Built-in profiles (Roadmap Phase 10 list)
# ─────────────────────────────────────────────────────────────

PROFILES = {
    "youtube": ExportProfile(
        key="youtube", name="YouTube (16:9)", aspect_ratio="16:9",
        tier="balanced",
        description="1920x1080, H.264 CRF 21 medium, AAC 192k, "
                    "+faststart. The standard long-form upload.",
    ),
    "shorts": ExportProfile(
        key="shorts", name="TikTok / Reels / Shorts (9:16)",
        aspect_ratio="9:16", tier="balanced",
        description="1080x1920 vertical, H.264 CRF 21 medium, "
                    "AAC 192k, +faststart.",
    ),
    "linkedin": ExportProfile(
        key="linkedin", name="LinkedIn (1:1)", aspect_ratio="1:1",
        tier="balanced",
        description="1080x1080 square, H.264 CRF 21 medium, "
                    "AAC 192k, +faststart.",
    ),
    "draft": ExportProfile(
        key="draft", name="Quick draft (16:9)", aspect_ratio="16:9",
        tier="draft",
        description="Fast sanity check: H.264 veryfast preset, CRF "
                    "26, AAC 128k. Small file, quick render.",
    ),
    "master": ExportProfile(
        key="master", name="High-quality master (16:9)",
        aspect_ratio="16:9", tier="master",
        description="Archival copy: H.264 slow preset, CRF 18, AAC 256k. "
                    "Recompress from this for any platform.",
    ),
}


def get_profile(key):
    """Profile by key; raises with the available list."""
    if key not in PROFILES:
        raise ProfileError(
            "Unknown profile '{0}'. Available: {1}".format(
                key, ", ".join(sorted(PROFILES))
            )
        )
    return PROFILES[key]


def suggest_metadata(title, description="", tags=()):
    """
    Title/description/hashtags text block for the clipboard or a
    .txt file (Roadmap: 'Copy title, description and hashtags…').

    Keeps the text plain (no platform API is touched — publishing
    integration is out of scope by design).
    """
    lines = [title.strip()]
    if description.strip():
        lines.append("")
        lines.append(description.strip())
    if tags:
        lines.append("")
        lines.append(" ".join(
            "#{0}".format(t.strip().replace(" ", "").lstrip("#"))
            for t in tags if t.strip()
        ))
    return "\n".join(lines)
