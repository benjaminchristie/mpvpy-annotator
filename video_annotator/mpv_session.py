"""A thin, purpose-built wrapper around python-mpv.

Isolating this in its own class means the rest of the package never touches
the `mpv` module directly, and could be pointed at a different player (say,
a VLC binding) by swapping this one file.
"""
try:
    import mpv as _mpv
except ImportError as exc:  # pragma: no cover - environment-dependent
    raise ImportError(
        "python-mpv is required for recording annotations. Install the mpv "
        "player and its shared library (e.g. `sudo apt install mpv libmpv2`) "
        "and the python binding (`pip install python-mpv --break-system-packages`). "
        "Reading back existing annotations (AnnotationDataset) does not need this."
    ) from exc


class MPVSession:
    """One mpv player instance for one video."""

    def __init__(self, speed: float = 1.0, fullscreen: bool = False, **extra_mpv_options):
        options = dict(
            input_default_bindings=True,
            input_vo_keyboard=True,
            osc=True,
            loop_file="inf",
            speed=speed,
            fullscreen=fullscreen,
            keep_open="always",
        )
        options.update(extra_mpv_options)
        self.player = _mpv.MPV(**options)

    def load(self, path: str):
        self.player.play(path)
        self.player.wait_until_playing()

    @property
    def time(self) -> float:
        return self.player.time_pos or 0.0

    @property
    def duration(self) -> float:
        return self.player.duration or 0.0

    def pause(self):
        self.player.pause = True

    def resume(self):
        self.player.pause = False

    def seek_to(self, t: float):
        """Absolute, frame-accurate seek (used by undo, so it must land
        exactly back on the mark rather than the nearest keyframe)."""
        self.player.seek(max(t, 0.0), reference="absolute", precision="exact")

    def show_text(self, text: str, duration_ms: int = 1500):
        self.player.show_text(text, str(duration_ms))

    def on_key(self, key: str):
        """Decorator: registers `key` (mpv keyname, e.g. "b") to call the
        decorated function with no arguments. Shadows mpv's built-in
        binding for that key, same as a custom input.conf entry would."""
        return self.player.on_key_press(key)

    def request_quit(self):
        self.player.command("quit")

    def wait_until_closed(self):
        self.player.wait_for_shutdown()

    def close(self):
        try:
            self.player.terminate()
        except Exception:
            pass
