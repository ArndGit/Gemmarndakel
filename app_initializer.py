from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from typing import TYPE_CHECKING

from legend_generator import write_legend_html
from settings import AppSettings, load_settings

if TYPE_CHECKING:
    from audio_recorder import AudioRecorder
    from fortune_service import FortuneTellerService


ProgressCallback = Callable[[str, int], None]


@dataclass(frozen=True)
class AppDependencies:
    settings: AppSettings
    recorder: AudioRecorder
    fortune_teller: FortuneTellerService


def initialize_app(progress: ProgressCallback) -> AppDependencies:
    progress("Die Zeichen werden gelesen...", 8)
    settings = load_settings()
    if settings.whisper_local_files_only:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    progress("Der alte Spruch wird aus dem Rauch gehoben...", 20)
    from prompt_loader import load_prompt_config

    load_prompt_config(settings.prompt_config_file)
    write_legend_html(
        settings.prompt_config_file,
        settings.prompt_config_file.resolve().with_name("legend.html"),
    )

    progress("Das Ohr des Orakels wird geöffnet...", 35)
    from audio_recorder import AudioRecorder

    recorder = AudioRecorder(
        rate=settings.audio_rate,
        frames_per_buffer=settings.audio_frames_per_buffer,
    )

    try:
        progress("Nach göttlichen Dämpfen wird gesucht...", 58)
        from transcriber import SpeechTranscriber

        transcriber = SpeechTranscriber(
            settings.whisper_model_size,
            local_files_only=settings.whisper_local_files_only,
        )

        progress("Die Kammer des lokalen Geistes wird betreten...", 80)
        from oracle_client import OracleClient

        oracle = OracleClient(settings)
        oracle.check_connection()

        progress("Das Orakel erwacht...", 100)
        from fortune_service import FortuneTellerService

        fortune_teller = FortuneTellerService(
            transcriber,
            oracle,
            audio_rate=settings.audio_rate,
        )
        return AppDependencies(
            settings=settings,
            recorder=recorder,
            fortune_teller=fortune_teller,
        )
    except Exception:
        recorder.close()
        raise
