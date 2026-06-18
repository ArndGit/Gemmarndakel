import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
REMOTE_LLM_CONFIG_FILE = BASE_DIR / "remote_llm.yaml"
DEFAULT_REMOTE_LLM_CONFIG: dict[str, Any] = {
    "address": "http://127.0.0.1:1234/v1",
    "api_key": None,
    "min_token_size": 10_000,
    "reasoning_level": "low",
    "analysis_reasoning_enabled": True,
    "recommendation_reasoning_enabled": True,
    "prophecy_reasoning_enabled": True,
}


@dataclass(frozen=True)
class AppSettings:
    lm_studio_url: str
    llm_api_key: str | None
    llm_min_token_size: int
    llm_reasoning_level: str
    llm_analysis_reasoning_enabled: bool
    llm_recommendation_reasoning_enabled: bool
    llm_prophecy_reasoning_enabled: bool
    llm_timeout_seconds: float
    llm_generation_timeout_seconds: float
    llm_model: str
    prompt_config_file: Path
    prompt_test_question: str
    whisper_model_size: str
    whisper_local_files_only: bool
    card_letter_delay_ms: int
    audio_rate: int
    audio_frames_per_buffer: int


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"{name} must be a boolean, got {value!r}")


def _read_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


def _read_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc


def _read_text(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default

    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{name} must be a non-empty string.")

    return stripped


def _write_default_remote_llm_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Remote LLM configuration.",
                "# The file is created automatically and ignored by Git.",
                'address: "http://127.0.0.1:1234/v1"',
                "# Set api_key if the endpoint requires credentials.",
                "api_key: null",
                "min_token_size: 10000",
                'reasoning_level: "low"',
                "analysis_reasoning_enabled: true",
                "recommendation_reasoning_enabled: true",
                "prophecy_reasoning_enabled: true",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _strip_yaml_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == "#" and quote is None:
            return value[:index].rstrip()

    return value.strip()


def _parse_yaml_scalar(value: str) -> Any:
    stripped = _strip_yaml_comment(value)
    if stripped in {"", "null", "Null", "NULL", "~"}:
        return None

    if len(stripped) >= 2 and stripped[0] == stripped[-1] == '"':
        return bytes(stripped[1:-1], "utf-8").decode("unicode_escape")

    if len(stripped) >= 2 and stripped[0] == stripped[-1] == "'":
        return stripped[1:-1].replace("''", "'")

    normalized = stripped.lower()
    if normalized in {"none", "no credentials"}:
        return None
    if normalized in {"true", "yes", "on"}:
        return True
    if normalized in {"false", "no", "off"}:
        return False

    int_value = stripped.replace("_", "")
    if int_value.isdigit():
        return int(int_value)

    return stripped


def _read_flat_yaml(path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(
                f"{path.name}:{line_number} must be a simple 'key: value' entry."
            )

        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"{path.name}:{line_number} has an empty key.")

        values[key] = _parse_yaml_scalar(value.strip())

    return values


def _load_remote_llm_config() -> dict[str, Any]:
    if not REMOTE_LLM_CONFIG_FILE.exists():
        _write_default_remote_llm_config(REMOTE_LLM_CONFIG_FILE)
        return dict(DEFAULT_REMOTE_LLM_CONFIG)

    config = dict(DEFAULT_REMOTE_LLM_CONFIG)
    config.update(_read_flat_yaml(REMOTE_LLM_CONFIG_FILE))
    unknown_keys = sorted(set(config) - set(DEFAULT_REMOTE_LLM_CONFIG))
    if unknown_keys:
        joined_keys = ", ".join(unknown_keys)
        raise ValueError(
            f"{REMOTE_LLM_CONFIG_FILE.name} contains unknown keys: {joined_keys}"
        )

    return config


def _read_config_string(config: dict[str, Any], name: str) -> str:
    value = config[name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{REMOTE_LLM_CONFIG_FILE.name}: {name} must be a string.")

    return value.strip()


def _read_config_optional_string(config: dict[str, Any], name: str) -> str | None:
    value = config[name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            f"{REMOTE_LLM_CONFIG_FILE.name}: {name} must be a string or null."
        )

    stripped = value.strip()
    return stripped or None


def _read_config_positive_int(config: dict[str, Any], name: str) -> int:
    value = config[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{REMOTE_LLM_CONFIG_FILE.name}: {name} must be an integer.")
    if value <= 0:
        raise ValueError(
            f"{REMOTE_LLM_CONFIG_FILE.name}: {name} must be greater than zero."
        )

    return value


def _read_config_bool(config: dict[str, Any], name: str) -> bool:
    value = config[name]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on"}:
            return True
        if normalized in {"false", "no", "off"}:
            return False

    raise ValueError(f"{REMOTE_LLM_CONFIG_FILE.name}: {name} must be a boolean.")


def load_settings() -> AppSettings:
    load_dotenv(BASE_DIR / ".env")
    remote_llm_config = _load_remote_llm_config()

    prompt_config_file = Path(
        os.getenv(
            "PROMPT_CONFIG_FILE",
            os.getenv("PREPROMPT_FILE", BASE_DIR / "config.json"),
        )
    )
    if not prompt_config_file.is_absolute():
        prompt_config_file = BASE_DIR / prompt_config_file

    return AppSettings(
        lm_studio_url=_read_config_string(remote_llm_config, "address"),
        llm_api_key=_read_config_optional_string(remote_llm_config, "api_key"),
        llm_min_token_size=_read_config_positive_int(
            remote_llm_config,
            "min_token_size",
        ),
        llm_reasoning_level=_read_config_string(remote_llm_config, "reasoning_level"),
        llm_analysis_reasoning_enabled=_read_config_bool(
            remote_llm_config,
            "analysis_reasoning_enabled",
        ),
        llm_recommendation_reasoning_enabled=_read_config_bool(
            remote_llm_config,
            "recommendation_reasoning_enabled",
        ),
        llm_prophecy_reasoning_enabled=_read_config_bool(
            remote_llm_config,
            "prophecy_reasoning_enabled",
        ),
        llm_timeout_seconds=_read_float("LLM_TIMEOUT_SECONDS", 5.0),
        llm_generation_timeout_seconds=_read_float("LLM_GENERATION_TIMEOUT_SECONDS", 600.0),
        llm_model=os.getenv("LLM_MODEL", "google/gemma-4-12b-qat"),
        prompt_config_file=prompt_config_file,
        prompt_test_question=_read_text(
            "PROMPT_TEST_QUESTION",
            "Gibt es Aliens und wird die Menschheit Sie entdecken",
        ),
        whisper_model_size=os.getenv("WHISPER_MODEL_SIZE", "base"),
        whisper_local_files_only=_read_bool("WHISPER_LOCAL_FILES_ONLY", True),
        card_letter_delay_ms=_read_int("CARD_LETTER_DELAY_MS", 50),
        audio_rate=_read_int("AUDIO_RATE", 16000),
        audio_frames_per_buffer=_read_int("AUDIO_FRAMES_PER_BUFFER", 1024),
    )
