from collections.abc import Callable
from dataclasses import dataclass
import json
import os
import random
import re
from time import monotonic
import traceback
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from openai import OpenAI

from persona import PersonaProfile
from prompt_loader import PromptStage, PromptVariant, load_prompt_config
from settings import AppSettings


ProgressCallback = Callable[..., None]
PHASE_PROGRESS: dict[tuple[str, str], int] = {
    ("analysis", "selected"): 10,
    ("analysis", "reasoning"): 16,
    ("analysis", "answer"): 24,
    ("analysis", "done"): 32,
    ("recommendation", "selected"): 38,
    ("recommendation", "reasoning"): 44,
    ("recommendation", "answer"): 54,
    ("recommendation", "done"): 64,
    ("prophecy", "selected"): 70,
    ("prophecy", "reasoning"): 76,
    ("prophecy", "answer"): 88,
    ("prophecy", "done"): 98,
}
NO_LOADED_LLM_MESSAGE = "Es gibt gerade schlechte Schwingungen..."
LOADED_MODEL_STATES = {"active", "loaded", "ready", "running", "started"}
UNLOADED_MODEL_STATES = {
    "error",
    "inactive",
    "notloaded",
    "notrunning",
    "stopped",
    "unavailable",
    "unloaded",
}
MODEL_LOADED_FLAG_KEYS = {
    "is_loaded",
    "is_loaded_model",
    "is_model_loaded",
    "loaded",
    "model_loaded",
}
MODEL_STATE_KEYS = {
    "load_state",
    "loaded_state",
    "loading_state",
    "runtime_state",
    "state",
    "status",
}
RUNTIME_CONTEXT_TOKEN_KEYS = {
    "configured_context_length",
    "configured_context_size",
    "configured_context_window",
    "context_length",
    "context_size",
    "context_window",
    "ctx_length",
    "loaded_context_length",
    "loaded_context_size",
    "loaded_context_window",
    "n_ctx",
    "num_ctx",
    "runtime_context_length",
    "runtime_context_size",
    "runtime_context_window",
}
MAX_CONTEXT_TOKEN_KEYS = {
    "max_context_length",
    "max_context_tokens",
    "max_context_window",
    "max_model_len",
    "max_position_embeddings",
    "max_sequence_length",
    "max_seq_len",
}
NORMALIZED_RUNTIME_CONTEXT_TOKEN_KEYS = {
    re.sub(r"[^a-z0-9]", "", key) for key in RUNTIME_CONTEXT_TOKEN_KEYS
}
NORMALIZED_MAX_CONTEXT_TOKEN_KEYS = {
    re.sub(r"[^a-z0-9]", "", key) for key in MAX_CONTEXT_TOKEN_KEYS
}
NORMALIZED_MODEL_LOADED_FLAG_KEYS = {
    re.sub(r"[^a-z0-9]", "", key) for key in MODEL_LOADED_FLAG_KEYS
}
NORMALIZED_MODEL_STATE_KEYS = {
    re.sub(r"[^a-z0-9]", "", key) for key in MODEL_STATE_KEYS
}


@dataclass(frozen=True)
class StageRunResult:
    stage_name: str
    variant_name: str
    variant_fill_color: str
    variant_outline_color: str
    variant_weight: float
    output: str


@dataclass(frozen=True)
class ProphecyMatrixResult:
    question: str
    analysis: StageRunResult
    recommendation: StageRunResult
    prophecies: tuple[StageRunResult, ...]


class MersenneTwisterPromptSelector:
    def __init__(self, seed: int | None = None) -> None:
        if seed is None:
            seed = int.from_bytes(os.urandom(32), "big")
            seed_source = "os-entropy"
            seed_detail = "seed_bytes=32"
        else:
            seed_source = "explicit"
            seed_detail = f"seed={seed}"

        self._rng = random.Random(seed)
        print(
            "[PromptRNG] Mersenne Twister initialized: "
            f"source={seed_source}, {seed_detail}",
            flush=True,
        )

    def choose(self, stage_name: str, stage: PromptStage) -> PromptVariant:
        total_weight = sum(variant.weight for variant in stage.variants)
        draw = self._rng.random() * total_weight
        cumulative_weight = 0.0
        selected = stage.variants[-1]

        for variant in stage.variants:
            cumulative_weight += variant.weight
            if draw < cumulative_weight:
                selected = variant
                break

        print(
            "[Prompt] PICKED_VARIANT "
            f"stage={stage_name}, "
            f"name={selected.name}, "
            f"weight={selected.weight:g}, "
            f"total_weight={total_weight:g}, "
            f"draw={draw:.6f}, "
            f"fill={selected.fill_color}, "
            f"outline={selected.outline_color}",
            flush=True,
        )
        return selected


class OracleClient:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._model_id = settings.llm_model
        self._client = OpenAI(
            base_url=settings.lm_studio_url,
            api_key=settings.llm_api_key or "lm-studio",
            timeout=settings.llm_timeout_seconds,
        )
        credentials_state = "configured" if settings.llm_api_key else "none"
        print(
            "[LLM] Client configured: "
            f"base_url={settings.lm_studio_url}, "
            f"model={settings.llm_model}, "
            f"credentials={credentials_state}, "
            f"min_context_tokens={settings.llm_min_token_size}, "
            f"reasoning_effort={settings.llm_reasoning_level}, "
            "stage_reasoning="
            f"analysis:{self._stage_reasoning_enabled('analysis')},"
            f"recommendation:{self._stage_reasoning_enabled('recommendation')},"
            f"prophecy:{self._stage_reasoning_enabled('prophecy')}, "
            f"connect_timeout={settings.llm_timeout_seconds}s, "
            f"generation_timeout={settings.llm_generation_timeout_seconds}s",
            flush=True,
        )

    def _stage_reasoning_enabled(self, stage_name: str) -> bool:
        if stage_name == "analysis":
            return self._settings.llm_analysis_reasoning_enabled
        if stage_name == "recommendation":
            return self._settings.llm_recommendation_reasoning_enabled
        if stage_name == "prophecy":
            return self._settings.llm_prophecy_reasoning_enabled

        raise ValueError(f"Unknown stage name: {stage_name}")

    def _stage_reasoning_effort(self, stage_name: str) -> str | None:
        if not self._stage_reasoning_enabled(stage_name):
            return None

        return self._settings.llm_reasoning_level

    def _find_model_metadata(self, models: Any, model_id: str) -> Any | None:
        for model in self._iter_model_items(models):
            if self._read_metadata_value(model, "id") == model_id:
                return model

        return None

    def check_connection(self) -> None:
        print("[LLM] Checking LM Studio connection...", flush=True)
        try:
            models = self._client.models.list()
        except Exception as exc:
            print(f"[LLM] Connection check failed: {exc!r}", flush=True)
            raise RuntimeError(NO_LOADED_LLM_MESSAGE) from exc

        openai_model_items = self._iter_model_items(models)
        native_model_items = self._iter_model_items(self._load_native_model_metadata())
        print(
            "[LLM] Model metadata received: "
            f"openai_models={len(openai_model_items)}, "
            f"native_models={len(native_model_items)}",
            flush=True,
        )
        native_model_metadata = self._find_matching_model_metadata(
            native_model_items,
            self._settings.llm_model,
        )
        openai_model_metadata = self._find_matching_model_metadata(
            openai_model_items,
            self._settings.llm_model,
        )
        model_metadata = native_model_metadata or openai_model_metadata

        if model_metadata is None:
            if not native_model_items and not openai_model_items:
                raise RuntimeError(NO_LOADED_LLM_MESSAGE)

            model_items = [*native_model_items, *openai_model_items]
            available_models = self._format_available_models(model_items)
            detail = f" Verfuegbare Modelle: {available_models}." if available_models else ""
            raise RuntimeError(
                f"Das konfigurierte LLM-Modell '{self._settings.llm_model}' wurde nicht gefunden."
                f"{detail}"
            )

        resolved_model_id = self._read_metadata_value(model_metadata, "id")
        if isinstance(resolved_model_id, str) and resolved_model_id:
            self._model_id = resolved_model_id
        print(f"[LLM] Resolved model id: {self._model_id}", flush=True)

        native_model_metadata = self._find_matching_model_metadata(
            native_model_items,
            self._model_id,
        )
        openai_model_metadata = self._find_matching_model_metadata(
            openai_model_items,
            self._model_id,
        )
        if not self._is_model_loaded(native_model_metadata, openai_model_metadata):
            print("[LLM] Selected model is not loaded.", flush=True)
            raise RuntimeError(NO_LOADED_LLM_MESSAGE)

        context_tokens = self._extract_context_tokens(native_model_metadata, model_metadata)
        print(f"[LLM] Reported context tokens: {context_tokens}", flush=True)
        if context_tokens is None:
            raise RuntimeError(
                "Die Kontextgroesse des verbundenen LLM konnte nicht geprueft werden. "
                f"Mindestens {self._settings.llm_min_token_size} Token sind erforderlich."
            )

        if context_tokens < self._settings.llm_min_token_size:
            raise RuntimeError(
                f"Das verbundene LLM unterstuetzt nur {context_tokens} Kontext-Token. "
                f"Mindestens {self._settings.llm_min_token_size} sind erforderlich."
            )

    def _load_native_model_metadata(self) -> Any | None:
        try:
            request = Request(self._native_models_url())
            if self._settings.llm_api_key:
                request.add_header(
                    "Authorization",
                    f"Bearer {self._settings.llm_api_key}",
                )

            with urlopen(request, timeout=self._settings.llm_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

    def _native_models_url(self) -> str:
        parts = urlsplit(self._settings.lm_studio_url)
        path = parts.path.rstrip("/")
        if path.endswith("/v1"):
            path = path[:-3]

        native_path = f"{path}/api/v0/models" if path else "/api/v0/models"
        return urlunsplit((parts.scheme, parts.netloc, native_path, "", ""))

    def _find_matching_model_metadata(self, models: list[Any], model_id: str) -> Any | None:
        return self._find_model_metadata(
            models,
            model_id,
        ) or self._find_unique_compatible_model_metadata(
            models,
            model_id,
        )

    def _find_unique_compatible_model_metadata(
        self,
        models: list[Any],
        model_id: str,
    ) -> Any | None:
        normalized_model_id = model_id.lower()
        matches = [
            model
            for model in models
            if normalized_model_id in str(self._read_metadata_value(model, "id")).lower()
        ]
        unique_matches: dict[Any, Any] = {}
        for model in matches:
            model_key = self._read_metadata_value(model, "id")
            if model_key is None:
                continue

            existing_model = unique_matches.get(model_key)
            if existing_model is None:
                unique_matches[model_key] = model
                continue

            existing_context = self._extract_context_tokens(existing_model)
            model_context = self._extract_context_tokens(model)
            if existing_context is None and model_context is not None:
                unique_matches[model_key] = model

        if len(unique_matches) == 1:
            return next(iter(unique_matches.values()))

        return None

    def _is_model_loaded(self, native_model_metadata: Any, openai_model_metadata: Any) -> bool:
        native_loaded = self._model_loaded_status(native_model_metadata)
        if native_loaded is not None:
            return native_loaded

        return openai_model_metadata is not None

    def _model_loaded_status(self, metadata: Any) -> bool | None:
        for value in self._find_metadata_values(
            metadata,
            NORMALIZED_MODEL_LOADED_FLAG_KEYS,
        ):
            if isinstance(value, bool):
                return value

        for value in self._find_metadata_values(metadata, NORMALIZED_MODEL_STATE_KEYS):
            if not isinstance(value, str):
                continue

            normalized = re.sub(r"[^a-z0-9]", "", value.lower())
            if normalized in LOADED_MODEL_STATES:
                return True
            if normalized in UNLOADED_MODEL_STATES:
                return False

        return None

    def _find_metadata_values(
        self,
        value: Any,
        normalized_keys: set[str],
        depth: int = 0,
    ) -> list[Any]:
        if value is None or depth > 6:
            return []

        if isinstance(value, dict):
            matches: list[Any] = []
            for key, item in value.items():
                normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if normalized_key in normalized_keys:
                    matches.append(item)

                matches.extend(
                    self._find_metadata_values(item, normalized_keys, depth + 1)
                )

            return matches

        if isinstance(value, list):
            matches: list[Any] = []
            for item in value:
                matches.extend(
                    self._find_metadata_values(item, normalized_keys, depth + 1)
                )

            return matches

        model_dump = self._metadata_to_dict(value)
        if model_dump is not None:
            return self._find_metadata_values(model_dump, normalized_keys, depth + 1)

        return []

    def _format_available_models(self, models: list[Any]) -> str:
        model_ids = sorted(
            {
                str(model_id)
                for model_id in (
                    self._read_metadata_value(model, "id") for model in models
                )
                if model_id
            }
        )
        return ", ".join(model_ids)

    def _iter_model_items(self, models: Any) -> list[Any]:
        data = self._read_metadata_value(models, "data")
        if isinstance(data, list):
            return data

        if isinstance(models, list):
            return models

        return []

    def _read_metadata_value(self, metadata: Any, key: str) -> Any:
        if isinstance(metadata, dict):
            return metadata.get(key)

        return getattr(metadata, key, None)

    def _extract_context_tokens(self, *metadata_sources: Any) -> int | None:
        for metadata in metadata_sources:
            context_tokens = self._extract_context_tokens_from_value(metadata)
            if context_tokens is not None:
                return context_tokens

        return None

    def _extract_context_tokens_from_value(self, value: Any, depth: int = 0) -> int | None:
        runtime_context_tokens = self._extract_context_tokens_by_keys(
            value,
            NORMALIZED_RUNTIME_CONTEXT_TOKEN_KEYS,
            depth,
        )
        if runtime_context_tokens is not None:
            return runtime_context_tokens

        return self._extract_context_tokens_by_keys(
            value,
            NORMALIZED_MAX_CONTEXT_TOKEN_KEYS,
            depth,
        )

    def _extract_context_tokens_by_keys(
        self,
        value: Any,
        normalized_keys: set[str],
        depth: int = 0,
    ) -> int | None:
        if value is None or depth > 6:
            return None

        if isinstance(value, dict):
            for key, item in value.items():
                normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if normalized_key in normalized_keys:
                    context_tokens = self._coerce_token_count(item)
                    if context_tokens is not None:
                        return context_tokens

            for item in value.values():
                context_tokens = self._extract_context_tokens_by_keys(
                    item,
                    normalized_keys,
                    depth + 1,
                )
                if context_tokens is not None:
                    return context_tokens

            return None

        if isinstance(value, list):
            for item in value:
                context_tokens = self._extract_context_tokens_by_keys(
                    item,
                    normalized_keys,
                    depth + 1,
                )
                if context_tokens is not None:
                    return context_tokens

            return None

        model_dump = self._metadata_to_dict(value)
        if model_dump is not None:
            return self._extract_context_tokens_by_keys(
                model_dump,
                normalized_keys,
                depth + 1,
            )

        return None

    def _metadata_to_dict(self, value: Any) -> dict[str, Any] | None:
        data: dict[str, Any] | None = None

        if hasattr(value, "model_dump"):
            try:
                model_dump = value.model_dump()
            except Exception:
                model_dump = None
            if isinstance(model_dump, dict):
                data = model_dump

        if data is None and hasattr(value, "dict"):
            try:
                legacy_dump = value.dict()
            except Exception:
                legacy_dump = None
            if isinstance(legacy_dump, dict):
                data = legacy_dump

        model_extra = getattr(value, "model_extra", None)
        if isinstance(model_extra, dict):
            data = {**(data or {}), **model_extra}

        if data is None and hasattr(value, "__dict__"):
            data = {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }

        return data

    def _coerce_token_count(self, value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if value.is_integer() else None
        if not isinstance(value, str):
            return None

        normalized = value.strip().lower().replace(",", "").replace("_", "")
        match = re.fullmatch(r"(\d+(?:\.\d+)?)([km])?(?:\s*tokens?)?", normalized)
        if match is None:
            return None

        amount = float(match.group(1))
        suffix = match.group(2)
        if suffix == "k":
            amount *= 1_000
        elif suffix == "m":
            amount *= 1_000_000

        return int(amount)

    def create_prophecy(
        self,
        user_text: str,
        persona: PersonaProfile | None = None,
        progress: ProgressCallback | None = None,
    ) -> str:
        persona_profile = persona or PersonaProfile.unknown()
        started_at = monotonic()
        prompt_config = load_prompt_config(self._settings.prompt_config_file)
        prompt_selector = MersenneTwisterPromptSelector()
        print(
            "[LLM] Starting agentic prophecy pipeline: "
            f"model={self._model_id}, "
            f"user_chars={len(user_text)}, "
            f"persona={persona_profile.as_json()}, "
            f"timeout={self._settings.llm_generation_timeout_seconds}s",
            flush=True,
        )
        stage_outputs: dict[str, str] = {}
        try:
            analysis_variant = prompt_selector.choose(
                "analysis",
                prompt_config.analysis,
            )
            self._emit_phase_status(
                progress,
                stage_name="analysis",
                phase_state="selected",
                variant_name=analysis_variant.name,
                phase_fill_color=analysis_variant.fill_color,
                phase_outline_color=analysis_variant.outline_color,
                message="Die Moiren greifen nach dem ersten Faden...",
                star_count=0,
            )
            stage_outputs["analysis"] = self._run_llm_stage(
                stage_name="analysis",
                variant_name=analysis_variant.name,
                phase_fill_color=analysis_variant.fill_color,
                phase_outline_color=analysis_variant.outline_color,
                system_prompt=self._build_stage_prompt(
                    analysis_variant,
                    prompt_config.analysis.style,
                ),
                user_content=self._analysis_input(user_text, persona_profile),
                progress=progress,
                temperature=0.25,
            )
            recommendation_variant = prompt_selector.choose(
                "recommendation",
                prompt_config.recommendation,
            )
            self._emit_phase_status(
                progress,
                stage_name="recommendation",
                phase_state="selected",
                variant_name=recommendation_variant.name,
                phase_fill_color=recommendation_variant.fill_color,
                phase_outline_color=recommendation_variant.outline_color,
                message="Hermes trägt ein verborgenes Zeichen heran...",
                star_count=0,
            )
            stage_outputs["recommendation"] = self._run_llm_stage(
                stage_name="recommendation",
                variant_name=recommendation_variant.name,
                phase_fill_color=recommendation_variant.fill_color,
                phase_outline_color=recommendation_variant.outline_color,
                system_prompt=self._build_stage_prompt(
                    recommendation_variant,
                    prompt_config.recommendation.style,
                ),
                user_content=self._recommendation_input(
                    user_text,
                    persona_profile,
                    stage_outputs["analysis"],
                ),
                progress=progress,
                temperature=0.55,
            )
            prophecy_variant = prompt_selector.choose(
                "prophecy",
                prompt_config.prophecy,
            )
            self._emit_phase_status(
                progress,
                stage_name="prophecy",
                phase_state="selected",
                variant_name=prophecy_variant.name,
                phase_fill_color=prophecy_variant.fill_color,
                phase_outline_color=prophecy_variant.outline_color,
                message="Hekates Fackel fällt auf den letzten Faden...",
                star_count=0,
            )
            prophecy_prompt = self._build_stage_prompt(
                prophecy_variant,
                prompt_config.prophecy.style,
            )
            print(
                "[Prompt] Prophecy style appended: "
                f"style_chars={len(prompt_config.prophecy.style or '')}",
                flush=True,
            )
            stage_outputs["prophecy"] = self._run_llm_stage(
                stage_name="prophecy",
                variant_name=prophecy_variant.name,
                phase_fill_color=prophecy_variant.fill_color,
                phase_outline_color=prophecy_variant.outline_color,
                system_prompt=prophecy_prompt,
                user_content=self._prophecy_input(
                    persona_profile,
                    stage_outputs["analysis"],
                    stage_outputs["recommendation"],
                ),
                progress=progress,
                temperature=0.35,
            )
            if progress is not None:
                progress("The card is being written.", 98, 0)

            full_prophecy = stage_outputs["prophecy"].strip()
            elapsed = monotonic() - started_at
            print(
                "[LLM] Agentic prophecy pipeline finished: "
                f"answer_chars={len(full_prophecy)}, "
                f"elapsed={elapsed:.1f}s",
                flush=True,
            )
            return full_prophecy
        finally:
            stage_outputs.clear()
            print("[Pipeline] Prophecy run context reset.", flush=True)

    def create_prophecy_matrix(
        self,
        user_text: str,
        persona: PersonaProfile | None = None,
        *,
        seed: int | None = None,
        stream_output: bool = False,
    ) -> ProphecyMatrixResult:
        normalized_user_text = user_text.strip()
        if not normalized_user_text:
            raise ValueError("Prompt test question must not be empty.")

        persona_profile = persona or PersonaProfile.unknown()
        started_at = monotonic()
        prompt_config = load_prompt_config(self._settings.prompt_config_file)
        prompt_selector = MersenneTwisterPromptSelector(seed=seed)
        print(
            "[PromptTest] Starting prophecy matrix run: "
            f"model={self._model_id}, "
            f"user_chars={len(normalized_user_text)}, "
            f"prophecy_variants={len(prompt_config.prophecy.variants)}",
            flush=True,
        )

        analysis_variant = prompt_selector.choose("analysis", prompt_config.analysis)
        analysis_output = self._run_llm_stage(
            stage_name="analysis",
            variant_name=analysis_variant.name,
            phase_fill_color=analysis_variant.fill_color,
            phase_outline_color=analysis_variant.outline_color,
            system_prompt=self._build_stage_prompt(
                analysis_variant,
                prompt_config.analysis.style,
            ),
            user_content=self._analysis_input(normalized_user_text, persona_profile),
            progress=None,
            temperature=0.25,
            stream_output=stream_output,
        )
        analysis_result = StageRunResult(
            stage_name="analysis",
            variant_name=analysis_variant.name,
            variant_fill_color=analysis_variant.fill_color,
            variant_outline_color=analysis_variant.outline_color,
            variant_weight=analysis_variant.weight,
            output=analysis_output,
        )

        recommendation_variant = prompt_selector.choose(
            "recommendation",
            prompt_config.recommendation,
        )
        recommendation_output = self._run_llm_stage(
            stage_name="recommendation",
            variant_name=recommendation_variant.name,
            phase_fill_color=recommendation_variant.fill_color,
            phase_outline_color=recommendation_variant.outline_color,
            system_prompt=self._build_stage_prompt(
                recommendation_variant,
                prompt_config.recommendation.style,
            ),
            user_content=self._recommendation_input(
                normalized_user_text,
                persona_profile,
                analysis_result.output,
            ),
            progress=None,
            temperature=0.55,
            stream_output=stream_output,
        )
        recommendation_result = StageRunResult(
            stage_name="recommendation",
            variant_name=recommendation_variant.name,
            variant_fill_color=recommendation_variant.fill_color,
            variant_outline_color=recommendation_variant.outline_color,
            variant_weight=recommendation_variant.weight,
            output=recommendation_output,
        )

        prophecy_input = self._prophecy_input(
            persona_profile,
            analysis_result.output,
            recommendation_result.output,
        )
        prophecy_results: list[StageRunResult] = []
        total_prophecy_variants = len(prompt_config.prophecy.variants)
        print(
            "[Prompt] Prophecy style appended for matrix run: "
            f"style_chars={len(prompt_config.prophecy.style or '')}",
            flush=True,
        )
        for index, prophecy_variant in enumerate(prompt_config.prophecy.variants, start=1):
            print(
                "[PromptTest] Running prophecy variant: "
                f"index={index}/{total_prophecy_variants}, "
                f"name={prophecy_variant.name}, "
                f"weight={prophecy_variant.weight:g}, "
                f"fill={prophecy_variant.fill_color}, "
                f"outline={prophecy_variant.outline_color}",
                flush=True,
            )
            prophecy_output = self._run_llm_stage(
                stage_name="prophecy",
                variant_name=prophecy_variant.name,
                phase_fill_color=prophecy_variant.fill_color,
                phase_outline_color=prophecy_variant.outline_color,
                system_prompt=self._build_stage_prompt(
                    prophecy_variant,
                    prompt_config.prophecy.style,
                ),
                user_content=prophecy_input,
                progress=None,
                temperature=0.35,
                stream_output=stream_output,
            )
            prophecy_results.append(
                StageRunResult(
                    stage_name="prophecy",
                    variant_name=prophecy_variant.name,
                    variant_fill_color=prophecy_variant.fill_color,
                    variant_outline_color=prophecy_variant.outline_color,
                    variant_weight=prophecy_variant.weight,
                    output=prophecy_output,
                )
            )

        elapsed = monotonic() - started_at
        print(
            "[PromptTest] Prophecy matrix finished: "
            f"analysis_variant={analysis_result.variant_name}, "
            f"recommendation_variant={recommendation_result.variant_name}, "
            f"prophecy_variants={len(prophecy_results)}, "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )
        print("[PromptTest] Each prophecy stage used a fresh chat completion.", flush=True)
        return ProphecyMatrixResult(
            question=normalized_user_text,
            analysis=analysis_result,
            recommendation=recommendation_result,
            prophecies=tuple(prophecy_results),
        )

    def _emit_phase_status(
        self,
        progress: ProgressCallback | None,
        *,
        stage_name: str,
        phase_state: str,
        variant_name: str,
        phase_fill_color: str,
        phase_outline_color: str,
        message: str,
        star_count: int,
    ) -> None:
        progress_value = PHASE_PROGRESS[(stage_name, phase_state)]
        print(
            "[Pipeline] STATUS_TRANSITION "
            f"stage={stage_name}, "
            f"phase={phase_state}, "
            f"variant={variant_name}, "
            f"fill={phase_fill_color}, "
            f"outline={phase_outline_color}, "
            f"progress={progress_value}, "
            f"message={message!r}",
            flush=True,
        )
        if progress is None:
            return

        try:
            progress(
                message,
                progress_value,
                star_count,
                stage_name,
                phase_state,
                variant_name,
                phase_fill_color,
                phase_outline_color,
            )
        except TypeError:
            progress(message, progress_value, star_count)

    def _run_llm_stage(
        self,
        *,
        stage_name: str,
        variant_name: str,
        phase_fill_color: str,
        phase_outline_color: str,
        system_prompt: str,
        user_content: str,
        progress: ProgressCallback | None,
        temperature: float,
        stream_output: bool = True,
    ) -> str:
        started_at = monotonic()
        print(
            "[LLM] Starting stage: "
            f"stage={stage_name}, "
            f"variant={variant_name}, "
            f"system_chars={len(system_prompt)}, "
            f"user_chars={len(user_content)}, "
            f"reasoning_effort={self._stage_reasoning_effort(stage_name) or 'off'}",
            flush=True,
        )
        reasoning_message = self._stage_status_message(stage_name, "reasoning")
        self._emit_phase_status(
            progress,
            stage_name=stage_name,
            phase_state="reasoning",
            variant_name=variant_name,
            phase_fill_color=phase_fill_color,
            phase_outline_color=phase_outline_color,
            message=reasoning_message,
            star_count=0,
        )

        full_response = ""
        chunk_count = 0
        reasoning_started = False
        content_started = False
        pending_reasoning_carriage_return = False
        pending_output_word_fragment = ""
        try:
            request_kwargs: dict[str, Any] = {
                "model": self._model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "stream": True,
                "temperature": temperature,
                "timeout": self._settings.llm_generation_timeout_seconds,
            }
            reasoning_effort = self._stage_reasoning_effort(stage_name)
            if reasoning_effort is not None:
                request_kwargs["reasoning_effort"] = reasoning_effort

            response = self._client.chat.completions.create(**request_kwargs)

            print(
                f"[LLM][{stage_name}] Stream opened; waiting for first chunk...",
                flush=True,
            )
            for chunk in response:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                reasoning_content = getattr(delta, "reasoning_content", None)

                if reasoning_content:
                    if not reasoning_started:
                        reasoning_started = True
                        if stream_output:
                            print(f"\n[LLM][{stage_name}][reasoning] BEGIN", flush=True)
                    if stream_output:
                        print(reasoning_content, end="", flush=True)
                    star_count, pending_reasoning_carriage_return = self._count_line_breaks(
                        reasoning_content,
                        pending_reasoning_carriage_return,
                    )
                    self._emit_reasoning_stars(
                        progress,
                        stage_name=stage_name,
                        variant_name=variant_name,
                        phase_fill_color=phase_fill_color,
                        phase_outline_color=phase_outline_color,
                        message=reasoning_message,
                        star_count=star_count,
                    )
                elif pending_reasoning_carriage_return:
                    self._emit_reasoning_stars(
                        progress,
                        stage_name=stage_name,
                        variant_name=variant_name,
                        phase_fill_color=phase_fill_color,
                        phase_outline_color=phase_outline_color,
                        message=reasoning_message,
                        star_count=1,
                    )
                    pending_reasoning_carriage_return = False

                if content is not None:
                    if reasoning_started and not content_started and stream_output:
                        print(f"\n[LLM][{stage_name}][reasoning] END", flush=True)
                    if not content_started:
                        content_started = True
                        if stream_output:
                            print(f"[LLM][{stage_name}][answer] BEGIN", flush=True)
                        self._emit_phase_status(
                            progress,
                            stage_name=stage_name,
                            phase_state="answer",
                            variant_name=variant_name,
                            phase_fill_color=phase_fill_color,
                            phase_outline_color=phase_outline_color,
                            message=self._stage_status_message(stage_name, "answer"),
                            star_count=0,
                        )
                    if stream_output:
                        print(content, end="", flush=True)
                    word_star_count, pending_output_word_fragment = self._count_completed_words(
                        content,
                        pending_output_word_fragment,
                    )
                    self._emit_answer_stars(
                        progress,
                        stage_name=stage_name,
                        variant_name=variant_name,
                        phase_fill_color=phase_fill_color,
                        phase_outline_color=phase_outline_color,
                        message=self._stage_status_message(stage_name, "answer"),
                        star_count=word_star_count,
                    )
                    full_response += content
                    chunk_count += 1
        except Exception as exc:
            elapsed = monotonic() - started_at
            print(
                f"\n[LLM] Stage '{stage_name}' failed after {elapsed:.1f}s: {exc!r}",
                flush=True,
            )
            traceback.print_exc()
            raise

        if pending_reasoning_carriage_return:
            self._emit_reasoning_stars(
                progress,
                stage_name=stage_name,
                variant_name=variant_name,
                phase_fill_color=phase_fill_color,
                phase_outline_color=phase_outline_color,
                message=reasoning_message,
                star_count=1,
            )

        if pending_output_word_fragment:
            self._emit_answer_stars(
                progress,
                stage_name=stage_name,
                variant_name=variant_name,
                phase_fill_color=phase_fill_color,
                phase_outline_color=phase_outline_color,
                message=self._stage_status_message(stage_name, "answer"),
                star_count=1,
            )

        if reasoning_started and not content_started and stream_output:
            print(f"\n[LLM][{stage_name}][reasoning] END", flush=True)
        if content_started and stream_output:
            print(f"\n[LLM][{stage_name}][answer] END", flush=True)

        response_text = full_response.strip()
        if not response_text:
            raise RuntimeError(f"LLM stage '{stage_name}' returned an empty answer.")

        elapsed = monotonic() - started_at
        self._emit_phase_status(
            progress,
            stage_name=stage_name,
            phase_state="done",
            variant_name=variant_name,
            phase_fill_color=phase_fill_color,
            phase_outline_color=phase_outline_color,
            message=self._stage_status_message(stage_name, "done"),
            star_count=0,
        )
        print(
            "[LLM] Stage finished: "
            f"stage={stage_name}, "
            f"answer_chars={len(response_text)}, "
            f"chunks={chunk_count}, "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )
        return response_text

    def _emit_reasoning_stars(
        self,
        progress: ProgressCallback | None,
        *,
        stage_name: str,
        variant_name: str,
        phase_fill_color: str,
        phase_outline_color: str,
        message: str,
        star_count: int,
    ) -> None:
        if progress is None or star_count <= 0:
            return

        progress_value = PHASE_PROGRESS[(stage_name, "reasoning")]
        try:
            progress(
                message,
                progress_value,
                star_count,
                stage_name,
                "reasoning",
                variant_name,
                phase_fill_color,
                phase_outline_color,
            )
        except TypeError:
            progress(message, progress_value, star_count)

    def _emit_answer_stars(
        self,
        progress: ProgressCallback | None,
        *,
        stage_name: str,
        variant_name: str,
        phase_fill_color: str,
        phase_outline_color: str,
        message: str,
        star_count: int,
    ) -> None:
        if progress is None or star_count <= 0:
            return

        progress_value = PHASE_PROGRESS[(stage_name, "answer")]
        try:
            progress(
                message,
                progress_value,
                star_count,
                stage_name,
                "answer",
                variant_name,
                phase_fill_color,
                phase_outline_color,
            )
        except TypeError:
            progress(message, progress_value, star_count)

    def _count_line_breaks(
        self,
        text: str,
        pending_carriage_return: bool = False,
    ) -> tuple[int, bool]:
        line_break_count = 0
        index = 0

        if pending_carriage_return:
            line_break_count += 1
            if text.startswith("\n"):
                index = 1
            pending_carriage_return = False

        while index < len(text):
            character = text[index]
            if character == "\r":
                if index + 1 < len(text):
                    if text[index + 1] == "\n":
                        line_break_count += 1
                        index += 2
                        continue

                    line_break_count += 1
                else:
                    pending_carriage_return = True
            elif character == "\n":
                line_break_count += 1

            index += 1

        return line_break_count, pending_carriage_return

    def _count_completed_words(
        self,
        text: str,
        pending_word_fragment: str = "",
    ) -> tuple[int, str]:
        combined = f"{pending_word_fragment}{text}"
        if not combined:
            return 0, ""

        words = list(re.finditer(r"\S+", combined))
        if not words:
            return 0, ""

        completed_word_count = 0
        trailing_fragment = ""
        ends_with_whitespace = combined[-1].isspace()
        for match in words:
            if match.end() == len(combined) and not ends_with_whitespace:
                trailing_fragment = match.group(0)
                continue

            completed_word_count += 1

        return completed_word_count, trailing_fragment

    def _stage_status_message(self, stage_name: str, phase_state: str) -> str:
        messages = {
            ("analysis", "reasoning"): "Ich lausche den Echos aus dem Tartaros...",
            ("analysis", "answer"): "Athene ordnet die Splitter im Rauch...",
            ("analysis", "done"): "Der erste Faden glänzt im Licht der Moiren.",
            ("recommendation", "reasoning"): "Hekate hebt die Fackel an die Schwelle...",
            ("recommendation", "answer"): "Hermes flüstert zwischen Schatten und Schwur...",
            ("recommendation", "done"): "Der zweite Faden ruht unter dunklem Lorbeer.",
            ("prophecy", "reasoning"): "Apollons Leier klingt hinter dem Nebel...",
            ("prophecy", "answer"): "Die Moiren ziehen den Spruch aus der Nacht...",
            ("prophecy", "done"): "Das Zeichen sinkt auf die Karte.",
        }
        return messages.get((stage_name, phase_state), "Die Zeichen wandern weiter...")

    def _build_stage_prompt(
        self,
        stage_variant: PromptVariant,
        stage_style: str | None,
    ) -> str:
        if stage_style is None or stage_variant.ignore_style:
            return stage_variant.prompt

        return f"{stage_variant.prompt}\n\n{stage_style}"

    def _analysis_input(self, user_text: str, persona: PersonaProfile) -> str:
        return (
            "Persona JSON:\n"
            f"{persona.as_json()}\n\n"
            "User spoken input:\n"
            "\"\"\"\n"
            f"{user_text.strip()}\n"
            "\"\"\""
        )

    def _recommendation_input(
        self,
        user_text: str,
        persona: PersonaProfile,
        analysis: str,
    ) -> str:
        return (
            "Persona JSON:\n"
            f"{persona.as_json()}\n\n"
            "Original user spoken input:\n"
            "\"\"\"\n"
            f"{user_text.strip()}\n"
            "\"\"\"\n\n"
            "Analysis from stage A:\n"
            f"{analysis}"
        )

    def _prophecy_input(
        self,
        persona: PersonaProfile,
        analysis: str,
        recommendation: str,
    ) -> str:
        return (
            "Persona JSON:\n"
            f"{persona.as_json()}\n\n"
            "JSON-A:\n"
            f"{analysis}\n\n"
            "JSON-B:\n"
            f"{recommendation}"
    )
