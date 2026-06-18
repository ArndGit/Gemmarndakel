from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Sequence

from legend_generator import write_legend_html
from oracle_client import ProphecyMatrixResult, OracleClient
from settings import load_settings


DEFAULT_OUTPUT_FILE = "prompt_test_results.csv"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the oracle prompt pipeline directly: pick one weighted analysis "
            "variant, pick one weighted recommendation variant, then run every "
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
        help="Optional RNG seed for reproducible weighted A/B variant selection.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Stream reasoning and answer tokens for each stage to stdout.",
    )
    return parser.parse_args(argv)


def _csv_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def _write_csv(path: Path, result: ProphecyMatrixResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "question",
                "analysis_variant",
                "analysis_fill_color",
                "analysis_outline_color",
                "analysis_weight",
                "recommendation_variant",
                "recommendation_fill_color",
                "recommendation_outline_color",
                "recommendation_weight",
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
                    "analysis_variant": result.analysis.variant_name,
                    "analysis_fill_color": result.analysis.variant_fill_color,
                    "analysis_outline_color": result.analysis.variant_outline_color,
                    "analysis_weight": result.analysis.variant_weight,
                    "recommendation_variant": result.recommendation.variant_name,
                    "recommendation_fill_color": result.recommendation.variant_fill_color,
                    "recommendation_outline_color": result.recommendation.variant_outline_color,
                    "recommendation_weight": result.recommendation.variant_weight,
                    "prophecy_variant": prophecy.variant_name,
                    "prophecy_fill_color": prophecy.variant_fill_color,
                    "prophecy_outline_color": prophecy.variant_outline_color,
                    "prophecy_weight": prophecy.variant_weight,
                    "answer_text": _csv_text(prophecy.output),
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
    result = oracle.create_prophecy_matrix(
        question,
        seed=args.seed,
        stream_output=args.verbose,
    )

    output_path = args.output.expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    _write_csv(output_path, result)

    print(f"[PromptTest] Question: {result.question}", flush=True)
    print(
        "[PromptTest] Picked analysis variant: "
        f"{result.analysis.variant_name} "
        f"(weight={result.analysis.variant_weight:g}, "
        f"fill={result.analysis.variant_fill_color}, "
        f"outline={result.analysis.variant_outline_color})",
        flush=True,
    )
    print(
        "[PromptTest] Picked recommendation variant: "
        f"{result.recommendation.variant_name} "
        f"(weight={result.recommendation.variant_weight:g}, "
        f"fill={result.recommendation.variant_fill_color}, "
        f"outline={result.recommendation.variant_outline_color})",
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
