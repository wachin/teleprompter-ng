"""
tests/test_edit_model.py — Tests for the non-destructive edit list (Phase 6).

Pure-Python: segment math, undo/redo, validation, persistence.
"""

import pytest

from edit_model import EditError, EditList, Segment


@pytest.fixture
def timeline():
    """A 60 s clip 'a' and a 30 s clip 'b' (as ffprobe would report)."""
    edit = EditList({"a.ts": 60.0, "b.ts": 30.0})
    edit.load_clips(["a.ts", "b.ts"])
    return edit


class TestLoading:
    def test_whole_clips(self, timeline):
        assert len(timeline.segments) == 2
        assert timeline.segments[0].in_s == 0.0
        assert timeline.segments[0].out_s == 60.0
        assert timeline.total_duration() == 90.0

    def test_unknown_clip_skipped(self):
        edit = EditList({"a.ts": 60.0})
        edit.load_clips(["a.ts", "ghost.ts"])
        assert len(edit.segments) == 1

    def test_load_from_project_json(self, timeline):
        timeline.trim_head(0, 5.0)
        data = timeline.to_project_json()
        fresh = EditList({"a.ts": 60.0, "b.ts": 30.0})
        fresh.load_project_json(data)
        assert fresh.segments[0].in_s == 5.0
        assert len(fresh.segments) == 2

    def test_load_skips_missing_clips(self):
        edit = EditList({"a.ts": 60.0})
        edit.load_project_json([
            {"clip": "gone.ts", "in": 0, "out": 10},
            {"clip": "a.ts", "in": 1, "out": 20},
        ])
        assert len(edit.segments) == 1
        assert edit.segments[0].clip == "a.ts"

    def test_load_clamps_overlong_and_empty(self):
        edit = EditList({"a.ts": 10.0})
        edit.load_project_json([
            {"clip": "a.ts", "in": 0, "out": 99},   # clamped to 10
            {"clip": "a.ts", "in": 5, "out": 5},   # empty → skipped
        ])
        assert len(edit.segments) == 1
        assert edit.segments[0].out_s == 10.0


class TestTrims:
    def test_trim_head(self, timeline):
        timeline.trim_head(0, 10.5)
        assert timeline.segments[0].in_s == 10.5
        assert timeline.total_duration() == 79.5

    def test_trim_tail(self, timeline):
        timeline.trim_tail(0, 50.0)
        assert timeline.segments[0].out_s == 50.0

    def test_trim_head_beyond_out_rejected(self, timeline):
        timeline.trim_tail(0, 20.0)
        with pytest.raises(EditError, match="between"):
            timeline.trim_head(0, 25.0)

    def test_trim_tail_before_in_rejected(self, timeline):
        timeline.trim_head(0, 30.0)
        with pytest.raises(EditError, match="Trim point"):
            timeline.trim_tail(0, 25.0)

    def test_trim_head_to_zero_is_valid(self, timeline):
        """0.0 is the natural 'no trim' value — must be accepted."""
        timeline.trim_head(0, 0.0)
        assert timeline.segments[0].in_s == 0.0


class TestCutAndDelete:
    def test_cut_hole_splits(self, timeline):
        timeline.cut_hole(0, 20.0, hole_seconds=5.0)
        assert len(timeline.segments) == 3
        left, right, _b = timeline.segments
        assert (left.in_s, left.out_s) == (0.0, 20.0)
        assert (right.in_s, right.out_s) == (25.0, 60.0)
        assert timeline.total_duration() == 85.0  # 90 - 5 hole

    def test_cut_zero_hole_is_split(self, timeline):
        timeline.cut_hole(0, 30.0, hole_seconds=0.0)
        assert len(timeline.segments) == 3
        assert timeline.total_duration() == 90.0  # nothing lost

    def test_cut_outside_segment_rejected(self, timeline):
        with pytest.raises(EditError, match="inside"):
            timeline.cut_hole(0, 99.0)
        with pytest.raises(EditError, match="inside"):
            timeline.cut_hole(0, 0.0)

    def test_hole_beyond_end_rejected(self, timeline):
        with pytest.raises(EditError, match="rest of the segment"):
            timeline.cut_hole(0, 55.0, hole_seconds=10.0)

    def test_delete_range(self, timeline):
        timeline.delete(0)
        assert [s.clip for s in timeline.segments] == ["b.ts"]
        assert timeline.total_duration() == 30.0

    def test_delete_invalid_index(self, timeline):
        with pytest.raises(EditError, match="does not exist"):
            timeline.delete(5)


class TestMove:
    def test_reorder(self, timeline):
        timeline.move(0, 1)
        assert [s.clip for s in timeline.segments] == ["b.ts", "a.ts"]

    def test_move_invalid(self, timeline):
        with pytest.raises(EditError, match="position"):
            timeline.move(0, 9)


class TestUndoRedo:
    """Every mutation checkpoints; undo/redo round-trips exactly."""

    def test_undo_trims(self, timeline):
        timeline.trim_head(0, 10.0)
        timeline.undo()
        assert timeline.segments[0].in_s == 0.0
        assert not timeline.can_undo()
        with pytest.raises(EditError, match="undo"):
            timeline.undo()

    def test_redo_restores(self, timeline):
        timeline.trim_head(0, 10.0)
        timeline.undo()
        timeline.redo()
        assert timeline.segments[0].in_s == 10.0

    def test_undo_cuts(self, timeline):
        timeline.cut_hole(0, 20.0, 5.0)
        assert len(timeline.segments) == 3
        timeline.undo()
        assert len(timeline.segments) == 2
        assert timeline.total_duration() == 90.0

    def test_undo_delete(self, timeline):
        timeline.delete(1)
        timeline.undo()
        assert len(timeline.segments) == 2

    def test_linear_history(self, timeline):
        timeline.trim_head(0, 5.0)
        timeline.trim_head(0, 10.0)
        timeline.undo()
        timeline.undo()
        assert timeline.segments[0].in_s == 0.0
        timeline.redo()
        assert timeline.segments[0].in_s == 5.0

    def test_new_edit_clears_redo(self, timeline):
        timeline.trim_head(0, 5.0)
        timeline.undo()
        assert timeline.can_redo()
        timeline.trim_tail(0, 50.0)  # new edit forks history
        assert not timeline.can_redo()

    def test_undo_nothing_raises(self, timeline):
        with pytest.raises(EditError, match="undo"):
            timeline.undo()
        with pytest.raises(EditError, match="redo"):
            timeline.redo()

    def test_history_capped(self):
        edit = EditList({"a.ts": 1000.0})
        edit.load_clips(["a.ts"])
        for i in range(150):
            edit.trim_head(0, float(i + 1))
        # Capped at MAX_HISTORY=100: undoing all of them lands at
        # trim #50 (the 100th checkpoint from the end), never crashes
        for _ in range(100):
            edit.undo()
        assert edit.segments[0].in_s == 50.0
        with pytest.raises(EditError):
            edit.undo()

    def test_persistence_round_trip(self, timeline):
        timeline.trim_head(0, 3.0)
        timeline.cut_hole(0, 20.0, 2.0)
        data = timeline.to_project_json()
        assert data[0] == {"clip": "a.ts", "in": 3.0, "out": 20.0}
        assert data[1] == {"clip": "a.ts", "in": 22.0, "out": 60.0}


class TestSegmentDataclass:
    def test_to_from_dict(self):
        seg = Segment("x.ts", 1.5, 9.5, 12.0)
        data = seg.to_dict()
        assert data == {"clip": "x.ts", "in": 1.5, "out": 9.5}
        clone = Segment.from_dict(data, 12.0)
        assert clone.duration == 8.0

    def test_duration(self):
        assert Segment("x", 2.0, 7.0, 10.0).duration == 5.0
