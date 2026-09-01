"""Pop up a real terminal window to collect a line of free text from the user.

Kept deliberately separate from the mpv/annotation logic: it has no idea it's
being used for video annotation, so it's easy to swap for a GUI dialog
(tkinter, zenity, ...) by writing another class with the same `.ask()` method.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

# (executable name, argv prefix used to run a command inside a new window)
# Each prefix is followed by [sys.executable, script_path] when launched.
_CANDIDATES: List[Tuple[str, List[str]]] = [
    ("gnome-terminal", ["--wait", "--"]),
    ("x-terminal-emulator", ["-e"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["--disable-server", "-x"]),
    ("alacritty", ["-e"]),
    ("kitty", []),
    ("xterm", ["-e"]),
]


class NoTerminalFoundError(RuntimeError):
    pass


class TerminalPrompt:
    """Spawns a terminal emulator running a tiny python `input()` script,
    waits for it to close, and returns whatever was typed."""

    def __init__(self, terminal: Optional[str] = None):
        """`terminal` forces a specific emulator name (e.g. "xterm"); by
        default the first available one from a preference list is used."""
        self._terminal, self._prefix = self._resolve(terminal)

    def _resolve(self, terminal: Optional[str]) -> Tuple[str, List[str]]:
        if terminal:
            for name, prefix in _CANDIDATES:
                if name == terminal:
                    if not shutil.which(name):
                        raise NoTerminalFoundError(f"'{name}' was requested but is not on PATH.")
                    return name, prefix
            if shutil.which(terminal):
                return terminal, ["-e"]
            raise NoTerminalFoundError(f"'{terminal}' was requested but is not on PATH.")

        for name, prefix in _CANDIDATES:
            if shutil.which(name):
                return name, prefix

        raise NoTerminalFoundError(
            "No terminal emulator found on PATH. Install one (e.g. "
            "`sudo apt install xterm`) or pass `terminal=` explicitly."
        )

    def ask(self, prompt: str) -> Optional[str]:
        """Opens a terminal window, shows `prompt`, and blocks until the
        user presses Enter (or closes the window / hits Ctrl-C).

        Returns the typed text with surrounding whitespace stripped, or
        None if the input was empty/cancelled.
        """
        with tempfile.TemporaryDirectory(prefix="video_annotator_") as d:
            result_path = os.path.join(d, "result.txt")
            script_path = os.path.join(d, "prompt.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(_PROMPT_SCRIPT.format(prompt=repr(prompt), result_path=repr(result_path)))

            argv = [self._terminal, *self._prefix, sys.executable, script_path]
            subprocess.run(argv)  # blocks until the terminal window exits

            if not os.path.exists(result_path):
                return None
            with open(result_path, encoding="utf-8") as f:
                text = f.read().strip()
            return text or None


_PROMPT_SCRIPT = """\
import sys
print({prompt})
try:
    text = input("> ")
except (EOFError, KeyboardInterrupt):
    text = ""
with open({result_path}, "w", encoding="utf-8") as out:
    out.write(text)
"""
