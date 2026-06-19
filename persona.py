from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from threading import Event, Lock, Thread
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any

from openai import OpenAI

if TYPE_CHECKING:
    from settings import AppSettings


CAPTURE_INTERVAL_SECONDS = 1.0
MAX_CAPTURED_FRAMES = 12


@dataclass(frozen=True)
class PersonaProfile:
    age: str = "unknown"
    gender: str = "unknown"
    mood: str = "unknown"

    @classmethod
    def unknown(cls) -> PersonaProfile:
        return cls()

    @classmethod
    def from_llm_payload(cls, payload: Any) -> PersonaProfile:
        if not isinstance(payload, dict):
            return cls.unknown()

        persona = payload.get("persona")
        if not isinstance(persona, dict):
            return cls.unknown()

        return cls(
            age=cls._normalize_age(persona.get("age")),
            gender=cls._normalize_gender(persona.get("gender")),
            mood=cls._normalize_mood(persona.get("mood")),
        )

    def as_payload(self) -> dict[str, dict[str, str]]:
        return {
            "persona": {
                "age": self.age,
                "gender": self.gender,
                "mood": self.mood,
            }
        }

    def as_json(self) -> str:
        return json.dumps(self.as_payload(), ensure_ascii=True, separators=(",", ":"))

    @staticmethod
    def _normalize_age(value: Any) -> str:
        if not isinstance(value, str):
            return "unknown"

        normalized = value.strip().lower()
        mapping = {
            "adult": "Erwachsener",
            "child": "Kind",
            "erwachsener": "Erwachsener",
            "jugendlicher": "Jugendlicher",
            "kind": "Kind",
            "rentner": "Rentner",
            "retiree": "Rentner",
            "senior": "Rentner",
            "teen": "Jugendlicher",
            "teenager": "Jugendlicher",
            "unbekannt": "unknown",
            "unknown": "unknown",
        }
        return mapping.get(normalized, "unknown")

    @staticmethod
    def _normalize_gender(value: Any) -> str:
        if not isinstance(value, str):
            return "unknown"

        normalized = value.strip().lower()
        if normalized in {"m", "male", "mann"}:
            return "m"
        if normalized in {"f", "female", "frau", "w"}:
            return "w"
        return "unknown"

    @staticmethod
    def _normalize_mood(value: Any) -> str:
        if not isinstance(value, str):
            return "unknown"

        normalized = value.strip().lower()
        if not normalized or normalized in {"unbekannt", "unknown"}:
            return "unknown"

        aliases = {
            "angry": "wuetend",
            "anxious": "nervoes",
            "calm": "ruhig",
            "confused": "verwirrt",
            "exhausted": "erschopft",
            "fatigued": "erschopft",
            "happy": "freudig",
            "irritated": "gereizt",
            "melancholic": "melancholisch",
            "nervous": "nervoes",
            "neutral": "neutral",
            "relieved": "erleichtert",
            "sad": "traurig",
            "serious": "ernst",
            "tense": "angespannt",
            "thoughtful": "nachdenklich",
            "worried": "besorgt",
        }
        return aliases.get(normalized, normalized[:32])


@dataclass(frozen=True)
class _CapturedFrame:
    offset_seconds: float
    jpeg_bytes: bytes


class PersonaCaptureSession:
    def __init__(self, analyzer: PersonaCameraAnalyzer) -> None:
        self._analyzer = analyzer
        self._stop_event = Event()
        self._frames: list[_CapturedFrame] = []
        self._frames_lock = Lock()
        self._thread = Thread(target=self._capture_loop, daemon=True)
        self._started_at = monotonic()
        self._camera_opened = False
        self._capture_error: str | None = None

    def start(self) -> None:
        self._thread.start()

    def finish(self) -> PersonaProfile:
        self._stop_event.set()
        self._thread.join()
        return self._analyzer.analyze_captured_frames(
            self._snapshot_frames(),
            camera_opened=self._camera_opened,
            capture_error=self._capture_error,
        )

    def _snapshot_frames(self) -> list[_CapturedFrame]:
        with self._frames_lock:
            return list(self._frames)

    def _capture_loop(self) -> None:
        if self._analyzer.settings.persona_camera_device_index < 0:
            self._capture_error = "invalid device index"
            print("[Camera] Persona capture not configured: invalid device index.", flush=True)
            return

        try:
            import cv2
        except ImportError:
            self._capture_error = "opencv missing"
            print("[Camera] OpenCV is not installed; persona capture unavailable.", flush=True)
            return

        backend = cv2.CAP_ANY
        if os.name == "nt" and hasattr(cv2, "CAP_DSHOW"):
            backend = cv2.CAP_DSHOW

        print(
            "[Camera] Opening default camera for in-memory sampling: "
            f"device_index={self._analyzer.settings.persona_camera_device_index}",
            flush=True,
        )
        camera = cv2.VideoCapture(
            self._analyzer.settings.persona_camera_device_index,
            backend,
        )
        if not camera.isOpened():
            self._capture_error = "camera unavailable"
            print("[Camera] No camera available or device could not be opened.", flush=True)
            camera.release()
            return

        self._camera_opened = True
        next_capture_at = monotonic()
        try:
            while not self._stop_event.is_set():
                ok, frame = camera.read()
                now = monotonic()
                if ok and frame is not None and now >= next_capture_at:
                    ok_encode, encoded = cv2.imencode(".jpg", frame)
                    if ok_encode:
                        with self._frames_lock:
                            self._frames.append(
                                _CapturedFrame(
                                    offset_seconds=now - self._started_at,
                                    jpeg_bytes=encoded.tobytes(),
                                )
                            )
                            if len(self._frames) > MAX_CAPTURED_FRAMES:
                                self._frames.pop(0)
                        print(
                            "[Camera] Sampled in-memory frame during speech: "
                            f"t={now - self._started_at:.1f}s, frames={len(self._frames)}",
                            flush=True,
                        )
                    next_capture_at = now + CAPTURE_INTERVAL_SECONDS
                sleep(0.05)
        finally:
            camera.release()
            print("[Camera] In-memory speech capture session closed.", flush=True)


class PersonaCameraAnalyzer:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._client = OpenAI(
            base_url=settings.lm_studio_url,
            api_key=settings.llm_api_key or "lm-studio",
            timeout=settings.llm_timeout_seconds,
        )
        self._model_id = settings.persona_model or settings.llm_model

    @property
    def settings(self) -> AppSettings:
        return self._settings

    def start_capture_session(self) -> PersonaCaptureSession | None:
        if not self._settings.persona_camera_enabled:
            print("[Camera] Persona capture disabled by config.", flush=True)
            return None

        session = PersonaCaptureSession(self)
        session.start()
        return session

    def analyze_captured_frames(
        self,
        frames: list[_CapturedFrame],
        *,
        camera_opened: bool,
        capture_error: str | None,
    ) -> PersonaProfile:
        if not camera_opened:
            if capture_error:
                print(f"[Camera] Persona capture unavailable: {capture_error}.", flush=True)
            return PersonaProfile.unknown()

        if not frames:
            print("[Camera] Camera session finished without any sampled frame.", flush=True)
            return PersonaProfile.unknown()

        candidate_frames = self._select_candidate_frames(frames)
        print(
            "[Camera] Sending sampled frames to local LLM for persona analysis: "
            f"model={self._model_id}, sampled={len(frames)}, candidates={len(candidate_frames)}",
            flush=True,
        )
        try:
            response = self._client.chat.completions.create(
                model=self._model_id,
                temperature=0.0,
                timeout=self._settings.llm_generation_timeout_seconds,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Analyze sequential webcam frames of exactly one person speaking. "
                            "Prefer a frame from the temporal middle of the sequence. "
                            "If the exact middle frame is blurry, turned away, or expressionless while a nearby frame is clearer, choose the nearest clearer frame. "
                            "Be sensitive to subtle facial affect such as sadness, tension, fatigue, worry, irritation, shyness, relief, or joy. "
                            "Do not default to neutral unless the visible expression is genuinely unreadable or plainly neutral across the frames. "
                            "Estimate only visible surface traits. If uncertain, return unknown. "
                            "Output only compact JSON in this exact shape: "
                            '{"selected_frame":1,"persona":{"age":"unknown|Kind|Jugendlicher|Erwachsener|Rentner","gender":"unknown|m|w","mood":"unknown|neutral|traurig|besorgt|angespannt|nervoes|gereizt|erschopft|ernst|nachdenklich|ruhig|freudig|erleichtert|verwirrt|melancholisch"}}. '
                            "Do not add any extra keys or text."
                        ),
                    },
                    {
                        "role": "user",
                        "content": self._build_multi_frame_prompt(candidate_frames),
                    },
                ],
            )
        except Exception as exc:
            print(f"[Camera] Persona analysis failed: {exc!r}", flush=True)
            return PersonaProfile.unknown()

        response_text = self._extract_response_text(response)
        if not response_text:
            print("[Camera] Persona analysis returned empty content.", flush=True)
            return PersonaProfile.unknown()

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            print(
                "[Camera] Persona analysis returned invalid JSON: "
                f"{exc!r}, content={response_text!r}",
                flush=True,
            )
            return PersonaProfile.unknown()

        persona = PersonaProfile.from_llm_payload(payload)
        print(f"[Camera] Persona result: {persona.as_json()}", flush=True)
        return persona

    def _select_candidate_frames(
        self,
        frames: list[_CapturedFrame],
    ) -> list[_CapturedFrame]:
        midpoint = frames[-1].offset_seconds / 2.0
        sorted_candidates = sorted(
            frames,
            key=lambda frame: (abs(frame.offset_seconds - midpoint), frame.offset_seconds),
        )
        chosen = sorted(sorted_candidates[:3], key=lambda frame: frame.offset_seconds)
        return chosen

    def _build_multi_frame_prompt(
        self,
        frames: list[_CapturedFrame],
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "These are sequential speech-time webcam frames of the same person. "
                    "Choose the best frame near the middle that reveals age, gender, and especially mood most clearly. "
                    "Return the JSON only."
                ),
            }
        ]
        for index, frame in enumerate(frames, start=1):
            content.append(
                {
                    "type": "text",
                    "text": f"Frame {index}, captured at {frame.offset_seconds:.1f} seconds.",
                }
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            "data:image/jpeg;base64,"
                            + base64.b64encode(frame.jpeg_bytes).decode("ascii")
                        )
                    },
                }
            )
        return content

    def _extract_response_text(self, response: Any) -> str:
        choices = getattr(response, "choices", None)
        if not choices:
            return ""

        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                else:
                    text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts).strip()

        return ""
