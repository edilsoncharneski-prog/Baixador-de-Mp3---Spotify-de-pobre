# -*- mode: python ; coding: utf-8 -*-
import os
import shutil
import sysconfig

from PyInstaller.utils.hooks import collect_all


datas = []
binaries = []
hiddenimports = ["darkdetect"]

if os.path.exists("icon.ico"):
    datas.append(("icon.ico", "."))

for binary_name in ["ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe"]:
    binary_path = binary_name
    if binary_name == "yt-dlp.exe" and not os.path.exists(binary_path):
        scripts_path = sysconfig.get_path("scripts")
        candidate_path = os.path.join(scripts_path, binary_name) if scripts_path else None
        binary_path = candidate_path if candidate_path and os.path.exists(candidate_path) else None

    if binary_path and os.path.exists(binary_path):
        binaries.append((binary_path, "."))

tmp_ret = collect_all("customtkinter")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ["main_gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BibliotecaOffline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico" if os.path.exists("icon.ico") else None,
    version="version_info.txt",
)
