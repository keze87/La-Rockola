"""
Cálculo de mood_score normalizado y extracción de características acústicas vía FFmpeg.
"""

from __future__ import annotations

import array
import math
import subprocess
from pathlib import Path
from typing import Any

from app.infrastructure.binaries.manager import find_binary, get_clean_env


def is_mood_available() -> bool:
	"""Determina si la capacidad de análisis acústico (FFmpeg) está disponible."""
	return find_binary("ffmpeg") is not None


def calculate_mood_scores(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Calcula y asigna el mood_score normalizado [0.0, 1.0] para una lista de pistas."""
	if not tracks:
		return tracks

	def _normalize(val: float, values: list[float]) -> float:
		if val <= 0 or not values:
			return 0.5
		lo, hi = min(values), max(values)
		if hi - lo < 1e-9:
			return 0.5
		return (val - lo) / (hi - lo)

	valid_bpms = [t.get("bpm", -1.0) for t in tracks if t.get("bpm", -1.0) > 0]
	valid_energies = [t.get("energy", -1.0) for t in tracks if t.get("energy", -1.0) > 0]
	valid_centroids = [t.get("spectral_centroid", -1.0) for t in tracks if t.get("spectral_centroid", -1.0) > 0]

	for t in tracks:
		b = t.get("bpm", -1.0)
		e = t.get("energy", -1.0)
		c = t.get("spectral_centroid", -1.0)

		if b <= 0:
			t["mood_score"] = 0.0
		else:
			nb = _normalize(b, valid_bpms)
			ne = _normalize(e, valid_energies)
			nc = _normalize(c, valid_centroids)
			t["mood_score"] = round(0.5 * nb + 0.35 * ne + 0.15 * nc, 4)

	return tracks


def extract_audio_features_ffmpeg(path: str | Path, ffmpeg_bin: str = "ffmpeg") -> tuple[float, float, float]:
	"""
	Extrae BPM, energía RMS y brillo espectral (ZCR * Nyquist) decodificando
	un fragmento de audio PCM s16le a 11025 Hz vía FFmpeg.
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

		sum_sq = sum(s * s for s in samples)
		rms = math.sqrt(sum_sq / num_samples) / 32768.0
		energy = round(min(1.0, rms * 2.5), 3)

		zero_crossings = 0
		for i in range(1, num_samples):
			if (samples[i] >= 0 and samples[i - 1] < 0) or (samples[i] < 0 and samples[i - 1] >= 0):
				zero_crossings += 1
		zcr = zero_crossings / (num_samples - 1)
		spectral_centroid = round(zcr * 5512.5, 1)

		hop = 220
		sr_env = 11025.0 / hop
		envelope = [math.sqrt(sum(s * s for s in samples[i : i + hop]) / hop) for i in range(0, num_samples - hop, hop)]
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

			bpm = round(sr_env * 60.0 / best_lag, 1) if (best_lag > 0 and best_corr > 0) else 120.0
		else:
			bpm = 120.0

		return (bpm, energy, spectral_centroid)
	except Exception:
		return (-1.0, -1.0, -1.0)
