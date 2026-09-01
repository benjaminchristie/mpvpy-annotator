import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from video_annotator import AnnotationStore, ProgressStore, TimestampStore
from video_annotator.annotator import VideoAnnotator


class FakeSession:
    """Stands in for MPVSession: no mpv, no window, just enough surface
    area for VideoAnnotator to drive. Tests call `press(key)` to simulate
    the user hitting a key, and set `.time` directly to simulate playback
    position advancing."""

    def __init__(self, speed=1.0, fullscreen=False):
        self.time = 0.0
        self.duration = 10.0
        self.quit_requested = False
        self.paused = False
        self._handlers = {}
        self.seeks = []
        self.messages = []

    def on_key(self, key):
        def register(fn):
            self._handlers[key] = fn
            return fn
        return register

    def press(self, key):
        self._handlers[key]()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def seek_to(self, t):
        self.seeks.append(t)
        self.time = t

    def show_text(self, text, duration_ms=1500):
        self.messages.append(text)

    def request_quit(self):
        self.quit_requested = True

    def load(self, path):
        pass

    def wait_until_closed(self):
        pass

    def close(self):
        pass


class ScriptedPrompt:
    """Returns each label in order; records the prompt text it was shown."""

    def __init__(self, labels):
        self._labels = list(labels)
        self.prompts_seen = []

    def ask(self, prompt_text):
        self.prompts_seen.append(prompt_text)
        return self._labels.pop(0) if self._labels else None


class TestVideoAnnotator(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.timestamps = TimestampStore(os.path.join(self.tmpdir.name, "timestamps.csv"))
        self.annotations = AnnotationStore(os.path.join(self.tmpdir.name, "annotations.csv"))
        self.progress = ProgressStore(os.path.join(self.tmpdir.name, "progress.txt"))

    def tearDown(self):
        self.tmpdir.cleanup()

    def _make(self, labels, session_holder):
        prompt = ScriptedPrompt(labels)

        def factory(**kwargs):
            session_holder["session"] = FakeSession(**kwargs)
            return session_holder["session"]

        return VideoAnnotator(
            self.timestamps, self.annotations, self.progress, prompt,
            session_factory=factory,
        ), prompt

    def test_full_contiguous_segmentation(self):
        holder = {}
        annotator, prompt = self._make(["pick salt shaker", "season salt on steak"], holder)

        # Run annotate() in a way we can drive: since FakeSession.wait_until_closed
        # returns immediately, we need to simulate key presses that happen
        # "during" playback before annotate() calls wait_until_closed().
        # We do this by wrapping wait_until_closed to run our script.
        events = []

        def scripted_wait():
            session = holder["session"]
            session.time = 3.0
            session.press("b")   # segment 0: 0.0 -> 3.0
            session.time = 10.0
            session.press("e")   # segment 1: 3.0 -> 10.0, finalizes video
            events.append("done")

        result = self._run_with_script(annotator, "video.mp4", "video.mp4", scripted_wait)

        self.assertEqual(result.status, "done")
        segs = self.timestamps.segments_for("video.mp4")
        self.assertEqual(len(segs), 2)
        self.assertEqual((segs[0].start, segs[0].end), (0.0, 3.0))
        self.assertEqual((segs[1].start, segs[1].end), (3.0, 10.0))
        self.assertEqual(self.annotations.label_for("video.mp4", 0), "pick salt shaker")
        self.assertEqual(self.annotations.label_for("video.mp4", 1), "season salt on steak")
        self.assertTrue(self.progress.is_done("video.mp4"))

        # The result object itself carries the segments directly, with
        # duration/fraction already filled in -- no CSV parsing needed.
        self.assertEqual(result.duration, 10.0)
        self.assertEqual(len(result.segments), 2)
        self.assertEqual(result.segments[0].label, "pick salt shaker")
        self.assertAlmostEqual(result.segments[0].start_frac, 0.0)
        self.assertAlmostEqual(result.segments[0].end_frac, 0.3)
        self.assertAlmostEqual(result.segments[1].start_frac, 0.3)
        self.assertAlmostEqual(result.segments[1].end_frac, 1.0)

    def test_undo_removes_last_segment_and_rewinds(self):
        holder = {}
        annotator, prompt = self._make(
            ["pick salt shaker", "pick salt shaker (retry)", "season salt on steak"], holder
        )

        def scripted_wait():
            session = holder["session"]
            session.time = 3.0
            session.press("b")     # segment 0 saved: 0.0 -> 3.0
            session.press("u")     # undo it
            self.assertEqual(session.seeks[-1], 0.0)  # rewound to segment start
            session.time = 4.0
            session.press("b")     # re-do it with a corrected label: 0.0 -> 4.0
            session.time = 10.0
            session.press("e")     # final segment: 4.0 -> 10.0

        result = self._run_with_script(annotator, "video.mp4", "video.mp4", scripted_wait)

        self.assertEqual(result.status, "done")
        segs = self.timestamps.segments_for("video.mp4")
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].end, 4.0)  # the corrected boundary, not the undone one
        self.assertEqual(self.annotations.label_for("video.mp4", 0), "pick salt shaker (retry)")

    def test_cancelled_label_does_not_save_segment(self):
        holder = {}
        annotator, prompt = self._make([None], holder)  # blank input -> cancel

        def scripted_wait():
            session = holder["session"]
            session.time = 3.0
            session.press("b")

        self._run_with_script(annotator, "video.mp4", "video.mp4", scripted_wait)

        self.assertEqual(self.timestamps.segments_for("video.mp4"), [])

    def test_skip_video_leaves_it_pending(self):
        holder = {}
        annotator, prompt = self._make([], holder)

        def scripted_wait():
            holder["session"].press("n")

        result = self._run_with_script(annotator, "video.mp4", "video.mp4", scripted_wait)

        self.assertEqual(result.status, "skipped")
        self.assertFalse(self.progress.is_done("video.mp4"))

    def test_resumes_from_last_end_on_second_call(self):
        self.timestamps.add("video.mp4", 0, 0.0, 3.0)
        self.annotations.add("video.mp4", 0, "pick salt shaker")

        holder = {}
        annotator, prompt = self._make(["season salt on steak"], holder)

        def scripted_wait():
            session = holder["session"]
            self.assertEqual(session.seeks[0], 3.0)  # resumed at the right spot
            session.time = 10.0
            session.press("e")

        result = self._run_with_script(annotator, "video.mp4", "video.mp4", scripted_wait)

        self.assertEqual(result.status, "done")
        segs = self.timestamps.segments_for("video.mp4")
        self.assertEqual(len(segs), 2)
        self.assertEqual((segs[1].start, segs[1].end), (3.0, 10.0))

    def _run_with_script(self, annotator, full_path, video_key, script_fn):
        # Monkeypatch FakeSession.wait_until_closed for this one call so the
        # "user interaction" happens at the right point in annotate()'s flow.
        original = FakeSession.wait_until_closed
        FakeSession.wait_until_closed = lambda self: script_fn()
        try:
            return annotator.annotate(full_path, video_key=video_key)
        finally:
            FakeSession.wait_until_closed = original


if __name__ == "__main__":
    unittest.main()
