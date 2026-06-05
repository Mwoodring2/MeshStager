"""Shared brand colors and application stylesheet (The Yard / Roundup suite identity)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

APP_COLORS = {
    "bg": "#0F1115",
    "surface": "#1E2126",
    "surface_2": "#2B2F36",
    "border": "#3A404A",
    "text": "#E6E6E6",
    "muted": "#A8B0BA",
    "primary": "#4A7BD1",
    "success": "#2E7D32",
    "warning": "#E67E22",
    "danger": "#C94C4C",
}

LIGHT_APP_COLORS = {
    "bg": "#ECEEF1",
    "surface": "#FFFFFF",
    "surface_2": "#DDE1E8",
    "border": "#B4BAC4",
    "text": "#1A1D22",
    "muted": "#5F6368",
    "primary": "#1A5FB4",
    "success": "#1B5E20",
    "warning": "#E65100",
    "danger": "#C62828",
}


def _palette_colors(theme_mode: str) -> dict[str, str]:
    """Return the active color token map for ``theme_mode``."""
    if theme_mode == "light":
        return LIGHT_APP_COLORS
    return APP_COLORS


def build_inspector_tabs_stylesheet(theme_mode: str = "dark") -> str:
    """
    Stylesheet for the asset inspector tab bar only (:obj:`InspectorTabs`).

    Improves contrast for unselected tabs in dark mode without affecting other tab widgets.
    """
    mode = theme_mode if theme_mode in ("dark", "light") else "dark"
    c = _palette_colors(mode)
    if mode == "dark":
        tab_bar_bg = c["bg"]
        tab_unselected_bg = "#1f252d"
        tab_selected_bg = "#2f3742"
        tab_hover_bg = "#28313b"
        tab_border = "#3a4350"
        tab_text = "#d7dde6"
        tab_text_selected = "#ffffff"
        tab_text_hover = "#e8edf4"
        tab_disabled_bg = "#1a1f26"
        tab_disabled_text = "#8a939f"
        tab_disabled_border = "#323a46"
    else:
        tab_bar_bg = c["bg"]
        tab_unselected_bg = "#e4e8ee"
        tab_selected_bg = "#ffffff"
        tab_hover_bg = "#d8dee8"
        tab_border = c["border"]
        tab_text = "#4a5260"
        tab_text_selected = c["text"]
        tab_text_hover = "#2f3640"
        tab_disabled_bg = "#eceef1"
        tab_disabled_text = "#9aa0a8"
        tab_disabled_border = "#c8ccd4"

    accent = c["primary"]
    pane_bg = c["surface"]

    return f"""
    QTabWidget#InspectorTabs::pane {{
        border: 1px solid {tab_border};
        border-top: 1px solid {tab_border};
        background-color: {pane_bg};
        border-radius: 0px 0px 6px 6px;
        padding: 4px 2px 2px 2px;
        top: -1px;
    }}

    QTabWidget#InspectorTabs > QTabBar {{
        background-color: {tab_bar_bg};
        border-bottom: 1px solid {tab_border};
    }}

    QTabWidget#InspectorTabs > QTabBar::tab {{
        background-color: {tab_unselected_bg};
        color: {tab_text};
        border: 1px solid {tab_border};
        border-bottom-color: {tab_unselected_bg};
        padding: 5px 9px;
        min-width: 56px;
        margin-right: 2px;
        margin-top: 2px;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
    }}

    QTabWidget#InspectorTabs > QTabBar::tab:selected {{
        background-color: {tab_selected_bg};
        color: {tab_text_selected};
        border-color: {tab_border};
        border-bottom-color: {tab_selected_bg};
        border-top: 2px solid {accent};
        padding-top: 4px;
        font-weight: 600;
    }}

    QTabWidget#InspectorTabs > QTabBar::tab:hover:!selected {{
        background-color: {tab_hover_bg};
        color: {tab_text_hover};
        border-color: {tab_border};
    }}

    QTabWidget#InspectorTabs > QTabBar::tab:disabled {{
        background-color: {tab_disabled_bg};
        color: {tab_disabled_text};
        border-color: {tab_disabled_border};
    }}

    QScrollArea#InspectorTabScroll {{
        background-color: transparent;
        border: none;
    }}

    QScrollArea#InspectorTabScroll > QWidget > QWidget {{
        background-color: transparent;
    }}

    QWidget#InspectorDock {{
        background-color: transparent;
    }}
    """


def build_app_stylesheet(theme_mode: str = "dark") -> str:
    """Return the application Qt stylesheet for the given ``theme_mode`` (``dark`` or ``light``)."""
    mode = theme_mode if theme_mode in ("dark", "light") else "dark"
    c = _palette_colors(mode)
    source_path_bg = "#111418" if mode == "dark" else "#F5F6F8"
    source_path_border = "#2E3440" if mode == "dark" else "#C8CCD4"
    source_path_text = c["text"]
    table_bg = "#1A1D22" if mode == "dark" else "#FFFFFF"
    table_alt = "#20242A" if mode == "dark" else "#F0F2F5"
    table_grid = "#303640" if mode == "dark" else "#D0D4DC"
    header_bg = "#2B2F36" if mode == "dark" else "#E3E6EB"
    brand_header_bg = "#1E2126" if mode == "dark" else "#FFFFFF"
    brand_header_border = "#2E3440" if mode == "dark" else "#C8CCD4"
    brand_title = "#F2F2F2" if mode == "dark" else "#111418"
    brand_sub = "#B6BEC8" if mode == "dark" else "#5F6368"
    divider = "#343A44" if mode == "dark" else "#D0D4DC"
    btn_hover = "#343A44" if mode == "dark" else "#D5DAE2"
    disabled_fg = "#8A939F" if mode == "dark" else "#6E7580"
    disabled_bg = "#1A1D22" if mode == "dark" else "#E8EAED"
    disabled_border = "#2A2F36" if mode == "dark" else "#C8CCD4"
    export_dis_fg = "#5c626c" if mode == "dark" else "#9AA0A8"
    export_dis_border = "#3a3f4a" if mode == "dark" else "#B4BAC4"

    # Native QMenu popups can otherwise pick up QWidget foreground color (#E6E6E6) with a light
    # platform background → unreadable menus. Explicit QMenu + QMenu::item rules fix Jobs / context.
    menu_bg = "#1e1f24" if mode == "dark" else c["surface"]
    menu_border = "#3a3d46" if mode == "dark" else c["border"]
    menu_text = "#f0f0f0" if mode == "dark" else c["text"]
    menu_hover_bg = "#2f5ea8" if mode == "dark" else c["primary"]
    menu_hover_fg = "#ffffff"
    menu_disabled_item = "#7a7d85" if mode == "dark" else export_dis_fg
    menu_separator = "#3a3d46" if mode == "dark" else c["border"]

    # Canvas surfaces: table + gallery backgrounds (distinct from outer app bg).
    canvas_bg = table_bg
    canvas_alt = table_alt

    return f"""
    QMainWindow {{
        background-color: {c["bg"]};
        color: {c["text"]};
    }}

    QWidget {{
        color: {c["text"]};
        font-size: 12px;
    }}

    QMenu {{
        background-color: {menu_bg};
        color: {menu_text};
        border: 1px solid {menu_border};
        padding: 4px 0px;
    }}

    QMenu::item {{
        padding: 6px 24px 6px 12px;
        background-color: transparent;
        color: {menu_text};
    }}

    QMenu::item:selected {{
        background-color: {menu_hover_bg};
        color: {menu_hover_fg};
    }}

    QMenu::item:disabled {{
        background-color: transparent;
        color: {menu_disabled_item};
    }}

    QMenu::separator {{
        height: 1px;
        background: {menu_separator};
        margin-top: 4px;
        margin-bottom: 4px;
        margin-left: 8px;
        margin-right: 8px;
    }}

    QFrame#BrandHeader {{
        background-color: {brand_header_bg};
        border: 1px solid {brand_header_border};
        border-radius: 8px;
    }}

    QLabel#BrandTitle {{
        font-size: 20px;
        font-weight: 800;
        color: {brand_title};
    }}

    QLabel#BrandSubtitle {{
        font-size: 11px;
        color: {brand_sub};
    }}

    QLabel#SectionTitle {{
        color: {c["primary"]};
        font-size: 12px;
        font-weight: 800;
    }}

    QLabel#PanelSubTitle {{
        color: {c["text"]};
        font-weight: 700;
        font-size: 12px;
    }}

    QLabel#MutedLabel {{
        color: {c["muted"]};
        font-size: 11px;
    }}

    QLabel#EmptyStateTitle {{
        color: {c["text"]};
        font-size: 12px;
        font-weight: 700;
    }}

    QLabel#EmptyStateBody {{
        color: {c["muted"]};
        font-size: 11px;
    }}

    QLabel#EmptyStateAction {{
        color: {c["primary"]};
        font-size: 11px;
    }}

    QWidget#EmptyStateBlock {{
        background-color: transparent;
    }}

    QLabel#SourcePath {{
        background-color: {source_path_bg};
        border: 1px solid {source_path_border};
        border-radius: 6px;
        padding: 6px;
        color: {source_path_text};
    }}

    QLabel#PreviewImage {{
        background-color: {source_path_bg};
        border: 1px solid {source_path_border};
        border-radius: 8px;
        padding: 8px;
        color: {c["muted"]};
    }}

    QLabel#InspectorBadge {{
        color: {c["primary"]};
        font-size: 11px;
        font-weight: 600;
    }}

    QLabel#PreviewThumbState {{
        color: {c["text"]};
        font-size: 11px;
        font-weight: 600;
    }}

    QLabel#PreviewThumbSubline {{
        color: {c["muted"]};
        font-size: 11px;
    }}

    QFrame#Panel {{
        background-color: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
    }}

    QStackedWidget {{
        background-color: transparent;
    }}

    QWidget#PanelInner {{
        background-color: transparent;
    }}

    QScrollArea#PanelScroll {{
        background-color: transparent;
        border: none;
    }}

    QScrollArea#PanelScroll QWidget#qt_scrollarea_viewport {{
        background-color: transparent;
    }}

    QFrame#Divider {{
        background-color: {divider};
        border: none;
    }}

    QFrame#PanelHeader {{
        background-color: {c["bg"]};
        border: 1px solid {c["border"]};
        border-radius: 6px;
    }}

    QLineEdit, QComboBox {{
        background-color: {c["bg"]};
        border: 1px solid {c["border"]};
        border-radius: 6px;
        padding: 6px;
        color: {c["text"]};
    }}

    QLineEdit:focus, QComboBox:focus {{
        border-color: {c["primary"]};
    }}

    QPushButton {{
        background-color: {c["surface_2"]};
        border: 1px solid {c["border"]};
        border-radius: 7px;
        padding: 7px 12px;
        color: {c["text"]};
    }}

    QPushButton:hover {{
        background-color: {btn_hover};
    }}

    QPushButton:disabled {{
        color: {disabled_fg};
        background-color: {disabled_bg};
        border-color: {disabled_border};
    }}

    QPushButton#PrimaryButton {{
        background-color: {c["primary"]};
        border-color: {c["primary"]};
        color: white;
        font-weight: 600;
    }}

    QPushButton#SecondaryButton {{
        background-color: {c["surface_2"]};
        border-color: {c["border"]};
        color: {c["text"]};
        font-weight: 600;
    }}

    QPushButton#CopyButton {{
        background-color: {c["success"]};
        border-color: {c["success"]};
        color: white;
        font-weight: 600;
    }}

    QPushButton#MoveButton {{
        background-color: {c["warning"]};
        border-color: {c["warning"]};
        color: white;
        font-weight: 600;
    }}

    QPushButton#ExportButton {{
        background-color: transparent;
        border: 1px solid {c["text"]};
        border-radius: 7px;
        color: {c["text"]};
        font-weight: 500;
    }}

    QPushButton#ExportButton:hover {{
        background-color: {c["surface_2"]};
    }}

    QPushButton#ExportButton:disabled {{
        color: {export_dis_fg};
        border-color: {export_dis_border};
    }}

    QToolButton#HeaderActionButton {{
        background: transparent;
        border: 1px solid {c["border"]};
        border-radius: 7px;
        color: {c["text"]};
        font-weight: 600;
        padding: 4px 8px;
    }}

    QFrame#WelcomeCenterPanel {{
        background-color: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
    }}

    QFrame#WelcomeDivider {{
        background-color: {divider};
        border: none;
    }}

    QLabel#WelcomeFeatureRow {{
        color: {c["muted"]};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.12em;
    }}

    QToolButton#HeaderActionButton:hover {{
        background-color: {c["surface_2"]};
    }}

    QTableView {{
        background-color: {table_bg};
        alternate-background-color: {table_alt};
        border: none;
        gridline-color: {table_grid};
        border-radius: 6px;
        selection-background-color: rgba(74, 123, 209, 140);
    }}

    QListView {{
        background-color: {canvas_bg};
        border: none;
        border-radius: 6px;
    }}

    QListView::item {{
        background-color: transparent;
    }}

    QListView::item:selected {{
        background-color: rgba(74, 123, 209, 140);
    }}

    QPlainTextEdit {{
        background-color: {canvas_alt};
        border: 1px solid {c["border"]};
        border-radius: 6px;
        padding: 6px;
    }}

    QHeaderView::section {{
        background-color: {header_bg};
        color: {c["text"]};
        border: none;
        border-right: 1px solid {c["border"]};
        border-bottom: 1px solid {c["border"]};
        padding: 7px;
        font-weight: 700;
    }}

    QGroupBox {{
        border: 1px solid {c["border"]};
        border-radius: 8px;
        margin-top: 12px;
        padding: 8px;
        background-color: {c["surface"]};
    }}

    QGroupBox::title {{
        color: {c["primary"]};
        padding: 0 6px;
    }}

    QCheckBox {{
        color: {c["text"]};
    }}

    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
    }}

    QWidget#TagChip {{
        background-color: {c["surface_2"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
    }}

    QLabel#TagChipLabel {{
        color: {c["text"]};
        font-size: 11px;
    }}

    QPushButton#TagChipRemove {{
        color: {c["muted"]};
        border: none;
        font-weight: 700;
    }}

    QPushButton#TagChipRemove:hover {{
        color: {c["danger"]};
    }}

    QStatusBar {{
        background-color: {c["surface"]};
        border-top: 1px solid {c["border"]};
        color: {c["muted"]};
    }}

    {build_inspector_tabs_stylesheet(mode)}
    """


def apply_theme_palette(app: QApplication, theme_mode: str = "dark") -> None:
    """Set ``app`` palette for dialogs and native controls to match ``theme_mode``."""
    mode = theme_mode if theme_mode in ("dark", "light") else "dark"
    c = _palette_colors(mode)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(c["bg"]))
    palette.setColor(QPalette.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.Base, QColor(c["bg"]))
    palette.setColor(QPalette.AlternateBase, QColor(c["surface"]))
    palette.setColor(QPalette.ToolTipBase, QColor(c["surface_2"]))
    palette.setColor(QPalette.ToolTipText, QColor(c["text"]))
    palette.setColor(QPalette.Text, QColor(c["text"]))
    palette.setColor(QPalette.Button, QColor(c["surface_2"]))
    palette.setColor(QPalette.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.BrightText, QColor(c["danger"]))
    palette.setColor(QPalette.Highlight, QColor(c["primary"]))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


def apply_dark_theme(app: QApplication) -> None:
    """Backward-compatible alias: apply the dark palette to ``app``."""
    apply_theme_palette(app, "dark")
