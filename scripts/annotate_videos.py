#!/usr/bin/env python3
"""
Thin convenience wrapper. After `pip install -e .`, prefer the installed
`annotate-videos` command or `python -m video_annotator.cli` -- this file
just lets you run the tool straight from a checkout without installing it.

See `video_annotator/cli.py` for the actual implementation and `--help`
text.
"""
from video_annotator.cli import main

if __name__ == "__main__":
    main()
