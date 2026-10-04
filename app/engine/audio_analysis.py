"""
Extracción de métricas acústicas (BPM, energía RMS, brillo espectral) y huellas Chromaprint.
"""

from __future__ import annotations

import array
import logging
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("RockolaCarpincho")


try:
	from scripts.binary_utils import ensure_display_env, get_clean_env
except ImportError:
	try:
		from binary_utils import ensure_display_env, get_clean_env
	except ImportError:

		def ensure_display_env(env: Any = None) -> None:
			pass

		def get_clean_env() -> dict[str, str]:
			return os.environ.copy()


def find_binary(bin_name: str) -> str | None:
	"""Busca un binario en rutas prioritarias locales, datos de usuario o en el PATH del sistema."""
	from app.core.config import get_carpincho_data_dir

	is_win = sys.platform == "win32" or os.name == "nt"
	base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
	exts = [".exe", ""] if is_win else [""]

	py_bin_dir = Path(sys.prefix) / ("Scripts" if is_win else "bin")
	dirs: list[Path] = [base, base / "bin", base / "mpv", base / bin_name, py_bin_dir]
	data_dir = get_carpincho_data_dir()
	dirs.extend(
		[
			data_dir,
			data_dir / "bin",
			data_dir / "mpv",
			data_dir / bin_name,
			data_dir.parent / "mpv",
			data_dir.parent / bin_name,
		]
	)

	# 1. Buscar en directorios locales prioritarios de la aplicación
	for d in dirs:
		for ext in exts:
			cand = d / f"{bin_name}{ext}"
			if cand.is_file():
				return str(cand)

	def _safe_which(cmd: str) -> str | None:
		try:
			return shutil.which(cmd)
		except Exception:
			return None

	# 2. Buscar en PATH estándar
	found = _safe_which(bin_name)
	if not found and is_win and not bin_name.lower().endswith(".exe"):
		found = _safe_which(f"{bin_name}.exe")
	if found:
		return found

	# 3. Si buscamos yt-dlp, verificar si está en la misma carpeta que mpv
	if bin_name == "yt-dlp":
		try:
			mpv_found = _safe_which("mpv") or (_safe_which("mpv.exe") if is_win else None)
			if mpv_found:
				mpv_dir = Path(mpv_found).parent
				for ext in exts:
					cand = mpv_dir / f"{bin_name}{ext}"
					if cand.is_file():
						return str(cand)
		except Exception:
			pass

	# 4. Entorno de Python (Scripts / bin) donde pip instala herramientas como yt-dlp
	py_scripts = "Scripts" if is_win else "bin"
	py_dirs = [
		Path(sys.prefix) / py_scripts,
		Path(sys.exec_prefix) / py_scripts,
		Path(sys.executable).parent / py_scripts,
	]
	try:
		import site

		user_base = getattr(site, "USER_BASE", None)
		if user_base:
			py_dirs.append(Path(user_base) / py_scripts)
	except Exception:
		pass

	for pd in py_dirs:
		for ext in exts:
			cand = pd / f"{bin_name}{ext}"
			if cand.is_file():
				return str(cand)

	# 5. En Windows: Gestores de paquetes populares (Scoop, WinGet, Chocolatey)
	if is_win:
		home = Path.home()
		mgr_dirs = [
			home / "scoop" / "shims",
			home / "scoop" / "apps" / bin_name / "current",
			home / "scoop" / "apps" / "python" / "current" / "Scripts",
			home / "scoop" / "apps" / "mpv" / "current",
		]
		prog_data = os.environ.get("ProgramData", "C:\\ProgramData")
		mgr_dirs.append(Path(prog_data) / "scoop" / "shims")

		local_app_data = os.environ.get("LOCALAPPDATA")
		if local_app_data:
			mgr_dirs.append(Path(local_app_data) / "Microsoft" / "WinGet" / "Links")

		choco = os.environ.get("ChocolateyInstall", os.path.join(prog_data, "chocolatey"))
		if choco:
			mgr_dirs.append(Path(choco) / "bin")

		for md in mgr_dirs:
			for ext in exts:
				cand = md / f"{bin_name}{ext}"
				if cand.is_file():
					return str(cand)

	return None


def is_mood_available() -> bool:
	"""Determina si la capacidad de análisis acústico (FFmpeg) está disponible."""
	return find_binary("ffmpeg") is not None


def extract_audio_features_ffmpeg(path: str | Path, ffmpeg_bin: str = "ffmpeg") -> tuple[float, float, float]:
	"""
	Extrae BPM, energía RMS y brillo espectral (ZCR * Nyquist) decodificando
	un fragmento de audio PCM s16le a 11025 Hz vía FFmpeg.
	Devuelve (bpm, energy, centroid). Si falla, retorna (-1.0, -1.0, -1.0).
	"""
	try:
		bin_path = find_binary(ffmpeg_bin) or ffmpeg_bin
		clean_env = get_clean_env()
		cmd = [
			bin_path,
			"-nostats",
			"-loglevel",
			"error",
			"-ss",
			"15",
			"-t",
			"12",
			"-i",
			str(path),
			"-ac",
			"1",
			"-ar",
			"11025",
			"-f",
			"s16le",
			"pipe:1",
		]
		res = subprocess.run(cmd, env=clean_env, capture_output=True, timeout=5.0, check=False)
		pcm_data = res.stdout
		if not pcm_data or len(pcm_data) < 22050:
			cmd_short = [
				bin_path,
				"-nostats",
				"-loglevel",
				"error",
				"-t",
				"12",
				"-i",
				str(path),
				"-ac",
				"1",
				"-ar",
				"11025",
				"-f",
				"s16le",
				"pipe:1",
			]
			res = subprocess.run(cmd_short, env=clean_env, capture_output=True, timeout=5.0, check=False)
			pcm_data = res.stdout

		if not pcm_data or len(pcm_data) < 4000:
			return (-1.0, -1.0, -1.0)

		samples = array.array("h")
		samples.frombytes(pcm_data)
		num_samples = len(samples)
		if num_samples < 2000:
			return (-1.0, -1.0, -1.0)

		# 1. Energía RMS normalizada a [0.0, 1.0]
		sum_sq = sum(s * s for s in samples)
		rms = math.sqrt(sum_sq / num_samples) / 32768.0
		energy = round(min(1.0, rms * 2.5), 3)

		# 2. Brillo espectral aproximado por cruces por cero (ZCR * Nyquist)
		zero_crossings = 0
		for i in range(1, num_samples):
			if (samples[i] >= 0 and samples[i - 1] < 0) or (samples[i] < 0 and samples[i - 1] >= 0):
				zero_crossings += 1
		zcr = zero_crossings / (num_samples - 1)
		spectral_centroid = round(zcr * 5512.5, 1)

		# 3. Estimación de BPM por autocorrelación
		hop = 220
		sr_env = 11025.0 / hop
		envelope = []
		for i in range(0, num_samples - hop, hop):
			frame_energy = math.sqrt(sum(s * s for s in samples[i : i + hop]) / hop)
			envelope.append(frame_energy)

		diff_env = [max(0.0, envelope[j] - envelope[j - 1]) for j in range(1, len(envelope))]

		if len(diff_env) > 60:
			mean_diff = sum(diff_env) / len(diff_env)
			centered_diff = [d - mean_diff for d in diff_env]
			min_lag = max(1, int(sr_env * 60.0 / 185.0))
			max_lag = min(len(centered_diff) - 1, int(sr_env * 60.0 / 60.0))

			best_lag = 0
			best_corr = -1e9
			n_env = len(centered_diff)

			for lag in range(min_lag, max_lag + 1):
				corr = sum(centered_diff[k] * centered_diff[k + lag] for k in range(n_env - lag))
				if corr > best_corr:
					best_corr = corr
					best_lag = lag

			if best_lag > 0 and best_corr > 0:
				bpm = round(sr_env * 60.0 / best_lag, 1)
			else:
				bpm = 120.0
		else:
			bpm = 120.0

		return (bpm, energy, spectral_centroid)
	except Exception:
		return (-1.0, -1.0, -1.0)


def parse_fp(fp_str: str | None) -> list[int] | None:
	"""Convierte una cadena de enteros separados por coma en lista de hashes."""
	if not fp_str:
		return None
	try:
		return [int(x) for x in fp_str.split(",")]
	except (ValueError, TypeError, AttributeError):
		return None


def compare_fps(fp1: list[int] | None, fp2: list[int] | None) -> float:
	"""Compara dos huellas Chromaprint calculando similitud bit a bit [0.0, 1.0]."""
	if not fp1 or not fp2:
		return 0.0
	min_len = min(len(fp1), len(fp2))
	if min_len < 10:
		return 0.0

	diff_bits = sum(((fp1[i] ^ fp2[i]) & 0xFFFFFFFF).bit_count() for i in range(min_len))
	return 1.0 - (diff_bits / (min_len * 32))
