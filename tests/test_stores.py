import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from video_annotator import AnnotationDataset, AnnotationStore, ProgressStore, TimestampStore


class TestTimestampStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "timestamps.csv")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_add_and_read_back(self):
        store = TimestampStore(self.path)
        store.add("vid_a.mp4", 0, 0.0, 2.5)
        store.add("vid_a.mp4", 1, 2.5, 5.0)

        segs = store.segments_for("vid_a.mp4")
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].start, 0.0)
        self.assertEqual(segs[1].end, 5.0)

    def test_next_index_and_last_end(self):
        store = TimestampStore(self.path)
        self.assertEqual(store.next_index("vid_a.mp4"), 0)
        self.assertEqual(store.last_end("vid_a.mp4"), 0.0)

        store.add("vid_a.mp4", 0, 0.0, 3.0)
        self.assertEqual(store.next_index("vid_a.mp4"), 1)
        self.assertEqual(store.last_end("vid_a.mp4"), 3.0)

    def test_remove_last_is_lifo_per_video(self):
        store = TimestampStore(self.path)
        store.add("vid_a.mp4", 0, 0.0, 1.0)
        store.add("vid_b.mp4", 0, 0.0, 1.0)
        store.add("vid_a.mp4", 1, 1.0, 2.0)

        removed = store.remove_last("vid_a.mp4")
        self.assertEqual(removed.index, 1)
        self.assertEqual(len(store.segments_for("vid_a.mp4")), 1)
        self.assertEqual(len(store.segments_for("vid_b.mp4")), 1)  # untouched

    def test_remove_last_on_empty_video_returns_none(self):
        store = TimestampStore(self.path)
        self.assertIsNone(store.remove_last("nothing.mp4"))

    def test_persists_and_reloads_from_disk(self):
        store = TimestampStore(self.path)
        store.add("vid_a.mp4", 0, 0.0, 1.234)

        reloaded = TimestampStore(self.path)
        segs = reloaded.segments_for("vid_a.mp4")
        self.assertEqual(len(segs), 1)
        self.assertAlmostEqual(segs[0].end, 1.234, places=3)

    def test_videos_lists_distinct_keys(self):
        store = TimestampStore(self.path)
        store.add("vid_a.mp4", 0, 0.0, 1.0)
        store.add("vid_b.mp4", 0, 0.0, 1.0)
        store.add("vid_a.mp4", 1, 1.0, 2.0)
        self.assertEqual(store.videos(), ["vid_a.mp4", "vid_b.mp4"])


class TestAnnotationStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "annotations.csv")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_add_and_lookup(self):
        store = AnnotationStore(self.path)
        store.add("vid_a.mp4", 0, "pick salt shaker")
        store.add("vid_a.mp4", 1, "season salt on steak")

        self.assertEqual(store.label_for("vid_a.mp4", 0), "pick salt shaker")
        self.assertEqual(store.label_for("vid_a.mp4", 1), "season salt on steak")
        self.assertIsNone(store.label_for("vid_a.mp4", 2))

    def test_remove_specific_index(self):
        store = AnnotationStore(self.path)
        store.add("vid_a.mp4", 0, "pick salt shaker")
        store.add("vid_a.mp4", 1, "season salt on steak")

        store.remove("vid_a.mp4", 0)
        self.assertIsNone(store.label_for("vid_a.mp4", 0))
        self.assertEqual(store.label_for("vid_a.mp4", 1), "season salt on steak")

    def test_labels_with_commas_round_trip(self):
        store = AnnotationStore(self.path)
        store.add("vid_a.mp4", 0, "pick up the salt, then the pepper")
        reloaded = AnnotationStore(self.path)
        self.assertEqual(reloaded.label_for("vid_a.mp4", 0), "pick up the salt, then the pepper")


class TestProgressStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "progress.txt")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_mark_and_check(self):
        store = ProgressStore(self.path)
        self.assertFalse(store.is_done("vid_a.mp4"))
        store.mark_done("vid_a.mp4")
        self.assertTrue(store.is_done("vid_a.mp4"))

    def test_unmark(self):
        store = ProgressStore(self.path)
        store.mark_done("vid_a.mp4")
        store.unmark("vid_a.mp4")
        self.assertFalse(store.is_done("vid_a.mp4"))

    def test_persists_across_instances(self):
        ProgressStore(self.path).mark_done("vid_a.mp4")
        reloaded = ProgressStore(self.path)
        self.assertTrue(reloaded.is_done("vid_a.mp4"))


class TestAnnotationDataset(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.ts_path = os.path.join(self.tmpdir.name, "timestamps.csv")
        self.an_path = os.path.join(self.tmpdir.name, "annotations.csv")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_join_produces_full_segments(self):
        ts = TimestampStore(self.ts_path)
        an = AnnotationStore(self.an_path)
        ts.add("vid_a.mp4", 0, 0.0, 2.0)
        an.add("vid_a.mp4", 0, "pick salt shaker")
        ts.add("vid_a.mp4", 1, 2.0, 5.0)
        an.add("vid_a.mp4", 1, "season salt on steak")

        ds = AnnotationDataset(self.ts_path, self.an_path)
        segs = ds.segments("vid_a.mp4")
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0].label, "pick salt shaker")
        self.assertEqual(segs[1].duration, 3.0)

    def test_missing_label_is_none_not_error(self):
        ts = TimestampStore(self.ts_path)
        ts.add("vid_a.mp4", 0, 0.0, 2.0)  # no matching annotation written

        ds = AnnotationDataset(self.ts_path, self.an_path)
        segs = ds.segments("vid_a.mp4")
        self.assertEqual(len(segs), 1)
        self.assertIsNone(segs[0].label)

    def test_all_segments_spans_multiple_videos(self):
        ts = TimestampStore(self.ts_path)
        an = AnnotationStore(self.an_path)
        ts.add("vid_a.mp4", 0, 0.0, 1.0)
        an.add("vid_a.mp4", 0, "a")
        ts.add("vid_b.mp4", 0, 0.0, 1.0)
        an.add("vid_b.mp4", 0, "b")

        ds = AnnotationDataset(self.ts_path, self.an_path)
        all_segs = ds.all_segments()
        self.assertEqual({s.video for s in all_segs}, {"vid_a.mp4", "vid_b.mp4"})


if __name__ == "__main__":
    unittest.main()
