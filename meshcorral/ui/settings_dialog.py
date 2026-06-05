"""Minimal Settings dialog (saved only when the user accepts)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from meshcorral.app.bridge.blender_locator import find_blender_executable, get_blender_version
from meshcorral.app.dcc.dcc_profiles import all_dcc_profiles
from meshcorral.app.dcc.maya_locator import describe_maya_readiness, find_maya_executable
from meshcorral.services.environment.native_renderer_health import (
    check_startup_environment,
    get_native_renderer_health,
)
from meshcorral.app.icon_branding import apply_window_icon
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.layout_constants import (
    SETTINGS_DIALOG_MIN_HEIGHT,
    SETTINGS_DIALOG_MIN_WIDTH,
)
from meshcorral.ui.responsive_dialog import (
    ResponsiveModalDialog,
    create_content_scroll_area,
    create_pinned_button_row,
)


class SettingsDialog(ResponsiveModalDialog):
    """Edit MeshStager preferences; writes to :class:`~meshcorral.services.settings_service.SettingsService` on Save."""

    responsive_min_width = SETTINGS_DIALOG_MIN_WIDTH
    responsive_min_height = SETTINGS_DIALOG_MIN_HEIGHT

    def __init__(
        self,
        settings_service: SettingsService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        self._settings_service = settings_service
        self._settings_scroll: QScrollArea | None = None
        self._button_box: QDialogButtonBox | None = None

        self._dark_radio = QRadioButton("Dark")
        self._light_radio = QRadioButton("Light")
        self._theme_group = QButtonGroup(self)
        self._include_subfolders_check = QCheckBox("Include subfolders by default")
        self._default_destination_edit = QLineEdit()
        self._confirm_before_move_check = QCheckBox("Show confirmation before moving files")
        self._blender_path_edit = QLineEdit()
        self._maya_path_edit = QLineEdit()
        self._blender_status_label = QLabel("—")
        self._maya_status_label = QLabel("—")
        self._auto_thumb_after_scan_check = QCheckBox(
            "Auto-generate thumbnails after scan (.stl, .obj, .fbx)"
        )
        self._auto_thumb_cap_combo = QComboBox()
        self._auto_thumb_cap_combo.addItem("25", SettingsService.CAP_AUTO_THUMB_25)
        self._auto_thumb_cap_combo.addItem("100", SettingsService.CAP_AUTO_THUMB_100)
        self._auto_thumb_cap_combo.addItem("Unlimited", SettingsService.CAP_AUTO_THUMB_UNLIMITED)
        self._auto_thumb_cap_combo.setToolTip(
            "When auto-thumbnails are on, at most this many jobs are queued per scan. "
            "Use this to avoid a huge queue when browsing very large asset trees."
        )
        self._thumb_renderer_combo = QComboBox()
        self._thumb_renderer_combo.addItem("Auto recommended", SettingsService.THUMBNAIL_RENDERER_AUTO)
        self._thumb_renderer_combo.addItem("Native first", SettingsService.THUMBNAIL_RENDERER_NATIVE_FIRST)
        self._thumb_renderer_combo.addItem("Blender first", SettingsService.THUMBNAIL_RENDERER_BLENDER_FIRST)
        self._thumb_renderer_combo.addItem("Manual only", SettingsService.THUMBNAIL_RENDERER_MANUAL_ONLY)
        self._thumb_renderer_combo.setToolTip(
            "Auto recommended uses native CPU for STL/OBJ and Blender for specialized formats."
        )
        self._bridge_history_combo = QComboBox()
        self._bridge_history_combo.addItem(
            "30 days (recommended)",
            int(SettingsService.BRIDGE_HISTORY_DAYS_DEFAULT),
        )
        self._bridge_history_combo.addItem("90 days", int(90))
        self._bridge_history_combo.addItem(
            "Forever (no automatic cleanup)",
            int(SettingsService.BRIDGE_HISTORY_FOREVER_DAYS),
        )
        self._bridge_history_combo.setToolTip(
            "Automatically remove old Blender bridge job outputs from the app data folder "
            "(not your scan folders) after startup. Use Jobs → Clean old thumbnail jobs… for manual cleanup."
        )
        self._native_renderer_status_label = QLabel("—")
        self._env_native_label = QLabel("—")
        self._env_blender_label = QLabel("—")
        self._env_metadata_label = QLabel("—")
        self._env_thumb_cache_label = QLabel("—")

        self._build_ui()
        self._load_values()
        self._install_keyboard_shortcuts()
        apply_window_icon(self)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        self._settings_scroll, _scroll_content, scroll_layout = create_content_scroll_area(
            self,
            object_name="SettingsScrollArea",
        )

        title = QLabel("MeshStager Settings")
        title.setObjectName("BrandTitle")
        scroll_layout.addWidget(title)
        intro = QLabel("Changes apply when you click Save. Groups below match how the app uses each option.")
        intro.setWordWrap(True)
        intro.setObjectName("MutedLabel")
        scroll_layout.addWidget(intro)

        general_group = QGroupBox("General")
        general_layout = QVBoxLayout(general_group)

        theme_row = QHBoxLayout()
        self._theme_group.addButton(self._dark_radio)
        self._theme_group.addButton(self._light_radio)
        theme_row.addWidget(QLabel("Theme:"))
        theme_row.addWidget(self._dark_radio)
        theme_row.addWidget(self._light_radio)
        theme_row.addStretch()
        general_layout.addLayout(theme_row)

        scroll_layout.addWidget(general_group)

        env_group = QGroupBox("Environment")
        env_layout = QFormLayout(env_group)
        env_layout.addRow("Native renderer:", self._env_native_label)
        env_layout.addRow("Blender:", self._env_blender_label)
        env_layout.addRow("Metadata cache:", self._env_metadata_label)
        env_layout.addRow("Thumbnail cache:", self._env_thumb_cache_label)
        scroll_layout.addWidget(env_group)

        scan_group = QGroupBox("Scan")
        scan_layout = QVBoxLayout(scan_group)
        scan_layout.addWidget(self._include_subfolders_check)
        scroll_layout.addWidget(scan_group)

        transfer_group = QGroupBox("Transfer")
        transfer_layout = QFormLayout(transfer_group)

        destination_row = QHBoxLayout()
        self._default_destination_edit.setPlaceholderText("Optional default destination folder...")
        destination_row.addWidget(self._default_destination_edit, 1)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_default_destination)
        destination_row.addWidget(browse_btn)

        transfer_layout.addRow("Default destination:", destination_row)

        scroll_layout.addWidget(transfer_group)

        safety_group = QGroupBox("Safety")
        safety_layout = QVBoxLayout(safety_group)
        safety_layout.addWidget(self._confirm_before_move_check)
        scroll_layout.addWidget(safety_group)

        dcc_group = QGroupBox("DCC Integrations (optional)")
        dcc_layout = QVBoxLayout(dcc_group)
        dcc_help = QLabel(
            "Optional: open scene files in Blender or Maya. "
            "Blender also generates mesh thumbnails; Maya open-only today."
        )
        dcc_help.setWordWrap(True)
        dcc_help.setTextFormat(Qt.TextFormat.PlainText)
        dcc_layout.addWidget(dcc_help)

        form = QFormLayout()

        blender_row = QHBoxLayout()
        self._blender_path_edit.setPlaceholderText("Path to blender.exe (optional)…")
        blender_row.addWidget(self._blender_path_edit, 1)
        blend_browse = QPushButton("Browse…")
        blend_browse.clicked.connect(self._browse_blender_executable)
        blender_row.addWidget(blend_browse)
        form.addRow("Blender:", blender_row)
        form.addRow("Blender status:", self._blender_status_label)
        self._blender_caps_row = self._make_capability_row(("Open Files", "Thumbnails"))
        form.addRow("", self._blender_caps_row)

        maya_row = QHBoxLayout()
        self._maya_path_edit.setPlaceholderText("Path to maya.exe (optional)…")
        maya_row.addWidget(self._maya_path_edit, 1)
        maya_browse = QPushButton("Browse…")
        maya_browse.clicked.connect(self._browse_maya_executable)
        maya_row.addWidget(maya_browse)
        form.addRow("Maya:", maya_row)
        form.addRow("Maya status:", self._maya_status_label)
        self._maya_caps_row = self._make_capability_row(("Open Files",))
        form.addRow("", self._maya_caps_row)

        pref_row = QHBoxLayout()
        self._preferred_dcc_combo = QComboBox()
        self._preferred_dcc_combo.addItem("Auto", "auto")
        for p in all_dcc_profiles():
            if p.capabilities.can_open:
                self._preferred_dcc_combo.addItem(p.display_name, p.id)
        self._preferred_dcc_combo.setToolTip(
            "Preferred DCC controls which application opens compatible files when double-clicking assets."
        )
        pref_row.addWidget(self._preferred_dcc_combo, 1)
        form.addRow("Preferred DCC:", pref_row)

        dcc_layout.addLayout(form)
        scroll_layout.addWidget(dcc_group)

        bridge_group = QGroupBox("Thumbnail Generation")
        bridge_layout = QVBoxLayout(bridge_group)
        bridge_help = QLabel(
            "STL/OBJ use the native CPU renderer by default. Blender is used for .fbx, "
            ".blend, and optional high-quality renders."
        )
        bridge_help.setWordWrap(True)
        bridge_help.setTextFormat(Qt.TextFormat.PlainText)
        bridge_layout.addWidget(bridge_help)

        test_row = QHBoxLayout()
        test_row.addStretch()
        test_blender_btn = QPushButton("Test Blender")
        test_blender_btn.clicked.connect(self._on_test_blender)
        test_row.addWidget(test_blender_btn)
        bridge_layout.addLayout(test_row)

        auto_row = QVBoxLayout()
        self._auto_thumb_after_scan_check.setToolTip(
            "After each 3D folder scan, queue missing thumbnails for supported mesh formats. "
            "Uses native CPU for STL/OBJ by default; Blender for specialized formats when configured."
        )
        auto_row.addWidget(self._auto_thumb_after_scan_check)
        cap_form = QFormLayout()
        cap_form.addRow("Max auto-queued jobs per scan:", self._auto_thumb_cap_combo)
        cap_form.addRow("Thumbnail generation:", self._thumb_renderer_combo)
        cap_form.addRow("Native renderer:", self._native_renderer_status_label)
        auto_row.addLayout(cap_form)
        bridge_layout.addLayout(auto_row)
        self._auto_thumb_after_scan_check.toggled.connect(
            self._auto_thumb_cap_combo.setEnabled
        )
        retention = QFormLayout()
        retention.addRow("Keep thumbnail job outputs:", self._bridge_history_combo)
        bridge_layout.addLayout(retention)

        scroll_layout.addWidget(bridge_group)

        root.addWidget(self._settings_scroll, 1)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._save_and_accept)
        self._button_box.rejected.connect(self.reject)
        save_btn = self._button_box.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = self._button_box.button(QDialogButtonBox.StandardButton.Cancel)
        if save_btn is not None:
            save_btn.setText("Save")
            save_btn.setDefault(True)
        if cancel_btn is not None:
            cancel_btn.setText("Cancel")
        root.addWidget(create_pinned_button_row(self._button_box, object_name="SettingsButtonRow"), 0)

    def _install_keyboard_shortcuts(self) -> None:
        """Ctrl+S / Ctrl+Enter save; Esc cancels via the button box."""
        save_action = QAction("Save settings", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._save_and_accept)
        self.addAction(save_action)

        ctrl_enter = QAction("Save settings (Ctrl+Enter)", self)
        ctrl_enter.setShortcut(QKeySequence("Ctrl+Return"))
        ctrl_enter.triggered.connect(self._save_and_accept)
        self.addAction(ctrl_enter)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Enter saves when focus is not on text entry controls."""
        if event.key() in (int(Qt.Key.Key_Return), int(Qt.Key.Key_Enter)):
            if self._enter_triggers_save(self.focusWidget()):
                self._save_and_accept()
                return
        if event.key() == int(Qt.Key.Key_Escape):
            self.reject()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _enter_triggers_save(focus_widget: QWidget | None) -> bool:
        """Return whether Return/Enter should commit settings for the focused widget."""
        if focus_widget is None:
            return True
        if isinstance(focus_widget, (QLineEdit, QComboBox)):
            return False
        return True

    def _load_values(self) -> None:
        theme = self._settings_service.theme_mode()
        self._dark_radio.setChecked(theme == "dark")
        self._light_radio.setChecked(theme == "light")

        self._include_subfolders_check.setChecked(
            self._settings_service.include_subfolders_default()
        )
        self._default_destination_edit.setText(
            self._settings_service.default_destination()
        )
        self._confirm_before_move_check.setChecked(
            self._settings_service.confirm_before_move()
        )
        self._blender_path_edit.setText(self._settings_service.blender_executable())
        self._maya_path_edit.setText(self._settings_service.maya_executable())
        want = self._settings_service.preferred_dcc()
        for i in range(self._preferred_dcc_combo.count()):
            if str(self._preferred_dcc_combo.itemData(i)) == want:
                self._preferred_dcc_combo.setCurrentIndex(i)
                break
        self._auto_thumb_after_scan_check.setChecked(
            self._settings_service.auto_thumbnail_after_scan()
        )
        cap = self._settings_service.auto_thumbnail_max_per_scan()
        for i in range(self._auto_thumb_cap_combo.count()):
            if int(self._auto_thumb_cap_combo.itemData(i)) == cap:
                self._auto_thumb_cap_combo.setCurrentIndex(i)
                break
        self._auto_thumb_cap_combo.setEnabled(
            self._auto_thumb_after_scan_check.isChecked()
        )
        pref = self._settings_service.thumbnail_renderer_preference()
        for i in range(self._thumb_renderer_combo.count()):
            if str(self._thumb_renderer_combo.itemData(i)) == pref:
                self._thumb_renderer_combo.setCurrentIndex(i)
                break
        dh = self._settings_service.bridge_history_keep_days()
        for i in range(self._bridge_history_combo.count()):
            if int(self._bridge_history_combo.itemData(i)) == dh:
                self._bridge_history_combo.setCurrentIndex(i)
                break

        self._refresh_dcc_status_labels()
        self._refresh_environment_labels()

    def _refresh_environment_labels(self) -> None:
        """Startup health summary (native, Blender, caches)."""
        summary = check_startup_environment(self._settings_service)
        native = get_native_renderer_health()
        self._env_native_label.setText(summary.native_renderer)
        self._env_blender_label.setText(summary.blender)
        self._env_metadata_label.setText(summary.metadata_cache)
        self._env_thumb_cache_label.setText(summary.thumbnail_cache)
        self._native_renderer_status_label.setText(native.settings_message)
        if native.available:
            self._native_renderer_status_label.setStyleSheet("color: #7bd88f;")
        else:
            self._native_renderer_status_label.setStyleSheet("color: #b89a6c;")

    def _refresh_dcc_status_labels(self) -> None:
        """Update DCC readiness labels without spawning external apps."""
        blender = find_blender_executable(self._settings_service)
        maya = find_maya_executable(self._settings_service)

        # Blender readiness label is kept lightweight in the bridge module.
        from meshcorral.app.bridge.blender_locator import describe_blender_readiness

        b_label = describe_blender_readiness(self._settings_service, blender)
        m_label = describe_maya_readiness(self._settings_service, maya)

        b_manual = bool((self._settings_service.blender_executable() or "").strip())
        m_manual = bool((self._settings_service.maya_executable() or "").strip())

        if b_label == "Ready" and not b_manual:
            self._set_status_label(self._blender_status_label, "Detected")
        elif b_manual:
            self._set_status_label(
                self._blender_status_label,
                "Manual path set" if b_label == "Ready" else "Not found",
            )
        else:
            self._set_status_label(self._blender_status_label, "Not found")

        if m_label == "Ready" and not m_manual:
            self._set_status_label(self._maya_status_label, "Detected")
        elif m_manual:
            self._set_status_label(
                self._maya_status_label,
                "Manual path set" if m_label == "Ready" else "Not found",
            )
        else:
            self._set_status_label(self._maya_status_label, "Not found")

    def _set_status_label(self, label: QLabel, text: str) -> None:
        """
        Set short status copy plus subtle color cues (presentation only).
        """
        t = (text or "").strip()
        label.setText(t or "—")
        if t == "Detected":
            label.setStyleSheet("color: #7bd88f;")  # subtle green on dark
        elif t == "Manual path set":
            label.setStyleSheet("color: #6aa8ff;")  # subtle blue on dark
        elif t == "Not found":
            label.setStyleSheet("color: #b89a6c;")  # muted orange/gray on dark
        else:
            label.setStyleSheet("")

    def _make_capability_row(self, labels: tuple[str, ...]) -> QWidget:
        """Compact capability chips shown under a DCC status row (polish-only)."""
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for text in labels:
            chip = QLabel(text)
            chip.setObjectName("CapabilityChip")
            chip.setStyleSheet(
                "color: rgba(220, 220, 220, 0.9);"
                "border: 1px solid rgba(255, 255, 255, 0.18);"
                "border-radius: 10px;"
                "padding: 2px 8px;"
            )
            row.addWidget(chip, 0)
        row.addStretch(1)
        return w

    def _browse_blender_executable(self) -> None:
        """Open a file picker for blender.exe (optional)."""
        start = self._blender_path_edit.text().strip()
        if start and Path(start).is_file():
            start_dir = str(Path(start).parent)
        else:
            candidate = Path("C:/Program Files/Blender Foundation")
            start_dir = str(candidate) if candidate.exists() else str(Path.home())

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Blender executable",
            start_dir,
            "Executable (blender.exe);;All files (*.*)",
        )
        if path:
            self._blender_path_edit.setText(path)
            self._refresh_dcc_status_labels()

    def _browse_maya_executable(self) -> None:
        """Open a file picker for maya.exe (optional)."""
        start = self._maya_path_edit.text().strip()
        if start and Path(start).is_file():
            start_dir = str(Path(start).parent)
        else:
            candidate = Path("C:/Program Files/Autodesk")
            start_dir = str(candidate) if candidate.exists() else str(Path.home())

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Maya executable",
            start_dir,
            "Executable (maya.exe);;All files (*.*)",
        )
        if path:
            self._maya_path_edit.setText(path)
            self._refresh_dcc_status_labels()

    def _on_test_blender(self) -> None:
        """
        Check whether Blender is available: auto-detect, saved path, or path in the text field.
        """
        raw = self._blender_path_edit.text().strip()
        if raw:
            candidate = Path(raw)
            if not candidate.is_file():
                QMessageBox.warning(
                    self,
                    "Blender not found",
                    f"The path does not exist or is not a file:\n{candidate}\n\n"
                    "Set the full path to blender.exe, or clear the field to try auto-detect.",
                )
                return
            version = get_blender_version(candidate)
            if version.startswith("Error:"):
                QMessageBox.warning(
                    self,
                    "Blender not valid",
                    f"Path:\n{candidate}\n\n{version}\n\n"
                    "Choose a valid blender.exe, or clear the field to try auto-detect.",
                )
                return
            QMessageBox.information(
                self,
                "Blender found",
                f"Blender is available.\n\nPath:\n{candidate}\n\nVersion:\n{version}",
            )
            return

        found = find_blender_executable(self._settings_service)
        if found is None:
            QMessageBox.information(
                self,
                "Blender not found",
                "Blender was not found automatically, and the path is empty.\n\n"
                "You can set the full path to blender.exe above and click “Test Blender” again. "
                "The rest of MeshStager works without Blender.",
            )
            return

        version = get_blender_version(found)
        if version.startswith("Error:"):
            QMessageBox.warning(
                self,
                "Blender not valid",
                f"Path:\n{found}\n\n{version}",
            )
            return
        QMessageBox.information(
            self,
            "Blender found",
            f"Blender is available.\n\nPath:\n{found}\n\nVersion:\n{version}",
        )

    def _browse_default_destination(self) -> None:
        start_dir = self._default_destination_edit.text().strip()
        if not start_dir or not Path(start_dir).exists():
            start_dir = str(Path.home())

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select default destination",
            start_dir,
        )
        if folder:
            self._default_destination_edit.setText(folder)

    def _save_and_accept(self) -> None:
        theme = "light" if self._light_radio.isChecked() else "dark"

        self._settings_service.set_theme_mode(theme)
        self._settings_service.set_include_subfolders_default(
            self._include_subfolders_check.isChecked()
        )
        self._settings_service.set_default_destination(
            self._default_destination_edit.text()
        )
        self._settings_service.set_confirm_before_move(
            self._confirm_before_move_check.isChecked()
        )
        self._settings_service.set_blender_executable(
            self._blender_path_edit.text()
        )
        self._settings_service.set_maya_executable(
            self._maya_path_edit.text()
        )
        self._settings_service.set_preferred_dcc(
            str(self._preferred_dcc_combo.currentData() or "auto")
        )
        self._settings_service.set_auto_thumbnail_after_scan(
            self._auto_thumb_after_scan_check.isChecked()
        )
        cap_data = self._auto_thumb_cap_combo.currentData()
        if cap_data is not None:
            self._settings_service.set_auto_thumbnail_max_per_scan(int(cap_data))
        else:
            self._settings_service.set_auto_thumbnail_max_per_scan(
                SettingsService.CAP_AUTO_THUMB_25
            )
        self._settings_service.set_thumbnail_renderer_preference(
            str(self._thumb_renderer_combo.currentData() or SettingsService.THUMBNAIL_RENDERER_AUTO)
        )
        dh = self._bridge_history_combo.currentData()
        if dh is not None:
            self._settings_service.set_bridge_history_keep_days(int(dh))

        self.accept()
