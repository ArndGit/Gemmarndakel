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
    ("therapy_plan", "selected"): 10,
    ("therapy_plan", "reasoning"): 16,
    ("therapy_plan", "answer"): 24,
    ("therapy_plan", "done"): 32,
    ("scenario", "selected"): 38,
    ("scenario", "reasoning"): 44,
    ("scenario", "answer"): 54,
    ("scenario", "done"): 64,
    ("prophecy", "selected"): 70,
    ("prophecy", "reasoning"): 76,
    ("prophecy", "answer"): 88,
    ("prophecy", "done"): 92,
    ("spellcheck", "selected"): 93,
    ("spellcheck", "reasoning"): 94,
    ("spellcheck", "answer"): 97,
    ("spellcheck", "done"): 98,
}
_PHASE_MESSAGE_PARTS: dict[tuple[str, str], tuple[tuple[str, ...], tuple[str, ...]]] = {
    ("therapy_plan", "selected"): (
        (
            "Die Moiren tasten nach dem ersten Faden.",
            "Athene hebt die erste Scherbe aus dem Rauch.",
            "Am Anfang der Deutung regt sich ein stiller Zug.",
            "Der erste Kreis der Lesung schließt sich langsam.",
        ),
        (
            "Die innere Ordnung wird gesucht.",
            "Ein verborgenes Muster drängt ans Licht.",
            "Die Frage legt ihr erstes Gesicht frei.",
            "Das Herz der Unruhe wird vorsichtig berührt.",
            "Ein stiller Plan tritt aus dem Schatten.",
        ),
    ),
    ("therapy_plan", "reasoning"): (
        (
            "Ich lausche den Echos aus dem Tartaros.",
            "Athene neigt sich über die rauchenden Splitter.",
            "Unter dem ersten Schleier ordnet sich ein Gedanke.",
            "Die innere Karte wird Stein um Stein gelegt.",
        ),
        (
            "Verdeckte Ursachen treten hervor.",
            "Das Bedürfnis hinter der Frage wird hörbar.",
            "Ein blinder Fleck zeichnet seinen Rand.",
            "Der verborgene Zug der Seele nimmt Form an.",
            "Die stille Spannung erhält einen Namen.",
        ),
    ),
    ("therapy_plan", "answer"): (
        (
            "Athene ordnet die Splitter im Rauch.",
            "Der erste Spruch sammelt sich zur Form.",
            "Die Deutung rinnt in klarere Linien.",
            "Die erste Lesung bindet ihre Knoten.",
        ),
        (
            "Ein innerer Faden wird sichtbar.",
            "Das Verborgene schreibt sich in Zeichen.",
            "Die Wurzel der Frage spricht leiser, aber klarer.",
            "Die seelische Spur tritt aus dem Nebel.",
            "Die verborgene Richtung zeigt ihr Gesicht.",
        ),
    ),
    ("therapy_plan", "done"): (
        (
            "Der erste Faden glänzt im Licht der Moiren.",
            "Die innere Lesung liegt gefasst bereit.",
            "Der erste Kreis der Deutung ist geschlossen.",
            "Athene legt die erste Tafel beiseite.",
        ),
        (
            "Der verborgene Plan ist benannt.",
            "Die innere Ordnung ruht vorerst still.",
            "Die erste Schicht der Frage ist geöffnet.",
            "Das seelische Muster steht im Zeichenkreis.",
            "Die erste Antwort schweigt nun fest.",
        ),
    ),
    ("scenario", "selected"): (
        (
            "Hermes trägt ein verborgenes Zeichen heran.",
            "Der zweite Faden hebt sich aus dem Dämmer.",
            "An der Schwelle der Zukunft regt sich ein Schritt.",
            "Ein kommendes Bild sucht seinen Eingang.",
        ),
        (
            "Die Szene von morgen will Gestalt gewinnen.",
            "Ein mögliches Ereignis verlangt nach Stimme.",
            "Die Zukunft tastet nach einem Umriss.",
            "Ein Omen sucht sein weltliches Gewand.",
            "Der Weg der nächsten Wendung öffnet sich.",
        ),
    ),
    ("scenario", "reasoning"): (
        (
            "Hekate hebt die Fackel an die Schwelle.",
            "Hermes zählt die Wege zwischen Tür und Tor.",
            "Der zweite Kreis der Lesung wird abgemessen.",
            "Im Dämmer der Möglichkeiten formt sich ein Bild.",
        ),
        (
            "Ein künftiges Ereignis sucht seine Stunde.",
            "Das Omen wägt Nähe und Gefahr.",
            "Die Welt der nächsten Tage wird befragt.",
            "Ein kommender Zug bindet sich an den ersten Faden.",
            "Die Zukunft legt ihre Schuhe an.",
        ),
    ),
    ("scenario", "answer"): (
        (
            "Hermes flüstert zwischen Schatten und Schwur.",
            "Das zweite Bild tritt an den Rand der Karte.",
            "Die Zukunft gießt sich in irdische Zeichen.",
            "Ein Omen nimmt sein sichtbares Kleid an.",
        ),
        (
            "Der kommende Schritt wird greifbar.",
            "Ein weltliches Ereignis hebt den Schleier.",
            "Das Nächste spricht in klareren Bildern.",
            "Die Szene der Zukunft rückt näher.",
            "Die Wendung des Weges wird benannt.",
        ),
    ),
    ("scenario", "done"): (
        (
            "Der zweite Faden ruht unter dunklem Lorbeer.",
            "Die Szene der Zukunft liegt gebunden vor.",
            "Das Omen der nächsten Wendung steht fest.",
            "Der zweite Kreis der Deutung ist geschlossen.",
        ),
        (
            "Das kommende Bild schweigt nun klar.",
            "Die Zukunft hat ihren Umriss gezeigt.",
            "Ein Ereignis steht im Schatten bereit.",
            "Der Weg vor der Tür ist bezeichnet.",
            "Das zweite Zeichen hält seine Form.",
        ),
    ),
    ("prophecy", "selected"): (
        (
            "Hekates Fackel fällt auf den letzten Faden.",
            "Apollons Atem streift den Rand der Karte.",
            "Der letzte Kreis der Vision hebt an.",
            "Das Orakel hebt die Stimme aus der Nacht.",
        ),
        (
            "Der Spruch sucht seinen Klang.",
            "Die Vision verlangt nach ihrer Zunge.",
            "Das Omen will in alte Worte treten.",
            "Die letzte Form der Weissagung erwacht.",
            "Die Karte wartet auf ihren Satz.",
        ),
    ),
    ("prophecy", "reasoning"): (
        (
            "Apollons Leier klingt hinter dem Nebel.",
            "Die letzte Vision zieht durch den Tempelrauch.",
            "Am Rand der Nacht sammelt sich der Spruch.",
            "Das Orakel neigt sein Ohr dem letzten Faden.",
        ),
        (
            "Bild und Schicksal suchen einen Ton.",
            "Die Zeichen bitten um ihre alte Sprache.",
            "Ein Omen formt sich zur Weissagung.",
            "Die Bilder werden zu einem einzigen Atem.",
            "Der Spruch wägt Gold gegen Schatten.",
        ),
    ),
    ("prophecy", "answer"): (
        (
            "Die Moiren ziehen den Spruch aus der Nacht.",
            "Der letzte Satz tropft aus dem Sternenrauch.",
            "Die Karte nimmt die Weissagung auf.",
            "Die Vision schreibt sich in den Rand des Lichts.",
        ),
        (
            "Das Omen spricht nun in Bildern.",
            "Die Zukunft singt mit altem Mund.",
            "Der Spruch legt sich auf die Karte.",
            "Die Weissagung erhält ihre Gestalt.",
            "Das Zeichen wird zu hörbarem Schicksal.",
        ),
    ),
    ("prophecy", "done"): (
        (
            "Das Zeichen sinkt auf die Karte.",
            "Der Spruch ruht im letzten Licht.",
            "Die Weissagung hat ihren Platz gefunden.",
            "Der letzte Kreis der Vision ist geschlossen.",
        ),
        (
            "Die Karte trägt nun ihr Omen.",
            "Das Bild der Zukunft ist gesprochen.",
            "Die Nacht gibt den Satz nicht mehr frei.",
            "Der Spruch liegt im offenen Zeichen.",
            "Die Vision steht still auf dem Papier.",
        ),
    ),
    ("spellcheck", "selected"): (
        (
            "Der letzte Blick gleitet über den Spruch.",
            "Eine stille Hand hebt die Feder der Korrektur.",
            "Die Schrift wird noch einmal an das Licht gehalten.",
            "Der Nachhall der Worte wird geprüft.",
        ),
        (
            "Der Feinschliff beginnt.",
            "Der Randfehler wird gesucht.",
            "Die letzte Unschärfe soll weichen.",
            "Die Oberfläche des Spruchs wird geglättet.",
            "Der Wortlaut wird gewogen.",
        ),
    ),
    ("spellcheck", "reasoning"): (
        (
            "Die Schrift wird gegen den Wind gelesen.",
            "Ein stilles Auge prüft die Fugen der Worte.",
            "Die letzten Körner im Satz werden gewendet.",
            "Der Nachklang des Spruchs wird bedacht.",
        ),
        (
            "Feine Risse treten hervor.",
            "Die Grammatik legt ihre Maßstäbe an.",
            "Der Ton soll rein bewahrt bleiben.",
            "Die letzte Unruhe im Satz wird geortet.",
            "Die Feder prüft jedes Glied der Rede.",
        ),
    ),
    ("spellcheck", "answer"): (
        (
            "Der letzte Fehler weicht aus dem Spruch.",
            "Die Feder glättet die Kanten der Worte.",
            "Die Schrift fällt sauber in ihr Bett.",
            "Der Nachhall wird in klares Deutsch gebunden.",
        ),
        (
            "Der Satz gewinnt an Ruhe.",
            "Die Form wird ohne Verlust geschärft.",
            "Der Ton bleibt, der Stolperstein fällt.",
            "Die Rede wird lichter und fester.",
            "Die letzte Unschärfe verlässt die Zeile.",
        ),
    ),
    ("spellcheck", "done"): (
        (
            "Der Spruch liegt bereinigt vor.",
            "Die letzte Feder ist zur Ruhe gekommen.",
            "Die Schrift steht nun ohne Wanken.",
            "Der Feinschliff ist vollendet.",
        ),
        (
            "Kein loser Rand bleibt zurück.",
            "Der Wortlaut ist fest und klar.",
            "Die Zeilen halten nun still.",
            "Der Satzkreis ist geschlossen.",
            "Die letzte Korrektur ist versiegelt.",
        ),
    ),
}
SPELLCHECK_SYSTEM_PROMPT = (
    "Du bist die letzte deutsche Korrekturstufe nach einem Orakeltext. "
    "Du bekommst ausschliesslich den fertigen Ausgabetext der Orakelstufe. "
    "Erzeuge fehlerfreies Standarddeutsch. "
    "Korrigiere konsequent Grammatik, Flexion, Kasus, Genus, Numerus, Verbformen, Satzbau, Bezuege, Zeichensetzung, Gross- und Kleinschreibung sowie offensichtliche Tippfehler. "
    "Pruefe besonders Subjekt-Verb-Kongruenz, Artikel-Nomen-Kongruenz, Pronomenbezuege, Kommasetzung und holprige Satzanschluesse. "
    "Wenn der Text erkennbar ein Bibelvers oder ein Bibelzitat mit Stellenangabe ist, behandle ihn nicht wie freie Prosa. "
    "Pruefe stattdessen, ob Wortlaut und Stellenangabe zusammenpassen, und korrigiere den Vers auf die wahrscheinlich richtige Fassung sowie bei Bedarf auch die Referenz. "
    "Wenn du die genaue Fassung nicht sicher wiederherstellen kannst, nimm nur minimale orthografische Korrekturen vor und erfinde keinen neuen Vers. "
    "Wenn ein Satz grammatisch falsch ist, formuliere ihn so weit um, wie es fuer korrektes Deutsch noetig ist, aber aendere nicht Sinn, Ton, Mehrdeutigkeit, Anrede, Stil oder grobe Laenge. "
    "Bei Bibelversen hat die Wiederherstellung des korrekten Zitats Vorrang vor stilistischen Glaettungen. "
    "Erfinde nichts hinzu, lasse nichts Wesentliches weg und kommentiere nichts. "
    "Wenn der Text bereits korrekt ist, gib ihn unveraendert zurueck. "
    "Gib ausschliesslich den korrigierten deutschen Text aus, ohne Anfuehrungszeichen, Labels oder Kommentar."
)
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
    therapy_plan: StageRunResult
    scenario: StageRunResult
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
        self._stage_variant_overrides: dict[str, str] = {}
        self._answer_star_remainder_by_stage: dict[str, float] = {}
        self._status_message_cache: dict[tuple[str, str], str] = {}
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
            f"therapy_plan:{self._stage_reasoning_enabled('therapy_plan')},"
            f"scenario:{self._stage_reasoning_enabled('scenario')},"
            f"prophecy:{self._stage_reasoning_enabled('prophecy')}, "
            f"connect_timeout={settings.llm_timeout_seconds}s, "
            f"generation_timeout={settings.llm_generation_timeout_seconds}s",
            flush=True,
        )

    def get_stage_variant_names(self) -> dict[str, tuple[str, ...]]:
        prompt_config = load_prompt_config(self._settings.prompt_config_file)
        return {
            "therapy_plan": tuple(
                variant.name for variant in prompt_config.therapy_plan.variants
            ),
            "scenario": tuple(variant.name for variant in prompt_config.scenario.variants),
            "prophecy": tuple(variant.name for variant in prompt_config.prophecy.variants),
        }

    def set_stage_variant_overrides(
        self,
        overrides: dict[str, str | None],
    ) -> None:
        prompt_config = load_prompt_config(self._settings.prompt_config_file)
        stages = {
            "therapy_plan": prompt_config.therapy_plan,
            "scenario": prompt_config.scenario,
            "prophecy": prompt_config.prophecy,
        }
        normalized: dict[str, str] = {}
        for stage_name, variant_name in overrides.items():
            if stage_name not in stages:
                raise ValueError(f"Unknown stage override: {stage_name}")
            if variant_name is None:
                continue
            self._get_variant_by_name(stages[stage_name], variant_name)
            normalized[stage_name] = variant_name

        self._stage_variant_overrides = normalized

    def _stage_reasoning_enabled(self, stage_name: str) -> bool:
        if stage_name == "therapy_plan":
            return self._settings.llm_therapy_plan_reasoning_enabled
        if stage_name == "scenario":
            return self._settings.llm_scenario_reasoning_enabled
        if stage_name == "prophecy":
            return self._settings.llm_prophecy_reasoning_enabled
        if stage_name == "spellcheck":
            return False

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
        self._reset_status_message_cache()
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
            therapy_plan_variant = self._choose_stage_variant(
                "therapy_plan",
                prompt_config.therapy_plan,
                prompt_selector,
            )
            self._emit_phase_status(
                progress,
                stage_name="therapy_plan",
                phase_state="selected",
                variant_name=therapy_plan_variant.name,
                phase_fill_color=therapy_plan_variant.fill_color,
                phase_outline_color=therapy_plan_variant.outline_color,
                message=self._stage_status_message("therapy_plan", "selected"),
                star_count=0,
            )
            stage_outputs["therapy_plan"] = self._run_llm_stage(
                stage_name="therapy_plan",
                variant_name=therapy_plan_variant.name,
                phase_fill_color=therapy_plan_variant.fill_color,
                phase_outline_color=therapy_plan_variant.outline_color,
                system_prompt=self._build_stage_prompt(
                    stage_name="therapy_plan",
                    stage_variant=therapy_plan_variant,
                    stage_style=prompt_config.therapy_plan.style,
                    persona=persona_profile,
                ),
                user_content=self._therapy_plan_input(user_text, persona_profile),
                progress=progress,
                temperature=0.25,
            )
            scenario_variant = self._choose_stage_variant(
                "scenario",
                prompt_config.scenario,
                prompt_selector,
            )
            self._emit_phase_status(
                progress,
                stage_name="scenario",
                phase_state="selected",
                variant_name=scenario_variant.name,
                phase_fill_color=scenario_variant.fill_color,
                phase_outline_color=scenario_variant.outline_color,
                message="Hermes trägt ein verborgenes Zeichen heran...",
                star_count=0,
            )
            stage_outputs["scenario"] = self._run_llm_stage(
                stage_name="scenario",
                variant_name=scenario_variant.name,
                phase_fill_color=scenario_variant.fill_color,
                phase_outline_color=scenario_variant.outline_color,
                system_prompt=self._build_stage_prompt(
                    stage_name="scenario",
                    stage_variant=scenario_variant,
                    stage_style=prompt_config.scenario.style,
                    persona=persona_profile,
                ),
                user_content=self._scenario_input(
                    user_text,
                    persona_profile,
                    stage_outputs["therapy_plan"],
                ),
                progress=progress,
                temperature=0.55,
            )
            prophecy_variant = self._choose_stage_variant(
                "prophecy",
                prompt_config.prophecy,
                prompt_selector,
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
                stage_name="prophecy",
                stage_variant=prophecy_variant,
                stage_style=prompt_config.prophecy.style,
                persona=persona_profile,
            )
            print(
                "[Prompt] Prophecy style appended: "
                f"style_chars={len(prompt_config.prophecy.style or '')}",
                flush=True,
            )
            stage_outputs["prophecy"] = self._normalize_prophecy_address(
                self._run_llm_stage(
                stage_name="prophecy",
                variant_name=prophecy_variant.name,
                phase_fill_color=prophecy_variant.fill_color,
                phase_outline_color=prophecy_variant.outline_color,
                system_prompt=prophecy_prompt,
                user_content=self._prophecy_input(
                    persona_profile,
                    stage_outputs["therapy_plan"],
                    stage_outputs["scenario"],
                ),
                progress=progress,
                temperature=0.35,
                ),
                persona_profile,
            )
            self._emit_phase_status(
                progress,
                stage_name="spellcheck",
                phase_state="selected",
                variant_name="spellcheck-de",
                phase_fill_color=prophecy_variant.fill_color,
                phase_outline_color=prophecy_variant.outline_color,
                message="Der Spruch wird im letzten Licht geglaettet...",
                star_count=0,
            )
            stage_outputs["spellcheck"] = self._run_llm_stage(
                stage_name="spellcheck",
                variant_name="spellcheck-de",
                phase_fill_color=prophecy_variant.fill_color,
                phase_outline_color=prophecy_variant.outline_color,
                system_prompt=SPELLCHECK_SYSTEM_PROMPT,
                user_content=self._spellcheck_input(stage_outputs["prophecy"]),
                progress=progress,
                temperature=0.0,
            ).strip()
            if progress is not None:
                progress("The card is being written.", 98, 0)

            full_prophecy = stage_outputs["spellcheck"]
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
            self._reset_status_message_cache()
            print("[Pipeline] Prophecy run context reset.", flush=True)

    def _choose_stage_variant(
        self,
        stage_name: str,
        stage: PromptStage,
        prompt_selector: MersenneTwisterPromptSelector,
    ) -> PromptVariant:
        override_name = self._stage_variant_overrides.get(stage_name)
        if override_name is None:
            return prompt_selector.choose(stage_name, stage)

        selected = self._get_variant_by_name(stage, override_name)
        print(
            "[Prompt] FORCED_VARIANT "
            f"stage={stage_name}, "
            f"name={selected.name}, "
            f"weight={selected.weight:g}, "
            f"fill={selected.fill_color}, "
            f"outline={selected.outline_color}",
            flush=True,
        )
        return selected

    def _get_variant_by_name(
        self,
        stage: PromptStage,
        variant_name: str,
    ) -> PromptVariant:
        for variant in stage.variants:
            if variant.name == variant_name:
                return variant

        raise ValueError(f"Unknown prompt variant: {variant_name}")

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

        therapy_plan_variant = prompt_selector.choose(
            "therapy_plan",
            prompt_config.therapy_plan,
        )
        therapy_plan_output = self._run_llm_stage(
            stage_name="therapy_plan",
            variant_name=therapy_plan_variant.name,
            phase_fill_color=therapy_plan_variant.fill_color,
            phase_outline_color=therapy_plan_variant.outline_color,
            system_prompt=self._build_stage_prompt(
                stage_name="therapy_plan",
                stage_variant=therapy_plan_variant,
                stage_style=prompt_config.therapy_plan.style,
                persona=persona_profile,
            ),
            user_content=self._therapy_plan_input(normalized_user_text, persona_profile),
            progress=None,
            temperature=0.25,
            stream_output=stream_output,
        )
        therapy_plan_result = StageRunResult(
            stage_name="therapy_plan",
            variant_name=therapy_plan_variant.name,
            variant_fill_color=therapy_plan_variant.fill_color,
            variant_outline_color=therapy_plan_variant.outline_color,
            variant_weight=therapy_plan_variant.weight,
            output=therapy_plan_output,
        )

        scenario_variant = prompt_selector.choose(
            "scenario",
            prompt_config.scenario,
        )
        scenario_output = self._run_llm_stage(
            stage_name="scenario",
            variant_name=scenario_variant.name,
            phase_fill_color=scenario_variant.fill_color,
            phase_outline_color=scenario_variant.outline_color,
            system_prompt=self._build_stage_prompt(
                stage_name="scenario",
                stage_variant=scenario_variant,
                stage_style=prompt_config.scenario.style,
                persona=persona_profile,
            ),
            user_content=self._scenario_input(
                normalized_user_text,
                persona_profile,
                therapy_plan_result.output,
            ),
            progress=None,
            temperature=0.55,
            stream_output=stream_output,
        )
        scenario_result = StageRunResult(
            stage_name="scenario",
            variant_name=scenario_variant.name,
            variant_fill_color=scenario_variant.fill_color,
            variant_outline_color=scenario_variant.outline_color,
            variant_weight=scenario_variant.weight,
            output=scenario_output,
        )

        prophecy_input = self._prophecy_input(
            persona_profile,
            therapy_plan_result.output,
            scenario_result.output,
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
                    stage_name="prophecy",
                    stage_variant=prophecy_variant,
                    stage_style=prompt_config.prophecy.style,
                    persona=persona_profile,
                ),
                user_content=prophecy_input,
                progress=None,
                temperature=0.35,
                stream_output=stream_output,
            )
            spellchecked_output = self._run_llm_stage(
                stage_name="spellcheck",
                variant_name="spellcheck-de",
                phase_fill_color=prophecy_variant.fill_color,
                phase_outline_color=prophecy_variant.outline_color,
                system_prompt=SPELLCHECK_SYSTEM_PROMPT,
                user_content=self._spellcheck_input(
                    self._normalize_prophecy_address(
                        prophecy_output,
                        persona_profile,
                    )
                ),
                progress=None,
                temperature=0.0,
                stream_output=stream_output,
            )
            prophecy_results.append(
                StageRunResult(
                    stage_name="spellcheck",
                    variant_name=prophecy_variant.name,
                    variant_fill_color=prophecy_variant.fill_color,
                    variant_outline_color=prophecy_variant.outline_color,
                    variant_weight=prophecy_variant.weight,
                    output=spellchecked_output.strip(),
                )
            )

        elapsed = monotonic() - started_at
        print(
            "[PromptTest] Prophecy matrix finished: "
            f"therapy_plan_variant={therapy_plan_result.variant_name}, "
            f"scenario_variant={scenario_result.variant_name}, "
            f"prophecy_variants={len(prophecy_results)}, "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )
        print("[PromptTest] Each prophecy stage used a fresh chat completion.", flush=True)
        return ProphecyMatrixResult(
            question=normalized_user_text,
            therapy_plan=therapy_plan_result,
            scenario=scenario_result,
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
        response_text: str | None = None,
    ) -> None:
        if phase_state == "selected":
            message = self._stage_status_message(stage_name, phase_state)

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
                response_text,
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
        self._answer_star_remainder_by_stage.pop(stage_name, None)
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
                        response_text=f"{full_response}{content}",
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
                response_text=full_response,
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
            response_text=response_text,
        )
        self._answer_star_remainder_by_stage.pop(stage_name, None)
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
        response_text: str | None = None,
    ) -> None:
        star_count = self._scaled_answer_star_count(stage_name, star_count)
        if progress is None:
            return
        if star_count <= 0 and response_text is None:
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
                response_text,
            )
        except TypeError:
            progress(message, progress_value, star_count)

    def _scaled_answer_star_count(self, stage_name: str, star_count: int) -> int:
        if star_count <= 0:
            return 0

        if self._stage_reasoning_enabled(stage_name):
            return star_count

        carry = self._answer_star_remainder_by_stage.get(stage_name, 0.0) + star_count * 0.5
        emitted_stars = int(carry)
        self._answer_star_remainder_by_stage[stage_name] = carry - emitted_stars
        return emitted_stars

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
        cache_key = (stage_name, phase_state)
        cached_message = self._status_message_cache.get(cache_key)
        if cached_message is not None:
            return cached_message

        variants = self._stage_message_variants(stage_name, phase_state)
        if not variants:
            message = "Die Zeichen wandern weiter..."
        else:
            message = random.choice(variants)

        self._status_message_cache[cache_key] = message
        return message

    def _stage_message_variants(
        self,
        stage_name: str,
        phase_state: str,
    ) -> tuple[str, ...]:
        parts = _PHASE_MESSAGE_PARTS.get((stage_name, phase_state))
        if parts is None:
            return ()

        openings, endings = parts
        return tuple(f"{opening} {ending}" for opening in openings for ending in endings)

    def _build_stage_prompt(
        self,
        *,
        stage_name: str,
        stage_variant: PromptVariant,
        stage_style: str | None,
        persona: PersonaProfile,
    ) -> str:
        variant_prompt = stage_variant.prompt
        if stage_name == "prophecy":
            variant_prompt = self._personalize_prophecy_prompt(variant_prompt, persona)

        if stage_style is None or stage_variant.ignore_style:
            return variant_prompt

        return f"{variant_prompt}\n\n{stage_style}"

    def _personalize_prophecy_prompt(
        self,
        prompt: str,
        persona: PersonaProfile,
    ) -> str:
        positive_opening, warning_opening = self._prophecy_openings(persona)
        return (
            prompt.replace("'Suchender, ich sage dir'", f"'{positive_opening}'")
            .replace("Sei gewarnt, Suchender, denn", warning_opening)
            .replace("'Sei gewarnt, Suchender, denn'", f"'{warning_opening}'")
        )

    def _normalize_prophecy_address(
        self,
        prophecy: str,
        persona: PersonaProfile,
    ) -> str:
        positive_opening, warning_opening = self._prophecy_openings(persona)
        normalized = prophecy.strip()

        opening_replacements = {
            "Suchender, ich sage dir": positive_opening,
            "Suchende, ich sage dir": positive_opening,
            "Kind, ich sage dir": positive_opening,
            "mein Sohn, ich sage dir": positive_opening,
            "meine Tochter, ich sage dir": positive_opening,
            "Sei gewarnt, Suchender, denn": warning_opening,
            "Sei gewarnt, Suchende, denn": warning_opening,
            "Sei gewarnt, Kind, denn": warning_opening,
            "Sei gewarnt, mein Sohn, denn": warning_opening,
            "Sei gewarnt, meine Tochter, denn": warning_opening,
        }
        for source, target in opening_replacements.items():
            if normalized.startswith(source):
                return f"{target}{normalized[len(source):]}"

        return normalized

    def _prophecy_openings(self, persona: PersonaProfile) -> tuple[str, str]:
        address = self._prophecy_address(persona)
        return (f"{address}, ich sage dir", f"Sei gewarnt, {address}, denn")

    def _prophecy_address(self, persona: PersonaProfile) -> str:
        if persona.age in {"Kind", "Jugendlicher"}:
            if persona.gender == "m":
                return "mein Sohn"
            if persona.gender == "w":
                return "meine Tochter"
            return "Kind"

        if persona.gender == "w":
            return "Suchende"

        return "Suchender"

    def _therapy_plan_input(self, user_text: str, persona: PersonaProfile) -> str:
        return (
            "Persona JSON:\n"
            f"{persona.as_json()}\n\n"
            "User spoken input:\n"
            "\"\"\"\n"
            f"{user_text.strip()}\n"
            "\"\"\""
        )

    def _scenario_input(
        self,
        user_text: str,
        persona: PersonaProfile,
        therapy_plan: str,
    ) -> str:
        return (
            "Persona JSON:\n"
            f"{persona.as_json()}\n\n"
            "Original user spoken input:\n"
            "\"\"\"\n"
            f"{user_text.strip()}\n"
            "\"\"\"\n\n"
            "Therapy plan from stage A:\n"
            f"{therapy_plan}"
        )

    def _prophecy_input(
        self,
        persona: PersonaProfile,
        therapy_plan: str,
        scenario: str,
    ) -> str:
        return (
            "Persona JSON:\n"
            f"{persona.as_json()}\n\n"
            "JSON-A Therapy Plan:\n"
            f"{therapy_plan}\n\n"
            "JSON-B Scenario:\n"
            f"{scenario}"
        )

    def _spellcheck_input(self, prophecy: str) -> str:
        return prophecy.strip()

    def _reset_status_message_cache(self) -> None:
        self._status_message_cache.clear()

