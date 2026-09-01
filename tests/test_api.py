import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from video_annotator.models import Segment


class TestSegmentFractions(unittest.TestCase):
    def test_fractions_computed_when_duration_known(self):
        seg = Segment(video="v.mp4", index=0, start=2.0, end=5.0, label="pick", video_duration=10.0)
        self.assertAlmostEqual(seg.start_frac, 0.2)
        self.assertAlmostEqual(seg.end_frac, 0.5)
        self.assertAlmostEqual(seg.duration_frac, 0.3)

    def test_fractions_none_when_duration_unknown(self):
        seg = Segment(video="v.mp4", index=0, start=2.0, end=5.0, label="pick")
        self.assertIsNone(seg.start_frac)
        self.assertIsNone(seg.end_frac)
        self.assertIsNone(seg.duration_frac)


class TestInMemoryStores(unittest.TestCase):
    """path=None should behave like a normal store but never touch disk."""

    def test_timestamp_store_in_memory_roundtrip(self):
        from video_annotator import TimestampStore

        store = TimestampStore(None)
        store.add("v.mp4", 0, 0.0, 3.0)
        self.assertEqual(store.last_end("v.mp4"), 3.0)
        self.assertEqual(len(store.segments_for("v.mp4")), 1)

    def test_in_memory_store_writes_no_file(self):
        from video_annotator import AnnotationStore

        with tempfile.TemporaryDirectory() as d:
            before = set(os.listdir(d))
            store = AnnotationStore(None)
            store.add("v.mp4", 0, "pick salt shaker")
            after = set(os.listdir(d))
            self.assertEqual(before, after)  # nothing appeared in the cwd-ish dir


try:
    from video_annotator import MPVSession
    HAVE_MPV = True
except ImportError:
    HAVE_MPV = False


@unittest.skipUnless(HAVE_MPV, "python-mpv / libmpv not installed in this environment")
class TestAnnotateVideoAPI(unittest.TestCase):
    """End-to-end: real (headless) mpv, real VideoAnnotator, driven through
    the annotate_video()/annotate_videos() convenience functions, with only
    the terminal popup stubbed out (it needs a real display)."""

    @classmethod
    def setUpClass(cls):
        import shutil
        import subprocess

        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.video_path = os.path.join(cls.tmpdir.name, "demo.mp4")
        if shutil.which("ffmpeg") is None:
            raise unittest.SkipTest("ffmpeg not available to synthesize a test video")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=160x120:rate=10",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.video_path],
            check=True, capture_output=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _drive(self, session_created, presses):
        """Background thread: waits for the session to exist, then sends
        each (delay, key) in `presses` via mpv's synthetic keypress command."""
        import threading
        import time

        def run():
            while "session" not in session_created:
                time.sleep(0.02)
            player = session_created["session"].player
            player.wait_until_playing()
            for delay, key in presses:
                time.sleep(delay)
                player.command("keypress", key)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

    def test_annotate_video_returns_segments_with_fractions_no_csv(self):
        import video_annotator.api as api_module
        from video_annotator import MPVSession

        with tempfile.TemporaryDirectory() as d:
            before = set(os.listdir(d))
            created = {}

            def headless_factory(**kw):
                # Force the null (windowless, silent) backend so this runs
                # in CI/containers with no display or audio device.
                s = MPVSession(vo="null", ao="null", **kw)
                created["session"] = s
                return s

            # Stub only the terminal popup (it needs a real display); drive
            # everything else -- mpv, VideoAnnotator, the stores -- for real.
            class StubPrompt:
                def __init__(self):
                    self.labels = iter(["pick salt shaker", "season salt on steak"])

                def ask(self, _text):
                    return next(self.labels, None)

            orig_prompt_cls = api_module.TerminalPrompt
            api_module.TerminalPrompt = lambda terminal=None: StubPrompt()
            try:
                t = self._drive(created, [(0.4, "b"), (0.4, "e")])
                result = api_module.annotate_video(
                    self.video_path, speed=8.0, session_factory=headless_factory,
                )
                t.join(timeout=2)
            finally:
                api_module.TerminalPrompt = orig_prompt_cls

            self.assertEqual(result.status, "done")
            self.assertEqual(len(result.segments), 2)
            self.assertEqual(result.segments[0].label, "pick salt shaker")
            self.assertEqual(result.segments[1].label, "season salt on steak")
            for seg in result.segments:
                self.assertIsNotNone(seg.start_frac)
                self.assertIsNotNone(seg.end_frac)
                self.assertGreaterEqual(seg.end_frac, seg.start_frac)

            # Nothing written to disk anywhere -- confirmed via cwd snapshot.
            after = set(os.listdir(d))
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
