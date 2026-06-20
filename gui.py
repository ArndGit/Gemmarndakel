from __future__ import annotations

import base64
from io import BytesIO
import json
import math
import random
import struct
from threading import Thread
from time import monotonic
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
import traceback
import zlib

from audio_player import MusicPlayer
from audio_recorder import AudioRecorder
from fortune_service import FortuneTellerService, NoAudioError, NoSpeechError


CREDIT_TEXT = (
    "'I Walk With Ghosts' by Scott Buckley - released under CC-BY 4.0. "
    "www.scottbuckley.com.au"
)
CONTENT_WIDTH = 640
CONTENT_HEIGHT = 760
EXTINGUISHED_CANDLE_SECONDS = 5.0
FOG_FILL_SECONDS = 0.75
FOG_CLEAR_SECONDS = 1.5
SCENE_FADE_IN_SECONDS = 1.2
SCENE_FADE_HOLD_SECONDS = 0.12
SCENE_FADE_OUT_SECONDS = 0.9
SCENE_FADE_MAX_ALPHA = 0.5
SCENE_FADE_COLOR = (255, 255, 255)
STAR_SLOT_COUNT = 320
STAR_HOLD_SECONDS = 30.0
STAR_FADE_OUT_SECONDS = 50.0
CARD_LETTER_DELAY_MS = 50
CARD_LETTER_SHARPEN_SECONDS = 0.55
CRYSTAL_CORE_CYCLE_SECONDS = 30.0
FRAME_DELAY_MS = 33
SHUTDOWN_SECONDS = 5.0
MIN_WINDOW_ALPHA = 0.04
PROGRESS_SMOOTHING_PER_SECOND = 4.0
PHASE_MARKER_POSITIONS = {
    "persona": (156, 96),
    "therapy_plan": (238, 84),
    "scenario": (320, 96),
    "prophecy": (402, 84),
}
CHEAT_STAGE_NAMES = ("therapy_plan", "scenario", "prophecy")
CHEAT_STAGE_LABELS = {
    "therapy_plan": "Therapy Plan",
    "scenario": "Scenario",
    "prophecy": "Prophecy",
}
CHEAT_RANDOM_OPTION = "(random)"


class FortuneTellerGUI:
    def __init__(
        self,
        root: tk.Tk,
        recorder: AudioRecorder,
        fortune_teller: FortuneTellerService,
        music_player: MusicPlayer,
        card_letter_delay_ms: int = CARD_LETTER_DELAY_MS,
    ) -> None:
        self.root = root
        self.recorder = recorder
        self.fortune_teller = fortune_teller
        self.music_player = music_player
        self.card_letter_delay_ms = max(0, card_letter_delay_ms)

        self.mode = "candle"
        self.status_text = "Halte die Flamme entzündet."
        self.progress = 0.0
        self._display_progress = 0.0
        self.prophecy = ""
        self._angle = 0.0
        self._vapor_angle = 0.0
        self._star_angle = 0.0
        self._angle_velocity = 0.0
        self._vapor_velocity = 0.0
        self._star_velocity = 0.0
        self._last_frame_at = monotonic()
        self._smoke_age = 0.0
        self._audio_level = 0.0
        self._audio_visual_level = 0.0
        self._is_recording = False
        self._extinguish_started_at: float | None = None
        self._fog_clear_started_at: float | None = None
        self._pending_prophecy: str | None = None
        self._pending_reset_message: str | None = None
        self._scene_fade_started_at: float | None = None
        self._scene_fade_phase: str | None = None
        self._is_shutting_down = False
        self._is_destroyed = False
        self._shutdown_started_at: float | None = None
        self._shutdown_start_volume = self.music_player.volume_percent
        self._content_offset_x = 0
        self._content_offset_y = 0
        self._star_phases: list[float] = []
        self._star_activated_at: list[float | None] = []
        self._star_sizes: list[int] = []
        self._star_fill_colors: list[str] = []
        self._star_outline_colors: list[str] = []
        self._next_star_slot = 0
        self._phase_markers: dict[str, tuple[str, str, str, float, str | None]] = {}
        self._phase_marker_hitboxes: dict[str, tuple[float, float, float]] = {}
        self._hovered_phase_marker: str | None = None
        self._card_reveal_started_at: float | None = None
        self._card_layout_key: tuple[str, int, int, int, int] | None = None
        self._card_letters: list[tuple[str, float, float, tkfont.Font, int | None]] = []
        self._cloud_image_cache: dict[tuple[int, int, str], tk.PhotoImage] = {}
        self._vignette_image_cache: dict[tuple[int, int], tk.PhotoImage] = {}
        self._gray_veil_strength = 0.0
        self._gray_veil_image: tk.PhotoImage | None = None
        self._gray_veil_image_key: tuple[int, int, int] | None = None
        self._frame_images: list[tk.PhotoImage] = []
        self._cheat_mode_enabled = False
        self._alt_pressed = False
        self._alt_code_digits = ""
        self._cheat_stage_options = self.fortune_teller.get_stage_variant_names()
        self._cheat_stage_vars = {
            stage_name: tk.StringVar(value=CHEAT_RANDOM_OPTION)
            for stage_name in CHEAT_STAGE_NAMES
        }
        self._cheat_panel = tk.Frame(
            self.root,
            bg="#161d26",
            bd=1,
            highlightbackground="#c9a45f",
            highlightthickness=1,
        )
        self._cheat_status_label = tk.Label(
            self._cheat_panel,
            text="CHEAT MODE",
            bg="#161d26",
            fg="#f2d28b",
            font=("Consolas", 11, "bold"),
            anchor="w",
        )
        self._cheat_combo_boxes: dict[str, ttk.Combobox] = {}
        self._reset_stars()

        self.root.title("Gemmarndakel")
        self.root.configure(bg="#10151d")
        self.root.attributes("-fullscreen", True)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<F11>", self._keep_fullscreen)
        self.root.bind("<Escape>", lambda event: self.close())

        self.canvas = tk.Canvas(
            root,
            width=self.root.winfo_screenwidth(),
            height=self.root.winfo_screenheight(),
            bg="#10151d",
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.tag_bind("candle_hotspot", "<Button-1>", self.start_recording)
        self.canvas.tag_bind("card_close", "<Button-1>", self.dismiss_card)
        self.canvas.bind("<ButtonRelease-1>", self.stop_recording)
        self.canvas.bind("<Motion>", self._handle_pointer_motion)
        self.canvas.bind("<Leave>", self._handle_pointer_leave)
        self.root.bind("<KeyPress>", self._handle_key_press, add="+")
        self.root.bind("<KeyRelease>", self._handle_key_release, add="+")

        self._build_cheat_panel()

        self._animate()

    def _keep_fullscreen(self, event: tk.Event) -> str:
        self.root.attributes("-fullscreen", True)
        return "break"

    def start_recording(self, event: tk.Event) -> None:
        if self._is_shutting_down:
            return

        if self.mode != "candle":
            return

        self.fortune_teller.set_stage_variant_overrides(
            self._current_stage_variant_overrides()
        )

        self._is_recording = True
        self.mode = "recording"
        self.status_text = "Die Kerze brennt. Sprich in die Flamme."
        self._reset_progress()
        self.prophecy = ""
        self._pending_prophecy = None
        self._pending_reset_message = None
        self._fog_clear_started_at = None
        self._extinguish_started_at = None
        self._scene_fade_started_at = None
        self._scene_fade_phase = None
        self._audio_level = 0.0
        self._audio_visual_level = 0.0
        self._reset_card_reveal()
        self._reset_stars()
        self._reset_phase_markers()
        self._refresh_cheat_panel()
        self.recorder.start()

        Thread(target=self._capture_and_process, daemon=True).start()

    def stop_recording(self, event: tk.Event) -> None:
        if self._is_shutting_down:
            return

        if self.mode != "recording":
            return

        self._is_recording = False
        self._audio_level = 0.0
        self._smoke_age = 0
        self._extinguish_started_at = monotonic()
        self.mode = "extinguishing"
        self.status_text = "Die Kerze erlischt..."
        self.recorder.stop()
        self.root.after(int(EXTINGUISHED_CANDLE_SECONDS * 1000), self._start_revealing)

    def dismiss_card(self, event: tk.Event) -> None:
        if self._is_shutting_down:
            return

        if self.mode != "card":
            return

        self.mode = "candle"
        self.status_text = "Halte die Flamme entzündet."
        self._reset_progress()
        self.prophecy = ""
        self._pending_prophecy = None
        self._pending_reset_message = None
        self._fog_clear_started_at = None
        self._extinguish_started_at = None
        self._scene_fade_started_at = None
        self._scene_fade_phase = None
        self._audio_level = 0.0
        self._audio_visual_level = 0.0
        self._reset_card_reveal()
        self._reset_stars()
        self._reset_phase_markers()
        self._refresh_cheat_panel()

    def close(self) -> None:
        if self._is_destroyed:
            return

        if self._is_shutting_down:
            return

        self._is_shutting_down = True
        self._shutdown_started_at = monotonic()
        self._shutdown_start_volume = self.music_player.volume_percent
        self._audio_level = 0.0
        self._audio_visual_level = 0.0
        self.recorder.stop()
        self._refresh_cheat_panel()
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        self.root.after(int(SHUTDOWN_SECONDS * 1000), self._finish_shutdown)

    def _finish_shutdown(self) -> None:
        if self._is_destroyed:
            return

        self._is_destroyed = True
        self.music_player.stop()
        self.recorder.close()
        self.root.destroy()

    def _start_revealing(self) -> None:
        if self.mode != "extinguishing":
            return

        self._scene_fade_started_at = monotonic()
        self._scene_fade_phase = "in"

    def _finish_revealing(self) -> None:
        if self.mode != "revealing":
            return

        if self._pending_prophecy is not None:
            self._show_prophecy_now(self._pending_prophecy)
            return

        if self._pending_reset_message is not None:
            self._return_to_candle(self._pending_reset_message)
            return

        self.mode = "processing"
        self.status_text = "Die Kristallkugel erwacht..."
        self.progress = max(self.progress, 4)

    def _update_scene_transition(self) -> float:
        if self._scene_fade_started_at is None or self._scene_fade_phase is None:
            return 0.0

        elapsed = monotonic() - self._scene_fade_started_at

        if self._scene_fade_phase == "in":
            progress = min(1.0, elapsed / SCENE_FADE_IN_SECONDS)
            if progress >= 1.0:
                self._scene_fade_started_at = monotonic()
                self._scene_fade_phase = "hold"

            return progress

        if self._scene_fade_phase == "hold":
            if elapsed >= SCENE_FADE_HOLD_SECONDS:
                self.mode = "revealing"
                self.status_text = "Der Nebel lichtet sich..."
                self._fog_clear_started_at = monotonic()
                self._scene_fade_started_at = monotonic()
                self._scene_fade_phase = "out"
                self.root.after(int(FOG_CLEAR_SECONDS * 1000), self._finish_revealing)

            return 1.0

        if self._scene_fade_phase == "out":
            progress = min(1.0, elapsed / SCENE_FADE_OUT_SECONDS)
            if progress >= 1.0:
                self._scene_fade_started_at = None
                self._scene_fade_phase = None

            return 1.0 - progress

        return 0.0

    def _capture_and_process(self) -> None:
        try:
            persona_session = self.fortune_teller.start_persona_capture()
            audio = self.recorder.capture_until_stopped(level_callback=self._set_audio_level)
            persona = self.fortune_teller.finish_persona_capture(persona_session)
            self._after_ui(lambda persona=persona: self._set_persona_marker(persona))
            prophecy = self.fortune_teller.tell_fortune(
                audio,
                persona=persona if hasattr(persona, "as_json") else None,
                progress=self._set_progress,
            )
        except (NoAudioError, NoSpeechError) as exc:
            if self._is_shutting_down:
                return

            message = str(exc)
            self._after_ui(lambda message=message: self._skip_card_after_transition(message))
            return
        except Exception as exc:
            if self._is_shutting_down:
                return

            print(f"Fehler: {exc}")
            traceback.print_exc()
            message = "Die Vision ist im Rauch zerfallen."
            self._after_ui(lambda message=message: self._skip_card_after_transition(message))
            return

        if self._is_shutting_down:
            return

        self._after_ui(lambda: self.show_prophecy(prophecy))

    def _set_progress(
        self,
        message: str,
        progress: int,
        star_count: int = 0,
        phase_name: str | None = None,
        phase_state: str | None = None,
        variant_name: str | None = None,
        phase_fill_color: str | None = None,
        phase_outline_color: str | None = None,
        response_text: str | None = None,
    ) -> None:
        if self._is_shutting_down:
            return

        def update() -> None:
            if self._is_shutting_down:
                return

            next_progress = max(0.0, min(100.0, float(progress)))
            self.status_text = message
            if (
                phase_name
                and phase_state == "selected"
                and variant_name
                and phase_fill_color
                and phase_outline_color
            ):
                self._phase_markers[phase_name] = (
                    variant_name,
                    phase_fill_color,
                    phase_outline_color,
                    monotonic(),
                    None,
                )
            elif phase_name and response_text is not None:
                existing_marker = self._phase_markers.get(phase_name)
                if existing_marker is not None:
                    label, fill_color, outline_color, activated_at, _ = existing_marker
                    self._phase_markers[phase_name] = (
                        label,
                        fill_color,
                        outline_color,
                        activated_at,
                        response_text,
                    )
            self.progress = max(self.progress, next_progress)
            self._activate_stars(
                star_count,
                phase_fill_color,
                phase_outline_color,
            )

        self._after_ui(update)

    def _set_audio_level(self, level: float) -> None:
        if self._is_shutting_down:
            return

        self._after_ui(lambda level=level: setattr(self, "_audio_level", level))

    def _after_ui(self, callback) -> None:
        if self._is_destroyed:
            return

        try:
            self.root.after(0, callback)
        except tk.TclError:
            self._is_destroyed = True

    def _build_cheat_panel(self) -> None:
        self._cheat_status_label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=10,
            pady=(8, 6),
        )
        for row_index, stage_name in enumerate(CHEAT_STAGE_NAMES, start=1):
            label = tk.Label(
                self._cheat_panel,
                text=CHEAT_STAGE_LABELS.get(stage_name, stage_name.replace("_", " ").title()),
                bg="#161d26",
                fg="#f4e5bd",
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            )
            label.grid(row=row_index, column=0, sticky="w", padx=(10, 8), pady=4)
            values = (CHEAT_RANDOM_OPTION, *self._cheat_stage_options.get(stage_name, ()))
            combo_box = ttk.Combobox(
                self._cheat_panel,
                textvariable=self._cheat_stage_vars[stage_name],
                values=values,
                state="readonly",
                width=24,
            )
            combo_box.grid(row=row_index, column=1, sticky="ew", padx=(0, 10), pady=4)
            self._cheat_combo_boxes[stage_name] = combo_box

        self._cheat_panel.grid_columnconfigure(1, weight=1)
        self._refresh_cheat_panel()

    def _refresh_cheat_panel(self) -> None:
        is_visible = (
            self._cheat_mode_enabled
            and self.mode == "candle"
            and not self._is_shutting_down
        )
        if is_visible:
            self._cheat_panel.place(x=28, y=28, width=330)
            self._cheat_panel.lift()
        else:
            self._cheat_panel.place_forget()

        combo_state = "readonly" if is_visible else "disabled"
        for combo_box in self._cheat_combo_boxes.values():
            combo_box.configure(state=combo_state)

    def _current_stage_variant_overrides(self) -> dict[str, str | None]:
        overrides: dict[str, str | None] = {}
        for stage_name, variable in self._cheat_stage_vars.items():
            selected = variable.get().strip()
            overrides[stage_name] = None if selected == CHEAT_RANDOM_OPTION else selected

        return overrides

    def _toggle_cheat_mode(self) -> None:
        if self._is_shutting_down:
            return

        self._cheat_mode_enabled = not self._cheat_mode_enabled
        self._refresh_cheat_panel()

    def _handle_key_press(self, event: tk.Event) -> None:
        if event.char == "\xa0":
            self._toggle_cheat_mode()
            self._alt_code_digits = ""
            return

        if event.keysym in {"Alt_L", "Alt_R"}:
            self._alt_pressed = True
            self._alt_code_digits = ""
            return

        if not self._alt_pressed:
            return

        digit: str | None = None
        if (
            event.keysym.startswith("KP_")
            and len(event.keysym) == 4
            and event.keysym[-1].isdigit()
        ):
            digit = event.keysym[-1]
        elif event.keysym.isdigit():
            digit = event.keysym

        if digit is None:
            return

        self._alt_code_digits = (self._alt_code_digits + digit)[-4:]
        if self._alt_code_digits == "0160":
            self._toggle_cheat_mode()
            self._alt_code_digits = ""

    def _handle_key_release(self, event: tk.Event) -> None:
        if event.keysym not in {"Alt_L", "Alt_R"}:
            return

        if self._alt_code_digits == "0160":
            self._toggle_cheat_mode()
        self._alt_pressed = False
        self._alt_code_digits = ""

    def _handle_pointer_motion(self, event: tk.Event) -> None:
        local_x = event.x - self._content_offset_x
        local_y = event.y - self._content_offset_y
        self._hovered_phase_marker = self._hit_test_phase_marker(local_x, local_y)

    def _handle_pointer_leave(self, event: tk.Event) -> None:
        self._hovered_phase_marker = None

    def _hit_test_phase_marker(self, x: float, y: float) -> str | None:
        for stage_name, (marker_x, marker_y, radius) in self._phase_marker_hitboxes.items():
            if math.hypot(x - marker_x, y - marker_y) <= radius:
                return stage_name

        return None

    def _skip_card_after_transition(self, message: str) -> None:
        self._pending_prophecy = None
        self._pending_reset_message = message

        if self.mode == "processing":
            self.mode = "revealing"
            self.status_text = "Der Nebel lichtet sich..."
            self._fog_clear_started_at = monotonic()
            self.root.after(int(FOG_CLEAR_SECONDS * 1000), self._finish_revealing)
        elif self.mode == "candle":
            self._return_to_candle(message)

    def _return_to_candle(self, message: str) -> None:
        self.mode = "candle"
        self.status_text = message
        self._reset_progress()
        self.prophecy = ""
        self._pending_prophecy = None
        self._pending_reset_message = None
        self._fog_clear_started_at = None
        self._extinguish_started_at = None
        self._scene_fade_started_at = None
        self._scene_fade_phase = None
        self._audio_level = 0.0
        self._audio_visual_level = 0.0
        self._reset_card_reveal()
        self._reset_stars()
        self._reset_phase_markers()
        self._refresh_cheat_panel()

    def show_prophecy(self, prophecy: str) -> None:
        if self._is_shutting_down:
            return

        clean_prophecy = prophecy.strip()
        if self.mode in {"extinguishing", "revealing"}:
            self._pending_prophecy = clean_prophecy
            return

        self._show_prophecy_now(clean_prophecy)

    def _show_prophecy_now(self, prophecy: str) -> None:
        self.prophecy = prophecy
        self.progress = 100
        self.mode = "card"
        self.status_text = "Die Karte ist gefallen."
        self._pending_prophecy = None
        self._card_reveal_started_at = monotonic()
        self._card_layout_key = None
        self._card_letters = []
        self._refresh_cheat_panel()

    def _animate(self) -> None:
        if self._is_destroyed:
            return

        now = monotonic()
        dt = min(0.12, max(0.0, now - self._last_frame_at))
        self._last_frame_at = now
        self._advance_animation(dt)

        if self.mode == "extinguishing":
            self._smoke_age += dt * 14.0

        self.canvas.delete("backdrop")
        self.canvas.delete("vignette")
        self.canvas.delete("veil")
        self.canvas.delete("scene")
        self._frame_images = []
        self._gray_veil_strength = 0.0
        self._update_content_offset()
        self._draw_fullscreen_backdrop()
        self._draw_background()

        if self.mode in {"candle", "recording", "extinguishing"}:
            self._draw_candle_scene()
            if self.mode == "extinguishing":
                fog_strength = self._current_extinguish_fog_strength()
                self._draw_fog(fog_strength)
        elif self.mode == "revealing":
            self._draw_processing_scene()
            fog_strength = self._current_reveal_fog_strength()
            self._draw_fog(fog_strength)
        elif self.mode == "processing":
            self._draw_processing_scene()
        elif self.mode == "card":
            self._draw_tarot_card()

        scene_transition_strength = self._update_scene_transition()
        self._draw_gray_veil(scene_transition_strength)

        if self._is_shutting_down:
            self._apply_shutdown_fade()

        self._position_scene()
        self._draw_fullscreen_vignette()
        self._draw_fullscreen_gray_veil()
        self._draw_phase_marker_tooltip()
        self.root.after(FRAME_DELAY_MS, self._animate)

    def _update_content_offset(self) -> None:
        canvas_width = max(CONTENT_WIDTH, self.canvas.winfo_width())
        canvas_height = max(CONTENT_HEIGHT, self.canvas.winfo_height())
        self._content_offset_x = int((canvas_width - CONTENT_WIDTH) / 2)
        self._content_offset_y = int((canvas_height - CONTENT_HEIGHT) / 2)

    def _position_scene(self) -> None:
        if self._content_offset_x or self._content_offset_y:
            self.canvas.move("scene", self._content_offset_x, self._content_offset_y)

    def _draw_phase_marker_tooltip(self) -> None:
        if self._hovered_phase_marker is None:
            return

        marker = self._phase_markers.get(self._hovered_phase_marker)
        hitbox = self._phase_marker_hitboxes.get(self._hovered_phase_marker)
        if marker is None or hitbox is None:
            return

        variant_name, fill_color, outline_color, _, response_text = marker
        marker_x, marker_y, radius = hitbox
        tooltip_x = marker_x + self._content_offset_x
        tooltip_y = marker_y + self._content_offset_y - radius - 22
        label = self._phase_marker_tooltip_text(variant_name, response_text)
        padding_x = 10
        padding_y = 6
        font = ("Consolas", 10, "bold")
        tooltip_font = tkfont.Font(font=font)
        lines = label.splitlines() or [label]
        width = max(tooltip_font.measure(line) for line in lines)
        line_height = tooltip_font.metrics("linespace")
        text_height = line_height * len(lines)
        x1 = tooltip_x - width / 2 - padding_x
        y1 = tooltip_y - text_height - padding_y
        x2 = tooltip_x + width / 2 + padding_x
        y2 = tooltip_y + padding_y
        self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            fill=fill_color,
            outline=outline_color,
            width=2,
            tags="vignette",
        )
        self.canvas.create_text(
            tooltip_x,
            tooltip_y - text_height / 2,
            text=label,
            fill="#10151d",
            font=font,
            tags="vignette",
            justify=tk.CENTER,
        )

    def _draw_fullscreen_backdrop(self) -> None:
        width = max(CONTENT_WIDTH, self.canvas.winfo_width())
        height = max(CONTENT_HEIGHT, self.canvas.winfo_height())
        self.canvas.create_rectangle(0, 0, width, height, fill="#000000", outline="", tags="backdrop")

    def _draw_fullscreen_vignette(self) -> None:
        width = max(CONTENT_WIDTH, self.canvas.winfo_width())
        height = max(CONTENT_HEIGHT, self.canvas.winfo_height())
        image = self._get_vignette_image(width, height)
        self.canvas.create_image(
            0,
            0,
            anchor=tk.NW,
            image=image,
            tags="vignette",
            state=tk.DISABLED,
        )

    def _get_vignette_image(self, width: int, height: int) -> tk.PhotoImage:
        key = (width, height)
        if key not in self._vignette_image_cache:
            png_data = self._build_vignette_png(width, height)
            encoded = base64.b64encode(png_data).decode("ascii")
            self._vignette_image_cache[key] = tk.PhotoImage(data=encoded, format="png")

        return self._vignette_image_cache[key]

    def _build_vignette_png(self, width: int, height: int) -> bytes:
        pixels = bytearray(width * height * 4)
        center_x = width / 2.0
        center_y = height / 2.0
        radius_x = CONTENT_WIDTH * 0.43
        radius_y = CONTENT_HEIGHT * 0.57
        clear_until = 0.78
        black_at = 1.36
        clear_until_squared = clear_until * clear_until
        black_at_squared = black_at * black_at
        fade_span = black_at - clear_until

        x_terms = [((x + 0.5 - center_x) / radius_x) ** 2 for x in range(width)]
        for y in range(height):
            y_term = ((y + 0.5 - center_y) / radius_y) ** 2
            row_offset = y * width * 4
            for x, x_term in enumerate(x_terms):
                distance_squared = x_term + y_term
                if distance_squared <= clear_until_squared:
                    continue

                if distance_squared >= black_at_squared:
                    alpha = 255
                else:
                    fade = (math.sqrt(distance_squared) - clear_until) / fade_span
                    eased = fade * fade * (3.0 - 2.0 * fade)
                    alpha = int(255 * eased)

                pixels[row_offset + x * 4 + 3] = alpha

        return self._encode_png(width, height, pixels)

    def _advance_animation(self, dt: float) -> None:
        angle_target, vapor_target, star_target = self._animation_targets()
        acceleration = min(1.0, dt * 1.45)

        self._angle_velocity += (angle_target - self._angle_velocity) * acceleration
        self._vapor_velocity += (vapor_target - self._vapor_velocity) * acceleration
        self._star_velocity += (star_target - self._star_velocity) * acceleration

        self._angle += self._angle_velocity * dt
        self._vapor_angle += self._vapor_velocity * dt
        self._star_angle += self._star_velocity * dt

        audio_acceleration = min(1.0, dt * 5.0)
        self._audio_visual_level += (self._audio_level - self._audio_visual_level) * audio_acceleration

        progress_target = self._current_progress_target()
        if progress_target < self._display_progress:
            self._display_progress = progress_target
        else:
            progress_acceleration = 1.0 - math.exp(-PROGRESS_SMOOTHING_PER_SECOND * dt)
            self._display_progress += (progress_target - self._display_progress) * progress_acceleration
            if progress_target - self._display_progress < 0.05:
                self._display_progress = progress_target

    def _animation_targets(self) -> tuple[float, float, float]:
        if self._is_shutting_down:
            return 0.05, 0.03, 0.03
        if self.mode == "recording":
            return 0.38, 0.0, 0.0
        if self.mode in {"processing", "revealing"}:
            return 0.08, 0.038, 0.052
        if self.mode == "extinguishing":
            return 0.16, 0.0, 0.0
        return 0.07, 0.0, 0.0

    def _shutdown_progress(self) -> float:
        if self._shutdown_started_at is None:
            return 0.0

        elapsed = monotonic() - self._shutdown_started_at
        return max(0.0, min(1.0, elapsed / SHUTDOWN_SECONDS))

    def _apply_shutdown_fade(self) -> None:
        progress = self._ease_in_out(self._shutdown_progress())
        volume = round(self._shutdown_start_volume * (1.0 - progress))
        self.music_player.set_volume(volume)

        alpha = max(MIN_WINDOW_ALPHA, 1.0 - progress)
        try:
            self.root.attributes("-alpha", alpha)
        except tk.TclError:
            pass

    def _ease_in_out(self, value: float) -> float:
        value = max(0.0, min(1.0, value))
        return value * value * (3.0 - 2.0 * value)

    def _reset_progress(self) -> None:
        self.progress = 0.0
        self._display_progress = 0.0

    def _current_progress_target(self) -> float:
        return max(0.0, min(100.0, self.progress))

    def _draw_background(self) -> None:
        self.canvas.create_rectangle(0, 0, 640, 760, fill="#10151d", outline="", tags="scene")
        self.canvas.create_rectangle(0, -128, 640, 132, fill="#15111a", outline="", tags="scene")
        self.canvas.create_oval(72, 88, 568, 820, fill="#161d25", outline="", tags="scene")
        self.canvas.create_rectangle(0, 615, 640, 760, fill="#2c2021", outline="", tags="scene")
        self.canvas.create_rectangle(0, 615, 640, 622, fill="#735244", outline="", tags="scene")

        self._draw_header_stars()

        self.canvas.create_text(
            320,
            58,
            text="Gemmarndakel",
            fill="#f3eee3",
            font=("Georgia", 24, "bold"),
            tags="scene",
        )
        self.canvas.create_text(
            320,
            704,
            text=self.status_text,
            fill="#f3eee3",
            font=("Segoe UI", 13),
            width=560,
            tags="scene",
        )
        self.canvas.create_text(
            320,
            744,
            text=CREDIT_TEXT,
            fill="#7f8a95",
            font=("Segoe UI", 8),
            width=600,
            tags="scene",
        )

    def _draw_header_stars(self) -> None:
        for index, (base_x, base_y) in enumerate(
            ((66, 52), (118, 80), (494, 80), (554, 108), (332, 52), (258, 108))
        ):
            drift_x = math.sin(self._angle * 0.72 + index * 1.4) * 4.5
            drift_y = math.cos(self._angle * 0.56 + index * 1.1) * 2.8
            size = 2.0 + (math.sin(self._angle * 0.9 + index) + 1.0) * 0.55
            x = base_x + drift_x
            y = base_y + drift_y
            self.canvas.create_oval(
                x,
                y,
                x + size,
                y + size,
                fill="#c8d8ff",
                outline="",
                tags="scene",
            )

        self._draw_phase_markers()

    def _draw_phase_markers(self) -> None:
        now = monotonic()
        self._phase_marker_hitboxes = {}
        for index, stage_name in enumerate(
            ("persona", "therapy_plan", "scenario", "prophecy")
        ):
            marker = self._phase_markers.get(stage_name)
            if marker is None:
                continue

            _, fill_color, outline_color, activated_at, _ = marker
            base_x, base_y = PHASE_MARKER_POSITIONS[stage_name]
            age = max(0.0, now - activated_at)
            drift_x = math.sin(self._angle * 0.86 + index * 1.8) * 5.8
            drift_y = math.cos(self._angle * 0.64 + index * 1.2) * 3.8
            pulse = (math.sin(age * 2.8) + 1.0) * 0.5
            size = 5.0 + pulse * 1.6
            fill = fill_color
            outline = outline_color
            x = base_x + drift_x
            y = base_y + drift_y
            self._phase_marker_hitboxes[stage_name] = (x, y, size + 6.0)
            self._draw_star(x, y, size, fill, outline)

    def _set_persona_marker(self, persona: object) -> None:
        if not hasattr(persona, "age") or not hasattr(persona, "gender") or not hasattr(persona, "mood"):
            age = "unknown"
            gender = "unknown"
            mood = "unknown"
        else:
            age = str(getattr(persona, "age", "unknown"))
            gender = str(getattr(persona, "gender", "unknown"))
            mood = str(getattr(persona, "mood", "unknown"))

        label = (
            "Persona\n"
            f"Alter: {age}\n"
            f"Geschlecht: {gender}\n"
            f"Stimmung: {mood}"
        )
        if age == "unknown" and gender == "unknown" and mood == "unknown":
            fill_color = "#9c9c9c"
            outline_color = "#dfdfdf"
        else:
            fill_color = "#8fd6c2"
            outline_color = "#e8fff8"

        self._phase_markers["persona"] = (
            label,
            fill_color,
            outline_color,
            monotonic(),
            None,
        )

    def _phase_marker_tooltip_text(
        self,
        variant_name: str,
        response_text: str | None,
    ) -> str:
        if not response_text:
            return variant_name

        rendered_response = response_text.strip()
        try:
            parsed = json.loads(rendered_response)
        except json.JSONDecodeError:
            pass
        else:
            rendered_response = json.dumps(
                parsed,
                ensure_ascii=False,
                indent=2,
            )

        return f"{variant_name}\n\n{rendered_response}"

    def _draw_candle_scene(self) -> None:
        flame_on = self.mode == "recording"
        candle_x = 320

        self.canvas.create_oval(196, 586, 444, 626, fill="#0b0b0f", outline="", tags="scene")
        self.canvas.create_rectangle(
            270,
            310,
            370,
            590,
            fill="#eadcbe",
            outline="#fff4d6",
            width=2,
            tags=("scene", "candle_hotspot"),
        )
        self.canvas.create_arc(
            270,
            288,
            370,
            334,
            start=0,
            extent=180,
            fill="#fff3d0",
            outline="#fff4d6",
            tags=("scene", "candle_hotspot"),
        )
        self.canvas.create_rectangle(
            282,
            352,
            304,
            548,
            fill="#d0b78e",
            outline="",
            stipple="gray25",
            tags=("scene", "candle_hotspot"),
        )
        self.canvas.create_line(
            candle_x,
            294,
            candle_x,
            254,
            fill="#191113",
            width=4,
            tags=("scene", "candle_hotspot"),
        )

        if flame_on:
            level = max(0.12, min(1.0, self._audio_visual_level))
            level = min(1.0, level**0.62)
            flicker = 1.0 + math.sin(self._angle * 5.0) * 0.035
            flame_height = int((86 + level * 150) * flicker)
            flame_width = int(24 + level * 70)
            inner_height = int(flame_height * 0.58)
            inner_width = int(flame_width * 0.46)
            glow_width = int(88 + level * 150)
            glow_height = int(98 + level * 170)
            outer_fill = self._blend_color("#c95f24", "#ffd062", level)
            inner_fill = self._blend_color("#fff0a2", "#ffffff", min(1.0, level * 1.15))

            self.canvas.create_oval(
                candle_x - glow_width // 2,
                292 - glow_height,
                candle_x + glow_width // 2,
                292,
                fill="#533214",
                outline="",
                stipple="gray50",
                tags="scene",
            )
            self.canvas.create_polygon(
                candle_x,
                292 - flame_height,
                candle_x - flame_width,
                258,
                candle_x,
                305,
                candle_x + flame_width,
                258,
                fill=outer_fill,
                outline="#ffd18a",
                tags=("scene", "candle_hotspot"),
            )
            self.canvas.create_polygon(
                candle_x,
                286 - inner_height,
                candle_x - inner_width,
                257,
                candle_x,
                289,
                candle_x + inner_width,
                257,
                fill=inner_fill,
                outline="",
                tags=("scene", "candle_hotspot"),
            )
            self.canvas.create_text(
                320,
                665,
                text="Halte die Flamme.",
                fill="#cda77a",
                font=("Segoe UI", 10),
                tags="scene",
            )
        elif self.mode == "extinguishing":
            self._draw_candle_smoke()
        else:
            self.canvas.create_oval(
                298,
                254,
                342,
                296,
                fill="#35221d",
                outline="#7d5b45",
                tags=("scene", "candle_hotspot"),
            )
            self.canvas.create_line(
                candle_x,
                292,
                candle_x,
                252,
                fill="#191113",
                width=4,
                tags=("scene", "candle_hotspot"),
            )

    def _draw_candle_smoke(self) -> None:
        for index in range(12):
            drift = self._smoke_age * 1.7 + index * 15
            x = 320 + math.sin(self._angle * 1.3 + index) * (10 + index * 2)
            y = 250 - drift
            if y < 90:
                continue

            self.canvas.create_oval(
                x - 22,
                y - 9,
                x + 22,
                y + 9,
                fill="#a5b2b5",
                outline="",
                stipple="gray50",
                tags="scene",
            )

    def _draw_processing_scene(self) -> None:
        center_x = 320
        center_y = 365
        displayed_progress = self._display_progress
        vapor_count = 5 + int(displayed_progress / 12)

        self.canvas.create_oval(170, 474, 470, 528, fill="#080a0f", outline="", tags="scene")
        self.canvas.create_rectangle(242, 480, 398, 536, fill="#5e463a", outline="", tags="scene")
        self.canvas.create_rectangle(222, 528, 418, 562, fill="#8b684f", outline="", tags="scene")
        self.canvas.create_line(222, 528, 418, 528, fill="#c39b68", width=2, tags="scene")

        self._draw_crystal_glow(center_x, center_y)
        self._draw_orbiting_stars(center_x, center_y, "back")
        self.canvas.create_oval(170, 198, 470, 498, fill="#1b7188", outline="#d8fbff", width=2, tags="scene")
        self.canvas.create_oval(192, 220, 448, 476, fill="#4cc6d2", outline="", tags="scene")
        self._draw_crystal_core(center_x, center_y - 16)
        self.canvas.create_arc(217, 228, 436, 458, start=26, extent=72, outline="#f8ffff", width=8, style=tk.ARC, tags="scene")
        self.canvas.create_oval(256, 244, 318, 302, fill="#f8ffff", outline="", tags="scene")

        self.canvas.create_arc(
            142,
            170,
            498,
            526,
            start=90,
            extent=-360 * displayed_progress / 100,
            outline="#d7c28f",
            width=5,
            style=tk.ARC,
            tags="scene",
        )

        self._draw_orbiting_stars(center_x, center_y, "front")

        for index in range(vapor_count):
            radius = 94 + index * 9
            angle = self._vapor_angle + index * 0.68
            x = center_x + math.cos(angle) * radius
            y = center_y + 48 + math.sin(angle * 0.78) * 42
            self._draw_cloud_image(x, y, 54, 22, "vapor")

    def _draw_crystal_glow(self, center_x: int, center_y: int) -> None:
        for index, size in enumerate((388, 338, 292)):
            self.canvas.create_oval(
                center_x - size // 2,
                center_y - size // 2,
                center_x + size // 2,
                center_y + size // 2,
                fill=("#4d2d67", "#6c3f86", "#8e66a8")[index],
                outline="",
                stipple="gray50",
                tags="scene",
            )

    def _draw_crystal_core(self, center_x: int, center_y: int) -> None:
        phase = (monotonic() % CRYSTAL_CORE_CYCLE_SECONDS) / CRYSTAL_CORE_CYCLE_SECONDS
        blend = (1.0 - math.cos(math.tau * phase)) / 2.0
        scale = 1.0 - blend * 0.05
        width = 190 * scale
        height = 190 * scale
        x1 = center_x - width / 2
        y1 = center_y - height / 2
        x2 = center_x + width / 2
        y2 = center_y + height / 2
        halo = self._blend_color("#a9fff2", "#e3d8ff", blend)
        core = self._blend_color("#74d6de", "#c9b8ec", blend)

        self.canvas.create_oval(x1, y1, x2, y2, fill=halo, outline="", tags="scene")
        inset = 9 * scale
        self.canvas.create_oval(
            x1 + inset,
            y1 + inset,
            x2 - inset,
            y2 - inset,
            fill=core,
            outline="",
            tags="scene",
        )

    def _draw_orbiting_stars(self, center_x: int, center_y: int, layer: str) -> None:
        now = monotonic()
        for index, activated_at in enumerate(self._star_activated_at):
            if activated_at is None:
                continue

            opacity = self._star_opacity(now, activated_at)
            if opacity <= 0.0:
                self._star_activated_at[index] = None
                continue

            angle = self._star_angle + self._star_phases[index]
            is_moving_left = math.sin(angle) > 0.0
            if (layer == "front") != is_moving_left:
                continue

            x = center_x + math.cos(angle) * 178
            y = center_y + math.sin(angle) * 66
            depth_scale = 0.82 if y < center_y else 1.0
            size = self._star_sizes[index] * (0.72 + opacity * 0.28) * depth_scale
            fill_base = self._star_fill_colors[index]
            outline_base = self._star_outline_colors[index]
            fill = fill_base
            outline = outline_base
            self._draw_star(x, y, size, fill, outline)

    def _star_opacity(self, now: float, activated_at: float) -> float:
        age = now - activated_at
        if age < STAR_HOLD_SECONDS:
            return 1.0

        fade_age = age - STAR_HOLD_SECONDS
        if fade_age >= STAR_FADE_OUT_SECONDS:
            return 0.0

        return 1.0 - fade_age / STAR_FADE_OUT_SECONDS

    def _draw_star(self, x: float, y: float, size: float, fill: str, outline: str) -> None:
        points: list[float] = []
        for index in range(10):
            radius = size if index % 2 == 0 else size * 0.42
            angle = -math.pi / 2 + index * math.pi / 5
            points.extend((x + math.cos(angle) * radius, y + math.sin(angle) * radius))

        self.canvas.create_polygon(points, fill=fill, outline=outline, tags="scene")

    def _reset_stars(self) -> None:
        self._star_phases = [0.0 for _ in range(STAR_SLOT_COUNT)]
        self._star_activated_at = [None for _ in range(STAR_SLOT_COUNT)]
        self._star_sizes = [4 for _ in range(STAR_SLOT_COUNT)]
        self._star_fill_colors = ["#fff7d6" for _ in range(STAR_SLOT_COUNT)]
        self._star_outline_colors = ["#b99b52" for _ in range(STAR_SLOT_COUNT)]
        self._next_star_slot = 0

    def _reset_phase_markers(self) -> None:
        self._phase_markers = {}
        self._phase_marker_hitboxes = {}
        self._hovered_phase_marker = None

    def _reset_card_reveal(self) -> None:
        self._card_reveal_started_at = None
        self._card_layout_key = None
        self._card_letters = []

    def _activate_stars(
        self,
        count: int,
        fill_color: str | None = None,
        outline_color: str | None = None,
    ) -> None:
        if count <= 0:
            return

        now = monotonic()
        for _ in range(count):
            slot = self._next_available_star_slot(now)
            if slot is None:
                return

            self._star_phases[slot] = random.random() * math.tau
            self._star_activated_at[slot] = now
            self._star_sizes[slot] = random.choice((4, 5, 6))
            self._star_fill_colors[slot] = fill_color or "#fff7d6"
            self._star_outline_colors[slot] = outline_color or "#b99b52"
            self._next_star_slot = (slot + 1) % STAR_SLOT_COUNT

    def _next_available_star_slot(self, now: float) -> int | None:
        for offset in range(STAR_SLOT_COUNT):
            slot = (self._next_star_slot + offset) % STAR_SLOT_COUNT
            activated_at = self._star_activated_at[slot]
            if activated_at is None or self._star_opacity(now, activated_at) <= 0.0:
                return slot

        return None

    def _draw_fog(self, strength: float) -> None:
        strength = max(0.0, min(1.0, strength))
        if strength <= 0:
            return

        band_count = 18
        for index in range(band_count):
            width = 230 + strength * 420
            height = 58 + strength * 130
            x = -35 + (index % 6) * 142 + math.sin(self._angle * 0.16 + index) * 14
            y = 205 + (index // 3) * 78 + math.sin(self._angle * 0.13 + index) * 30
            self._draw_cloud_image(x, y, width, height, "fog")

    def _draw_gray_veil(self, strength: float) -> None:
        strength = max(0.0, min(1.0, strength))
        self._gray_veil_strength = max(self._gray_veil_strength, strength)

    def _draw_fullscreen_gray_veil(self) -> None:
        strength = max(0.0, min(1.0, self._gray_veil_strength))
        if strength <= 0.0:
            return

        width = max(CONTENT_WIDTH, self.canvas.winfo_width())
        height = max(CONTENT_HEIGHT, self.canvas.winfo_height())
        alpha = int(round(self._ease_in_out(strength) * SCENE_FADE_MAX_ALPHA * 255))
        if alpha <= 0:
            return

        image = self._get_gray_veil_image(width, height, alpha)
        self.canvas.create_image(
            0,
            0,
            anchor=tk.NW,
            image=image,
            tags="veil",
            state=tk.DISABLED,
        )

    def _get_gray_veil_image(self, width: int, height: int, alpha: int) -> tk.PhotoImage:
        quantized_alpha = max(0, min(255, int(round(alpha / 8.0) * 8)))
        key = (width, height, quantized_alpha)
        if self._gray_veil_image_key != key or self._gray_veil_image is None:
            png_data = self._build_solid_alpha_png(width, height, SCENE_FADE_COLOR, quantized_alpha)
            encoded = base64.b64encode(png_data).decode("ascii")
            self._gray_veil_image = tk.PhotoImage(data=encoded, format="png")
            self._gray_veil_image_key = key

        return self._gray_veil_image

    def _build_solid_alpha_png(
        self,
        width: int,
        height: int,
        color: tuple[int, int, int],
        alpha: int,
    ) -> bytes:
        pixel = bytes((color[0], color[1], color[2], max(0, min(255, alpha))))
        row = pixel * width
        pixels = row * height
        return self._encode_png(width, height, pixels)

    def _draw_cloud_image(self, x: float, y: float, width: float, height: float, kind: str) -> None:
        image = self._get_cloud_image(width, height, kind)
        self._frame_images.append(image)
        self.canvas.create_image(x, y, image=image, tags="scene")

    def _get_cloud_image(self, width: float, height: float, kind: str) -> tk.PhotoImage:
        rounded_width = max(8, int(round(width / 8.0) * 8))
        rounded_height = max(8, int(round(height / 8.0) * 8))
        key = (rounded_width, rounded_height, kind)
        if key not in self._cloud_image_cache:
            png_data = self._build_cloud_png(rounded_width, rounded_height, kind)
            encoded = base64.b64encode(png_data).decode("ascii")
            self._cloud_image_cache[key] = tk.PhotoImage(data=encoded, format="png")

        return self._cloud_image_cache[key]

    def _build_cloud_png(self, width: int, height: int, kind: str) -> bytes:
        if kind == "vapor":
            colors = ((211, 238, 240), (232, 246, 246), (255, 255, 255))
        else:
            colors = ((184, 195, 197), (210, 218, 218), (238, 242, 242))

        pixels = bytearray(width * height * 4)
        layers = (
            (1.0, colors[0], 128),
            (0.72, colors[1], 128),
            (0.48, colors[2], 128),
        )

        for scale, color, alpha in layers:
            radius_x = max(1.0, width * scale / 2.0)
            radius_y = max(1.0, height * scale / 2.0)
            center_x = width / 2.0
            center_y = height / 2.0

            for y in range(height):
                normalized_y = (y + 0.5 - center_y) / radius_y
                y_term = normalized_y * normalized_y
                if y_term > 1.0:
                    continue

                for x in range(width):
                    normalized_x = (x + 0.5 - center_x) / radius_x
                    distance = normalized_x * normalized_x + y_term
                    if distance > 1.0:
                        continue

                    edge_softness = min(1.0, max(0.0, (1.0 - distance) * 2.4))
                    source_alpha = int(alpha * edge_softness)
                    self._alpha_composite_pixel(pixels, width, x, y, color, source_alpha)

        return self._encode_png(width, height, pixels)

    def _alpha_composite_pixel(
        self,
        pixels: bytearray,
        width: int,
        x: int,
        y: int,
        color: tuple[int, int, int],
        alpha: int,
    ) -> None:
        if alpha <= 0:
            return

        offset = (y * width + x) * 4
        destination_alpha = pixels[offset + 3]
        source_alpha = alpha / 255.0
        destination_alpha_float = destination_alpha / 255.0
        out_alpha = source_alpha + destination_alpha_float * (1.0 - source_alpha)
        if out_alpha <= 0.0:
            return

        for channel in range(3):
            destination = pixels[offset + channel] / 255.0
            source = color[channel] / 255.0
            out = (source * source_alpha + destination * destination_alpha_float * (1.0 - source_alpha)) / out_alpha
            pixels[offset + channel] = int(out * 255)

        pixels[offset + 3] = int(out_alpha * 255)

    def _encode_png(self, width: int, height: int, pixels: bytes) -> bytes:
        def chunk(chunk_type: bytes, data: bytes) -> bytes:
            checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)

        raw_rows = bytearray()
        row_stride = width * 4
        for y in range(height):
            raw_rows.append(0)
            start = y * row_stride
            raw_rows.extend(pixels[start : start + row_stride])

        png = BytesIO()
        png.write(b"\x89PNG\r\n\x1a\n")
        png.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)))
        png.write(chunk(b"IDAT", zlib.compress(bytes(raw_rows), level=6)))
        png.write(chunk(b"IEND", b""))
        return png.getvalue()

    def _current_reveal_fog_strength(self) -> float:
        if self._fog_clear_started_at is None:
            return 1.0

        elapsed = monotonic() - self._fog_clear_started_at
        return max(0.0, 1.0 - elapsed / FOG_CLEAR_SECONDS)

    def _current_extinguish_fog_strength(self) -> float:
        if self._extinguish_started_at is None:
            return 0.0

        elapsed = monotonic() - self._extinguish_started_at
        return min(1.0, elapsed / FOG_FILL_SECONDS)

    def _blend_color(self, start: str, end: str, amount: float) -> str:
        amount = max(0.0, min(1.0, amount))
        start_rgb = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
        end_rgb = tuple(int(end[index : index + 2], 16) for index in (1, 3, 5))
        mixed = tuple(
            int(start_channel + (end_channel - start_channel) * amount)
            for start_channel, end_channel in zip(start_rgb, end_rgb)
        )
        return f"#{mixed[0]:02x}{mixed[1]:02x}{mixed[2]:02x}"

    def _draw_tarot_card(self) -> None:
        x1, y1, x2, y2 = 155, 125, 485, 650
        self.canvas.create_oval(132, 620, 508, 680, fill="#080a0f", outline="", tags="scene")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#efe3c0", outline="#c9a45f", width=5, tags="scene")
        self.canvas.create_rectangle(x1 + 18, y1 + 18, x2 - 18, y2 - 18, fill="#f8edcf", outline="#b88d4f", width=2, tags="scene")
        self.canvas.create_rectangle(x1 + 30, y1 + 74, x2 - 30, y2 - 42, fill="#f4e5bd", outline="#d5b672", tags="scene")

        self.canvas.create_text(
            320,
            y1 + 42,
            text="DIE PROPHEZEIUNG",
            fill="#5c3432",
            font=("Georgia", 15, "bold"),
            tags="scene",
        )

        self.canvas.create_oval(
            x2 - 48,
            y1 + 18,
            x2 - 18,
            y1 + 48,
            fill="#5c3432",
            outline="#d5b672",
            tags=("scene", "card_close"),
        )
        self.canvas.create_text(
            x2 - 33,
            y1 + 33,
            text="X",
            fill="#f8edcf",
            font=("Segoe UI", 12, "bold"),
            tags=("scene", "card_close"),
        )

        self._draw_card_text(self.prophecy, x1 + 42, y1 + 98, x2 - 42, y2 - 58)

    def _draw_card_text(self, text: str, x1: int, y1: int, x2: int, y2: int) -> None:
        self._prepare_card_text_layout(text, x1, y1, x2, y2)
        if self._card_reveal_started_at is None:
            self._card_reveal_started_at = monotonic()

        elapsed_ms = (monotonic() - self._card_reveal_started_at) * 1000.0
        for character, x, y, font, reveal_index in self._card_letters:
            if reveal_index is None:
                continue

            starts_at = reveal_index * self.card_letter_delay_ms
            progress = (elapsed_ms - starts_at) / (CARD_LETTER_SHARPEN_SECONDS * 1000.0)
            progress = max(0.0, min(1.0, progress))
            if progress <= 0.0:
                continue

            self._draw_revealing_character(character, x, y, font, progress)

    def _prepare_card_text_layout(self, text: str, x1: int, y1: int, x2: int, y2: int) -> None:
        key = (text, x1, y1, x2, y2)
        if self._card_layout_key == key:
            return

        self._card_layout_key = key
        self._card_letters = []

        paragraphs = [paragraph.strip() for paragraph in text.splitlines() if paragraph.strip()]
        max_width = x2 - x1
        max_height = y2 - y1

        for size in range(15, 9, -1):
            font = tkfont.Font(family="Georgia", size=size)
            lines = self._wrap_paragraphs(paragraphs, font, max_width)
            line_height = font.metrics("linespace") + 2
            total_height = len(lines) * line_height + max(0, len(paragraphs) - 1) * 8
            if total_height <= max_height:
                break
        else:
            font = tkfont.Font(family="Georgia", size=9)
            lines = self._wrap_paragraphs(paragraphs, font, max_width)
            line_height = font.metrics("linespace") + 1

        current_y = y1
        reveal_index = 0
        for line_index, line in enumerate(lines):
            if line is None:
                current_y += 8
                continue

            is_last_paragraph_line = line_index == len(lines) - 1 or lines[line_index + 1] is None
            should_justify = not is_last_paragraph_line and line.count(" ") > 0
            extra_space = 0.0
            if should_justify:
                remaining_width = max_width - font.measure(line)
                extra_space = max(0.0, remaining_width / line.count(" "))

            current_x = x1
            for character in line:
                if character.isspace():
                    current_x += font.measure(character) + extra_space
                    continue
                else:
                    character_reveal_index: int | None = reveal_index
                    reveal_index += 1

                self._card_letters.append(
                    (character, current_x, current_y, font, character_reveal_index)
                )
                current_x += font.measure(character)

            current_y += line_height

    def _draw_revealing_character(
        self,
        character: str,
        x: float,
        y: float,
        font: tkfont.Font,
        progress: float,
    ) -> None:
        paper_color = "#f4e5bd"
        target_color = "#3d2a24"
        eased = self._ease_in_out(progress)
        fill = self._blend_color(paper_color, target_color, eased)
        blur_radius = int(round((1.0 - eased) * 4.0))

        if blur_radius > 0:
            blur_color = self._blend_color(paper_color, target_color, eased * 0.45)
            for dx, dy in (
                (-blur_radius, 0),
                (blur_radius, 0),
                (0, -blur_radius),
                (0, blur_radius),
                (-blur_radius, -blur_radius),
                (blur_radius, blur_radius),
            ):
                self.canvas.create_text(
                    x + dx,
                    y + dy,
                    text=character,
                    anchor=tk.NW,
                    fill=blur_color,
                    font=font,
                    tags="scene",
                )

        self.canvas.create_text(
            x,
            y,
            text=character,
            anchor=tk.NW,
            fill=fill,
            font=font,
            tags="scene",
        )

    def _wrap_paragraphs(
        self,
        paragraphs: list[str],
        font: tkfont.Font,
        max_width: int,
    ) -> list[str | None]:
        wrapped: list[str | None] = []
        for paragraph_index, paragraph in enumerate(paragraphs):
            words = paragraph.split()
            line = ""
            for word in words:
                candidate = word if not line else f"{line} {word}"
                if font.measure(candidate) <= max_width:
                    line = candidate
                    continue

                if line:
                    wrapped.append(line)
                line = word

            if line:
                wrapped.append(line)
            if paragraph_index < len(paragraphs) - 1:
                wrapped.append(None)

        return wrapped
