"""Pruebas para el verificador de binarios ELF y alineamiento de 16 KB en APK/AAB."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

from scripts.verify_android_apk import inspect_elf_bytes, verify_android_archive


def _build_elf64(
	*,
	e_machine: int = 183,  # EM_AARCH64
	p_align: int = 0x4000,
	runpath: bytes | None = None,
	truncate_phdr: bool = False,
) -> bytes:
	ehdr_size = 64
	phdr_size = 56
	phnum = 2 if runpath is not None else 1
	phoff = ehdr_size
	code_off = 0x1000
	strtab = (runpath + b"\x00") if runpath is not None else b""
	dyn_entries = b""
	if runpath is not None:
		dyn_off = code_off + 0x100
		strtab_off = code_off + 0x200
		dyn_entries = (
			struct.pack("<qQ", 5, strtab_off)  # DT_STRTAB
			+ struct.pack("<qQ", 10, len(strtab))  # DT_STRSZ
			+ struct.pack("<qQ", 29, 0)  # DT_RUNPATH
			+ struct.pack("<qQ", 0, 0)  # DT_NULL
		)
	else:
		dyn_off = 0
		strtab_off = 0

	total_size = max(code_off + 0x300, phoff + phnum * phdr_size)
	buf = bytearray(total_size)

	# ELF64 header
	struct.pack_into(
		"<16sHHIQQQIHHHHHH",
		buf,
		0,
		b"\x7fELF\x02\x01\x01" + b"\x00" * 9,
		3,  # ET_DYN
		e_machine,
		1,  # EV_CURRENT
		0,
		phoff,
		0,
		0,
		ehdr_size,
		phdr_size,
		phnum,
		0,
		0,
		0,
	)

	# PT_LOAD
	struct.pack_into(
		"<IIQQQQQQ",
		buf,
		phoff,
		1,  # PT_LOAD
		5,  # PF_R | PF_X
		0,
		0,
		0,
		len(buf),
		len(buf),
		p_align,
	)

	if runpath is not None:
		struct.pack_into(
			"<IIQQQQQQ",
			buf,
			phoff + phdr_size,
			2,  # PT_DYNAMIC
			6,
			dyn_off,
			dyn_off,
			dyn_off,
			len(dyn_entries),
			len(dyn_entries),
			8,
		)
		buf[dyn_off : dyn_off + len(dyn_entries)] = dyn_entries
		buf[strtab_off : strtab_off + len(strtab)] = strtab

	if truncate_phdr:
		return bytes(buf[: phoff + 10])
	return bytes(buf)


def test_inspect_elf_rejects_truncated_phdr_4kb_align_abi_mismatch_and_termux() -> None:
	ok_elf = _build_elf64(e_machine=183, p_align=0x4000)
	assert inspect_elf_bytes("lib/arm64-v8a/libok.so", ok_elf) == []

	trunc_elf = _build_elf64(truncate_phdr=True)
	assert any("truncada" in err.lower() for err in inspect_elf_bytes("lib/arm64-v8a/libtrunc.so", trunc_elf))

	bad_align = _build_elf64(p_align=0x1000)
	assert any("0x4000" in err for err in inspect_elf_bytes("lib/arm64-v8a/lib4k.so", bad_align))

	abi_mismatch = _build_elf64(e_machine=62, p_align=0x4000)  # x86_64 ELF en carpeta arm64
	assert any("abi" in err.lower() for err in inspect_elf_bytes("lib/arm64-v8a/libwrong.so", abi_mismatch))

	termux_elf = _build_elf64(runpath=b"/data/data/com.termux/files/usr/lib")
	assert any("com.termux" in err for err in inspect_elf_bytes("lib/arm64-v8a/libtermux.so", termux_elf))


def test_verify_android_archive_checks_apk_16kb_zip_alignment(tmp_path: Path) -> None:
	elf_bytes = _build_elf64(e_machine=183, p_align=0x4000)
	apk_unaligned = tmp_path / "unaligned.apk"
	with zipfile.ZipFile(apk_unaligned, "w", compression=zipfile.ZIP_STORED) as zf:
		zf.writestr("lib/arm64-v8a/libfoo.so", elf_bytes)

	res_unaligned = verify_android_archive(apk_unaligned)
	assert not res_unaligned.ok
	assert any("zip" in err.lower() or "alinea" in err.lower() for err in res_unaligned.errors)

	# Construimos un APK donde el payload de libfoo.so arranque exactamente en múltiplo de 0x4000
	apk_aligned = tmp_path / "aligned.apk"
	with zipfile.ZipFile(apk_aligned, "w", compression=zipfile.ZIP_STORED) as zf:
		info = zipfile.ZipInfo("lib/arm64-v8a/libfoo.so")
		# Local file header = 30 + len(filename); calculamos padding en extra field para llegar a 0x4000
		name_len = len(info.filename.encode("utf-8"))
		pad_needed = (0x4000 - (30 + name_len + 4)) % 0x4000
		# Extra field formato ZIP: header ID (0xFFFF) + data size (pad_needed) + zero bytes
		info.extra = struct.pack("<HH", 0xFFFF, pad_needed) + (b"\x00" * pad_needed)
		zf.writestr(info, elf_bytes)

	res_aligned = verify_android_archive(apk_aligned)
	assert res_aligned.ok, res_aligned.errors


def test_build_android_fails_without_sdk_unless_sync_only(tmp_path: Path, monkeypatch) -> None:
	"""build_android sin --sync-only debe fallar (exit != 0) si falta el Android SDK."""
	from scripts import build_android as build_mod

	(tmp_path / "app").mkdir()
	(tmp_path / "dist").mkdir()
	(tmp_path / "android").mkdir()
	monkeypatch.setattr(build_mod, "stage_android_assets", lambda *_a, **_k: tmp_path / "android")
	monkeypatch.setattr(build_mod.subprocess, "run", lambda *_a, **_k: None)
	monkeypatch.setattr(build_mod, "has_android_sdk", lambda *_a, **_k: False)

	assert build_mod.build_android(root_dir=tmp_path, skip_frontend=True, sync_only=True) == 0
	assert build_mod.build_android(root_dir=tmp_path, skip_frontend=True, sync_only=False) == 1


def test_verify_android_archive_rejects_corrupt_nested_zip_incongruent_elf_and_invalid_aab(
	tmp_path: Path, monkeypatch
) -> None:
	"""Valida congruencia p_offset/p_vaddr, límites de segmento, .imy corrupto y BundleConfig de AAB."""
	from scripts import verify_android_apk as vmod

	# 1. Segmento PT_LOAD con p_offset % p_align != p_vaddr % p_align
	bad_congruence = bytearray(_build_elf64(e_machine=183, p_align=0x4000))
	# Cambiamos p_vaddr de 0 a 0x100 manteniendo p_offset = 0
	struct.pack_into("<Q", bad_congruence, 64 + 16, 0x100)
	issues = inspect_elf_bytes("lib/arm64-v8a/libcong.so", bytes(bad_congruence))
	assert any("congruencia" in e.lower() or "p_vaddr" in e.lower() for e in issues)

	# 2. Segmento PT_LOAD fuera de los límites del archivo
	bad_bounds = bytearray(_build_elf64(e_machine=183, p_align=0x4000))
	struct.pack_into("<Q", bad_bounds, 64 + 32, len(bad_bounds) + 4096)  # p_filesz > len(data)
	issues_bounds = inspect_elf_bytes("lib/arm64-v8a/libbounds.so", bytes(bad_bounds))
	assert any("límite" in e.lower() or "rango" in e.lower() or "filesz" in e.lower() for e in issues_bounds)

	# 3. Archivo .imy corrupto no debe omitirse silenciosamente
	ok_elf = _build_elf64(e_machine=183, p_align=0x4000)
	apk_corrupt_imy = tmp_path / "corrupt_imy.apk"
	with zipfile.ZipFile(apk_corrupt_imy, "w", compression=zipfile.ZIP_STORED) as zf:
		info = zipfile.ZipInfo("lib/arm64-v8a/libok.so")
		pad = (0x4000 - (30 + len(info.filename.encode()) + 4)) % 0x4000
		info.extra = struct.pack("<HH", 0xFFFF, pad) + (b"\x00" * pad)
		zf.writestr(info, ok_elf)
		zf.writestr("assets/chaquopy/bad.imy", b"NOT_A_ZIP_AT_ALL")
	res_imy = verify_android_archive(apk_corrupt_imy)
	assert not res_imy.ok
	assert any("bad.imy" in err for err in res_imy.errors)

	# 4. AAB sin BundleConfig.pb debe fallar
	aab_missing_cfg = tmp_path / "no_cfg.aab"
	with zipfile.ZipFile(aab_missing_cfg, "w") as zf:
		zf.writestr("base/lib/arm64-v8a/libok.so", ok_elf)
	res_no_cfg = verify_android_archive(aab_missing_cfg, strict_aab=True)
	assert not res_no_cfg.ok
	assert any("BundleConfig.pb" in err for err in res_no_cfg.errors)

	# 5. AAB con bundletool reportando 4KB vs 16KB
	aab_with_cfg = tmp_path / "with_cfg.aab"
	with zipfile.ZipFile(aab_with_cfg, "w") as zf:
		zf.writestr("BundleConfig.pb", b"\x08\x01")
		zf.writestr("base/lib/arm64-v8a/libok.so", ok_elf)

	monkeypatch.setattr(vmod, "find_bundletool_command", lambda: ["bundletool"])

	class _Res4k:
		returncode = 0
		stdout = '{"optimizations":{"uncompressNativeLibraries":{"alignment":"PAGE_ALIGNMENT_4K"}}}'
		stderr = ""

	monkeypatch.setattr(vmod.subprocess, "run", lambda *_a, **_k: _Res4k())
	res_4k_aab = verify_android_archive(aab_with_cfg, strict_aab=True)
	assert not res_4k_aab.ok
	assert any("PAGE_ALIGNMENT_16K" in err for err in res_4k_aab.errors)

	class _Res16k:
		returncode = 0
		stdout = '{"optimizations":{"uncompressNativeLibraries":{"alignment":"PAGE_ALIGNMENT_16K"}}}'
		stderr = ""

	monkeypatch.setattr(vmod.subprocess, "run", lambda *_a, **_k: _Res16k())
	res_16k_aab = verify_android_archive(aab_with_cfg, strict_aab=True)
	assert res_16k_aab.ok, res_16k_aab.errors


def test_build_gradle_uses_monotonic_version_code_beyond_date_only() -> None:
	"""build.gradle debe generar versionCode monotónico (no solo yyMMdd) y validar colisiones ABI."""
	gradle_text = Path("android/app/build.gradle").read_text(encoding="utf-8")
	assert "HOUR_OF_DAY" in gradle_text or "MINUTE" in gradle_text
	assert "ROCKOLA_VERSION_CODE" in gradle_text
	assert "versionCode baseVersionCode * 10 + 1" in gradle_text
	assert "versionCode baseVersionCode * 10 + 2" in gradle_text
