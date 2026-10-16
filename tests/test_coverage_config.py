import configparser
from pathlib import Path


def test_pytest_ini_coverage_includes_app():
	"""Verifica que pytest.ini incluya el paquete 'app' en las opciones de cobertura (--cov=app)."""
	ini_path = Path(__file__).resolve().parent.parent / "pytest.ini"
	assert ini_path.exists(), "pytest.ini debe existir en la raíz del proyecto"

	config = configparser.ConfigParser()
	config.read(ini_path, encoding="utf-8")

	assert config.has_section("pytest"), "pytest.ini debe contener la sección [pytest]"
	addopts = config.get("pytest", "addopts", fallback="")

	options = addopts.split()
	assert "--cov=app" in options, f"--cov=app debe estar presente en addopts de pytest.ini. Encontrado: {addopts}"
