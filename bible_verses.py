from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re


BIBLE_VERSE_PROPHECY_VARIANT_NAME = "c-bible-verse"
DATA_FILE = Path(__file__).resolve().parent / "data" / "bible_lut1912.json"
_REFERENCE_PATTERN = re.compile(
    r"(?P<book>.+?)\s+(?P<chapter>\d+)\s*[:.,]\s*(?P<verse>\d+)",
    re.DOTALL,
)
_CURATED_VERSE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Trost in der Unruhe", "Psalmen 23:1"),
    ("Schutz auf dunklem Weg", "Psalmen 91:11"),
    ("Warten und Staerke", "Jesaja 40:31"),
    ("Vertrauen statt Selbstsorge", "Sprüche 3:5"),
    ("Gerader Pfad", "Sprüche 3:6"),
    ("Furcht weicht", "Jesaja 41:10"),
    ("Nicht entmutigen", "Josua 1:9"),
    ("Heilung des gebrochenen Herzens", "Psalmen 147:3"),
    ("Getragene Last", "Matthäus 11:28"),
    ("Friede fuer das Herz", "Johannes 14:27"),
    ("Liebe statt Angst", "1. Johannes 4:18"),
    ("Bewahrung der Gedanken", "Philipper 4:7"),
    ("Alles pruefen", "1. Thessalonicher 5:21"),
    ("Geduld in trueber Stunde", "Römer 12:12"),
    ("Mut zur Sanftmut", "Matthäus 5:9"),
    ("Saat und Ernte", "Galater 6:7"),
    ("Treue im Kleinen", "Lukas 16:10"),
    ("Zeit fuer alles", "Prediger 3:1"),
)


def build_bible_verse_prompt(prompt: str) -> str:
    option_lines = "\n".join(
        f"- {theme}: {reference}"
        for theme, reference in _CURATED_VERSE_OPTIONS
    )
    appendix = (
        "Use the local Luther 1912 verse catalog instead of memory.\n"
        "Choose exactly one verse key from the curated options below.\n"
        "Use the first fitting option and stop. A rough theme match is enough.\n"
        "Do not quote, reconstruct, or paraphrase any verse text.\n"
        "Output only the reference in the format <book> <chapter>:<verse>.\n"
        "Allowed options:\n"
        f"{option_lines}"
    )
    return f"{prompt}\n\n{appendix}"


def resolve_bible_verse_reference(raw_output: str) -> str:
    reference = extract_bible_reference(raw_output)
    catalog = load_bible_verse_catalog()
    verse_text = catalog["verse_index"].get(reference)
    if verse_text is None:
        raise ValueError(f"Unknown Bible verse reference: {reference}")
    return f"{verse_text} — {reference}"


def extract_bible_reference(raw_output: str) -> str:
    cleaned = raw_output.strip()
    cleaned = cleaned.strip("`*_\"' \t\r\n")
    if "\n" in cleaned:
        cleaned = cleaned.splitlines()[0].strip()
    cleaned = cleaned.rstrip(".,;:!?-–—")

    direct_reference = _normalize_reference(cleaned)
    catalog = load_bible_verse_catalog()
    if direct_reference in catalog["verse_index"]:
        return direct_reference

    for match in _REFERENCE_PATTERN.finditer(cleaned):
        parsed_reference = _normalize_reference(
            (
                f"{match.group('book')} "
                f"{match.group('chapter')}:{match.group('verse')}"
            )
        )
        if parsed_reference in catalog["verse_index"]:
            return parsed_reference

        book_tokens = match.group("book").split()
        for start_index in range(1, len(book_tokens)):
            shortened_reference = _normalize_reference(
                (
                    f"{' '.join(book_tokens[start_index:])} "
                    f"{match.group('chapter')}:{match.group('verse')}"
                )
            )
            if shortened_reference in catalog["verse_index"]:
                return shortened_reference

    raise ValueError("Bible verse response did not contain a known verse reference.")


def _normalize_reference(reference: str) -> str:
    compact = " ".join(reference.replace("\xa0", " ").split())
    match = re.fullmatch(r"(.+?)\s+(\d+)\s*[:.,]\s*(\d+)", compact)
    if match is None:
        return compact

    book = _normalize_book_name(match.group(1))
    chapter = int(match.group(2))
    verse = int(match.group(3))
    return f"{book} {chapter}:{verse}"


def _normalize_book_name(book: str) -> str:
    normalized = " ".join(book.split())
    numbered_match = re.fullmatch(r"([1-3])\.?\s+(.+)", normalized)
    if numbered_match is not None:
        normalized = f"{numbered_match.group(1)}. {numbered_match.group(2)}"

    aliases = {
        "psalm": "Psalmen",
        "koenige": "Könige",
        "konige": "Könige",
        "sprueche": "Sprüche",
        "spruche": "Sprüche",
        "matthaeus": "Matthäus",
        "matthaus": "Matthäus",
        "roemer": "Römer",
        "romer": "Römer",
        "hebraeer": "Hebräer",
        "hebraer": "Hebräer",
    }
    if normalized.casefold() in aliases:
        return aliases[normalized.casefold()]
    return normalized


@lru_cache(maxsize=1)
def load_bible_verse_catalog() -> dict:
    with DATA_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)
