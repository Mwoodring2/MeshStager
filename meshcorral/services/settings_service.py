"""Typed access to MeshStager preferences stored via :class:`~PySide6.QtCore.QSettings`."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from meshcorral.app.config import APP_NAME, LEGACY_APP_NAME


class SettingsService:
    """Read and write application settings (organization-scoped QSettings)."""

    ORG_NAME = "WoodringTools"
    APP_NAME = APP_NAME
    LEGACY_APP_NAME = LEGACY_APP_NAME

    KEY_THEME = "ui/theme_mode"
    KEY_INCLUDE_SUBFOLDERS = "scan/include_subfolders_default"
    KEY_SEARCH_MODE = "scan/search_mode"
    KEY_DEFAULT_DESTINATION = "transfer/default_destination"
    KEY_CONFIRM_BEFORE_MOVE = "transfer/confirm_before_move"
    KEY_BLENDER_EXECUTABLE = "bridge/blender_executable"
    KEY_MAYA_EXECUTABLE = "dcc/maya_executable"
    KEY_PREFERRED_DCC = "dcc/preferred_dcc"
    # Blender Bridge on-disk retention (automatic trim at startup): 30, 90, or 0=keep forever.
    KEY_BRIDGE_HISTORY_KEEP_DAYS = "bridge/history_keep_days"
    # After scan: auto-queue .stl/.obj thumbnail jobs (default off). Cap per scan: 25, 100, or 0=unlimited.
    KEY_AUTO_THUMBNAIL_AFTER_SCAN = "bridge/auto_thumbnail_after_scan"
    KEY_AUTO_THUMBNAIL_MAX_PER_SCAN = "bridge/auto_thumbnail_max_per_scan"
    KEY_THUMBNAIL_RENDERER_PREFERENCE = "bridge/thumbnail_renderer_preference"
    # Browse UI: file table vs icon gallery, and requested Blender thumbnail size (px).
    KEY_BROWSE_VIEW_MODE = "ui/browse_view_mode"
    KEY_THUMBNAIL_DISPLAY_PIXELS = "ui/thumbnail_display_pixels"

    CAP_AUTO_THUMB_25 = 25
    CAP_AUTO_THUMB_100 = 100
    CAP_AUTO_THUMB_UNLIMITED = 0

    VIEW_MODE_TABLE = "table"
    VIEW_MODE_GALLERY = "gallery"
    # Allowed thumbnail pixel steps (table thumb column + gallery).
    THUMB_PIXELS_48 = 48
    THUMB_PIXELS_96 = 96
    THUMB_PIXELS_160 = 160
    THUMB_PIXELS_256 = 256
    THUMB_PIXEL_CHOICES: tuple[int, ...] = (48, 96, 160, 256)

    BRIDGE_HISTORY_FOREVER_DAYS = 0
    BRIDGE_HISTORY_DAYS_DEFAULT = 30
    BRIDGE_HISTORY_DAYS_OPTIONAL: tuple[int, ...] = (0, BRIDGE_HISTORY_DAYS_DEFAULT, 90)

    THUMBNAIL_RENDERER_AUTO = "auto_recommended"
    THUMBNAIL_RENDERER_NATIVE_FIRST = "native_first"
    THUMBNAIL_RENDERER_BLENDER_FIRST = "blender_first"
    THUMBNAIL_RENDERER_MANUAL_ONLY = "manual_only"
    THUMBNAIL_RENDERER_CHOICES: tuple[str, ...] = (
        THUMBNAIL_RENDERER_AUTO,
        THUMBNAIL_RENDERER_NATIVE_FIRST,
        THUMBNAIL_RENDERER_BLENDER_FIRST,
        THUMBNAIL_RENDERER_MANUAL_ONLY,
    )

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings(self.ORG_NAME, self.APP_NAME)

    def theme_mode(self) -> str:
        """Return ``\"dark\"`` or ``\"light\"`` (invalid stored values fall back to dark)."""
        value = str(self._settings.value(self.KEY_THEME, "dark"))
        if value not in {"dark", "light"}:
            return "dark"
        return value

    def set_theme_mode(self, value: str) -> None:
        """Persist theme mode; unknown values are stored as dark."""
        if value not in {"dark", "light"}:
            value = "dark"
        self._settings.setValue(self.KEY_THEME, value)

    def include_subfolders_default(self) -> bool:
        """Default for the scan \"Include subfolders\" checkbox when the app starts."""
        return self._read_bool(self.KEY_INCLUDE_SUBFOLDERS, True)

    def set_include_subfolders_default(self, value: bool) -> None:
        """Persist default include-subfolders preference."""
        self._settings.setValue(self.KEY_INCLUDE_SUBFOLDERS, bool(value))

    def search_mode(self) -> str:
        """Return ``3d`` or ``images`` (the active Asset Mode for scans)."""
        value = str(self._settings.value(self.KEY_SEARCH_MODE, "3d"))
        if value not in {"3d", "images"}:
            return "3d"
        return value

    def set_search_mode(self, value: str) -> None:
        """Persist Asset Mode; unknown values are stored as ``3d``."""
        if value not in {"3d", "images"}:
            value = "3d"
        self._settings.setValue(self.KEY_SEARCH_MODE, value)

    def default_destination(self) -> str:
        """Optional default destination folder path (may be empty)."""
        return str(self._settings.value(self.KEY_DEFAULT_DESTINATION, ""))

    def set_default_destination(self, value: str) -> None:
        """Persist default destination (leading/trailing whitespace stripped)."""
        self._settings.setValue(self.KEY_DEFAULT_DESTINATION, value.strip())

    def confirm_before_move(self) -> bool:
        """If True, show an extra confirmation after the move preview before executing."""
        return self._read_bool(self.KEY_CONFIRM_BEFORE_MOVE, True)

    def set_confirm_before_move(self, value: bool) -> None:
        """Persist confirm-before-move preference."""
        self._settings.setValue(self.KEY_CONFIRM_BEFORE_MOVE, bool(value))

    def blender_executable(self) -> str:
        """
        Optional Blender executable path.

        When empty, Blender Bridge jobs should be considered unavailable (the app must still
        function without Blender installed).
        """
        return str(self._settings.value(self.KEY_BLENDER_EXECUTABLE, "")).strip()

    def set_blender_executable(self, value: str) -> None:
        """Persist Blender executable path (leading/trailing whitespace stripped)."""
        self._settings.setValue(self.KEY_BLENDER_EXECUTABLE, value.strip())

    def maya_executable(self) -> str:
        """Optional Maya executable path (maya.exe)."""
        return str(self._settings.value(self.KEY_MAYA_EXECUTABLE, "")).strip()

    def set_maya_executable(self, value: str) -> None:
        """Persist Maya executable path (leading/trailing whitespace stripped)."""
        self._settings.setValue(self.KEY_MAYA_EXECUTABLE, value.strip())

    def preferred_dcc(self) -> str:
        """
        Preferred DCC routing for “Open” actions.

        Values:
        - ``auto``: route by extension ownership mapping when possible
        - a DCC id like ``blender`` or ``maya``
        """
        v = str(self._settings.value(self.KEY_PREFERRED_DCC, "auto")).strip().lower()
        return v or "auto"

    def set_preferred_dcc(self, value: str) -> None:
        """Persist preferred DCC id or ``auto``."""
        v = (value or "").strip().lower()
        self._settings.setValue(self.KEY_PREFERRED_DCC, v or "auto")

    def auto_thumbnail_after_scan(self) -> bool:
        """If True, queue missing Blender thumbnails for .stl/.obj after each scan (3D mode)."""
        return self._read_bool(self.KEY_AUTO_THUMBNAIL_AFTER_SCAN, False)

    def set_auto_thumbnail_after_scan(self, value: bool) -> None:
        """Persist auto-thumbnail-after-scan."""
        self._settings.setValue(self.KEY_AUTO_THUMBNAIL_AFTER_SCAN, bool(value))

    def auto_thumbnail_max_per_scan(self) -> int:
        """
        Max auto-queued jobs per scan: :attr:`CAP_AUTO_THUMB_25`, :attr:`CAP_AUTO_THUMB_100`, or
        :attr:`CAP_AUTO_THUMB_UNLIMITED` (0) for no cap. Invalid values default to 25.
        """
        value = self._settings.value(
            self.KEY_AUTO_THUMBNAIL_MAX_PER_SCAN,
            self.CAP_AUTO_THUMB_25,
        )
        try:
            n = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self.CAP_AUTO_THUMB_25
        if n in (
            self.CAP_AUTO_THUMB_25,
            self.CAP_AUTO_THUMB_100,
            self.CAP_AUTO_THUMB_UNLIMITED,
        ):
            return n
        return self.CAP_AUTO_THUMB_25

    def set_auto_thumbnail_max_per_scan(self, value: int) -> None:
        """Persist cap; use :attr:`CAP_AUTO_THUMB_*` constants only."""
        if value not in (
            self.CAP_AUTO_THUMB_25,
            self.CAP_AUTO_THUMB_100,
            self.CAP_AUTO_THUMB_UNLIMITED,
        ):
            value = self.CAP_AUTO_THUMB_25
        self._settings.setValue(self.KEY_AUTO_THUMBNAIL_MAX_PER_SCAN, int(value))

    def thumbnail_renderer_preference(self) -> str:
        """
        Thumbnail backend preference for automatic generation.

        Default: ``auto_recommended`` (native CPU for STL/OBJ; Blender for specialized formats).
        """
        v = str(
            self._settings.value(
                self.KEY_THUMBNAIL_RENDERER_PREFERENCE,
                self.THUMBNAIL_RENDERER_AUTO,
            )
        ).strip()
        if v not in self.THUMBNAIL_RENDERER_CHOICES:
            return self.THUMBNAIL_RENDERER_AUTO
        return v

    def set_thumbnail_renderer_preference(self, value: str) -> None:
        """Persist thumbnail renderer preference."""
        v = (value or "").strip()
        if v not in self.THUMBNAIL_RENDERER_CHOICES:
            v = self.THUMBNAIL_RENDERER_AUTO
        self._settings.setValue(self.KEY_THUMBNAIL_RENDERER_PREFERENCE, v)

    def browse_view_mode(self) -> str:
        """``table`` (default) or :attr:`VIEW_MODE_GALLERY`."""
        v = str(self._settings.value(self.KEY_BROWSE_VIEW_MODE, self.VIEW_MODE_TABLE))
        if v not in (self.VIEW_MODE_TABLE, self.VIEW_MODE_GALLERY):
            return self.VIEW_MODE_TABLE
        return v

    def set_browse_view_mode(self, value: str) -> None:
        """Persist browse view: table or gallery."""
        if value not in (self.VIEW_MODE_TABLE, self.VIEW_MODE_GALLERY):
            value = self.VIEW_MODE_TABLE
        self._settings.setValue(self.KEY_BROWSE_VIEW_MODE, value)

    def thumbnail_display_pixels(self) -> int:
        """
        Thumbnail size in device-independent pixels: one of :attr:`THUMB_PIXEL_CHOICES`
        (default 48).
        """
        v = self._settings.value(
            self.KEY_THUMBNAIL_DISPLAY_PIXELS,
            self.THUMB_PIXELS_48,
        )
        try:
            n = int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self.THUMB_PIXELS_48
        if n in self.THUMB_PIXEL_CHOICES:
            return n
        return self.THUMB_PIXELS_48

    def set_thumbnail_display_pixels(self, value: int) -> None:
        """Persist thumb size; must be a member of :attr:`THUMB_PIXEL_CHOICES`."""
        if value not in self.THUMB_PIXEL_CHOICES:
            value = self.THUMB_PIXELS_48
        self._settings.setValue(self.KEY_THUMBNAIL_DISPLAY_PIXELS, int(value))

    def bridge_history_keep_days(self) -> int:
        """
        Auto-trim bridge job outputs older than this many days at startup.

        ``0`` means **keep forever** (no automatic purge). Allowed values: ``0``, ``30``, ``90``.
        """
        value = self._settings.value(
            self.KEY_BRIDGE_HISTORY_KEEP_DAYS,
            self.BRIDGE_HISTORY_DAYS_DEFAULT,
        )
        try:
            n = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return self.BRIDGE_HISTORY_DAYS_DEFAULT
        if n in self.BRIDGE_HISTORY_DAYS_OPTIONAL:
            return n
        return self.BRIDGE_HISTORY_DAYS_DEFAULT

    def set_bridge_history_keep_days(self, value: int) -> None:
        """Persist automatic bridge retention; must be one of :attr:`BRIDGE_HISTORY_DAYS_OPTIONAL`."""
        if value not in self.BRIDGE_HISTORY_DAYS_OPTIONAL:
            value = self.BRIDGE_HISTORY_DAYS_DEFAULT
        self._settings.setValue(self.KEY_BRIDGE_HISTORY_KEEP_DAYS, int(value))

    def _read_bool(self, key: str, default: bool) -> bool:
        value = self._settings.value(key, default)

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}

        return bool(value)
