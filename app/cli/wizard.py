"""
Asistente interactivo de primera ejecución y selectores nativos de carpetas por plataforma.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.core.config import DEFAULT_CONFIG, DEFAULT_WEATHER_LOCATION, load_config, save_config
from app.engine.audio_analysis import get_clean_env

logger = logging.getLogger("RockolaCarpincho")


def _srv(name: str, fallback: Any = None) -> Any:
	"""Resuelve símbolos dinámicos desde server.py para soportar monkeypatching en tests."""
	srv = sys.modules.get("server")
	if srv is not None and hasattr(srv, name):
		return getattr(srv, name)
	return fallback


def _parse_selected_dir(raw_out: str | None) -> str | None:
	"""Limpia y valida la salida devuelta por selectores de carpetas nativos."""
	if not raw_out:
		return None
	out = raw_out.strip()
	if out.startswith("file://"):
		import urllib.request
		from urllib.parse import unquote, urlparse

		parsed = urlparse(out)
		path_part = unquote(parsed.path)
		if parsed.netloc:
			path_part = f"{parsed.netloc}{path_part}"
		if sys.platform == "win32" or os.name == "nt":
			out = urllib.request.url2pathname(path_part)
		else:
			out = path_part
	out = out.strip("\"'")
	if out != "/" and out.endswith(("/", "\\")):
		out = out.rstrip("/\\")
	if out and Path(out).is_dir():
		return out
	return None


def _select_folder_powershell(title: str, initial_dir: str | None = None) -> str | None:
	"""Abre el diálogo nativo de Windows (FolderBrowserDialog) usando PowerShell."""
	ps_code = (
		"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
		"Add-Type -AssemblyName System.Windows.Forms; "
		"$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
		f"$d.Description = '{title}'; "
		"$d.ShowNewFolderButton = $true; "
	)
	if initial_dir and Path(initial_dir).is_dir():
		safe_dir = str(Path(initial_dir).resolve()).replace("'", "''")
		ps_code += f"$d.SelectedPath = '{safe_dir}'; "
	ps_code += (
		"$top = New-Object System.Windows.Forms.Form; "
		"$top.TopMost = $true; "
		"$res = $d.ShowDialog($top); "
		"if ($res -eq [System.Windows.Forms.DialogResult]::OK) { "
		"  [Console]::Out.WriteLine($d.SelectedPath) "
		"} "
		"$top.Dispose(); $d.Dispose();"
	)
	flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
	try:
		res = subprocess.run(
			["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_code],
			env=get_clean_env(),
			capture_output=True,
			text=True,
			encoding="utf-8",
			creationflags=flags,
			timeout=180,
			check=False,
		)
		return _parse_selected_dir(res.stdout)
	except Exception:
		pass
	return None


def _select_folder_tkinter(title: str, initial_dir: str | None = None) -> str | None:
	"""Abre el diálogo de carpetas mediante Tkinter si está disponible."""
	try:
		import tkinter as tk
		from tkinter import filedialog

		root = tk.Tk()
		root.withdraw()
		root.attributes("-topmost", True)
		init_path = str(Path(initial_dir).resolve()) if initial_dir and Path(initial_dir).is_dir() else str(Path.home())
		chosen = filedialog.askdirectory(title=title, initialdir=init_path)
		root.destroy()
		return _parse_selected_dir(chosen)
	except Exception:
		pass
	return None


def _select_folder_macos(title: str, initial_dir: str | None = None) -> str | None:
	"""Abre el diálogo nativo de macOS usando AppleScript."""
	try:
		safe_title = title.replace('"', '\\"')
		script = f'POSIX path of (choose folder with prompt "{safe_title}")'
		clean_env = _srv("get_clean_env", get_clean_env)()
		res = subprocess.run(
			["osascript", "-e", script],
			env=clean_env,
			capture_output=True,
			text=True,
			timeout=180,
			check=False,
		)
		return _parse_selected_dir(res.stdout)
	except Exception:
		pass
	return None


def _select_folder_linux(title: str, initial_dir: str | None = None) -> str | None:
	"""Abre el diálogo de carpetas en Linux mediante zenity, kdialog o yad."""
	clean_env = _srv("get_clean_env", get_clean_env)()
	start = str(Path(initial_dir).resolve()) if initial_dir and Path(initial_dir).is_dir() else str(Path.home())

	if shutil.which("zenity"):
		try:
			cmd = ["zenity", "--file-selection", "--directory", f"--title={title}"]
			if initial_dir and Path(initial_dir).is_dir():
				cmd.append(f"--filename={start}/")
			res = subprocess.run(cmd, env=clean_env, capture_output=True, text=True, timeout=180, check=False)
			parsed = _parse_selected_dir(res.stdout)
			if parsed:
				return parsed
		except Exception:
			pass

	if shutil.which("kdialog"):
		try:
			cmd = ["kdialog", f"--title={title}", "--getexistingdirectory", start]
			res = subprocess.run(cmd, env=clean_env, capture_output=True, text=True, timeout=180, check=False)
			parsed = _parse_selected_dir(res.stdout)
			if parsed:
				return parsed
		except Exception:
			pass

	if shutil.which("yad"):
		try:
			cmd = ["yad", "--file", "--directory", f"--title={title}", f"--filename={start}/"]
			res = subprocess.run(cmd, env=clean_env, capture_output=True, text=True, timeout=180, check=False)
			parsed = _parse_selected_dir(res.stdout)
			if parsed:
				return parsed
		except Exception:
			pass

	return None


def select_folder_dialog(title: str = "Seleccioná la carpeta de música", initial_dir: str | None = None) -> str | None:
	"""Abre un diálogo gráfico nativo según el sistema operativo."""
	if sys.platform == "win32":
		fn_ps = _srv("_select_folder_powershell", _select_folder_powershell)
		fn_tk = _srv("_select_folder_tkinter", _select_folder_tkinter)
		res = fn_ps(title, initial_dir)
		if res:
			return res
		return fn_tk(title, initial_dir)
	elif sys.platform == "darwin":
		fn_mac = _srv("_select_folder_macos", _select_folder_macos)
		fn_tk = _srv("_select_folder_tkinter", _select_folder_tkinter)
		res = fn_mac(title, initial_dir)
		if res:
			return res
		return fn_tk(title, initial_dir)
	else:
		fn_lin = _srv("_select_folder_linux", _select_folder_linux)
		fn_tk = _srv("_select_folder_tkinter", _select_folder_tkinter)
		res = fn_lin(title, initial_dir)
		if res:
			return res
		return fn_tk(title, initial_dir)


def setup_readline_completion() -> None:
	"""Habilita autocompletado con tecla Tab en la terminal si readline está disponible."""
	try:
		import glob
		import readline

		def path_completer(text: str, state: int):
			exp = os.path.expanduser(text)
			matches = glob.glob(exp + "*")
			matches = [m + "/" if os.path.isdir(m) else m for m in matches]
			if state < len(matches):
				return matches[state]
			return None

		readline.set_completer_delims(" \t\n")
		readline.set_completer(path_completer)
		readline.parse_and_bind("tab: complete")
	except Exception:
		pass


def select_folder_terminal(initial_dir: str | None = None) -> str | None:
	"""Navegador interactivo de carpetas en consola como fallback."""
	current = Path(initial_dir or Path.home()).expanduser().resolve()
	if not current.is_dir():
		current = Path.home().resolve()

	while True:
		subdirs = []
		try:
			for item in sorted(current.iterdir(), key=lambda p: p.name.lower()):
				if item.is_dir() and not item.name.startswith("."):
					subdirs.append(item)
		except PermissionError:
			print(f"\n⚠️  Sin permisos para leer: {current}")

		print("\n" + "-" * 55)
		print(f"📂 Navegador de carpetas: {current}")
		print("-" * 55)
		print("  [0]  ✅ Seleccionar esta carpeta actual")
		if current.parent != current:
			print("  [..] ⬆️  Subir al directorio superior")

		for idx, d in enumerate(subdirs[:25], start=1):
			print(f"  [{idx:<2}] 📁 {d.name}/")
		if len(subdirs) > 25:
			print(f"  ... y {len(subdirs) - 25} carpetas más.")

		print("  [q]  ❌ Cancelar y volver al menú anterior")

		try:
			ans = input("\nElegí un número [0=confirmar, ..=subir, q=cancelar]: ").strip()
		except (EOFError, KeyboardInterrupt):
			return None

		if ans.lower() in ("q", "quit", "cancel", "cancelar", "salir"):
			return None
		if ans == "0":
			return str(current)
		if ans == ".." and current.parent != current:
			current = current.parent
			continue
		if ans.isdigit() and 1 <= int(ans) <= len(subdirs):
			current = subdirs[int(ans) - 1].resolve()
		else:
			print("⚠️  Opción no válida. Ingresá un número de la lista o [0] para confirmar.")


def run_interactive_wizard(config_path: Path, current_config: dict[str, Any] | None = None) -> dict[str, Any]:
	"""Asistente interactivo en consola para la primera ejecución."""
	setup_readline_completion()
	cfg = {**DEFAULT_CONFIG, **(current_config or load_config(config_path))}

	print("\n" + "=" * 62)
	print("  🦦 BIENVENIDO A LA ROCKOLA DEL CARPINCHO 🧉")
	print("        Asistente de Configuración Inicial")
	print("=" * 62)
	print("Configuremos la carpeta de música para dejar La Rockola lista:\n")

	default_dir = cfg.get("music_dir") or "~/Music"
	default_resolved = str(Path(default_dir).expanduser().resolve())

	print("📁 Carpeta de música:")
	print("  [1] 📂 Abrir selector de carpetas... (Gráfico / Terminal) [predeterminado]")
	print(f"  [2] Usar carpeta estándar: {default_dir} ({default_resolved})")
	print("  [3] Escribir ruta manualmente (con soporte para tecla Tab)\n")

	while True:
		try:
			choice = input("Elegí una opción [1-3] o escribí la ruta [default: 1]: ").strip()
		except (EOFError, KeyboardInterrupt):
			print("\nOperación cancelada. Usando valores actuales.")
			return cfg

		if choice == "" or choice == "1" or choice.lower() in ("b", "e", "examinar", "browse", "selector"):
			print("⏳ Abriendo selector de carpetas...")
			fn_dialog = _srv("select_folder_dialog", select_folder_dialog)
			selected = fn_dialog(
				title="Seleccioná la carpeta principal de música",
				initial_dir=default_resolved if Path(default_resolved).is_dir() else None,
			)
			if selected:
				print(f"✅ Carpeta seleccionada: {selected}")
				chosen_dir = selected
			else:
				print("⚠️  No se seleccionó ninguna carpeta en el selector gráfico.")
				try:
					explore_tui = input(
						"   ¿Querés explorar las carpetas acá en la terminal? [S/n / o pegá la ruta]: "
					).strip()
					if explore_tui.lower() in ("", "s", "si", "y", "yes"):
						tui_selected = select_folder_terminal(initial_dir=default_resolved)
						if tui_selected:
							print(f"✅ Carpeta seleccionada: {tui_selected}")
							chosen_dir = tui_selected
						else:
							continue
					elif explore_tui.lower() in ("n", "no"):
						continue
					else:
						chosen_dir = explore_tui
				except (EOFError, KeyboardInterrupt):
					continue
		elif choice == "2" or choice.lower() in ("d", "defecto", "default"):
			chosen_dir = default_dir
		elif choice == "3":
			try:
				manual_val = input("📁 Ingresá la ruta de la carpeta (podés usar Tab para autocompletar): ").strip()
			except (EOFError, KeyboardInterrupt):
				manual_val = ""
			if not manual_val:
				continue
			chosen_dir = manual_val
		else:
			chosen_dir = choice

		expanded = Path(chosen_dir).expanduser().resolve()
		if not expanded.is_dir():
			print(f"⚠️  La carpeta '{expanded}' no existe actualmente.")
			try:
				create = input("¿Querés crearla ahora? [S/n]: ").strip().lower()
			except (EOFError, KeyboardInterrupt):
				create = "n"
			if create in ("", "s", "si", "y", "yes"):
				try:
					expanded.mkdir(parents=True, exist_ok=True)
					cfg["music_dir"] = str(expanded)
					break
				except Exception as e:
					print(f"❌ No se pudo crear la carpeta: {e}. Probemos otra opción.")
			else:
				print("Probemos indicando otra opción o ruta.")
		else:
			cfg["music_dir"] = str(expanded)
			break

	default_weather = cfg.get("weather_location") or DEFAULT_WEATHER_LOCATION
	print("\n🌤️  Ubicación para el reporte del clima en la radio:")
	print(f"   Podés ingresar tu ciudad o localidad [default: {default_weather}]:\n")
	try:
		weather_ans = input(f"Ciudad/Localidad [{default_weather}]: ").strip()
	except (EOFError, KeyboardInterrupt, StopIteration):
		weather_ans = ""

	chosen_weather = weather_ans if weather_ans else default_weather
	cfg["weather_location"] = chosen_weather
	print(f"✅ Clima configurado para: {chosen_weather}")

	save_config(config_path, cfg)
	print("\n✨ ¡Listo el pollo y pelada la gallina! Configuración guardada en:")
	print(f"   {config_path}\n")
	print("=" * 62 + "\n")
	return cfg
