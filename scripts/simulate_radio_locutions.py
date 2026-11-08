#!/usr/bin/env python3
"""
Simulador de locuciones radiales en modo mock para auditoría de cobertura de frases y categorías.

Permite simular cientos o miles de emisiones radiales aleatorias y contextualmente variadas
sin sintetizar audio ni realizar llamadas de red externas, garantizando que:
1. No se toque ni altere el historial de recencia en la base de datos real (rockola.db).
2. Se evalúe la cobertura de frases, intros, salidas, pases, reacciones y lead-ins de cada categoría.
3. Se identifiquen frases huérfanas o con restricciones contextuales muy estrictas.
"""

from __future__ import annotations

import argparse
import random
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Asegurar importación del paquete raíz
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
	sys.path.insert(0, str(ROOT_DIR))

from app.domain.radio.classification import (
	CARPINCHO_PHRASES,
)
from app.domain.radio.context import (
	build_radio_context,
)
from app.domain.radio.dialogue import build_radio_dialogue_plan, group_plan_into_speech_turns
from app.domain.radio.linguistics import format_fortune_for_speech
from app.domain.radio.nlp import (
	_clean_phrase_text,
	record_phrase_played,
	reset_radio_memory_state,
	select_radio_phrase,
)
from app.domain.radio.segments import (
	LEAD_INS_BY_CATEGORY,
	OUTROS_CHISMES,
	OUTROS_NOVELA,
	PASES_A_CLIMA,
	RADIO_INTROS,
	RADIO_OUTROS,
	RADIO_OUTROS_BREAK,
	RADIO_OUTROS_DJ,
	RADIO_OUTROS_PAUSE,
	REACCIONES_BY_CATEGORY,
	REACCIONES_CLIMA,
)
from app.domain.radio.templates import expand_phrase_variants
from app.domain.radio.voices import VOICE_NAMES


def collect_all_radio_banks() -> dict[str, list[str]]:
	"""Recopila todos los bancos estructurados de frases radiales por categoría."""
	return {
		"carpincho_fortuna": [p.text for p in CARPINCHO_PHRASES if p.category == "fortuna"],
		"carpincho_aviso": [p.text for p in CARPINCHO_PHRASES if p.category == "aviso"],
		"carpincho_oyentes": [p.text for p in CARPINCHO_PHRASES if p.category == "oyentes"],
		"carpincho_alerta_criolla": [p.text for p in CARPINCHO_PHRASES if p.category == "alerta_criolla"],
		"carpincho_chismes": [p.text for p in CARPINCHO_PHRASES if p.category == "chismes"],
		"carpincho_novela": [p.text for p in CARPINCHO_PHRASES if p.category == "novela"],
		"intros": list(RADIO_INTROS),
		"outros_continue": list(RADIO_OUTROS),
		"outros_chismes": list(OUTROS_CHISMES),
		"outros_novela": list(OUTROS_NOVELA),
		"outros_dj": list(RADIO_OUTROS_DJ),
		"outros_pause": list(RADIO_OUTROS_PAUSE),
		"outros_break": list(RADIO_OUTROS_BREAK),
		"pases": list(PASES_A_CLIMA),
		"lead_ins_fortuna": list(LEAD_INS_BY_CATEGORY["fortuna"]),
		"lead_ins_aviso": list(LEAD_INS_BY_CATEGORY["aviso"]),
		"lead_ins_oyentes": list(LEAD_INS_BY_CATEGORY["oyentes"]),
		"lead_ins_alerta": list(LEAD_INS_BY_CATEGORY["alerta_criolla"]),
		"lead_ins_chismes": list(LEAD_INS_BY_CATEGORY["chismes"]),
		"lead_ins_novela": list(LEAD_INS_BY_CATEGORY["novela"]),
		"reacciones_fortuna": list(REACCIONES_BY_CATEGORY["fortuna"]),
		"reacciones_aviso": list(REACCIONES_BY_CATEGORY["aviso"]),
		"reacciones_oyentes": list(REACCIONES_BY_CATEGORY["oyentes"]),
		"reacciones_alerta": list(REACCIONES_BY_CATEGORY["alerta_criolla"]),
		"reacciones_chismes": list(REACCIONES_BY_CATEGORY["chismes"]),
		"reacciones_novela": list(REACCIONES_BY_CATEGORY["novela"]),
		"reacciones_clima_calor": list(REACCIONES_CLIMA["calor"]),
		"reacciones_clima_frio": list(REACCIONES_CLIMA["frio"]),
		"reacciones_clima_lluvia": list(REACCIONES_CLIMA["lluvia"]),
		"reacciones_clima_agradable": list(REACCIONES_CLIMA["agradable"]),
	}


def _build_variant_lookup(
	all_banks: dict[str, list[Any]],
) -> dict[tuple[str, str], tuple[str, Any]]:
	"""
	Mapea (categoría, texto_normalizado) -> (categoría, plantilla_canónica).
	Permite asociar locuciones renderizadas y formateadas fonéticamente a su plantilla original.
	"""
	lookup: dict[tuple[str, str], tuple[str, Any]] = {}
	for category, templates in all_banks.items():
		is_content = category.startswith("carpincho_")
		for item in templates:
			sub_items = item.all_variants() if hasattr(item, "all_variants") else (item,)
			for tpl in sub_items:
				clean_tpl = _clean_phrase_text(tpl)
				lookup[(category, clean_tpl)] = (category, item)
				if is_content:
					formatted = format_fortune_for_speech(tpl)
					lookup[(category, _clean_phrase_text(formatted))] = (category, item)
				if "{" in tpl:
					for var in expand_phrase_variants(tpl):
						lookup[(category, _clean_phrase_text(var))] = (category, item)
						if is_content:
							lookup[(category, _clean_phrase_text(format_fortune_for_speech(var)))] = (category, item)
	return lookup


def run_mock_radio_simulation(
	iterations: int = 3000,
	db_path: Path | str | None = None,
	seed: int | None = None,
	verbose: bool = False,
) -> dict[str, Any]:
	"""
	Ejecuta una batería de locuciones radiales en un entorno completamente aislado.

	Parámetros:
	- `iterations`: cantidad de emisiones a simular.
	- `db_path`: ruta a base SQLite aislada o temporal (nunca la BDD real de producción).
	- `seed`: semilla aleatoria para repetibilidad determinista.
	- `verbose`: muestra progreso detallado en consola.
	"""
	if seed is not None:
		random.seed(seed)

	# Si no se pasó una ruta aislada, creamos una base SQLite temporal descartable
	temp_dir = None
	if db_path is None:
		temp_dir = tempfile.TemporaryDirectory()
		db_path = Path(temp_dir.name) / "mock_radio_recency.db"
	else:
		db_path = Path(db_path)

	# Limpiamos el estado en memoria y la base temporal
	reset_radio_memory_state(clear_db=True, db_path=db_path)

	banks = collect_all_radio_banks()
	lookup = _build_variant_lookup(banks)
	hits: dict[str, dict[str, int]] = {cat: {tpl: 0 for tpl in tpls} for cat, tpls in banks.items()}

	# Muestras sintéticas de clima y modos de cierre
	weather_conditions = ["agradable", "calor", "frio", "lluvia"]
	weather_samples = {
		"agradable": "En Tigre hacen 22 grados con cielo despejado y una brisa hermosa.",
		"calor": "En Tigre la térmica trepa a los 34 grados con un sol que raja la tierra.",
		"frio": "En Tigre el termómetro marca 6 grados y el viento sur se hace sentir.",
		"lluvia": "En Tigre llueve copiosamente y se vienen chaparrones fuertes para la tarde.",
	}
	outro_modes = ["continue", "dj", "pause", "break"]

	sim_hours = [2, 8, 12, 16, 21]
	sim_months = [1, 4, 7, 10]
	sim_days = [2, 5, 6]  # Miércoles, Sábado, Domingo

	last_reaction: str | None = None
	generated_locutions: list[dict[str, Any]] = []

	for i in range(iterations):
		m = random.choice(sim_months)
		d = random.choice(sim_days)
		h = random.choice(sim_hours)
		minute = random.randint(0, 59)
		cond = random.choice(weather_conditions)
		temp = 32 if cond == "calor" else (8 if cond == "frio" else 22)
		o_mode = random.choice(outro_modes)
		dt = datetime(2026, m, d, h, minute)
		ctx = build_radio_context(dt, temp_c=temp, outro_mode=o_mode)

		phrase, _is_sys = select_radio_phrase(force_system_fortune=False, db_path=db_path, ctx=ctx)
		w_text = weather_samples[cond] if random.random() < 0.85 else None

		is_dialogue = random.random() < 0.85
		plan = build_radio_dialogue_plan(
			fortuna=phrase,
			weather_text=w_text,
			weather_condition=cond,
			dialogue_mode=is_dialogue,
			last_reaction=last_reaction,
			db_path=db_path,
			ctx=ctx,
			outro_mode=o_mode,
			dt=dt,
		)

		speech_turns = group_plan_into_speech_turns(plan)
		formatted_turns: list[dict[str, str]] = []
		speakers_in_locution: set[str] = set()
		for text, voice, category, _allow_cache in speech_turns:
			speaker = VOICE_NAMES.get(voice, voice)
			speakers_in_locution.add(speaker)
			formatted_turns.append({"speaker": speaker, "category": category, "text": text})

		speaker_count = len(speakers_in_locution)
		locution_type = "dúo" if is_dialogue and speaker_count > 1 else "solo"

		generated_locutions.append(
			{
				"index": i + 1,
				"context": f"{ctx.dia_nombre} {ctx.franja} ({h}:{minute:02d}) - {cond} {temp}°C - {locution_type} ({speaker_count} locutor{'es' if speaker_count > 1 else ''}) - modo:{o_mode}",
				"is_dialogue": is_dialogue,
				"speaker_count": speaker_count,
				"turns": formatted_turns,
				"full_text": " ".join(t["text"] for t in formatted_turns),
			}
		)

		for seg_text, _voice, cat, _allow_cache in plan:
			clean = _clean_phrase_text(seg_text)
			record_phrase_played(seg_text, category=cat, timestamp=float(i * 60), db_path=db_path)

			for pool_name in banks:
				match = lookup.get((pool_name, clean))
				if match:
					hits[pool_name][match[1]] += 1

		reactions = [s[0] for s in plan if "reaccion" in s[2]]
		if reactions:
			last_reaction = reactions[-1]

	# Cálculo de métricas finales
	total_templates = 0
	total_hit_templates = 0
	category_coverage: dict[str, dict[str, Any]] = {}

	for cat, tpls in hits.items():
		unhit = [tpl for tpl, count in tpls.items() if count == 0]
		hit_count = len(tpls) - len(unhit)
		pct = (hit_count / len(tpls) * 100.0) if tpls else 100.0
		category_coverage[cat] = {
			"total": len(tpls),
			"hit": hit_count,
			"unhit": len(unhit),
			"coverage_pct": round(pct, 2),
			"unhit_phrases": unhit,
		}
		total_templates += len(tpls)
		total_hit_templates += hit_count

	overall_pct = (total_hit_templates / total_templates * 100.0) if total_templates else 100.0

	if temp_dir is not None:
		temp_dir.cleanup()

	return {
		"total_runs": iterations,
		"total_locutions": len(generated_locutions),
		"locutions": generated_locutions,
		"total_templates": total_templates,
		"hit_templates": total_hit_templates,
		"coverage_percentage": round(overall_pct, 2),
		"category_coverage": category_coverage,
		"generated_locutions": generated_locutions,
	}


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Simulación mock de locución radial y auditoría de cobertura de frases."
	)
	parser.add_argument(
		"--iterations",
		"-n",
		type=int,
		default=3000,
		help="Número de emisiones a simular (por defecto: 3000)",
	)
	parser.add_argument(
		"--seed",
		"-s",
		type=int,
		default=42,
		help="Semilla determinista para números aleatorios",
	)
	parser.add_argument(
		"--max-display",
		"-m",
		type=int,
		default=None,
		help="Cantidad máxima de locuciones a imprimir antes del resumen (por defecto: todas)",
	)
	args = parser.parse_args()

	print(f"🧉 Iniciando simulación mock de radio ({args.iterations} emisiones)...")
	t0 = time.time()
	results = run_mock_radio_simulation(iterations=args.iterations, seed=args.seed)
	elapsed = time.time() - t0

	locutions_to_show = results["generated_locutions"]
	if args.max_display is not None and args.max_display >= 0:
		locutions_to_show = locutions_to_show[: args.max_display]

	print("\n📻 --- LOCUCIONES GENERADAS ---")
	for loc in locutions_to_show:
		print(f"\n🎙️ Emisión #{loc['index']} [{loc['context']}]:")
		for turn in loc["turns"]:
			print(f'   [{turn["speaker"]}]: "{turn["text"]}"')

	if args.max_display is not None and len(results["generated_locutions"]) > len(locutions_to_show):
		print(
			f"\n... (mostrando {len(locutions_to_show)} de {len(results['generated_locutions'])} locuciones generadas)"
		)

	print("\n" + "=" * 70)
	print(f"⏱️ Simulación finalizada en {elapsed:.2f}s.")
	print(
		f"📊 Cobertura general: {results['hit_templates']}/{results['total_templates']} plantillas ({results['coverage_percentage']}%)"
	)
	print("\n--- Desglose por categoría ---")
	for cat, stats in results["category_coverage"].items():
		bar = "✅" if stats["unhit"] == 0 else "⚠️"
		print(f"{bar} {cat:<26}: {stats['hit']:>3}/{stats['total']:<3} ({stats['coverage_pct']:>6.2f}%)")
		if stats["unhit_phrases"]:
			for p in stats["unhit_phrases"][:3]:
				print(f"     ❌ Pendiente: {p}")


if __name__ == "__main__":
	main()
