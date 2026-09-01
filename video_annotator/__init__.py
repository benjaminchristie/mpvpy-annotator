"""
video_annotator
================

A small, composable toolkit for interactively segmenting videos (e.g. robot
task demonstrations) into non-overlapping, labeled skills/subtasks using
mpv, and for reading the results back in other python programs.

Quick start (CLI)
------------------
    python3 annotate_videos.py /path/to/videos

One-off, no-CSV usage
----------------------
    from video_annotator import annotate_video
    result = annotate_video("demo_03.mp4")
    for seg in result.segments:
        print(seg.label, seg.start, seg.end, seg.start_frac, seg.end_frac)

Batch recording over a folder (writes CSVs, resumable)
---------------------------------------------------------
    from video_annotator import BatchAnnotator
    BatchAnnotator(root_dir="videos/", video_exts=(".mp4", ".mov")).run()

Programmatic reading (no mpv/display needed)
---------------------------------------------
    from video_annotator import AnnotationDataset
    ds = AnnotationDataset("timestamps.csv", "annotations.csv")
    for segment in ds.all_segments():
        print(segment.video, segment.start, segment.end, segment.label)
"""
from .models import AnnotationResult, Segment
from .stores import AnnotationDataset, AnnotationStore, ProgressStore, TimestampStore
from .terminal_prompt import NoTerminalFoundError, TerminalPrompt

__all__ = [
    "Segment",
    "AnnotationResult",
    "TimestampStore",
    "AnnotationStore",
    "ProgressStore",
    "AnnotationDataset",
    "TerminalPrompt",
    "NoTerminalFoundError",
]

# The recording side of the package needs mpv + libmpv installed. Keep that
# optional so pure result-reading code (AnnotationDataset, the stores) works
# on any machine, including ones with no display and no mpv at all.
try:
    from .mpv_session import MPVSession
    from .annotator import VideoAnnotator
    from .batch import BatchAnnotator
    from .api import annotate_video, annotate_videos, probe_duration

    __all__ += [
        "MPVSession", "VideoAnnotator", "BatchAnnotator",
        "annotate_video", "annotate_videos", "probe_duration",
    ]
except ImportError:
    pass
