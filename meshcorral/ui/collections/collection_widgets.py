"""Small collection controls using existing responsive dialog standards."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from meshcorral.services.collections.collection_repository import MAX_NAME_LENGTH
from meshcorral.ui.responsive_dialog import (
    ResponsiveModalDialog, create_content_scroll_area, create_pinned_button_row,
)


class CollectionSidebar(QWidget):
    selection_changed = Signal()
    create_requested = Signal()
    rename_requested = Signal()
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Collections")
        title.setObjectName("SectionTitle")
        root.addWidget(title)
        self.combo = QComboBox()
        self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(12)
        self.combo.addItem("All Assets", None)
        self.combo.setToolTip("Filter loaded assets without changing the source or scanning.")
        root.addWidget(self.combo)
        row = QHBoxLayout()
        self.new_button = QPushButton("+ New")
        self.rename_button = QPushButton("Rename…")
        self.delete_button = QPushButton("Delete…")
        for button in (self.new_button, self.rename_button, self.delete_button):
            button.setObjectName("SecondaryButton")
            row.addWidget(button)
        root.addLayout(row)
        self.new_button.setToolTip("Create a collection")
        self.new_button.clicked.connect(self.create_requested.emit)
        self.rename_button.clicked.connect(self.rename_requested.emit)
        self.delete_button.clicked.connect(self.delete_requested.emit)
        self.combo.currentIndexChanged.connect(self._selected)
        self._update_buttons()

    def _update_buttons(self):
        enabled = self.selected_id() is not None
        self.rename_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def _selected(self):
        self._update_buttons()
        self.selection_changed.emit()

    def selected_id(self):
        return self.combo.currentData()

    def populate(self, collections):
        selected = self.selected_id()
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            self.combo.addItem("All Assets", None)
            for collection in collections:
                self.combo.addItem(f"{collection.name} ({collection.member_count:,})", collection.collection_id)
                self.combo.setItemData(self.combo.count() - 1, collection.name, Qt.ItemDataRole.ToolTipRole)
            self.combo.setCurrentIndex(max(0, self.combo.findData(selected)))
        finally:
            self.combo.blockSignals(False)
        self._update_buttons()

    def reset(self):
        self.combo.blockSignals(True)
        self.combo.setCurrentIndex(0)
        self.combo.blockSignals(False)
        self._update_buttons()


class CollectionEditor(QWidget):
    add_requested = Signal()
    remove_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Collections")
        title.setObjectName("PanelSubTitle")
        root.addWidget(title)
        self.summary = QLabel("Select an asset to manage collections.")
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setObjectName("MutedLabel")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.add_button = QPushButton("Add to Collection…")
        self.remove_button = QPushButton("Remove from Collection…")
        for button in (self.add_button, self.remove_button):
            button.setObjectName("SecondaryButton")
            root.addWidget(button)
            button.setEnabled(False)
        self.add_button.clicked.connect(self.add_requested.emit)
        self.remove_button.clicked.connect(self.remove_requested.emit)

    def set_selection(self, count, names, *, available=True):
        if not available:
            text = "Collections unavailable."
        elif not count:
            text = "Select an asset to manage collections."
        elif names:
            prefix = "Across selected assets: " if count > 1 else ""
            text = prefix + ", ".join(names)
        else:
            text = "No collections"
        self.summary.setText(text)
        self.add_button.setEnabled(available and count > 0)
        self.remove_button.setEnabled(available and count > 0 and bool(names))
        self.add_button.setToolTip(f"Apply to all {count} selected asset(s).")
        self.remove_button.setToolTip(f"Apply to all {count} selected asset(s).")


class CollectionDialog(ResponsiveModalDialog):
    """Name entry, collection choice, or confirmation with pinned actions."""

    def __init__(self, parent=None, *, title, prompt, name=None, choices=None, action="Save"):
        super().__init__(parent)
        self.setWindowTitle(title)
        root = QVBoxLayout(self)
        scroll, _, body = create_content_scroll_area(self)
        self._content_scroll = scroll
        label = QLabel(prompt)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        body.addWidget(label)
        self.input = None
        self.choices = None
        if name is not None:
            self.input = QLineEdit(name)
            self.input.setMaxLength(MAX_NAME_LENGTH)
            self.input.setAccessibleName("Collection name")
            self.input.selectAll()
            body.addWidget(self.input)
        if choices is not None:
            self.choices = QComboBox()
            self.choices.setAccessibleName("Collection")
            self.choices.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            for collection in choices:
                self.choices.addItem(collection.name, collection.collection_id)
            body.addWidget(self.choices)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        body.addWidget(self.error)
        body.addStretch(1)
        root.addWidget(scroll, 1)
        self._button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self._button_box.button(QDialogButtonBox.StandardButton.Save).setText(action)
        self._button_box.rejected.connect(self.reject)
        root.addWidget(create_pinned_button_row(self._button_box))
        self._button_box.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)

    def submit_with(self, operation):
        """Keep invalid input in place so users can correct it."""
        from meshcorral.services.collections.collection_service import CollectionError

        def submit():
            try:
                operation()
            except CollectionError as exc:
                self.error.setText(str(exc))
                return
            self.accept()

        self._button_box.accepted.connect(submit)
