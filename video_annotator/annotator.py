"""Interactive controller for annotating a single video."""
import os
from typing import Callable, List, Optional

from .models import AnnotationResult, Segment
from .mpv_session import MPVSession
from .stores import AnnotationStore, ProgressStore, TimestampStore
from .terminal_prompt import TerminalPrompt

KEYBINDS = """\
  b       mark boundary: end the current segment here and start the next one
  e       end the video: close out the final segment and move on
  u       undo: discard the last saved segment and rewind to its start
  n       skip this video entirely (leaves it pending for next run)
  q       save progress and quit the whole session
  SPACE   pause / resume            (mpv default)
  [ / ]   slow down / speed up      (mpv default)
"""


class VideoAnnotator:
    """Runs one interactive mpv session over a single video, letting the
    user carve it into a sequence of non-overlapping labeled segments.

    Each "mark boundary" press both ends the current segment and starts the
    next one at the exact same instant, so the saved segments always cover
    the video with no gaps and no overlaps -- matching a task that is fully
    decomposed into back-to-back skills/subtasks.
    """

    def __init__(
        self,
        timestamps: TimestampStore,
        annotations: AnnotationStore,
        progress: ProgressStore,
        prompt: TerminalPrompt,
        speed: float = 1.0,
        fullscreen: bool = False,
        session_factory: Callable[..., MPVSession] = MPVSession,
    ):
        self.timestamps = timestamps
        self.annotations = annotations
        self.progress = progress
        self.prompt = prompt
        self.speed = speed
        self.fullscreen = fullscreen
        self._session_factory = session_factory

    def annotate(self, full_path: str, video_key: Optional[str] = None) -> AnnotationResult:
        """Runs the interactive session for one video.

        `full_path` is what gets handed to mpv to actually play.
        `video_key` is what gets stored in the stores (defaults to
        `full_path`) -- pass a path relative to some root directory if you
        want the output to stay portable across machines.

        Returns an AnnotationResult: `.status` is "done", "skipped",
        "quit", or "unfinished"; `.duration` is the video's total length in
        seconds; `.segments` is the list of Segment objects saved during
        this call (each with `.start_frac`/`.end_frac` already filled in),
        regardless of whether the underlying stores write to disk or not.
        """
        video_key = video_key if video_key is not None else full_path
        session = self._session_factory(speed=self.speed, fullscreen=self.fullscreen)
        outcome = {"result": "unfinished", "duration": 0.0}
        segment_start = {"t": self.timestamps.last_end(video_key)}

        def save_segment(end_time: float, final: bool) -> bool:
            session.pause()
            index = self.timestamps.next_index(video_key)
            label = self.prompt.ask(
                f"{os.path.basename(full_path)}\n"
                f"segment #{index}   [{segment_start['t']:.2f}s -> {end_time:.2f}s]\n"
                "Describe this skill/subtask (blank cancels):"
            )
            if not label:
                session.show_text("Cancelled", 1200)
                session.resume()
                return False
            self.timestamps.add(video_key, index, segment_start["t"], end_time)
            self.annotations.add(video_key, index, label)
            session.show_text(f"Saved #{index}: {label}", 1500)
            segment_start["t"] = end_time
            if final:
                self.progress.mark_done(video_key)
            session.resume()
            return True

        @session.on_key("b")
        def _mark_boundary():
            t = session.time
            if t <= segment_start["t"] + 0.05:
                session.show_text("Nothing to save yet", 1000)
                return
            save_segment(t, final=False)

        @session.on_key("e")
        def _end_video():
            t = session.time or session.duration
            if t <= segment_start["t"] + 0.05:
                t = max(t, session.duration)
            if save_segment(t, final=True):
                outcome["result"] = "done"
                session.request_quit()

        @session.on_key("u")
        def _undo():
            removed = self.timestamps.remove_last(video_key)
            if removed is None:
                session.show_text("Nothing to undo", 1000)
                return
            self.annotations.remove(video_key, removed.index)
            self.progress.unmark(video_key)
            segment_start["t"] = removed.start
            session.seek_to(removed.start)
            session.show_text(f"Undid #{removed.index}", 1500)

        @session.on_key("n")
        def _skip_video():
            outcome["result"] = "skipped"
            session.request_quit()

        @session.on_key("q")
        def _quit_all():
            outcome["result"] = "quit"
            session.request_quit()

        session.load(full_path)
        outcome["duration"] = session.duration
        if segment_start["t"] > 0:
            session.seek_to(segment_start["t"])
        session.show_text("b=mark  e=end video  u=undo  n=skip  q=save & quit", 4000)

        try:
            session.wait_until_closed()
        finally:
            session.close()

        return AnnotationResult(
            video=video_key,
            status=outcome["result"],
            duration=outcome["duration"],
            segments=self._collect_segments(video_key, outcome["duration"]),
        )

    def _collect_segments(self, video_key: str, duration: float) -> List[Segment]:
        labels = {r.index: r.label for r in self.annotations.labels_for(video_key)}
        return [
            Segment(
                video=video_key, index=r.index, start=r.start, end=r.end,
                label=labels.get(r.index), video_duration=duration,
            )
            for r in self.timestamps.segments_for(video_key)
        ]
