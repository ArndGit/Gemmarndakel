from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class PromptVariant:
    name: str
    fill_color: str
    outline_color: str
    weight: float
    prompt: str
    ignore_style: bool = False


@dataclass(frozen=True)
class PromptStage:
    variants: tuple[PromptVariant, ...]
    style: str | None = None


@dataclass(frozen=True)
class PromptConfig:
    analysis: PromptStage
    recommendation: PromptStage
    prophecy: PromptStage


PROMPT_STAGE_NAMES = ( "analysis", "recommendation", "prophecy")


def load_prompt_config(path: Path) -> PromptConfig:
    if not path.exists():
        raise FileNotFoundError(f"Prompt config file not found: {path}")

    try:
        raw_config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Prompt config is not valid JSON: {path}") from exc

    if not isinstance(raw_config, dict):
        raise ValueError(f"Prompt config root must be a JSON object: {path}")

    unknown_keys = sorted(set(raw_config) - set(PROMPT_STAGE_NAMES))
    if unknown_keys:
        joined_keys = ", ".join(unknown_keys)
        raise ValueError(f"Prompt config contains unknown root keys: {joined_keys}")

    missing_keys = [name for name in PROMPT_STAGE_NAMES if name not in raw_config]
    if missing_keys:
        joined_keys = ", ".join(missing_keys)
        raise ValueError(f"Prompt config is missing root keys: {joined_keys}")

    return PromptConfig(
 
        analysis=_read_stage(raw_config["analysis"], "analysis", require_style=False),
        recommendation=_read_stage(
            raw_config["recommendation"],
            "recommendation",
            require_style=False,
        ),
        prophecy=_read_stage(raw_config["prophecy"], "prophecy", require_style=True),
    )


def _read_stage(raw_stage: Any, stage_name: str, require_style: bool) -> PromptStage:
    if not isinstance(raw_stage, dict):
        raise ValueError(f"Prompt stage '{stage_name}' must be a JSON object.")

    allowed_keys = {"variants", "style"}
    unknown_keys = sorted(set(raw_stage) - allowed_keys)
    if unknown_keys:
        joined_keys = ", ".join(unknown_keys)
        raise ValueError(
            f"Prompt stage '{stage_name}' contains unknown keys: {joined_keys}"
        )

    raw_variants = raw_stage.get("variants")
    if not isinstance(raw_variants, list) or not raw_variants:
        raise ValueError(
            f"Prompt stage '{stage_name}' must define a non-empty variants array."
        )

    style = raw_stage.get("style")
    if style is not None:
        if not isinstance(style, str) or not style.strip():
            raise ValueError(
                f"Prompt stage '{stage_name}' style must be a non-empty string."
            )
        style = style.strip()

    if require_style and style is None:
        raise ValueError(f"Prompt stage '{stage_name}' must define a style string.")

    variants = tuple(
        _read_variant(raw_variant, f"{stage_name}.variants[{index}]")
        for index, raw_variant in enumerate(raw_variants)
    )
    return PromptStage(variants=variants, style=style)


def _read_variant(raw_variant: Any, location: str) -> PromptVariant:
    if not isinstance(raw_variant, dict):
        raise ValueError(f"{location} must be a JSON object.")

    allowed_keys = {
        "name",
        "color",
        "fill_color",
        "outline_color",
        "weight",
        "prompt",
        "ignore_style",
    }
    unknown_keys = sorted(set(raw_variant) - allowed_keys)
    if unknown_keys:
        joined_keys = ", ".join(unknown_keys)
        raise ValueError(f"{location} contains unknown keys: {joined_keys}")

    name = raw_variant.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{location}.name must be a non-empty string.")

    fill_color = raw_variant.get("fill_color", raw_variant.get("color"))
    if not isinstance(fill_color, str) or not re.fullmatch(
        r"#[0-9a-fA-F]{6}",
        fill_color.strip(),
    ):
        raise ValueError(
            f"{location}.fill_color must be an HTML color like #7cc7ff."
        )
    fill_color = fill_color.strip()

    outline_color = raw_variant.get("outline_color")
    if outline_color is None:
        outline_color = _derive_outline_color(fill_color)
    if not isinstance(outline_color, str) or not re.fullmatch(
        r"#[0-9a-fA-F]{6}",
        outline_color.strip(),
    ):
        raise ValueError(
            f"{location}.outline_color must be an HTML color like #7cc7ff."
        )
    outline_color = outline_color.strip()

    weight = raw_variant.get("weight")
    if isinstance(weight, bool) or not isinstance(weight, int | float):
        raise ValueError(f"{location}.weight must be a positive number.")
    if weight <= 0:
        raise ValueError(f"{location}.weight must be greater than zero.")

    prompt = raw_variant.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"{location}.prompt must be a non-empty string.")

    ignore_style = raw_variant.get("ignore_style", False)
    if not isinstance(ignore_style, bool):
        raise ValueError(f"{location}.ignore_style must be a boolean.")

    return PromptVariant(
        name=name.strip(),
        fill_color=fill_color,
        outline_color=outline_color,
        weight=float(weight),
        prompt=prompt.strip(),
        ignore_style=ignore_style,
    )


def _derive_outline_color(fill_color: str) -> str:
    red = int(fill_color[1:3], 16)
    green = int(fill_color[3:5], 16)
    blue = int(fill_color[5:7], 16)
    return "#{:02x}{:02x}{:02x}".format(
        max(0, int(red * 0.55)),
        max(0, int(green * 0.55)),
        max(0, int(blue * 0.55)),
    )
