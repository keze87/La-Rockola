# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

datas = [
    ("dist", "dist"),
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
]

a = Analysis(
    ["server.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy"],
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
