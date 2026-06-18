from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pyaudio


LevelCallback = Callable[[float], None]


class AudioRecorder:
    def __init__(self, rate: int, frames_per_buffer: int) -> None:
        self.rate = rate
        self.frames_per_buffer = frames_per_buffer
        self._audio = pyaudio.PyAudio()
        self._stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=rate,
            input=True,
            frames_per_buffer=frames_per_buffer,
        )
        self._is_recording = False

    def start(self) -> None:
        self._is_recording = True

    def stop(self) -> None:
        self._is_recording = False

    def capture_until_stopped(self, level_callback: LevelCallback | None = None) -> np.ndarray:
        chunks: list[bytes] = []

        while self._is_recording:
            data = self._stream.read(
                self.frames_per_buffer,
                exception_on_overflow=False,
            )
            chunks.append(data)
            if level_callback is not None:
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
                level_callback(min(1.0, (rms * 32.0) ** 0.65))

        if not chunks:
            return np.array([], dtype=np.float32)

        return np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768.0

    def close(self) -> None:
        self.stop()
        self._stream.stop_stream()
        self._stream.close()
        self._audio.terminate()
