"""Plain data holders shared by the rest of the package."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TimestampRow:
    """One row of the timestamps store: a segment's time range."""
    video: str      # key used to join with AnnotationStore, e.g. a relative path
    index: int      # 0-based position of this segment within the video
    start: float    # seconds
    end: float      # seconds


@dataclass
class AnnotationRow:
    """One row of the annotations store: a segment's text label."""
    video: str
    index: int
    label: str


@dataclass
class Segment:
    """A fully joined segment: timing + label, for downstream consumption.

    `video_duration`, when known, lets you read `start`/`end` as fractions
    of the video's total length instead of only as raw seconds -- handy for
    feeding a fixed-length model that expects normalized positions.
    """
    video: str
    index: int
    start: float
    end: float
    label: Optional[str] = None
    video_duration: Optional[float] = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def start_frac(self) -> Optional[float]:
        """start / video_duration, or None if the duration isn't known."""
        if not self.video_duration:
            return None
        return self.start / self.video_duration

    @property
    def end_frac(self) -> Optional[float]:
        """end / video_duration, or None if the duration isn't known."""
        if not self.video_duration:
            return None
        return self.end / self.video_duration

    @property
    def duration_frac(self) -> Optional[float]:
        """This segment's share of the video's total length, or None."""
        if not self.video_duration:
            return None
        return self.duration / self.video_duration


@dataclass
class AnnotationResult:
    """Everything one `VideoAnnotator.annotate()` call produced, returned
    directly -- no CSV parsing required."""
    video: str
    status: str              # "done", "skipped", "quit", or "unfinished"
    duration: float          # total video length in seconds, from mpv
    segments: List[Segment] = field(default_factory=list)
