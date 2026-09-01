"""Walks a directory of videos and runs the interactive annotator on each
one that isn't already marked complete."""
import os
from typing import Iterable, List, Optional, Sequence

from .annotator import VideoAnnotator
from .stores import AnnotationStore, ProgressStore, TimestampStore
from .terminal_prompt import TerminalPrompt


class BatchAnnotator:
    """Ties the stores, the terminal prompt, and the per-video annotator
    together into a resumable batch run over a folder of videos.

    Safe to construct and re-run repeatedly: videos already marked done in
    `progress_path` are skipped, and partially-annotated videos resume
    exactly where the user left off.
    """

    def __init__(
        self,
        root_dir: str = ".",
        video_exts: Sequence[str] = (".mp4",),
        timestamps_path: str = "timestamps.csv",
        annotations_path: str = "annotations.csv",
        progress_path: str = "progress.txt",
        speed: float = 1.0,
        fullscreen: bool = False,
        terminal: Optional[str] = None,
    ):
        self.root_dir = root_dir
        self.video_exts = tuple(e.lower() for e in video_exts)

        self.timestamps = TimestampStore(timestamps_path)
        self.annotations = AnnotationStore(annotations_path)
        self.progress = ProgressStore(progress_path)
        self.prompt = TerminalPrompt(terminal=terminal)

        self.annotator = VideoAnnotator(
            timestamps=self.timestamps,
            annotations=self.annotations,
            progress=self.progress,
            prompt=self.prompt,
            speed=speed,
            fullscreen=fullscreen,
        )

    def discover_videos(self) -> List[str]:
        """Relative paths (from root_dir) of every matching video, sorted
        for a stable, repeatable ordering across runs."""
        found = []
        for root, _dirs, files in os.walk(self.root_dir):
            for filename in files:
                if filename.lower().endswith(self.video_exts):
                    full = os.path.normpath(os.path.join(root, filename))
                    found.append(os.path.relpath(full, self.root_dir))
        return sorted(found)

    def pending_videos(self) -> List[str]:
        return [v for v in self.discover_videos() if not self.progress.is_done(v)]

    def run(self) -> None:
        all_videos = self.discover_videos()
        pending = [v for v in all_videos if not self.progress.is_done(v)]
        print(f"{len(pending)}/{len(all_videos)} video(s) remaining to annotate.")

        for i, rel_path in enumerate(pending, start=1):
            full_path = os.path.join(self.root_dir, rel_path)
            print(f"[{i}/{len(pending)}] {rel_path}")
            result = self.annotator.annotate(full_path, video_key=rel_path)

            if result.status == "quit":
                print("Progress saved. Run again to resume.")
                return
            elif result.status == "skipped":
                print(f"Skipped (still pending): {rel_path}")
            else:
                print(f"Finished: {rel_path} ({len(result.segments)} segment(s))")

        print("All videos annotated!")
