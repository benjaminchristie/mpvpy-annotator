"""High-level, no-CSV-required convenience API.

Use this when you just want to call one function from your own code and get
segments back directly, rather than wiring up stores yourself.
"""
import os
from typing import Callable, Dict, List, Optional, Sequence

from .annotator import VideoAnnotator
from .models import AnnotationResult
from .mpv_session import MPVSession
from .stores import AnnotationStore, ProgressStore, TimestampStore
from .terminal_prompt import TerminalPrompt


def _annotator_kwargs(session_factory: Optional[Callable[..., MPVSession]]) -> dict:
    # Only override VideoAnnotator's default session_factory if the caller
    # supplied one (e.g. tests injecting a headless/fake session).
    return {"session_factory": session_factory} if session_factory is not None else {}


def probe_duration(path: str) -> float:
    """Opens `path` in a headless (no window, no audio) mpv instance just
    long enough to read its duration in seconds, then closes it. Useful for
    attaching start_frac/end_frac to segments read back from CSV via
    AnnotationDataset, which never opens video files itself."""
    session = MPVSession(vo="null", ao="null")
    try:
        session.load(path)
        return session.duration
    finally:
        session.close()


def annotate_video(
    path: str,
    speed: float = 1.0,
    fullscreen: bool = False,
    terminal: Optional[str] = None,
    save_timestamps: Optional[str] = None,
    save_annotations: Optional[str] = None,
    session_factory: Optional[Callable[..., MPVSession]] = None,
) -> AnnotationResult:
    """Interactively annotate one video and get the result back directly.

    No CSV files are written by default. Pass `save_timestamps=` and/or
    `save_annotations=` paths if you'd *also* like a durable record on disk
    (e.g. an existing CSV to append to and resume from later) -- otherwise
    everything stays in memory and is returned to you.

    Returns an AnnotationResult with:
        .status     "done", "skipped", "quit", or "unfinished"
        .duration   total video length in seconds
        .segments   list of Segment, each with .start, .end, .label,
                    and .start_frac / .end_frac (start/end divided by
                    the video's duration)

    Example:
        >>> from video_annotator import annotate_video
        >>> result = annotate_video("demo_03.mp4")
        >>> for seg in result.segments:
        ...     print(seg.label, seg.start, seg.end, seg.start_frac, seg.end_frac)
    """
    video_key = os.path.basename(path)
    timestamps = TimestampStore(save_timestamps)
    annotations = AnnotationStore(save_annotations)
    progress = ProgressStore(None)  # one-off call; no persistent "done" list needed
    prompt = TerminalPrompt(terminal=terminal)

    annotator = VideoAnnotator(
        timestamps, annotations, progress, prompt, speed=speed, fullscreen=fullscreen,
        **_annotator_kwargs(session_factory),
    )
    return annotator.annotate(path, video_key=video_key)


def annotate_videos(
    paths: Sequence[str],
    speed: float = 1.0,
    fullscreen: bool = False,
    terminal: Optional[str] = None,
    save_timestamps: Optional[str] = None,
    save_annotations: Optional[str] = None,
    session_factory: Optional[Callable[..., MPVSession]] = None,
) -> Dict[str, AnnotationResult]:
    """Same as `annotate_video`, but for an explicit list of files (rather
    than a directory walk -- see BatchAnnotator for that). Shares one
    TimestampStore/AnnotationStore across all of them, so if you pass
    `save_timestamps`/`save_annotations`, all results land in the same
    two files. Returns {path: AnnotationResult}, in the order given.

    Stops early (without raising) if you press `q` on any video; the
    returned dict simply won't contain the videos not yet reached.
    """
    timestamps = TimestampStore(save_timestamps)
    annotations = AnnotationStore(save_annotations)
    progress = ProgressStore(None)
    prompt = TerminalPrompt(terminal=terminal)

    annotator = VideoAnnotator(
        timestamps, annotations, progress, prompt, speed=speed, fullscreen=fullscreen,
        **_annotator_kwargs(session_factory),
    )

    results: Dict[str, AnnotationResult] = {}
    for path in paths:
        # Use the full path (not just the basename) as the store key here,
        # since two files in different folders can share a filename.
        result = annotator.annotate(path, video_key=path)
        results[path] = result
        if result.status == "quit":
            break
    return results
