from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


BASE_DIR = Path(__file__).resolve().parent
TAROT_DIR = BASE_DIR / "tarot"
TAROT_CARD_BORDER_FILENAME = "cardBorder.png"
TAROT_CARD_BACK_FILENAME = "CardBacks.png"
_EXCLUDED_FILENAMES = {TAROT_CARD_BORDER_FILENAME, TAROT_CARD_BACK_FILENAME}

_MINOR_SUIT_LABELS = {
    "Cups": "Cups",
    "Pentacles": "Pentacles",
    "Swords": "Swords",
    "Wands": "Wands",
}
_MINOR_SUIT_MOTIFS = {
    "Cups": "emotion, relationships, intuition",
    "Pentacles": "work, body, money, stability",
    "Swords": "thought, conflict, truth, decision",
    "Wands": "will, action, growth, risk",
}
_MINOR_RANK_TITLES = {
    1: "Ace",
    2: "Two",
    3: "Three",
    4: "Four",
    5: "Five",
    6: "Six",
    7: "Seven",
    8: "Eight",
    9: "Nine",
    10: "Ten",
    11: "Page",
    12: "Knight",
    13: "Queen",
    14: "King",
}
_MINOR_RANK_MOTIFS = {
    1: "a new opening",
    2: "balance or division",
    3: "growth taking form",
    4: "stability and holding",
    5: "strain, lack, or conflict",
    6: "passage, exchange, or relief",
    7: "trial, doubt, or persistence",
    8: "movement, effort, or narrowing focus",
    9: "near-fulfillment or solitary intensity",
    10: "completion, burden, or overflow",
    11: "a message, student, or first stirrings",
    12: "forward drive, pursuit, or pressure",
    13: "inner mastery, care, or composure",
    14: "authority, command, or mature control",
}
_MAJOR_TITLE_MOTIFS = {
    "The Fool": "innocence, risk, and the first step",
    "The Magician": "focus, skill, and directed will",
    "The High Priestess": "intuition, secrecy, and still knowledge",
    "The Empress": "fertility, nurture, and abundance",
    "The Emperor": "order, rule, and structure",
    "The Hierophant": "tradition, ritual, and inherited wisdom",
    "The Lovers": "bond, choice, and joined destiny",
    "The Chariot": "control, momentum, and determination",
    "Strength": "courage, restraint, and calm power",
    "The Hermit": "withdrawal, searching, and the lantern of truth",
    "Wheel Of Fortune": "turning cycles, fate, and reversal",
    "Justice": "truth, consequence, and balance",
    "The Hanged Man": "delay, surrender, and altered sight",
    "Death": "ending, release, and transformation",
    "Temperance": "measure, blending, and healing balance",
    "The Devil": "bondage, hunger, and temptation",
    "The Tower": "shock, collapse, and sudden revelation",
    "The Star": "hope, renewal, and distant guidance",
    "The Moon": "uncertainty, dream, and the hidden path",
    "The Sun": "clarity, warmth, and joyful exposure",
    "Judgement": "reckoning, awakening, and return",
    "The World": "completion, wholeness, and arrival",
}


@dataclass(frozen=True)
class TarotCardAsset:
    filename: str
    title: str
    motif: str


def load_tarot_card_assets() -> tuple[TarotCardAsset, ...]:
    if not TAROT_DIR.exists():
        return ()

    cards: list[TarotCardAsset] = []
    for path in sorted(TAROT_DIR.glob("*.png")):
        if path.name in _EXCLUDED_FILENAMES:
            continue
        cards.append(TarotCardAsset(path.name, _derive_title(path.stem), _derive_motif(path.stem)))

    return tuple(cards)


def tarot_card_lookup() -> dict[str, TarotCardAsset]:
    return {card.filename: card for card in load_tarot_card_assets()}


def tarot_card_asset_path(filename: str) -> Path:
    return TAROT_DIR / filename


def build_tarot_card_catalog_prompt() -> str:
    cards = load_tarot_card_assets()
    if not cards:
        raise FileNotFoundError(f"No tarot card assets found in {TAROT_DIR}")

    lines = [
        "Allowed tarot card catalog. Use only these exact filenames and matching titles.",
    ]
    for card in cards:
        lines.append(f'- "{card.filename}" | {card.title} | {card.motif}')

    return "\n".join(lines)


def _derive_title(stem: str) -> str:
    minor_match = re.fullmatch(r"(Cups|Pentacles|Swords|Wands)(\d{2})", stem)
    if minor_match is not None:
        suit = minor_match.group(1)
        rank = int(minor_match.group(2))
        rank_title = _MINOR_RANK_TITLES.get(rank, str(rank))
        return f"{rank_title} of {_MINOR_SUIT_LABELS[suit]}"

    major_name = re.sub(r"^\d{2}-", "", stem)
    words = re.findall(r"[A-Z][a-z]*|[A-Z]+(?![a-z])|\d+", major_name)
    title = " ".join(words).strip()
    return title or stem


def _derive_motif(stem: str) -> str:
    minor_match = re.fullmatch(r"(Cups|Pentacles|Swords|Wands)(\d{2})", stem)
    if minor_match is not None:
        suit = minor_match.group(1)
        rank = int(minor_match.group(2))
        rank_motif = _MINOR_RANK_MOTIFS.get(rank, "a turning point")
        suit_motif = _MINOR_SUIT_MOTIFS[suit]
        return f"{rank_motif}; sphere of {suit_motif}"

    title = _derive_title(stem)
    major_motif = _MAJOR_TITLE_MOTIFS.get(title)
    if major_motif is not None:
        return f"major arcana of {major_motif}"

    return f"major arcana archetype around {title.lower()}"
