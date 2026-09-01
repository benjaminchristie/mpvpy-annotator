#!/usr/bin/env python3
"""
Segment-annotate a folder of demonstration videos with mpv.

Requirements:
    - mpv + libmpv installed on the system   (sudo apt install mpv libmpv2)
    - a terminal emulator on PATH            (xterm, gnome-terminal, ...)
    - pip install python-mpv --break-system-packages

Recursively finds every video under ROOT, plays each one in mpv, and lets
you carve it into a sequence of non-overlapping labeled segments -- for
example a robot demonstration made up of "pick salt shaker", then
"season salt on steak". Progress is saved after every segment, so you can
quit at any point (q) and pick up exactly where you left off next run.

Keybinds:
    b       mark boundary: end the current segment here, start the next one
    e       end the video: close out the final segment and move to the next video
    u       undo: discard the last saved segment and rewind to its start
    n       skip this video entirely (stays pending for next run)
    q       save progress and quit
    SPACE   pause / resume            (mpv default)
    [ / ]   slow down / speed up      (mpv default)

Output:
    timestamps.csv    video,index,start,end
    annotations.csv   video,index,label
    progress.txt      one fully-annotated video path per line

The two CSVs are joined by (video, index) but kept as separate files by
design -- see the video_annotator package docstring / README for why.
"""
import argparse

from . import BatchAnnotator


def main():
    parser = argparse.ArgumentParser(
        description="Segment-annotate a folder of demonstration videos with mpv.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("root", nargs="?", default=".", help="Root directory of videos (searched recursively). Default: current directory.")
    parser.add_argument("--ext", nargs="+", default=[".mp4"], metavar="EXT", help="Video file extensions to include, e.g. --ext .mp4 .mov. Default: .mp4")
    parser.add_argument("--timestamps", default="timestamps.csv", help="Path to the timestamps CSV. Default: timestamps.csv")
    parser.add_argument("--annotations", default="annotations.csv", help="Path to the annotations CSV. Default: annotations.csv")
    parser.add_argument("--progress", default="progress.txt", help="Path to the completed-videos list. Default: progress.txt")
    parser.add_argument("--speed", type=float, default=1.0, help="Initial playback speed. Default: 1.0")
    parser.add_argument("--fullscreen", action="store_true", help="Start mpv fullscreen (note: this can hide the terminal popup on some window managers).")
    parser.add_argument("--terminal", default=None, help="Force a specific terminal emulator (e.g. xterm, gnome-terminal). Default: auto-detect.")
    args = parser.parse_args()

    batch = BatchAnnotator(
        root_dir=args.root,
        video_exts=args.ext,
        timestamps_path=args.timestamps,
        annotations_path=args.annotations,
        progress_path=args.progress,
        speed=args.speed,
        fullscreen=args.fullscreen,
        terminal=args.terminal,
    )
    batch.run()


if __name__ == "__main__":
    main()
