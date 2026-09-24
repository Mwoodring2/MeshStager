"""Small existing-style sidebar and Metadata Inspector controls."""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView, QLayout, QSizePolicy
from meshcorral.services.housekeeping.models import LABELS

class HousekeepingSidebar(QWidget):
    changed = Signal()
    analyze = Signal()
    cancel = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        label = QLabel("Housekeeping")
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        self.categories = QTreeWidget()
        self.categories.setAccessibleName("Housekeeping categories")
        self.categories.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.categories.setColumnCount(2)
        self.categories.setHeaderHidden(True)
        self.categories.setRootIsDecorated(False)
        self.categories.setIndentation(0)
        self.categories.setUniformRowHeights(True)
        self.categories.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.categories.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.categories.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.categories.header().setStretchLastSection(False)
        self.categories.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.categories.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.categories)
        row = QHBoxLayout()
        self.analyze_button = QPushButton("Analyze…")
        self.analyze_button.setToolTip("Analyze Repository: inspect indexed assets without changing files.")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setToolTip("Cancel Housekeeping analysis. ESC remains assigned to source scanning.")
        self.cancel_button.setEnabled(False)
        for button in (self.analyze_button, self.cancel_button):
            button.setObjectName("SecondaryButton")
            row.addWidget(button)
        layout.addLayout(row)
        self.status = QLabel("Analyze indexed assets; files stay untouched.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.categories.currentItemChanged.connect(lambda _current, _previous: self.changed.emit())
        self.analyze_button.clicked.connect(lambda _checked=False: self.analyze.emit())
        self.cancel_button.clicked.connect(lambda _checked=False: self.cancel.emit())
        self.populate({})

    def current_data(self):
        item = self.categories.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def select(self, key):
        for index in range(self.categories.topLevelItemCount()):
            item = self.categories.topLevelItem(index)
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                self.categories.setCurrentItem(item)
                return

    def populate(self, counts, group=None):
        selected = self.current_data()
        self.categories.blockSignals(True)
        self.categories.clear()
        rows = [("All Assets", None, None), ("All Findings", "*", counts.get("*", 0))]
        rows.extend((label, key, counts.get(key, 0)) for key, label in LABELS.items())
        rows.append(("Ignored Findings", "ignored", counts.get("ignored", 0)))
        if group:
            rows.append(("Duplicate Group", "group:" + group, None))
        row_height = self.fontMetrics().height() + 8
        for label, key, count in rows:
            item = QTreeWidgetItem([label, f"{count:,}" if count is not None else ""])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setSizeHint(0, QSize(0, row_height))
            item.setToolTip(0, label)
            self.categories.addTopLevelItem(item)
        self.select(selected if any(key == selected for _, key, _ in rows) else None)
        # The existing outer sidebar owns scrolling; all category rows stay visible.
        self.categories.setFixedHeight(row_height * len(rows) + 2 * self.categories.frameWidth())
        self.categories.blockSignals(False)

    def reset(self):
        self.categories.blockSignals(True)
        self.select(None)
        self.categories.blockSignals(False)

class HousekeepingEditor(QWidget):
    view_group = Signal()
    ignore = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("Housekeeping")
        label.setObjectName("PanelSubTitle")
        layout.addWidget(label)
        self.combo = QComboBox()
        layout.addWidget(self.combo)
        self.details = QLabel()
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        row = QHBoxLayout()
        self.group_button = QPushButton("View Group")
        self.group_button.setToolTip("View Duplicate Group in the existing browser")
        self.ignore_button = QPushButton("Ignore Finding")
        for button in (self.group_button, self.ignore_button):
            button.setObjectName("SecondaryButton")
            row.addWidget(button)
        layout.addLayout(row)
        self.group_button.clicked.connect(lambda _checked=False: self.view_group.emit())
        self.ignore_button.clicked.connect(lambda _checked=False: self.ignore.emit())
        self.combo.currentIndexChanged.connect(self._changed)
        self.set_findings([])

    def set_findings(self, findings):
        selected = self.combo.currentData()
        selected_id = selected.finding_id if selected else None
        self.combo.blockSignals(True)
        self.combo.clear()
        selected_index = 0
        for f in findings:
            if f.finding_id == selected_id:
                selected_index = self.combo.count()
            self.combo.addItem(LABELS[f.kind] + (" (ignored)" if f.ignored else ""), f)
        self.combo.setCurrentIndex(selected_index)
        self.combo.blockSignals(False)
        self.setVisible(bool(findings))
        self._changed()

    def _changed(self):
        f = self.combo.currentData()
        self.group_button.setEnabled(bool(f and f.group_id and f.kind in ("exact_duplicate", "possible_duplicate")))
        self.ignore_button.setEnabled(f is not None)
        self.ignore_button.setText("Restore Finding" if f and f.ignored else "Ignore Finding")
        if f is None:
            self.details.clear()
            return
        details = f.details
        text = str(details.get("message", ""))
        if f.group_id:
            text += "\nGroup " + f.group_id[:12]
        if "matching_files" in details:
            text += f"\n{details['matching_files']} matching files"
        for key in ("reference", "archive", "member"):
            if key in details:
                text += "\n" + str(details[key])
        self.details.setText(text)
