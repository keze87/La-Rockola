#!/usr/bin/env python3
"""
Script de automatización para compilar el frontend y preparar los assets para empaquetado.
Uso:
    python scripts/build_dist.py
"""

import os
import subprocess
import sys
from pathlib import Path


def build_frontend() -> bool:
	# Determinamos el directorio raíz del proyecto
	root_dir = Path(__file__).resolve().parent.parent
	package_json = root_dir / "package.json"

	if not package_json.exists():
		print("❌ No se encontró 'package.json' en la raíz. ¿Dónde te paraste, fiera?", file=sys.stderr)
		return False

	print("🦦 Preparando el frontend de La Rockola del Carpincho...")
	npm_cmd = "npm.cmd" if os.name == "nt" else "npm"

	try:
		node_modules = root_dir / "node_modules"
		if not node_modules.exists():
			print("📦 Instalando dependencias del frontend (npm install)...")
			subprocess.run([npm_cmd, "install"], cwd=str(root_dir), check=True)

		print("🛠️ Ejecutando 'npm run build'...")
		subprocess.run([npm_cmd, "run", "build"], cwd=str(root_dir), check=True)

		dist_dir = root_dir / "dist"
		if not dist_dir.exists() or not (dist_dir / "index.html").exists():
			print("⚠️ La compilación terminó pero no se encontró 'dist/index.html'.", file=sys.stderr)
			return False

		print("✨ Build completado con éxito. ¡Todo piola y listo para rodar!")
		return True

	except subprocess.CalledProcessError as e:
		print(f"❌ Error al compilar el frontend: {e}", file=sys.stderr)
		return False
	except FileNotFoundError:
		print("❌ Error: No se encontró 'npm' en el PATH del sistema.", file=sys.stderr)
		return False


if __name__ == "__main__":
	success = build_frontend()
	sys.exit(0 if success else 1)
