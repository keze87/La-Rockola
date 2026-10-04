"""
Módulo de línea de comandos (CLI) y asistente interactivo de La Rockola del Carpincho.
"""

from app.cli.entrypoint import build_arg_parser, main
from app.cli.wizard import run_interactive_wizard, select_folder_dialog

__all__ = ["build_arg_parser", "main", "run_interactive_wizard", "select_folder_dialog"]
