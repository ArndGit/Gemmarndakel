from __future__ import annotations

from collections.abc import Callable
from time import monotonic

import numpy as np

from oracle_client import OracleClient
from persona import PersonaProfile
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
        persona_analyzer: object | None = None,
        audio_rate: int = DEFAULT_AUDIO_RATE,
    ) -> None:
        self._transcriber = transcriber
        self._oracle = oracle
        self._persona_analyzer = persona_analyzer
        self._audio_rate = audio_rate

    def start_persona_capture(self) -> object | None:
        if self._persona_analyzer is None:
            print("[Camera] No persona analyzer configured.", flush=True)
            return None

        start_capture_session = getattr(
            self._persona_analyzer,
            "start_capture_session",
            None,
        )
        if start_capture_session is None:
            print("[Camera] Persona analyzer has no start_capture_session method.", flush=True)
            return None

        return start_capture_session()

    def finish_persona_capture(self, session: object | None) -> PersonaProfile:
        if session is None:
            return PersonaProfile.unknown()

        finish = getattr(session, "finish", None)
        if finish is None:
            print("[Camera] Persona capture session has no finish method.", flush=True)
            return PersonaProfile.unknown()

        return finish()

    def get_stage_variant_names(self) -> dict[str, tuple[str, ...]]:
        return self._oracle.get_stage_variant_names()

    def set_stage_variant_overrides(
        self,
        overrides: dict[str, str | None],
    ) -> None:
        self._oracle.set_stage_variant_overrides(overrides)

    def tell_fortune(
        self,
        audio: np.ndarray,
        persona: PersonaProfile | None = None,
        progress: ProgressCallback | None = None,
    ) -> str:
        if audio.size == 0:
            raise NoAudioError("Keine Daten erhalten.")

        persona_profile = persona or PersonaProfile.unknown()

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
        print(f"[Pipeline] Persona context: {persona_profile.as_json()}", flush=True)
        print(f"[Pipeline] User said: {user_text}", flush=True)
        print("[Pipeline] Consulting oracle...", flush=True)
        return self._oracle.create_prophecy(
            user_text,
            persona=persona_profile,
            progress=progress,
        )
