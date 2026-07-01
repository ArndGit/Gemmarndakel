from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from time import sleep
from typing import Sequence

from legend_generator import write_legend_html
from oracle_client import ProphecyMatrixResult, OracleClient
from settings import AppSettings
from persona import PersonaCameraAnalyzer, PersonaProfile
from settings import load_settings


DEFAULT_OUTPUT_FILE = "prompt_test_results.csv"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the oracle prompt pipeline directly: pick one weighted therapy-plan "
            "variant, pick one weighted scenario variant, then run every "
            "prophecy variant and export the results to CSV."
        )
    )
    parser.add_argument(
        "--question",
        help="Override the question from settings.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(DEFAULT_OUTPUT_FILE),
        help=f"CSV output path. Default: {DEFAULT_OUTPUT_FILE}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Optional RNG seed for reproducible weighted Stage A/B variant selection.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Stream reasoning and answer tokens for each stage to stdout.",
    )
    return parser.parse_args(argv)


def _csv_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def _compact_tarot_output(value: str) -> str:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return value

    if not isinstance(payload, dict) or payload.get("mode") != "tarot_card":
        return value

    selected_cards: list[str] = []
    for position in ("past", "present", "future"):
        slot = payload.get(position)
        if not isinstance(slot, dict):
            continue
        title = slot.get("title")
        filename = slot.get("filename")
        if isinstance(title, str) and title.strip():
            selected_cards.append(title.strip())
        elif isinstance(filename, str) and filename.strip():
            selected_cards.append(filename.strip())

    return " | ".join(selected_cards) if selected_cards else value


def _capture_test_persona(settings: AppSettings) -> PersonaProfile:
    analyzer = PersonaCameraAnalyzer(settings)
    session = analyzer.start_capture_session()
    if session is None:
        return PersonaProfile.unknown()

    print(
        "[PromptTest] Sampling persona from camera once before matrix run: "
        f"timeout={settings.persona_capture_timeout_seconds}s",
        flush=True,
    )
    sleep(settings.persona_capture_timeout_seconds)
    persona = session.finish()
    print(f"[PromptTest] Persona for test run: {persona.as_json()}", flush=True)
    return persona


def _write_csv(path: Path, result: ProphecyMatrixResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "question",
                "therapy_plan_variant",
                "therapy_plan_fill_color",
                "therapy_plan_outline_color",
                "therapy_plan_weight",
                "scenario_variant",
                "scenario_fill_color",
                "scenario_outline_color",
                "scenario_weight",
                "prophecy_variant",
                "prophecy_fill_color",
                "prophecy_outline_color",
                "prophecy_weight",
                "answer_text",
            ],
        )
        writer.writeheader()
        for prophecy in result.prophecies:
            writer.writerow(
                {
                    "question": _csv_text(result.question),
                    "therapy_plan_variant": result.therapy_plan.variant_name,
                    "therapy_plan_fill_color": result.therapy_plan.variant_fill_color,
                    "therapy_plan_outline_color": result.therapy_plan.variant_outline_color,
                    "therapy_plan_weight": result.therapy_plan.variant_weight,
                    "scenario_variant": result.scenario.variant_name,
                    "scenario_fill_color": result.scenario.variant_fill_color,
                    "scenario_outline_color": result.scenario.variant_outline_color,
                    "scenario_weight": result.scenario.variant_weight,
                    "prophecy_variant": prophecy.variant_name,
                    "prophecy_fill_color": prophecy.variant_fill_color,
                    "prophecy_outline_color": prophecy.variant_outline_color,
                    "prophecy_weight": prophecy.variant_weight,
                    "answer_text": _csv_text(_compact_tarot_output(prophecy.output)),
                }
            )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings()
    write_legend_html(
        settings.prompt_config_file,
        settings.prompt_config_file.resolve().with_name("legend.html"),
    )
    question = (args.question or settings.prompt_test_question).strip()
    if not question:
        raise SystemExit("Prompt test question must not be empty.")

    oracle = OracleClient(settings)
    oracle.check_connection()
    persona = _capture_test_persona(settings)
    result = oracle.create_prophecy_matrix(
        question,
        persona=persona,
        seed=args.seed,
        stream_output=args.verbose,
    )

    output_path = args.output.expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    _write_csv(output_path, result)

    print(f"[PromptTest] Question: {result.question}", flush=True)
    print(
        "[PromptTest] Picked therapy-plan variant: "
        f"{result.therapy_plan.variant_name} "
        f"(weight={result.therapy_plan.variant_weight:g}, "
        f"fill={result.therapy_plan.variant_fill_color}, "
        f"outline={result.therapy_plan.variant_outline_color})",
        flush=True,
    )
    print(
        "[PromptTest] Picked scenario variant: "
        f"{result.scenario.variant_name} "
        f"(weight={result.scenario.variant_weight:g}, "
        f"fill={result.scenario.variant_fill_color}, "
        f"outline={result.scenario.variant_outline_color})",
        flush=True,
    )
    print(
        "[PromptTest] Exported prophecy rows: "
        f"{len(result.prophecies)} -> {output_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
