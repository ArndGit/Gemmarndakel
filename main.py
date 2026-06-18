from __future__ import annotations

import atexit
from pathlib import Path
from queue import Queue
from threading import Thread
from time import monotonic
import tkinter as tk

from audio_player import MusicPlayer
from splash import SplashScreen


MIN_SPLASH_SECONDS = 5.0
FINAL_PROGRESS_DELAY_MS = 500
CLOSE_AFTER_COMPLETE_MS = 120
INITIALIZATION_PROGRESS_LIMIT = 70


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    events: Queue[tuple[str, object]] = Queue()
    splash = SplashScreen(root)
    music_player = MusicPlayer(
        Path(__file__).resolve().with_name("sb_iwalkwithghosts.mp3"),
        volume_percent=20,
    )
    music_player.play_loop()
    atexit.register(music_player.stop)
    final_progress_started_at: float | None = None
    ready_dependencies: object | None = None
    is_finalizing = False
    startup_failed = False

    def initialize() -> None:
        try:
            from app_initializer import initialize_app

            dependencies = initialize_app(
                lambda message, progress: events.put(("progress", (message, progress)))
            )
        except Exception as exc:
            events.put(("error", exc))
        else:
            events.put(("ready", dependencies))

    def show_main_window(dependencies: object) -> None:
        from gui import FortuneTellerGUI

        splash.close()
        root.deiconify()
        FortuneTellerGUI(
            root,
            dependencies.recorder,
            dependencies.fortune_teller,
            music_player,
            card_letter_delay_ms=dependencies.settings.card_letter_delay_ms,
        )

    def complete_startup(dependencies: object) -> None:
        splash.set_status("Das Orakel erwacht...", 100)
        root.after(CLOSE_AFTER_COMPLETE_MS, lambda: show_main_window(dependencies))

    def try_complete_startup() -> None:
        nonlocal is_finalizing

        if is_finalizing or ready_dependencies is None or final_progress_started_at is None:
            return

        is_finalizing = True
        elapsed_ms = int((monotonic() - final_progress_started_at) * 1000)
        remaining_ms = max(0, FINAL_PROGRESS_DELAY_MS - elapsed_ms)
        root.after(remaining_ms, lambda: complete_startup(ready_dependencies))

    def show_final_progress() -> None:
        nonlocal final_progress_started_at

        if startup_failed or final_progress_started_at is not None:
            return

        final_progress_started_at = monotonic()
        splash.set_status("Die Vision nimmt Gestalt an...", 90)
        try_complete_startup()

    def poll_initialization() -> None:
        nonlocal ready_dependencies, startup_failed

        while not events.empty():
            event, payload = events.get()

            if event == "progress":
                message, progress = payload
                visible_progress = (
                    90
                    if final_progress_started_at is not None
                    else min(progress, INITIALIZATION_PROGRESS_LIMIT)
                )
                splash.set_status(message, visible_progress)
            elif event == "error":
                startup_failed = True
                splash.show_error(str(payload))
                return
            elif event == "ready":
                ready_dependencies = payload
                ready_progress = 90 if final_progress_started_at is not None else INITIALIZATION_PROGRESS_LIMIT
                splash.set_status("Die Vision verdichtet sich...", ready_progress)
                try_complete_startup()
                return

        root.after(80, poll_initialization)

    Thread(target=initialize, daemon=True).start()
    root.after(int(MIN_SPLASH_SECONDS * 1000), show_final_progress)
    root.after(80, poll_initialization)
    root.mainloop()


if __name__ == "__main__":
    main()
