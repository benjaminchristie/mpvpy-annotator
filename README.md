# video_annotator

> [!CAUTION]
> *This code was mostly written by Claude. Use at your own risk, and do not use it in production.*

Segment a folder of demonstration videos (e.g. robot task videos) into a
sequence of **non-overlapping** labels, using `mpv` for
playback and a popup terminal window for typing each label.

Example: a video of a robot might get split into two contiguous segments,
`pick salt shaker` (0.0s–4.2s) and `season salt on steak` (4.2s–6.0s).

It's built as a small set of composable classes rather than one script, so
you can call the pieces from your own code (e.g. drive it over a custom list
of videos, or just read the finished annotations into a training pipeline).

## Install

```bash
sudo apt install mpv libmpv2 xterm    # player, its shared library, a terminal
pip install -e .
```

`libmpv2` is the exact package name on Ubuntu 24.04 (Noble); on other
distros/versions it may be `libmpv1` or `libmpv-dev`. Any terminal emulator
works (`gnome-terminal`, `konsole`, `xfce4-terminal`, `alacritty`, `kitty`,
`xterm`, ...) — the tool auto-detects whichever is on your `PATH`.

`pip install -e .` (editable install) puts `video_annotator` on your
`PYTHONPATH` so you can `import video_annotator` from any other project on
the machine, and installs an `annotate-videos` command. If your system
Python is externally managed, add `--break-system-packages`, or install
into a virtualenv instead. If you'd rather just install the one runtime
dependency without installing the package itself, `requirements.txt` is
also provided (`pip install -r requirements.txt`).

## Usage

```bash
annotate-videos /path/to/videos
```

(Equivalent alternatives: `python -m video_annotator.cli /path/to/videos`,
or `python3 annotate_videos.py /path/to/videos` if you're running straight
out of a checkout without installing anything.)

It recursively finds every `.mp4` under that folder, opens each one in mpv,
and waits for you to mark segment boundaries. Every time you finish a
segment, a terminal window pops up asking you to type its label; mpv is
paused while you type.

Useful flags:

```bash
annotate-videos /path/to/videos \
    --ext .mp4 .mov \
    --speed 2.0 \
    --timestamps out/timestamps.csv \
    --annotations out/annotations.csv \
    --progress out/progress.txt
```

Run `annotate-videos --help` for the full list.

### Keybinds

| Key     | Action                                                                 |
|---------|-------------------------------------------------------------------------|
| `b`     | **Mark boundary** — ends the current segment *and* starts the next one at the same instant |
| `e`     | **End video** — closes out the final segment, marks the video complete, advances to the next video |
| `u`     | **Undo** — discards the last saved segment and rewinds playback to its start, so you can redo it |
| `n`     | **Skip video** — leaves it untouched/pending, moves to the next video |
| `q`     | **Save & quit** — stops the whole session; re-running the command later resumes exactly where you left off |
| Space   | Pause / resume (mpv default) |
| `[` `]` | Slow down / speed up (mpv default) |

Because `b` both ends one segment and starts the next, the saved segments
always cover the video with no gaps and no overlaps — matching a task
that's fully decomposed into back-to-back skills.

Progress is written after every single segment (not just at the end of a
video), so killing the process is always safe.

## Output files

Timestamps and annotations are kept in **two separate files**, joined by
`(video, index)`. That way either can be regenerated, reviewed, or consumed
independently — e.g. you might need the timing to build fixed-length
training chunks without caring about the text at all.

**`timestamps.csv`**
```
video,index,start,end
task_01/demo_03.mp4,0,0.000,4.200
task_01/demo_03.mp4,1,4.200,6.000
```

**`annotations.csv`**
```
video,index,label
task_01/demo_03.mp4,0,pick salt shaker
task_01/demo_03.mp4,1,season salt on steak
```

**`progress.txt`** — one fully-annotated video's relative path per line, used
to skip already-finished videos on the next run.

## Using it from other Python code

### One call, no CSV files

If you just want to annotate a single video from your own code and get the
segments back directly:

```python
from video_annotator import annotate_video

result = annotate_video("videos/demo_03.mp4")

result.status      # "done", "skipped", "quit", or "unfinished"
result.duration    # video length in seconds, from mpv

for seg in result.segments:
    print(seg.label)        # "pick salt shaker"
    print(seg.start, seg.end)              # seconds, e.g. 0.0 4.2
    print(seg.start_frac, seg.end_frac)    # fraction of video length, e.g. 0.0 0.7
```

Nothing is written to disk — everything lives in the returned `result`. If
you'd *also* like a durable, resumable CSV record (e.g. to build up a
dataset across many separate calls), pass paths explicitly:

```python
result = annotate_video(
    "videos/demo_03.mp4",
    save_timestamps="timestamps.csv",
    save_annotations="annotations.csv",
)
```

For an explicit list of files (sharing one in-memory session rather than a
directory walk), use `annotate_videos`:

```python
from video_annotator import annotate_videos

results = annotate_videos(["a.mp4", "b.mp4", "c.mp4"])
for path, result in results.items():
    print(path, [seg.label for seg in result.segments])
```

### Recording a whole folder (needs mpv + a terminal on the machine you run it on)

```python
from video_annotator import BatchAnnotator

batch = BatchAnnotator(
    root_dir="videos/",
    video_exts=(".mp4", ".mov"),
    speed=2.0,
)
batch.run()
```

Or drive a single video yourself:

```python
from video_annotator import TimestampStore, AnnotationStore, ProgressStore, TerminalPrompt
from video_annotator import VideoAnnotator

annotator = VideoAnnotator(
    TimestampStore("timestamps.csv"),
    AnnotationStore("annotations.csv"),
    ProgressStore("progress.txt"),
    TerminalPrompt(),
)
result = annotator.annotate("videos/demo_03.mp4", video_key="demo_03.mp4")
# "done", "skipped", "quit", or "unfinished"
```

### Reading finished annotations back (no mpv or display required)

This is the part you'd use in a training script, a notebook, or a CI job —
`AnnotationDataset` never imports `mpv` and never launches any process:

```python
from video_annotator import AnnotationDataset

ds = AnnotationDataset("timestamps.csv", "annotations.csv")
for video in ds.videos():
    for segment in ds.segments(video):
        print(f"{video}: [{segment.start:.2f}, {segment.end:.2f}] {segment.label}")
```

`AnnotationDataset` never opens the actual video files, so it has no way to
know their total length on its own — `start_frac`/`end_frac` are `None`
unless you supply durations yourself. If you want fractions here too, pass
them in (`probe_duration` uses mpv to measure a file's length):

```python
from video_annotator import AnnotationDataset, probe_duration

ds = AnnotationDataset("timestamps.csv", "annotations.csv")
durations = {v: probe_duration(f"videos/{v}") for v in ds.videos()}
for seg in ds.all_segments(durations=durations):
    print(seg.video, seg.start_frac, seg.end_frac)
```

## Extending

Every piece is a small, independent class, so swapping one out doesn't
touch the rest:

- **Different labeling UI** — write a class with an `ask(prompt: str) -> Optional[str]`
  method (matching `TerminalPrompt`) that shows a Tkinter dialog, a `zenity`
  popup, or a web form instead, and pass it to `VideoAnnotator`/`BatchAnnotator`.
- **Different storage backend** — subclass or replace `TimestampStore` /
  `AnnotationStore` (e.g. write to SQLite or a shared database) as long as
  they expose the same `add` / `segments_for` / `last_end` / `remove_last`
  methods.
- **Non-contiguous segments** (allowing gaps for "dead time" between
  skills) — add a second keybind in `annotator.py` that starts a fresh
  segment at the current time without requiring it to equal the previous
  segment's end.

## Project layout

```
video_annotator/
    models.py           Segment / AnnotationResult / TimestampRow / AnnotationRow dataclasses
    stores.py            TimestampStore, AnnotationStore, ProgressStore, AnnotationDataset
    terminal_prompt.py    TerminalPrompt (popup terminal text entry)
    mpv_session.py        MPVSession (thin wrapper around python-mpv)
    annotator.py          VideoAnnotator (single-video interaction logic)
    batch.py             BatchAnnotator (walks a folder, resumable)
    api.py               annotate_video / annotate_videos / probe_duration (no-CSV convenience)
    cli.py               argparse entry point, installed as the `annotate-videos` command
annotate_videos.py       Thin shim for running straight from a checkout without installing
pyproject.toml          `pip install -e .` packaging
tests/                  Unit tests (mpv-dependent ones auto-skip if unavailable)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

These test the stores and the annotation state machine (boundary marking,
undo, resume, cancel) using a fake mpv session, so they run anywhere with no
display and no mpv installed.
