"""
edit_model.py — Non-destructive edit decision list (Phase 6).

The original takes in media/raw are NEVER modified. All editing is a
list of Segment decisions stored in project.json (`segments`); export
(Phase 10) materializes them with FFmpeg.

Model:
- The timeline is the ordered list of "keep" ranges. A fresh project
  keeps each clip whole: [clip, 0, duration].
- Trimming a head/tail mutates in/out points; cutting splits one keep
  range in two (creating a hole between them); deleting removes one
  keep range entirely.
- Undo/redo is a plain snapshot stack of the segment list (cheap:
  decisions are tiny dicts, never media).
"""

import copy
import json

from logging_setup import get_logger

log = get_logger("Edit")

MAX_HISTORY = 100


class EditError(Exception):
    """Invalid edit operation with a user-facing message."""


class Segment:
    """One keep-range over one clip: [in_s, out_s) of clip_seconds."""

    __slots__ = ("clip", "clip_seconds", "in_s", "out_s")

    def __init__(self, clip, in_s, out_s, clip_seconds):
        self.clip = clip              # relative path inside the project
        self.in_s = float(in_s)
        self.out_s = float(out_s)
        self.clip_seconds = float(clip_seconds)

    @property
    def duration(self):
        return self.out_s - self.in_s

    def to_dict(self):
        return {
            "clip": self.clip,
            "in": round(self.in_s, 3),
            "out": round(self.out_s, 3),
        }

    @classmethod
    def from_dict(cls, data, clip_seconds):
        return cls(data["clip"], data["in"], data["out"], clip_seconds)

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Segment({self.clip}, {self.in_s:.2f}-{self.out_s:.2f})"


class EditList:
    """
    The ordered keep-ranges plus undo/redo.

    clip_durations: {clip_rel_path: seconds} — filled by ffprobe
    (ffmpeg_tools.probe_clip) before any edit is allowed.
    """

    def __init__(self, clip_durations=None):
        self._clip_durations = dict(clip_durations or {})
        self.segments = []
        self._undo_stack = []
        self._redo_stack = []

    # ── Setup ───────────────────────────────────────────────

    def set_clip_durations(self, durations):
        """{clip: seconds}; keeps segments that reference known clips."""
        self._clip_durations = dict(durations)
        self.segments = [s for s in self.segments if s.clip in durations]
        self._undo_stack.clear()
        self._redo_stack.clear()

    def load_clips(self, clip_paths):
        """
        Builds whole-clip segments for each clip (fresh timeline).

        Loading a document is NOT an undoable edit: like any editor,
        opening a file starts a fresh history.
        """
        self.segments = [
            Segment(path, 0.0, self._clip_durations[path],
                    self._clip_durations[path])
            for path in clip_paths
            if path in self._clip_durations
        ]
        self._undo_stack.clear()
        self._redo_stack.clear()
        log.info("Timeline loaded: %d whole clips", len(self.segments))

    # ── Queries ──────────────────────────────────────────────

    def total_duration(self):
        return sum(s.duration for s in self.segments)

    def find(self, index):
        """Segment by index with a clear error."""
        if not 0 <= index < len(self.segments):
            raise EditError(f"Segment {index} does not exist")
        return self.segments[index]

    def can_undo(self):
        return bool(self._undo_stack)

    def can_redo(self):
        return bool(self._redo_stack)

    # ── Edits (all checkpointed for undo) ─────────────────────

    def trim_head(self, index, new_in):
        """Moves the START of a keep range forward."""
        seg = self.find(index)
        if not 0.0 <= new_in < seg.out_s:
            raise EditError(
                f"Trim point must be between 0 and {seg.out_s:.2f}s"
            )
        self._checkpoint()
        seg.in_s = float(new_in)

    def trim_tail(self, index, new_out):
        """Moves the END of a keep range back."""
        seg = self.find(index)
        if not seg.in_s < new_out <= seg.clip_seconds:
            raise EditError(
                f"Trim point must be between {seg.in_s:.2f}s and the clip end "
                f"({seg.clip_seconds:.2f}s)"
            )
        self._checkpoint()
        seg.out_s = float(new_out)

    def cut(self, index, at_seconds):
        """
        Splits a keep range at at_seconds, dropping the middle when
        the caller cuts a hole: here 'cut' = split-and-remove, so the
        editor turns one keep range into two with a hole between.

        Concretely: [in, out) becomes [in, at) + [at2, out) where the
        HOLE is [at, at2). With hole=0 this is a plain split (for
        markers). hole_seconds defaults to 0.
        """
        return self.cut_hole(index, at_seconds, hole_seconds=0.0)

    def cut_hole(self, index, at_seconds, hole_seconds=0.0):
        seg = self.find(index)
        hole = max(0.0, float(hole_seconds))
        if not seg.in_s < at_seconds < seg.out_s:
            raise EditError(
                "Cut point must be inside the segment "
                f"({seg.in_s:.2f}-{seg.out_s:.2f}s)"
            )
        if at_seconds + hole >= seg.out_s:
            raise EditError("The hole would remove the rest of the segment")
        self._checkpoint()
        left = Segment(seg.clip, seg.in_s, at_seconds, seg.clip_seconds)
        right = Segment(seg.clip, at_seconds + hole, seg.out_s,
                        seg.clip_seconds)
        self.segments[index:index + 1] = [left, right]
        self._redo_stack.clear()

    def delete(self, index):
        """Removes one keep range from the timeline."""
        self.find(index)  # validates
        self._checkpoint()
        del self.segments[index]
        self._redo_stack.clear()

    def move(self, index, to_index):
        """Reorders timeline segments."""
        seg = self.find(index)
        if not 0 <= to_index <= len(self.segments):
            raise EditError("Invalid destination position")
        self._checkpoint()
        self.segments.pop(index)
        self.segments.insert(min(to_index, len(self.segments)), seg)
        self._redo_stack.clear()

    # ── Undo / redo ─────────────────────────────────────────

    def _checkpoint(self):
        snapshot = json.dumps([s.to_dict() for s in self.segments])
        if self._undo_stack and self._undo_stack[-1] == snapshot:
            return  # no change between checkpoints
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > MAX_HISTORY:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore(self, snapshot):
        data = json.loads(snapshot)
        self.segments = [
            Segment.from_dict(d, self._clip_durations[d["clip"]])
            for d in data
        ]

    def undo(self):
        if not self._undo_stack:
            raise EditError("Nothing to undo")
        self._redo_stack.append(
            json.dumps([s.to_dict() for s in self.segments])
        )
        self._restore(self._undo_stack.pop())
        log.info("Undo (%d left)", len(self._undo_stack))

    def redo(self):
        if not self._redo_stack:
            raise EditError("Nothing to redo")
        self._undo_stack.append(
            json.dumps([s.to_dict() for s in self.segments])
        )
        self._restore(self._redo_stack.pop())
        log.info("Redo (%d left)", len(self._redo_stack))

    # ── Persistence ─────────────────────────────────────────

    def to_project_json(self):
        """The `segments` array for project.json."""
        return [s.to_dict() for s in self.segments]

    def load_project_json(self, data):
        """Restores segments from project.json (validating clips)."""
        restored = []
        for d in data:
            if d["clip"] not in self._clip_durations:
                log.warning("Segment references missing clip: %s", d["clip"])
                continue
            seg = Segment.from_dict(d, self._clip_durations[d["clip"]])
            if seg.out_s > seg.clip_seconds:
                seg.out_s = seg.clip_seconds
            if seg.in_s >= seg.out_s:
                log.warning("Skipping empty segment: %r", seg)
                continue
            restored.append(seg)
        self.segments = restored
        self._undo_stack.clear()
        self._redo_stack.clear()

    def copy(self):
        """Deep copy for tests."""
        clone = EditList(copy.deepcopy(self._clip_durations))
        clone.segments = [
            Segment(s.clip, s.in_s, s.out_s, s.clip_seconds)
            for s in self.segments
        ]
        return clone
