#!/usr/bin/env python3
"""
Verificador binario ELF de alineamiento de 16 KB (0x4000) y saneamiento de RUNPATH
para APKs y AABs Android (incluidos archivos .so dentro de paquetes .imy de Chaquopy).
"""

from __future__ import annotations

import io
import struct
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


@dataclass(slots=True)
class VerificationResult:
	"""Resultado del análisis ELF sobre un artefacto APK/AAB."""

	ok: bool
	inspected_so_count: int = 0
	inspected_names: list[str] = field(default_factory=list)
	errors: list[str] = field(default_factory=list)


def _vaddr_to_offset(vaddr: int, load_segments: list[tuple[int, int, int, int]]) -> int | None:
	for p_offset, p_vaddr, _p_filesz, p_memsz in load_segments:
		if p_vaddr <= vaddr < p_vaddr + p_memsz:
			return p_offset + (vaddr - p_vaddr)
	return None


def inspect_elf_bytes(label: str, data: bytes) -> list[str]:
	"""Inspecciona headers ELF32/ELF64 para validar PT_LOAD >= 0x4000 y ausencia de com.termux en RUNPATH."""
	if len(data) < 52 or data[:4] != b"\x7fELF":
		return [f"{label}: no es un binario ELF válido"]

	ei_class = data[4]
	ei_data = data[5]
	endian = "<" if ei_data == 1 else ">" if ei_data == 2 else ""
	if not endian:
		return [f"{label}: endianness ELF desconocida ({ei_data})"]

	issues: list[str] = []
	load_segments: list[tuple[int, int, int, int]] = []
	dynamic_segment: tuple[int, int] | None = None

	if ei_class == 2:
		if len(data) < 64:
			return [f"{label}: cabecera ELF64 truncada"]
		e_phoff, e_phentsize, e_phnum = (
			struct.unpack_from(f"{endian}Q", data, 32)[0],
			*struct.unpack_from(f"{endian}HH", data, 54),
		)
		for idx in range(e_phnum):
			off = e_phoff + idx * e_phentsize
			if off + 56 > len(data):
				break
			p_type, _p_flags, p_offset, p_vaddr, _p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from(
				f"{endian}IIQQQQQQ", data, off
			)
			if p_type == PT_LOAD:
				load_segments.append((p_offset, p_vaddr, p_filesz, p_memsz))
				if p_align < REQUIRED_ALIGN_16KB:
					issues.append(
						f"{label}: segmento PT_LOAD con alineamiento 0x{p_align:x} < 0x{REQUIRED_ALIGN_16KB:x} (no compatible 16 KB)"
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
		for idx in range(e_phnum):
			off = e_phoff + idx * e_phentsize
			if off + 32 > len(data):
				break
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


def _inspect_zip_recursive(zf: zipfile.ZipFile, prefix: str, result: VerificationResult) -> None:
	for info in zf.infolist():
		if info.is_dir():
			continue
		name = f"{prefix}{info.filename}"
		lower = info.filename.lower()
		if lower.endswith(".so"):
			raw = zf.read(info.filename)
			result.inspected_so_count += 1
			result.inspected_names.append(name)
			result.errors.extend(inspect_elf_bytes(name, raw))
		elif lower.endswith((".imy", ".zip")):
			raw_nested = zf.read(info.filename)
			try:
				with zipfile.ZipFile(io.BytesIO(raw_nested), "r") as nested_zf:
					_inspect_zip_recursive(nested_zf, f"{name}::", result)
			except zipfile.BadZipFile:
				continue


def verify_android_archive(archive_path: Path) -> VerificationResult:
	"""Valida todas las bibliotecas nativas (.so directas y en .imy) dentro de un APK o AAB."""
	result = VerificationResult(ok=True)
	if not archive_path.is_file():
		return VerificationResult(ok=False, errors=[f"Artefacto no encontrado: {archive_path}"])

	with zipfile.ZipFile(archive_path, "r") as zf:
		_inspect_zip_recursive(zf, "", result)

	if result.inspected_so_count == 0:
		result.errors.append(f"{archive_path.name}: no se encontraron bibliotecas nativas (.so) dentro del paquete")

	result.ok = len(result.errors) == 0
	return result


def main(argv: list[str] | None = None) -> int:
	targets = argv if argv is not None else sys.argv[1:]
	if not targets:
		print("Uso: python3 scripts/verify_android_apk.py <apk_o_aab> [...]", file=sys.stderr)
		return 2

	overall_ok = True
	for raw_target in targets:
		path = Path(raw_target)
		res = verify_android_archive(path)
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
