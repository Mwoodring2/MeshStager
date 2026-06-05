"""DCC integration registry (lightweight, v0.1-safe).

This is intentionally not a plugin system and does not parse files or generate thumbnails.
It only defines discovery and "open file in DCC" affordances.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meshcorral.services.settings_service import SettingsService


@dataclass(frozen=True, slots=True)
class DCCCapabilities:
    """
    What a DCC integration can do inside Roundup.

    This is intentionally lightweight: no file parsing, no plugins, no scripting.
    """

    can_open: bool
    can_generate_thumbnails: bool
    can_reveal_project: bool
    can_batch_process: bool
    supports_scene_files: bool
    supports_geometry_files: bool


@dataclass(frozen=True, slots=True)
class DCCProfile:
    """Definition for a DCC integration."""

    id: str
    display_name: str
    executable_names: tuple[str, ...]
    supported_extensions: frozenset[str]
    manual_path_setting_key: str
    capabilities: DCCCapabilities

    @property
    def supports_open_file(self) -> bool:
        """Back-compat for older call sites; prefer :attr:`capabilities`."""
        return bool(self.capabilities.can_open)

    @property
    def supports_thumbnail_generation(self) -> bool:
        """Back-compat for older call sites; prefer :attr:`capabilities`."""
        return bool(self.capabilities.can_generate_thumbnails)


BLENDER_PROFILE = DCCProfile(
    id="blender",
    display_name="Blender",
    executable_names=("blender.exe", "blender"),
    supported_extensions=frozenset({".blend"}),
    manual_path_setting_key="bridge/blender_executable",
    capabilities=DCCCapabilities(
        can_open=True,
        can_generate_thumbnails=True,
        can_reveal_project=False,
        can_batch_process=False,
        supports_scene_files=True,
        supports_geometry_files=True,
    ),
)

MAYA_PROFILE = DCCProfile(
    id="maya",
    display_name="Maya",
    executable_names=("maya.exe", "maya"),
    supported_extensions=frozenset({".ma", ".mb"}),
    manual_path_setting_key="dcc/maya_executable",
    capabilities=DCCCapabilities(
        can_open=True,
        can_generate_thumbnails=False,
        can_reveal_project=False,
        can_batch_process=False,
        supports_scene_files=True,
        supports_geometry_files=True,
    ),
)

ZBRUSH_PROFILE = DCCProfile(
    id="zbrush",
    display_name="ZBrush",
    executable_names=(),
    supported_extensions=frozenset({".ztl", ".zpr"}),
    manual_path_setting_key="dcc/zbrush_executable",
    capabilities=DCCCapabilities(
        can_open=False,
        can_generate_thumbnails=False,
        can_reveal_project=False,
        can_batch_process=False,
        supports_scene_files=True,
        supports_geometry_files=False,
    ),
)

SUBSTANCE_PROFILE = DCCProfile(
    id="substance",
    display_name="Substance 3D",
    executable_names=(),
    supported_extensions=frozenset({".spp", ".sbsar", ".sbs"}),
    manual_path_setting_key="dcc/substance_executable",
    capabilities=DCCCapabilities(
        can_open=False,
        can_generate_thumbnails=False,
        can_reveal_project=False,
        can_batch_process=False,
        supports_scene_files=True,
        supports_geometry_files=False,
    ),
)

HOUDINI_PROFILE = DCCProfile(
    id="houdini",
    display_name="Houdini",
    executable_names=(),
    supported_extensions=frozenset({".hip", ".hiplc", ".hipnc"}),
    manual_path_setting_key="dcc/houdini_executable",
    capabilities=DCCCapabilities(
        can_open=False,
        can_generate_thumbnails=False,
        can_reveal_project=False,
        can_batch_process=False,
        supports_scene_files=True,
        supports_geometry_files=True,
    ),
)


# Extension → "owning" DCC id for more professional labeling and routing.
DCC_FILE_ASSOCIATIONS: dict[str, str] = {
    ".blend": "blender",
    ".ma": "maya",
    ".mb": "maya",
    ".ztl": "zbrush",
    ".zpr": "zbrush",
    ".spp": "substance",
    ".sbs": "substance",
    ".sbsar": "substance",
    ".hip": "houdini",
    ".hiplc": "houdini",
    ".hipnc": "houdini",
}

# Extension → professional kind label for the inspector subtitle.
DCC_EXTENSION_KIND_LABEL: dict[str, str] = {
    ".blend": "SCENE",
    ".ma": "SCENE",
    ".mb": "SCENE",
    ".ztl": "TOOL",
    ".zpr": "PROJECT",
    ".spp": "PROJECT",
    ".sbs": "GRAPH",
    ".sbsar": "MATERIAL",
    ".hip": "SCENE",
    ".hiplc": "SCENE",
    ".hipnc": "SCENE",
}


def all_dcc_profiles() -> tuple[DCCProfile, ...]:
    """Return the supported DCC profiles (stable order for UI)."""

    return (
        BLENDER_PROFILE,
        MAYA_PROFILE,
        ZBRUSH_PROFILE,
        SUBSTANCE_PROFILE,
        HOUDINI_PROFILE,
    )


def dcc_profile_for_id(dcc_id: str) -> DCCProfile | None:
    """Return the DCC profile for *dcc_id* when known."""
    want = (dcc_id or "").strip().lower()
    for p in all_dcc_profiles():
        if p.id == want:
            return p
    return None


def get_dcc_profile(dcc_id: str) -> DCCProfile | None:
    """Public helper alias for :func:`dcc_profile_for_id`."""
    return dcc_profile_for_id(dcc_id)


def dcc_id_for_extension(ext: str) -> str | None:
    """Return owning DCC id for *ext* (lowercase, with leading dot)."""
    e = (ext or "").strip().lower()
    if not e:
        return None
    if not e.startswith("."):
        e = f".{e}"
    return DCC_FILE_ASSOCIATIONS.get(e)


def dcc_profile_for_extension(ext: str) -> DCCProfile | None:
    """Return owning DCC profile for *ext* when mapped, else ``None``."""
    dcc_id = dcc_id_for_extension(ext)
    if dcc_id is None:
        return None
    return dcc_profile_for_id(dcc_id)


def configured_executable_for_profile(
    profile: DCCProfile, settings_service: SettingsService
) -> Path | None:
    """
    Return a configured executable path for *profile*, or ``None`` if unavailable.

    Resolution:
    - If the manual path setting is present and points to a file, use it.
    - Otherwise call the existing locator for that DCC.
    """
    pid = (profile.id or "").strip().lower()
    if pid == "blender":
        raw = (settings_service.blender_executable() or "").strip()
        if raw:
            p = Path(raw)
            if p.is_file():
                return p.resolve()
        from meshcorral.app.bridge.blender_locator import find_blender_executable

        return find_blender_executable(settings_service)
    if pid == "maya":
        raw = (settings_service.maya_executable() or "").strip()
        if raw:
            p = Path(raw)
            if p.is_file():
                return p.resolve()
        from meshcorral.app.dcc.maya_locator import find_maya_executable

        return find_maya_executable(settings_service)
    return None

