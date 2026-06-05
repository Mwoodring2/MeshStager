"""Prime v1.0 — inspector Diagnostics tab."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget

_NOT_AVAILABLE = "Not available"


class DiagnosticsPanel(QWidget):
    """Thumbnail, renderer, mesh, archive, and cache diagnostics."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _form_label(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("MutedLabel")
        font = QFont(lab.font())
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        lab.setFont(font)
        return lab

    def _value_label(self) -> QLabel:
        lab = QLabel(_NOT_AVAILABLE)
        lab.setObjectName("MutedLabel")
        font = QFont(lab.font())
        font.setPointSizeF(max(8.0, font.pointSizeF() - 1.0))
        lab.setFont(font)
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return lab

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        hint = QLabel(
            "Thumbnail and asset diagnostics for the selected row. "
            "Technical detail stays here; use Jobs for full job logs."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        self._thumb_state = self._value_label()
        self._thumb_backend = self._value_label()
        self._renderer = self._value_label()
        self._thumb_fallback = self._value_label()
        self._thumb_failure = self._value_label()
        self._thumb_suggested = self._value_label()
        self._mesh_health = self._value_label()
        self._archive_members = self._value_label()
        self._unsupported = self._value_label()
        self._cache_status = self._value_label()
        self._deferred_reason = self._value_label()

        form.addRow(self._form_label("Thumbnail state"), self._thumb_state)
        form.addRow(self._form_label("Thumbnail backend"), self._thumb_backend)
        form.addRow(self._form_label("Render profile"), self._renderer)
        form.addRow(self._form_label("Fallback reason"), self._thumb_fallback)
        form.addRow(self._form_label("Failure reason"), self._thumb_failure)
        form.addRow(self._form_label("Suggested action"), self._thumb_suggested)
        form.addRow(self._form_label("Mesh / geometry"), self._mesh_health)
        form.addRow(self._form_label("Archive members"), self._archive_members)
        form.addRow(self._form_label("Unsupported detail"), self._unsupported)
        form.addRow(self._form_label("Cache status"), self._cache_status)
        form.addRow(self._form_label("Deferred preview detail"), self._deferred_reason)
        root.addLayout(form)
        root.addStretch(1)

    @staticmethod
    def _set_value(label: QLabel, value: str) -> None:
        text = (value or "").strip() or _NOT_AVAILABLE
        label.setText(text)

    def apply(
        self,
        *,
        thumb_status: str,
        renderer_profile: str,
        mesh_health: str,
        archive_member_count: str,
        unsupported_reason: str,
        cache_status: str,
        deferred_reason: str = "",
        thumbnail_backend: str = "",
        thumbnail_failure_reason: str = "",
        thumbnail_fallback_reason: str = "",
        thumbnail_suggested_action: str = "",
        thumbnail_state_display: str = "",
    ) -> None:
        """Populate diagnostic rows; empty strings become Not available."""
        state = (thumbnail_state_display or "").strip() or (thumb_status or "").strip()
        self._set_value(self._thumb_state, state)
        self._set_value(self._thumb_backend, thumbnail_backend)
        self._set_value(self._renderer, renderer_profile)
        self._set_value(self._thumb_fallback, thumbnail_fallback_reason)
        self._set_value(self._thumb_failure, thumbnail_failure_reason)
        self._set_value(self._thumb_suggested, thumbnail_suggested_action)
        self._set_value(self._mesh_health, mesh_health)
        self._set_value(self._archive_members, archive_member_count)
        self._set_value(self._unsupported, unsupported_reason)
        self._set_value(self._cache_status, cache_status)
        if deferred_reason.strip():
            self._deferred_reason.setText(deferred_reason.strip())
        else:
            self._deferred_reason.setText(_NOT_AVAILABLE)
