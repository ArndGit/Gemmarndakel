from __future__ import annotations

import ctypes
from pathlib import Path
import sys


class MusicPlayer:
    def __init__(self, path: Path, volume_percent: int = 20) -> None:
        self.path = path
        self.volume_percent = max(0, min(100, volume_percent))
        self._alias = f"fortune_music_{id(self)}"
        self._is_playing = False

    def play_loop(self) -> None:
        if self._is_playing:
            return

        if sys.platform != "win32":
            print("Music playback is only configured for Windows.")
            return

        if not self.path.exists():
            print(f"Music file not found: {self.path}")
            return

        try:
            self._send(f'open "{self.path}" type mpegvideo alias {self._alias}')
            self.set_volume(self.volume_percent)
            self._send(f"play {self._alias} repeat")
        except RuntimeError as exc:
            print(f"Music playback failed: {exc}")
            self._send_quietly(f"close {self._alias}")
            return

        self._is_playing = True

    def set_volume(self, volume_percent: int) -> None:
        self.volume_percent = max(0, min(100, volume_percent))
        self._send_quietly(f"setaudio {self._alias} volume to {self.volume_percent * 10}")

    def stop(self) -> None:
        if not self._is_playing:
            return

        self._send_quietly(f"stop {self._alias}")
        self._send_quietly(f"close {self._alias}")
        self._is_playing = False

    def _send(self, command: str) -> None:
        error_code = ctypes.windll.winmm.mciSendStringW(command, None, 0, None)
        if error_code:
            message = ctypes.create_unicode_buffer(256)
            ctypes.windll.winmm.mciGetErrorStringW(error_code, message, 256)
            raise RuntimeError(message.value or f"MCI error {error_code}")

    def _send_quietly(self, command: str) -> None:
        try:
            self._send(command)
        except RuntimeError:
            pass
