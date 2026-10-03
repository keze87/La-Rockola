# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

datas = [
    ("dist", "dist"),
    ("scripts/fortune-es", "scripts/fortune-es"),
]

favicon = Path("public/favicon.ico")
icon_path = str(favicon) if favicon.exists() else None

hiddenimports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "websockets",
    "websockets.legacy",
    "websockets.legacy.server",
    "websockets.asyncio",
    "websockets.asyncio.server",
    "sqlite3",
    "mutagen",
    "mutagen.mp3",
    "mutagen.flac",
    "mutagen.oggvorbis",
    "mutagen.mp4",
    "mutagen.wave",
    "mutagen.id3",
    "pydantic",
    "fastapi",
    "starlette",
    "scripts",
    "scripts.binary_utils",
    "scripts.mpv_installer",
    "scripts.ytdlp_installer",
    "scripts.fpcalc_installer",
    "scripts.ffmpeg_installer",
    "scripts.radio_announcer",
    "scripts.radio_banks",
    "binary_utils",
    "mpv_installer",
    "ytdlp_installer",
    "fpcalc_installer",
    "ffmpeg_installer",
    "radio_announcer",
    "radio_banks",
    "edge_tts",
    "certifi",
    "aiohttp",
    "PIL",
    "PIL.Image",
]

import sys
if sys.platform != "win32":
    hiddenimports.extend(["dbus_next", "dbus_next.aio", "dbus_next.service"])

a = Analysis(
    ["server.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "librosa",
        "numpy",
        "numba",
        "llvmlite",
        "soundfile",
        "soxr",
        "torch",
        "pandas",
        "IPython",
        "pytest",
        "black",
        "jedi",
        "parso",
        "wx",
        "gevent",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="larockola",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
