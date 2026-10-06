"""
Módulo de línea de comandos (CLI) y asistente interactivo de La Rockola del Carpincho.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from app.cli.entrypoint import build_arg_parser, main
	from app.cli.wizard import run_interactive_wizard, select_folder_dialog

__all__ = ["build_arg_parser", "main", "run_interactive_wizard", "select_folder_dialog"]


def __getattr__(name: str):
	if name in ("build_arg_parser", "main"):
		from app.cli import entrypoint

		return getattr(entrypoint, name)
	if name in ("run_interactive_wizard", "select_folder_dialog"):
		from app.cli import wizard

		return getattr(wizard, name)
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
