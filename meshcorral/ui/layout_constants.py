"""
Layout constants for DPI/scaling regression checks (Prime v1.0 RC).

Values are tuned for 100%–150% Windows display scaling and narrow right panels.
"""

from __future__ import annotations

# Main window splitter / right column
MIN_RIGHT_PANEL_WIDTH: int = 320
DEFAULT_RIGHT_PANEL_WIDTH: int = 418
MAX_RIGHT_PANEL_WIDTH: int = 560

# Inspector tab bar and preview blocks
MIN_INSPECTOR_TAB_WIDTH: int = 56
INSPECTOR_TAB_MIN_HEIGHT: int = 28
INSPECTOR_PREVIEW_MIN_HEIGHT_3D: int = 128
INSPECTOR_PREVIEW_MIN_HEIGHT_IMAGES: int = 160
# Shared square framing for inspector preview pixmap (gallery/table use cell size).
INSPECTOR_PREVIEW_FRAME_PX: int = 280

# Shared control metrics (match theme / main window)
CONTROL_HEIGHT: int = 32
SECTION_GAP: int = 12
PANEL_GAP: int = 8

# Dialog minimum widths (100% baseline; Qt scales with DPI)
DIALOG_MIN_WIDTH: int = 420
SETTINGS_DIALOG_MIN_WIDTH: int = 520
SETTINGS_DIALOG_MIN_HEIGHT: int = 460
LARGE_FOLDER_DIALOG_MIN_WIDTH: int = 480
LARGE_FOLDER_DIALOG_MIN_HEIGHT: int = 360
COMPACT_DIALOG_MIN_HEIGHT: int = 200
SCAN_OPTIONS_DIALOG_MIN_HEIGHT: int = 220
TAG_DIALOG_MIN_WIDTH: int = 360
TAG_DIALOG_MIN_HEIGHT: int = 240
ABOUT_DIALOG_MIN_WIDTH: int = 360
ABOUT_DIALOG_MIN_HEIGHT: int = 180
BLENDER_QUEUE_DIALOG_MIN_WIDTH: int = 640
BLENDER_QUEUE_DIALOG_MIN_HEIGHT: int = 280
BLENDER_JOB_HISTORY_DIALOG_MIN_WIDTH: int = 640
BLENDER_JOB_HISTORY_DIALOG_MIN_HEIGHT: int = 320
MOVE_PREVIEW_DIALOG_MIN_WIDTH: int = 640
MOVE_PREVIEW_DIALOG_MIN_HEIGHT: int = 320
