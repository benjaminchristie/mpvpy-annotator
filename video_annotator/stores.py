"""
Resumable, atomically-written CSV stores.

Timestamps and annotations are kept in two separate files, joined by the
pair (video, index). Keeping them separate means either can be read, backed
up, regenerated, or fed into a different tool independently -- e.g. you
might want the timing information for computing action-chunk boundaries
without caring about the text labels at all.

None of the classes in this module import mpv or spawn any processes, so
they can be used (and unit tested) completely standalone.
"""
import csv
import os
import tempfile
from typing import Dict, List, Optional

from .models import TimestampRow, AnnotationRow, Segment


def _atomic_write_rows(path: str, header: List[str], rows: List[list]):
    """Write `rows` to `path` via a temp file + rename, so a crash or Ctrl-C
    mid-write can never leave a truncated/corrupt CSV behind."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_annot_")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


class TimestampStore:
    """CSV of (video, index, start, end). One row per finished segment.

    Pass `path=None` for a purely in-memory store that never touches disk
    -- useful when you want segments back directly in your own code and
    don't want CSV files left behind.
    """

    HEADER = ["video", "index", "start", "end"]

    def __init__(self, path: Optional[str] = "timestamps.csv"):
        self.path = path
        self._rows: List[TimestampRow] = []
        if self.path:
            self._load()

    def _load(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            return
        with open(self.path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self._rows.append(
                    TimestampRow(
                        video=r["video"],
                        index=int(r["index"]),
                        start=float(r["start"]),
                        end=float(r["end"]),
                    )
                )

    def _flush(self):
        if not self.path:
            return
        _atomic_write_rows(
            self.path,
            self.HEADER,
            [
                [r.video, r.index, f"{r.start:.3f}", f"{r.end:.3f}"]
                for r in self._rows
            ],
        )

    def videos(self) -> List[str]:
        """All distinct video keys that have at least one segment."""
        return sorted({r.video for r in self._rows})

    def segments_for(self, video: str) -> List[TimestampRow]:
        return sorted((r for r in self._rows if r.video == video), key=lambda r: r.index)

    def next_index(self, video: str) -> int:
        segs = self.segments_for(video)
        return segs[-1].index + 1 if segs else 0

    def last_end(self, video: str) -> float:
        """Where the next open segment should start -- 0.0 if none yet."""
        segs = self.segments_for(video)
        return segs[-1].end if segs else 0.0

    def add(self, video: str, index: int, start: float, end: float) -> TimestampRow:
        row = TimestampRow(video, index, start, end)
        self._rows.append(row)
        self._flush()
        return row

    def remove_last(self, video: str) -> Optional[TimestampRow]:
        """Pop the most recent segment for `video` (used by undo). Returns
        the removed row, or None if there was nothing to remove."""
        segs = self.segments_for(video)
        if not segs:
            return None
        last = segs[-1]
        self._rows.remove(last)
        self._flush()
        return last


class AnnotationStore:
    """CSV of (video, index, label). One row per finished segment's text.

    Pass `path=None` for a purely in-memory store (see TimestampStore).
    """

    HEADER = ["video", "index", "label"]

    def __init__(self, path: Optional[str] = "annotations.csv"):
        self.path = path
        self._rows: List[AnnotationRow] = []
        if self.path:
            self._load()

    def _load(self):
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            return
        with open(self.path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self._rows.append(
                    AnnotationRow(video=r["video"], index=int(r["index"]), label=r["label"])
                )

    def _flush(self):
        if not self.path:
            return
        _atomic_write_rows(
            self.path,
            self.HEADER,
            [[r.video, r.index, r.label] for r in self._rows],
        )

    def labels_for(self, video: str) -> List[AnnotationRow]:
        return sorted((r for r in self._rows if r.video == video), key=lambda r: r.index)

    def label_for(self, video: str, index: int) -> Optional[str]:
        for r in self._rows:
            if r.video == video and r.index == index:
                return r.label
        return None

    def add(self, video: str, index: int, label: str) -> AnnotationRow:
        row = AnnotationRow(video, index, label)
        self._rows.append(row)
        self._flush()
        return row

    def remove(self, video: str, index: int):
        before = len(self._rows)
        self._rows = [r for r in self._rows if not (r.video == video and r.index == index)]
        if len(self._rows) != before:
            self._flush()


class ProgressStore:
    """Tracks which videos have been fully annotated, so a batch run can
    skip them on resume. Plain one-path-per-line text file.

    Pass `path=None` for a purely in-memory store (see TimestampStore).
    """

    def __init__(self, path: Optional[str] = "progress.txt"):
        self.path = path
        self._done = set()
        if self.path:
            self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self._done = {line.strip() for line in f if line.strip()}

    def _flush(self):
        if not self.path:
            return
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_progress_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for v in sorted(self._done):
                f.write(v + "\n")
        os.replace(tmp_path, self.path)

    def is_done(self, video: str) -> bool:
        return video in self._done

    def mark_done(self, video: str):
        if video not in self._done:
            self._done.add(video)
            self._flush()

    def unmark(self, video: str):
        if video in self._done:
            self._done.discard(video)
            self._flush()

    def all_done(self) -> List[str]:
        return sorted(self._done)


class AnnotationDataset:
    """Read-only convenience view for consuming finished annotations from
    another program (a dataloader, an analysis script, etc.). Joins the two
    stores by (video, index) into fully populated Segment objects.

    Does not import mpv and never launches any process -- safe to use on a
    machine with no display, no mpv, and no terminal emulator.
    """

    def __init__(self, timestamps_path: str = "timestamps.csv", annotations_path: str = "annotations.csv"):
        self.timestamps = TimestampStore(timestamps_path)
        self.annotations = AnnotationStore(annotations_path)

    def videos(self) -> List[str]:
        return self.timestamps.videos()

    def segments(self, video: str, duration: Optional[float] = None) -> List[Segment]:
        """Segments for one video. Pass `duration` (seconds) if you know
        the video's total length and want `.start_frac`/`.end_frac` filled
        in -- this class never opens the video file itself, so it has no
        way to measure that on its own. `video_annotator.probe_duration()`
        can supply it if you don't already have it."""
        labels: Dict[int, str] = {r.index: r.label for r in self.annotations.labels_for(video)}
        return [
            Segment(
                video=r.video, index=r.index, start=r.start, end=r.end,
                label=labels.get(r.index), video_duration=duration,
            )
            for r in self.timestamps.segments_for(video)
        ]

    def all_segments(self, durations: Optional[Dict[str, float]] = None) -> List[Segment]:
        """All segments across all videos. `durations` optionally maps
        video key -> total length in seconds, for fraction support."""
        durations = durations or {}
        out: List[Segment] = []
        for video in self.videos():
            out.extend(self.segments(video, duration=durations.get(video)))
        return out
