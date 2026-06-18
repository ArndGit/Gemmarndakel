from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from prompt_loader import PromptConfig, PromptStage, PromptVariant, load_prompt_config


STAGE_SPECS = (
    ("analysis", "Stage A", "Analysis", "#ff8c42"),
    ("recommendation", "Stage B", "Recommendation", "#2ec4b6"),
    ("prophecy", "Stage C", "Prophecy", "#e71d36"),
)


def write_legend_html(config_path: Path, output_path: Path) -> Path:
    prompt_config = load_prompt_config(config_path)
    html = _render_legend_html(prompt_config, config_path)
    output_path.write_text(html, encoding="utf-8")
    print(f"[Legend] Wrote legend HTML: {output_path}", flush=True)
    return output_path


def _render_legend_html(prompt_config: PromptConfig, config_path: Path) -> str:
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    stage_sections = "\n".join(
        _render_stage_section(
            stage_name=stage_name,
            stage_label=stage_label,
            stage_title=stage_title,
            accent_color=accent_color,
            stage=getattr(prompt_config, stage_name),
        )
        for stage_name, stage_label, stage_title, accent_color in STAGE_SPECS
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Prompt Color Legend</title>
  <style>
    :root {{
      --bg-0: #120f1f;
      --bg-1: #1c1630;
      --panel: rgba(15, 17, 35, 0.78);
      --panel-border: rgba(255, 255, 255, 0.1);
      --text: #f8f2ff;
      --muted: #bfb4d6;
      --soft: #8f86aa;
      --line: rgba(255, 255, 255, 0.08);
      --shadow: 0 24px 70px rgba(0, 0, 0, 0.35);
    }}

    * {{
      box-sizing: border-box;
    }}

    html, body {{
      margin: 0;
      min-height: 100%;
    }}

    body {{
      background:
        radial-gradient(circle at top left, rgba(255, 79, 163, 0.18), transparent 34%),
        radial-gradient(circle at top right, rgba(76, 201, 240, 0.14), transparent 30%),
        radial-gradient(circle at bottom center, rgba(233, 196, 106, 0.12), transparent 28%),
        linear-gradient(160deg, var(--bg-0), var(--bg-1) 45%, #120d1e 100%);
      color: var(--text);
      font-family: "Palatino Linotype", Georgia, serif;
      padding: 40px 24px 64px;
    }}

    .page {{
      margin: 0 auto;
      max-width: 1200px;
    }}

    .hero {{
      margin-bottom: 28px;
      padding: 28px 32px;
      background: linear-gradient(160deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.03));
      border: 1px solid var(--panel-border);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}

    .hero p {{
      margin: 0;
    }}

    .eyebrow {{
      color: #ffd166;
      font-size: 0.8rem;
      letter-spacing: 0.22em;
      text-transform: uppercase;
    }}

    .hero h1 {{
      margin: 10px 0 12px;
      font-size: clamp(2.2rem, 4vw, 4rem);
      line-height: 0.95;
      font-weight: 700;
    }}

    .hero-copy {{
      max-width: 72ch;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.6;
    }}

    .meta {{
      margin-top: 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      color: var(--soft);
      font-size: 0.92rem;
    }}

    .meta-chip {{
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}

    .stage-grid {{
      display: grid;
      gap: 22px;
    }}

    .stage-card {{
      background: var(--panel);
      border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--panel-border));
      border-left: 10px solid var(--accent);
      border-radius: 26px;
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(10px);
    }}

    .stage-header {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 16px;
      padding: 22px 24px 18px;
      border-bottom: 1px solid var(--line);
      background:
        linear-gradient(90deg, color-mix(in srgb, var(--accent) 28%, transparent), transparent 60%);
    }}

    .stage-header h2 {{
      margin: 4px 0 0;
      font-size: 1.9rem;
      line-height: 1;
    }}

    .stage-label {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      color: #140f1c;
      background: var(--accent);
      letter-spacing: 0.16em;
      text-transform: uppercase;
      font-size: 0.82rem;
    }}

    .stage-count {{
      color: var(--soft);
      font-size: 0.95rem;
      white-space: nowrap;
    }}

    .table-wrap {{
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
    }}

    thead th {{
      color: var(--soft);
      font-size: 0.78rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      padding: 12px 24px;
      text-align: left;
    }}

    tbody td {{
      padding: 14px 24px;
      border-top: 1px solid var(--line);
      vertical-align: middle;
      font-size: 1rem;
    }}

    tbody tr:hover {{
      background: rgba(255, 255, 255, 0.03);
    }}

    .swatch-cell {{
      width: 110px;
    }}

    .swatch {{
      width: 62px;
      height: 62px;
      border-radius: 18px;
      background: var(--fill);
      border: 8px solid var(--outline);
      box-shadow:
        inset 0 1px 0 rgba(255, 255, 255, 0.22),
        0 12px 24px rgba(0, 0, 0, 0.25);
    }}

    .variant-name {{
      font-size: 1.08rem;
      font-weight: 700;
      color: var(--text);
    }}

    .variant-id {{
      color: var(--soft);
      font-size: 0.92rem;
      font-family: "Consolas", "SFMono-Regular", monospace;
    }}

    .hex {{
      font-family: "Consolas", "SFMono-Regular", monospace;
      color: var(--muted);
    }}

    .pill {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 5px 10px;
      border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(255, 255, 255, 0.05);
      color: var(--muted);
      font-size: 0.9rem;
    }}

    .pill.ignore {{
      color: #120f1f;
      background: #fff1cc;
      border-color: rgba(255, 241, 204, 0.55);
    }}

    @media (max-width: 720px) {{
      body {{
        padding: 22px 14px 36px;
      }}

      .hero,
      .stage-header,
      thead th,
      tbody td {{
        padding-left: 16px;
        padding-right: 16px;
      }}

      .hero h1 {{
        font-size: 2.4rem;
      }}

      .stage-header h2 {{
        font-size: 1.5rem;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <p class="eyebrow">Generated Legend</p>
      <h1>Oracle Color Memory Board</h1>
      <p class="hero-copy">
        This file is overwritten automatically on startup from the active prompt configuration.
        Border color matches the star outline, fill color matches the star body, and each stage uses a stronger accent so the sections stay easy to scan.
      </p>
      <div class="meta">
        <span class="meta-chip">Source: {escape(str(config_path.name))}</span>
        <span class="meta-chip">Generated: {escape(generated_at)}</span>
      </div>
    </section>
    <section class="stage-grid">
      {stage_sections}
    </section>
  </main>
</body>
</html>
"""


def _render_stage_section(
    *,
    stage_name: str,
    stage_label: str,
    stage_title: str,
    accent_color: str,
    stage: PromptStage,
) -> str:
    total_weight = sum(variant.weight for variant in stage.variants)
    rows = "\n".join(
        _render_variant_row(stage_name, variant, total_weight)
        for variant in sorted(stage.variants, key=lambda item: _short_name(item.name).lower())
    )
    return f"""
<section class="stage-card" style="--accent: {escape(accent_color)}">
  <div class="stage-header">
    <div>
      <div class="stage-label">{escape(stage_label)}</div>
      <h2>{escape(stage_title)}</h2>
    </div>
    <div class="stage-count">{len(stage.variants)} variants · total weight {total_weight:g}</div>
  </div>
  <div class="table-wrap">
    <table aria-label="{escape(stage_title)} variant legend">
      <thead>
        <tr>
          <th class="swatch-cell">Color</th>
          <th>Name</th>
          <th>Variant Id</th>
          <th>Fill</th>
          <th>Outline</th>
          <th>Weight</th>
          <th>Probability</th>
          <th>Style</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>
</section>
""".strip()


def _render_variant_row(
    stage_name: str,
    variant: PromptVariant,
    total_weight: float,
) -> str:
    short_name = _short_name(variant.name)
    probability = _selection_probability(variant.weight, total_weight)
    if stage_name == "prophecy":
        style_pill = (
            '<span class="pill ignore">Ignore style</span>'
            if variant.ignore_style
            else '<span class="pill">Use style</span>'
        )
    else:
        style_pill = '<span class="pill">n/a</span>'

    return f"""
<tr>
  <td class="swatch-cell"><div class="swatch" style="--fill: {escape(variant.fill_color)}; --outline: {escape(variant.outline_color)}"></div></td>
  <td><div class="variant-name">{escape(short_name)}</div></td>
  <td><div class="variant-id">{escape(variant.name)}</div></td>
  <td><span class="hex">{escape(variant.fill_color.upper())}</span></td>
  <td><span class="hex">{escape(variant.outline_color.upper())}</span></td>
  <td><span class="hex">{variant.weight:g}</span></td>
  <td><span class="hex">{_format_probability(probability)}</span></td>
  <td>{style_pill}</td>
</tr>
""".strip()


def _short_name(name: str) -> str:
    prefix, separator, remainder = name.partition("-")
    base_name = remainder if separator else prefix
    words = [word.capitalize() for word in base_name.split("-") if word]
    return " ".join(words) or name


def _selection_probability(weight: float, total_weight: float) -> float:
    if total_weight <= 0:
        return 0.0

    return weight / total_weight


def _format_probability(probability: float) -> str:
    return f"{probability * 100:.2f}%"
