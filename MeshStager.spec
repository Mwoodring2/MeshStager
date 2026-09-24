# -*- mode: python ; coding: utf-8 -*-

# Canonical PyInstaller input for MeshStager: both scripts/build_exe.bat (dev EXE) and
# scripts/build_shareable_windows.py (release portable ZIP) build from this file, so the
# two paths cannot drift apart on entry point, icon, windowed mode, or dependencies.
#
# HIDDEN_IMPORTS pins the native-renderer stack that static analysis can miss. MeshStager
# imports SciPy inside a guarded function (mesh_render_pipeline._load_mesh) and probes it
# with importlib.util.find_spec (native_renderer_health), while trimesh reaches SciPy
# through try/except wrappers. Naming the packages keeps them in the bundle no matter how
# those call sites are refactored. Only the subpackages the render path needs are listed;
# PyInstaller's bundled scipy hooks collect the matching extension modules and DLLs.
HIDDEN_IMPORTS = [
    'scipy',
    'scipy.sparse',
    'scipy.sparse.csgraph',
    'scipy.spatial',
]

a = Analysis(
    ['run_frozen.py'],
    pathex=['.'],
    binaries=[],
    # EXE.icon brands the executable; Qt also needs the artwork at runtime.
    datas=[('assets/icons', 'assets/icons')],
    hiddenimports=HIDDEN_IMPORTS,
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
    [],
    exclude_binaries=True,
    name='MeshStager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icons/MeshStager_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MeshStager',
)
