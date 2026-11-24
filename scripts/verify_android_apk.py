#!/usr/bin/env python3
"""
Verificador binario ELF de alineamiento de 16 KB (0x4000) y saneamiento de RUNPATH
para APKs y AABs Android (incluidos archivos .so dentro de paquetes .imy de Chaquopy).
"""

from __future__ import annotations

import io
import json
import os
import shutil
import struct
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_ALIGN_16KB = 0x4000
PT_LOAD = 1
PT_DYNAMIC = 2
DT_NULL = 0
DT_STRTAB = 5
DT_STRSZ = 10
DT_RPATH = 15
DT_RUNPATH = 29
ABI_MACHINE_MAP = {
	"arm64-v8a": 183,  # EM_AARCH64
	"x86_64": 62,  # EM_X86_64
}


@dataclass(slots=True)
class VerificationResult:
	"""Resultado del análisis ELF sobre un artefacto APK/AAB."""

	ok: bool
	inspected_so_count: int = 0
	inspected_names: list[str] = field(default_factory=list)
	errors: list[str] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)


def _sdk_search_roots() -> list[Path]:
	roots: list[Path] = []
	for env_var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
		val = os.environ.get(env_var, "").strip()
		if val:
			roots.append(Path(val))
	roots.extend([Path("/opt/android-sdk"), Path.home() / "Android" / "Sdk"])
	return roots


def find_zipalign_command() -> str | None:
	"""Localiza el binario `zipalign` en PATH o en los build-tools del Android SDK."""
	in_path = shutil.which("zipalign")
	if in_path:
		return in_path
	candidates: list[Path] = []
	for root in _sdk_search_roots():
		bt_dir = root / "build-tools"
		if bt_dir.is_dir():
			for tool in sorted(bt_dir.glob("*/zipalign")):
				if tool.is_file():
					candidates.append(tool)
	return str(candidates[-1]) if candidates else None


def find_bundletool_command() -> list[str] | None:
	"""Localiza `bundletool` en PATH o vía ANDROID_BUNDLETOOL_JAR."""
	in_path = shutil.which("bundletool")
	if in_path:
		return [in_path]
	jar = os.environ.get("ANDROID_BUNDLETOOL_JAR", "").strip()
	if jar and Path(jar).is_file():
		java_bin = shutil.which("java") or "java"
		return [java_bin, "-jar", jar]
	return None


def _vaddr_to_offset(vaddr: int, load_segments: list[tuple[int, int, int, int]]) -> int | None:
	for p_offset, p_vaddr, _p_filesz, p_memsz in load_segments:
		if p_vaddr <= vaddr < p_vaddr + p_memsz:
			return p_offset + (vaddr - p_vaddr)
	return None


def _expected_machine_for_label(label: str) -> tuple[str, int] | None:
	parts = label.replace("\\", "/").split("/")
	for idx, part in enumerate(parts):
		if part == "lib" and idx + 1 < len(parts):
			abi = parts[idx + 1]
			if abi in ABI_MACHINE_MAP:
				return abi, ABI_MACHINE_MAP[abi]
	return None


def inspect_elf_bytes(label: str, data: bytes) -> list[str]:
	"""Inspecciona headers ELF32/ELF64 para validar PT_LOAD >= 0x4000, ABI, tabla phdr y ausencia de com.termux en RUNPATH."""
	if len(data) < 52 or data[:4] != b"\x7fELF":
		return [f"{label}: no es un binario ELF válido"]

	ei_class = data[4]
	ei_data = data[5]
	endian = "<" if ei_data == 1 else ">" if ei_data == 2 else ""
	if not endian:
		return [f"{label}: endianness ELF desconocida ({ei_data})"]

	issues: list[str] = []
	e_machine = struct.unpack_from(f"{endian}H", data, 18)[0]
	expected_abi = _expected_machine_for_label(label)
	if expected_abi is not None:
		abi_name, expected_machine = expected_abi
		if e_machine != expected_machine:
			issues.append(
				f"{label}: ABI incompatible con {abi_name} (e_machine={e_machine}, esperado={expected_machine})"
			)

	load_segments: list[tuple[int, int, int, int]] = []
	dynamic_segment: tuple[int, int] | None = None

	if ei_class == 2:
		if len(data) < 64:
			return [f"{label}: cabecera ELF64 truncada"]
		e_phoff, e_phentsize, e_phnum = (
			struct.unpack_from(f"{endian}Q", data, 32)[0],
			*struct.unpack_from(f"{endian}HH", data, 54),
		)
		if e_phentsize < 56 or e_phnum == 0 or e_phoff + (e_phnum * e_phentsize) > len(data):
			return issues + [f"{label}: tabla de program headers ELF64 truncada o inválida"]
		for idx in range(e_phnum):
			off = e_phoff + idx * e_phentsize
			p_type, _p_flags, p_offset, p_vaddr, _p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from(
				f"{endian}IIQQQQQQ", data, off
			)
			if p_type == PT_LOAD:
				load_segments.append((p_offset, p_vaddr, p_filesz, p_memsz))
				if p_align == 0 or (p_align & (p_align - 1)) != 0:
					issues.append(f"{label}: segmento PT_LOAD con p_align inválido (no potencia de 2: 0x{p_align:x})")
				else:
					if p_align < REQUIRED_ALIGN_16KB:
						issues.append(
							f"{label}: segmento PT_LOAD con alineamiento 0x{p_align:x} < 0x{REQUIRED_ALIGN_16KB:x} (no compatible 16 KB)"
						)
					if (p_offset % p_align) != (p_vaddr % p_align):
						issues.append(
							f"{label}: segmento PT_LOAD sin congruencia p_offset/p_vaddr "
							f"(p_offset=0x{p_offset:x}, p_vaddr=0x{p_vaddr:x}, p_align=0x{p_align:x})"
						)
				if p_filesz > p_memsz or (p_offset + p_filesz) > len(data):
					issues.append(
						f"{label}: segmento PT_LOAD fuera de límites de archivo o p_filesz > p_memsz "
						f"(p_offset=0x{p_offset:x}, p_filesz=0x{p_filesz:x}, p_memsz=0x{p_memsz:x}, size=0x{len(data):x})"
					)
			elif p_type == PT_DYNAMIC:
				dynamic_segment = (p_offset, p_filesz)
		dyn_fmt = f"{endian}qQ"
		dyn_step = 16
	elif ei_class == 1:
		issues.append(f"{label}: binario ELF de 32 bits no soportado para publicación 64-bit / 16 KB")
		e_phoff, e_phentsize, e_phnum = (
			struct.unpack_from(f"{endian}I", data, 28)[0],
			*struct.unpack_from(f"{endian}HH", data, 42),
		)
		if e_phentsize < 32 or e_phnum == 0 or e_phoff + (e_phnum * e_phentsize) > len(data):
			return issues + [f"{label}: tabla de program headers ELF32 truncada o inválida"]
		for idx in range(e_phnum):
			off = e_phoff + idx * e_phentsize
			p_type, p_offset, p_vaddr, _p_paddr, p_filesz, p_memsz, _flags, p_align = struct.unpack_from(
				f"{endian}IIIIIIII", data, off
			)
			if p_type == PT_LOAD:
				load_segments.append((p_offset, p_vaddr, p_filesz, p_memsz))
			elif p_type == PT_DYNAMIC:
				dynamic_segment = (p_offset, p_filesz)
		dyn_fmt = f"{endian}iI"
		dyn_step = 8
	else:
		return [f"{label}: clase ELF desconocida ({ei_class})"]

	if not load_segments:
		issues.append(f"{label}: no posee segmentos PT_LOAD")

	if dynamic_segment is not None:
		dyn_off, dyn_sz = dynamic_segment
		strtab_vaddr: int | None = None
		strtab_sz: int = 0
		rpath_offsets: list[int] = []
		pos = dyn_off
		end = min(len(data), dyn_off + dyn_sz)
		while pos + dyn_step <= end:
			d_tag, d_val = struct.unpack_from(dyn_fmt, data, pos)
			pos += dyn_step
			if d_tag == DT_NULL:
				break
			if d_tag == DT_STRTAB:
				strtab_vaddr = d_val
			elif d_tag == DT_STRSZ:
				strtab_sz = d_val
			elif d_tag in (DT_RPATH, DT_RUNPATH):
				rpath_offsets.append(d_val)

		if strtab_vaddr is not None and rpath_offsets:
			strtab_off = _vaddr_to_offset(strtab_vaddr, load_segments)
			if strtab_off is None and strtab_vaddr < len(data):
				strtab_off = strtab_vaddr
			if strtab_off is not None:
				table_end = min(len(data), strtab_off + (strtab_sz or (len(data) - strtab_off)))
				strtab_bytes = data[strtab_off:table_end]
				for r_off in rpath_offsets:
					if 0 <= r_off < len(strtab_bytes):
						nul_idx = strtab_bytes.find(b"\x00", r_off)
						raw_val = strtab_bytes[r_off:] if nul_idx < 0 else strtab_bytes[r_off:nul_idx]
						decoded = raw_val.decode("utf-8", errors="replace")
						if "com.termux" in decoded.lower():
							issues.append(f"{label}: RUNPATH/RPATH prohibido contiene com.termux ({decoded})")

	return issues


def _check_apk_so_zip_alignment(archive_path: Path, zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> str | None:
	if archive_path.suffix.lower() != ".apk" or info.compress_type != zipfile.ZIP_STORED:
		return None
	with archive_path.open("rb") as raw_fp:
		raw_fp.seek(info.header_offset)
		local_hdr = raw_fp.read(30)
		if len(local_hdr) < 30 or local_hdr[:4] != b"PK\x03\x04":
			return f"{info.filename}: cabecera local ZIP inválida"
		name_len, extra_len = struct.unpack_from("<HH", local_hdr, 26)
		data_offset = info.header_offset + 30 + name_len + extra_len
		if data_offset % REQUIRED_ALIGN_16KB != 0:
			return (
				f"{info.filename}: payload ZIP_STORED en offset 0x{data_offset:x} no alineado a 16 KB "
				f"(ejecutar zipalign -P 16)"
			)
	return None


def _inspect_zip_recursive(
	zf: zipfile.ZipFile,
	prefix: str,
	result: VerificationResult,
	top_apk_path: Path | None = None,
) -> None:
	for info in zf.infolist():
		if info.is_dir():
			continue
		name = f"{prefix}{info.filename}"
		lower = info.filename.lower()
		if lower.endswith(".so"):
			if top_apk_path is not None and not prefix:
				align_err = _check_apk_so_zip_alignment(top_apk_path, zf, info)
				if align_err:
					result.errors.append(align_err)
			raw = zf.read(info.filename)
			result.inspected_so_count += 1
			result.inspected_names.append(name)
			result.errors.extend(inspect_elf_bytes(name, raw))
		elif lower.endswith((".imy", ".zip")):
			raw_nested = zf.read(info.filename)
			try:
				with zipfile.ZipFile(io.BytesIO(raw_nested), "r") as nested_zf:
					_inspect_zip_recursive(nested_zf, f"{name}::", result, None)
			except zipfile.BadZipFile as exc:
				result.errors.append(f"{name}: archivo ZIP/IMY corrupto o truncado ({exc})")


def _verify_aab_bundle_config(
	archive_path: Path, namelist: set[str], strict_aab: bool, result: VerificationResult
) -> None:
	if "BundleConfig.pb" not in namelist:
		result.errors.append(f"{archive_path.name}: falta BundleConfig.pb en el archivo AAB")
		return

	bundletool_cmd = find_bundletool_command()
	if bundletool_cmd is None:
		msg = f"{archive_path.name}: bundletool no encontrado para auditar PAGE_ALIGNMENT_16K en BundleConfig.pb"
		if strict_aab:
			result.errors.append(msg)
		else:
			result.warnings.append(msg)
		return

	proc = subprocess.run(
		[*bundletool_cmd, "dump", "config", "--bundle", str(archive_path)],
		capture_output=True,
		text=True,
		check=False,
	)
	if proc.returncode != 0:
		result.errors.append(
			f"{archive_path.name}: bundletool dump config falló (rc={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
		)
		return

	try:
		cfg = json.loads(proc.stdout)
		alignment = cfg.get("optimizations", {}).get("uncompressNativeLibraries", {}).get("alignment")
	except Exception as exc:
		result.errors.append(f"{archive_path.name}: no se pudo parsear JSON de bundletool dump config ({exc})")
		return

	if alignment != "PAGE_ALIGNMENT_16K":
		result.errors.append(
			f"{archive_path.name}: BundleConfig alignment inválido '{alignment}' (se requiere PAGE_ALIGNMENT_16K)"
		)


def _verify_apk_zipalign(archive_path: Path, result: VerificationResult) -> None:
	zipalign_cmd = find_zipalign_command()
	if zipalign_cmd is None:
		result.warnings.append(f"{archive_path.name}: zipalign no disponible en PATH/SDK; se usó verificación interna")
		return
	proc = subprocess.run(
		[zipalign_cmd, "-c", "-P", "16", "-v", "4", str(archive_path)],
		capture_output=True,
		text=True,
		check=False,
	)
	if proc.returncode != 0:
		detail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or ["exit != 0"]
		result.errors.append(f"{archive_path.name}: zipalign -c -P 16 -v 4 falló ({detail[0]})")


def verify_android_archive(archive_path: Path, strict_aab: bool = False) -> VerificationResult:
	"""Valida todas las bibliotecas nativas (.so directas y en .imy), ZIP alignment 16 KB y BundleConfig dentro de un APK/AAB."""
	result = VerificationResult(ok=True)
	if not archive_path.is_file():
		return VerificationResult(ok=False, errors=[f"Artefacto no encontrado: {archive_path}"])

	with zipfile.ZipFile(archive_path, "r") as zf:
		namelist = set(zf.namelist())
		_inspect_zip_recursive(zf, "", result, archive_path)

	if result.inspected_so_count == 0:
		result.errors.append(f"{archive_path.name}: no se encontraron bibliotecas nativas (.so) dentro del paquete")

	lower_name = archive_path.name.lower()
	if lower_name.endswith(".aab"):
		_verify_aab_bundle_config(archive_path, namelist, strict_aab, result)
	elif lower_name.endswith(".apk"):
		_verify_apk_zipalign(archive_path, result)

	result.ok = len(result.errors) == 0
	return result


def main(argv: list[str] | None = None) -> int:
	raw_args = list(argv if argv is not None else sys.argv[1:])
	strict_aab = False
	targets: list[str] = []
	for arg in raw_args:
		if arg == "--strict-aab":
			strict_aab = True
		else:
			targets.append(arg)

	if not targets:
		print("Uso: python3 scripts/verify_android_apk.py [--strict-aab] <apk_o_aab> [...]", file=sys.stderr)
		return 2

	overall_ok = True
	for raw_target in targets:
		path = Path(raw_target)
		res = verify_android_archive(path, strict_aab=strict_aab)
		for warn in res.warnings:
			print(f"⚠️  {warn}", file=sys.stderr)
		if res.ok:
			print(f"✅ {path.name}: {res.inspected_so_count} binarios .so verificados (16 KB OK, sin RUNPATH Termux)")
		else:
			overall_ok = False
			print(f"❌ {path.name}: falló la verificación ELF/16 KB ({len(res.errors)} problemas):")
			for err in res.errors:
				print(f"   • {err}")
	return 0 if overall_ok else 1


if __name__ == "__main__":
	sys.exit(main())
