from __future__ import annotations

from collections.abc import Callable
from time import monotonic

import numpy as np

from oracle_client import OracleClient
from transcriber import SpeechTranscriber


ProgressCallback = Callable[..., None]
DEFAULT_AUDIO_RATE = 16_000


class NoAudioError(RuntimeError):
    pass


class NoSpeechError(RuntimeError):
    pass


class FortuneTellerService:
    def __init__(
        self,
        transcriber: SpeechTranscriber,
        oracle: OracleClient,
        audio_rate: int = DEFAULT_AUDIO_RATE,
    ) -> None:
        self._transcriber = transcriber
        self._oracle = oracle
        self._audio_rate = audio_rate

    def tell_fortune(
        self,
        audio: np.ndarray,
        progress: ProgressCallback | None = None,
    ) -> str:
        if audio.size == 0:
            raise NoAudioError("Keine Daten erhalten.")

        if progress is not None:
            progress("Die Stimme wird gedeutet...", 4, 0)
        started_at = monotonic()
        duration_seconds = audio.size / self._audio_rate
        print(
            "[Pipeline] Processing audio: "
            f"samples={audio.size}, duration={duration_seconds:.2f}s",
            flush=True,
        )
        user_text = self._transcriber.transcribe(audio)
        if not user_text:
            raise NoSpeechError("Keine Sprache erkannt.")

        if progress is not None:
            progress("Die Frage wurde erkannt...", 8, 0)
        elapsed = monotonic() - started_at
        print(
            "[Pipeline] Transcription complete: "
            f"elapsed={elapsed:.1f}s, chars={len(user_text)}",
            flush=True,
        )
        print(f"[Pipeline] User said: {user_text}", flush=True)
        print("[Pipeline] Consulting oracle...", flush=True)
        return self._oracle.create_prophecy(user_text, progress=progress)
