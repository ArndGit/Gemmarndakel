from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable


CREDIT_TEXT = (
    "Musik: 'I Walk With Ghosts' by Scott Buckley - released under CC-BY 4.0. "
    "www.scottbuckley.com.au"
)


class SplashScreen:
    def __init__(
        self,
        root: tk.Tk,
        fade_out_music: Callable[[int], None] | None = None,
    ) -> None:
        self.root = root
        self.fade_out_music = fade_out_music
        self._progress = 0
        self._angle = 0
        self._closed = False
        self._failed = False

        self.window = tk.Toplevel(root)
        self.window.title("Gemmarndakel")
        self.window.overrideredirect(True)
        self.window.geometry("460x360")
        self.window.resizable(False, False)
        self.window.configure(bg="#10151d")
        self.window.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.window.attributes("-topmost", True)

        self.canvas = tk.Canvas(
            self.window,
            width=460,
            height=360,
            bg="#10151d",
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Nach göttlichen Dämpfen wird gesucht...")
        self.status_label = tk.Label(
            self.window,
            textvariable=self.status_var,
            bg="#10151d",
            fg="#f3eee3",
            font=("Segoe UI", 11),
        )
        self.status_label.place(x=30, y=276, width=400, height=28)

        self.progress_label = tk.Label(
            self.window,
            text="0%",
            bg="#10151d",
            fg="#9dd6ca",
            font=("Segoe UI", 10),
        )
        self.progress_label.place(x=210, y=318, width=40, height=20)

        self.close_button = tk.Button(
            self.window,
            text="×",
            command=self.root.destroy,
            bg="#10151d",
            fg="#f3eee3",
            activebackground="#2a303a",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            borderwidth=0,
            font=("Segoe UI", 15, "bold"),
            cursor="hand2",
        )

        self._center_on_screen()
        self._bring_to_foreground()
        self._draw_static_scene()
        self._animate()

    def set_status(self, message: str, progress: int) -> None:
        if self._failed:
            return

        self._progress = max(0, min(100, progress))
        self.status_var.set(message)
        self.progress_label.config(text=f"{self._progress}%")
        self._draw_progress()

    def show_error(self, message: str | None = None) -> None:
        self._failed = True

        self.status_var.set(message or "Der Æther ist heute zu weit weg.")
        self.status_label.config(fg="#d6d6d6")

        self.progress_label.place_forget()
        self.canvas.delete("progress")
        self.canvas.delete("shimmer")
        self.canvas.delete("mist")

        self._draw_failed_orb()

        self.canvas.create_text(
            230,
            318,
            text="Versuche es später erneut.",
            fill="#aeb4bd",
            font=("Segoe UI", 10),
            tags="error",
        )

        self.close_button.place(x=420, y=8, width=28, height=28)
        self._bring_to_foreground()

        self._fade_out_music()

    def close(self) -> None:
        self._closed = True
        self.window.destroy()

    def _fade_out_music(self) -> None:
        if self.fade_out_music is None:
            return

        try:
            self.fade_out_music(5000)
        except Exception:
            pass

    def _center_on_screen(self) -> None:
        self.window.update_idletasks()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        x = (self.window.winfo_screenwidth() - width) // 2
        y = (self.window.winfo_screenheight() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")

    def _bring_to_foreground(self) -> None:
        self.window.lift()
        self.window.focus_force()

    def _draw_static_scene(self) -> None:
        self.canvas.create_rectangle(0, 0, 460, 360, fill="#10151d", outline="")

        for index, x in enumerate((54, 92, 366, 410, 318)):
            y = 54 + (index % 3) * 34
            self.canvas.create_oval(x, y, x + 2, y + 2, fill="#c8d8ff", outline="")

        self.canvas.create_oval(126, 210, 334, 244, fill="#0a0d12", outline="")
        self.canvas.create_rectangle(178, 202, 282, 232, fill="#412f2f", outline="")
        self.canvas.create_rectangle(160, 226, 300, 244, fill="#6f5141", outline="")
        self.canvas.create_line(160, 226, 300, 226, fill="#9d7a55", width=2)

        self._draw_normal_orb()

        self.canvas.create_text(
            230,
            36,
            text="Gemmarndakel",
            fill="#f3eee3",
            font=("Georgia", 19, "bold"),
        )

        self.canvas.create_rectangle(78, 306, 382, 316, fill="#222a35", outline="#384656")
        self.canvas.create_text(
            230,
            348,
            text=CREDIT_TEXT,
            fill="#7f8a95",
            font=("Segoe UI", 7),
            width=430,
        )
        self._draw_progress()

    def _draw_normal_orb(self) -> None:
        self.canvas.delete("orb")

        self.canvas.create_oval(
            137,
            62,
            323,
            248,
            fill="#2a9fc2",
            outline="#ddf7ff",
            width=2,
            tags="orb",
        )
        self.canvas.create_oval(
            151,
            75,
            309,
            235,
            fill="#43bfd4",
            outline="",
            tags="orb",
        )
        self.canvas.create_oval(
            171,
            88,
            288,
            204,
            fill="#75d8e2",
            outline="",
            tags="orb",
        )
        self.canvas.create_arc(
            166,
            78,
            306,
            218,
            start=18,
            extent=84,
            outline="#f7ffff",
            width=6,
            style=tk.ARC,
            tags="orb",
        )
        self.canvas.create_oval(
            186,
            92,
            230,
            132,
            fill="#f8ffff",
            outline="",
            tags="orb",
        )

    def _draw_failed_orb(self) -> None:
        self.canvas.delete("orb")
        self.canvas.delete("shimmer")

        self.canvas.create_oval(
            137,
            62,
            323,
            248,
            fill="#4a4d53",
            outline="#9da1a8",
            width=2,
            tags="orb",
        )
        self.canvas.create_oval(
            151,
            75,
            309,
            235,
            fill="#666a72",
            outline="",
            tags="orb",
        )
        self.canvas.create_oval(
            171,
            88,
            288,
            204,
            fill="#8b8f97",
            outline="",
            tags="orb",
        )
        self.canvas.create_arc(
            166,
            78,
            306,
            218,
            start=18,
            extent=84,
            outline="#c4c7cc",
            width=5,
            style=tk.ARC,
            tags="orb",
        )
        self.canvas.create_oval(
            186,
            92,
            230,
            132,
            fill="#d4d6da",
            outline="",
            tags="orb",
        )

    def _draw_progress(self) -> None:
        self.canvas.delete("progress")
        width = int(300 * self._progress / 100)
        if width > 0:
            self.canvas.create_rectangle(
                80,
                308,
                80 + width,
                314,
                fill="#9dd6ca",
                outline="",
                tags="progress",
            )

    def _animate(self) -> None:
        if self._closed:
            return

        if self._failed:
            return

        self.canvas.delete("mist")
        for index in range(9):
            phase = self._angle + index * 0.9
            x = 118 + index * 28 + math.sin(phase) * 8
            y = 250 + math.cos(phase * 0.8) * 5
            self.canvas.create_oval(
                x,
                y,
                x + 42,
                y + 12,
                fill="#5b7f8e",
                outline="",
                stipple="gray50",
                tags="mist",
            )

        shimmer_x = 212 + math.sin(self._angle * 1.6) * 46
        self.canvas.delete("shimmer")
        self.canvas.create_oval(
            shimmer_x,
            118,
            shimmer_x + 20,
            138,
            fill="#fff7c8",
            outline="",
            tags="shimmer",
        )

        self._angle += 0.16
        self.window.after(60, self._animate)
