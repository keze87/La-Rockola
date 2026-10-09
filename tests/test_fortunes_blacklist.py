from __future__ import annotations

import re
import warnings
from pathlib import Path

FORTUNE_DIR = Path(__file__).resolve().parents[1] / "scripts" / "fortune-es"
OFFENSIVE_PATTERNS = [
	r"\bputa(s)?\b",
	r"\bputo(s)?\b",
	r"\bculo(s)?\b",
	r"\bcojones\b",
	r"\bmierda(s)?\b",
	r"\bmarica\b",
	r"\btesticulos?\b",
	r"\btestículos?\b",
	r"\b(hijo|hija|hijos|hijas) de puta\b",
	r"\bla puta madre\b",
	r"\bandate a la mierda\b",
	r"\bputecer\b",
]


def _fortune_blocks(path: Path) -> list[str]:
	text = path.read_text(encoding="utf-8")
	return [part.strip() for part in text.split("%") if part.strip()]


def _contains_offensive_content(text: str) -> bool:
	lowered = text.lower()
	return any(re.search(pattern, lowered) for pattern in OFFENSIVE_PATTERNS)


def test_fortune_files_have_no_offensive_entries():
	offenders: list[str] = []

	for path in sorted(FORTUNE_DIR.glob("*.fortunes")):
		for block in _fortune_blocks(path):
			if _contains_offensive_content(block):
				preview = block.replace("\n", " ")[:120]
				offenders.append(f"{path.name}: {preview}...")

	warnings.warn("Se encontraron entradas ofensivas en la colección de fortunas:\n" + "\n".join(offenders[:20]))
