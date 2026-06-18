from __future__ import annotations

import inspect
import os

import numpy as np
from faster_whisper import WhisperModel


class SpeechTranscriber:
    def __init__(self, model_size: str, local_files_only: bool) -> None:
        if local_files_only:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        model_kwargs: dict[str, object] = {
            "device": "cpu",
            "compute_type": "int8",
        }
        if "local_files_only" in inspect.signature(WhisperModel).parameters:
            model_kwargs["local_files_only"] = local_files_only

        self._model = WhisperModel(model_size, **model_kwargs)

    def transcribe(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""

        segments, _ = self._model.transcribe(audio)
        return "".join(segment.text for segment in segments).strip()
