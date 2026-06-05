"""Prime v1.0 Sprint B — tabbed asset inspector tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QVBoxLayout

from meshcorral.ui.asset_inspector import AssetInspectorPanel
from meshcorral.ui.empty_states import NO_SELECTION, READY_TO_SCAN, empty_state_spec
from meshcorral.ui.inspector.diagnostics_panel import DiagnosticsPanel
from meshcorral.ui.inspector.inspector_context import InspectorSingleDetail
from meshcorral.ui.inspector.inspector_tabs import InspectorTabbedPanel
from meshcorral.ui.inspector.metadata_panel import MetadataPanel
from meshcorral.ui.inspector.preview_panel import PreviewPanel
from meshcorral.ui.theme import build_app_stylesheet, build_inspector_tabs_stylesheet


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


class TestAssetInspectorEmpty(unittest.TestCase):
    """Existing empty-state tests (API preserved)."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def test_show_empty_session_active_uses_selection_copy(self) -> None:
        panel = AssetInspectorPanel()
        panel.show_empty(session_active=True)
        self.assertEqual(
            panel._empty_detail_label.text(),
            empty_state_spec(NO_SELECTION).body,
        )

    def test_show_empty_no_session_uses_scan_first_copy(self) -> None:
        panel = AssetInspectorPanel()
        panel.show_empty(session_active=False)
        self.assertEqual(
            panel._empty_detail_label.text(),
            empty_state_spec(READY_TO_SCAN).body,
        )


class TestPreviewPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def test_receives_selected_asset(self) -> None:
        panel = PreviewPanel()
        pm = QPixmap(32, 32)
        pm.fill()
        panel.apply(
            name="mesh.stl",
            extension_badge="STL",
            thumbnail_state="Missing thumbnail",
            preview_kind="STL mesh",
            preview_subline="No Blender thumbnail yet",
            pixmap=pm,
            missing_file=False,
            preview_blocked_message=None,
            can_regenerate=True,
            blender_enabled=True,
        )
        self.assertIn("mesh.stl", panel._filename_label.text())
        self.assertIn("STL", panel._badge_label.text())
        self.assertTrue(panel._btn_regenerate.isEnabled())


class TestMetadataPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def test_formats_path_size_modified(self) -> None:
        panel = MetadataPanel()
        panel.apply(
            path_str="C:/proj/mesh.stl",
            folder_display="proj",
            extension=".STL",
            size_display="1.2 MB",
            modified_display="2024-01-01",
            asset_mode_display="3D / DCC Assets",
            metadata_source_display="cache",
            tags="tag1",
            metadata_block="{}",
            metadata_copy_text="copy-me",
            path_actions_enabled=True,
        )
        self.assertEqual(panel._path_value.text(), "C:/proj/mesh.stl")
        self.assertEqual(panel._size_value.text(), "1.2 MB")
        self.assertEqual(panel._mod_value.text(), "2024-01-01")
        self.assertEqual(panel._source_value.text(), "cache")


class TestDiagnosticsPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def test_missing_metadata_shows_not_available(self) -> None:
        panel = DiagnosticsPanel()
        panel.apply(
            thumb_status="",
            renderer_profile="",
            mesh_health="",
            archive_member_count="",
            unsupported_reason="",
            cache_status="",
        )
        self.assertEqual(panel._thumb_state.text(), "Not available")
        self.assertEqual(panel._cache_status.text(), "Not available")

    def test_populated_values(self) -> None:
        panel = DiagnosticsPanel()
        panel.apply(
            thumb_status="Ready",
            renderer_profile="Standard",
            mesh_health="Watertight · 12,500 faces",
            archive_member_count="12 members",
            unsupported_reason="",
            cache_status="READY, indexed",
            thumbnail_state_display="Ready",
        )
        self.assertEqual(panel._renderer.text(), "Standard")
        self.assertEqual(panel._archive_members.text(), "12 members")


class TestInspectorLayoutOwnership(unittest.TestCase):
    """Tab stack vs empty/multi pages; no duplicate preview widgets."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def test_preview_tab_visible_after_construction(self) -> None:
        tabs = InspectorTabbedPanel()
        tabs.show()
        bar = tabs._tabs.tabBar()
        self.assertTrue(bar.isVisible())
        self.assertEqual(bar.tabText(0), "Preview")
        self.assertEqual(tabs.inspector_tab_index(), 0)
        self.assertTrue(tabs.preview_panel().isVisibleTo(tabs._tabs))

    def test_tab_count_and_order_stable(self) -> None:
        tabs = InspectorTabbedPanel()
        bar = tabs._tabs.tabBar()
        self.assertEqual(bar.count(), 4)
        self.assertEqual(
            [bar.tabText(i) for i in range(bar.count())],
            ["Preview", "Metadata", "Diagnostics", "Actions"],
        )

    def test_single_selection_one_preview_image_widget(self) -> None:
        panel = AssetInspectorPanel()
        panel.show_single(
            name="mesh.stl",
            path_str="C:/work/mesh.stl",
            extension=".STL",
            size_display="1 KB",
            modified_display="today",
            tags="",
            metadata_block="",
            metadata_copy_text="",
            pixmap=None,
            missing_file=False,
            can_generate_blender_thumbnail=True,
            has_blender_thumbnail=False,
            blender_thumbnail_path="",
        )
        self.assertEqual(panel._stack.currentIndex(), 2)
        from PySide6.QtWidgets import QLabel

        preview_labels = [
            w
            for w in panel.findChildren(QLabel)
            if w.objectName() == "PreviewImage"
        ]
        self.assertEqual(len(preview_labels), 1)
        self.assertIs(preview_labels[0], panel._tabbed.preview_panel()._image_label)

    def test_empty_state_bypasses_tab_stack(self) -> None:
        panel = AssetInspectorPanel()
        panel.show_empty(session_active=True)
        self.assertEqual(panel._stack.currentIndex(), 0)
        self.assertFalse(panel._tabbed.isVisibleTo(panel))

    def test_multi_state_bypasses_tab_stack(self) -> None:
        panel = AssetInspectorPanel()
        panel.show_multi(count=3, mesh_count=2)
        self.assertEqual(panel._stack.currentIndex(), 1)
        self.assertFalse(panel._tabbed.isVisibleTo(panel))


class TestInspectorTabStyling(unittest.TestCase):
    """Inspector tab bar stylesheet and tab order (Prime v1.0)."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def test_tab_order_and_labels(self) -> None:
        tabs = InspectorTabbedPanel()
        bar = tabs._tabs.tabBar()
        self.assertEqual(
            [bar.tabText(i) for i in range(bar.count())],
            ["Preview", "Metadata", "Diagnostics", "Actions"],
        )

    def test_dark_inspector_tab_stylesheet_has_contrast_rules(self) -> None:
        css = build_inspector_tabs_stylesheet("dark")
        self.assertIn("QTabWidget#InspectorTabs", css)
        self.assertIn("QTabBar::tab:selected", css)
        self.assertIn("#4A7BD1", css)
        self.assertIn("#d7dde6", css)
        self.assertIn("min-width: 56px", css)

    def test_app_stylesheet_includes_inspector_tabs(self) -> None:
        css = build_app_stylesheet("dark")
        self.assertIn("QTabWidget#InspectorTabs", css)


def _expanding_spacer_indices(layout: QVBoxLayout) -> list[int]:
    """Layout item indices that use an expanding QSizePolicy spacer."""
    indices: list[int] = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        spacer = item.spacerItem()
        if spacer is None:
            continue
        if spacer.expandingDirections() != Qt.Orientation(0):
            indices.append(index)
    return indices


class TestRightPanelFileActionsRhythm(unittest.TestCase):
    """File actions block sits directly above InspectorDock with compact rhythm."""

    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def _main_window(self):
        from meshcorral.ui.main_window import MainWindow

        window = MainWindow()
        window.show()
        QApplication.processEvents()
        return window

    def test_outer_column_order_scroll_file_actions_inspector_summary(self) -> None:
        window = self._main_window()
        outer = window._right_panel.layout()
        self.assertIsInstance(outer, QVBoxLayout)
        scroll = outer.itemAt(0).widget()
        file_actions = outer.itemAt(1).widget()
        inspector = outer.itemAt(2).widget()
        summary = outer.itemAt(3).widget()
        self.assertIsInstance(scroll, QScrollArea)
        self.assertEqual(file_actions.objectName(), "RightFileActionsBlock")
        self.assertIs(file_actions, window._right_file_actions_wrap)
        self.assertEqual(inspector.objectName(), "InspectorDock")
        self.assertEqual(summary.objectName(), "PanelInner")

    def test_export_in_transfer_scroll_file_actions_title_outside(self) -> None:
        window = self._main_window()
        scroll = window._right_panel.findChild(QScrollArea, "PanelScroll")
        self.assertIsNotNone(scroll)
        transfer_block = scroll.widget()
        transfer_layout = transfer_block.layout()
        self.assertGreaterEqual(transfer_layout.indexOf(window._export_top_btn), 0)
        scroll_file_action_titles = [
            label
            for label in transfer_block.findChildren(QLabel)
            if label.text() == "File actions"
        ]
        self.assertEqual(scroll_file_action_titles, [])
        file_actions_layout = window._right_file_actions_wrap.layout()
        title_widgets = [
            file_actions_layout.itemAt(index).widget()
            for index in range(file_actions_layout.count())
            if file_actions_layout.itemAt(index).widget() is not None
        ]
        self.assertTrue(
            any(
                widget.objectName() == "SectionTitle" and widget.text() == "File actions"
                for widget in title_widgets
            )
        )

    def test_export_separated_from_file_actions_by_scroll_tail(self) -> None:
        window = self._main_window()
        scroll = window._right_panel.findChild(QScrollArea, "PanelScroll")
        transfer_layout = scroll.widget().layout()
        export_index = transfer_layout.indexOf(window._export_top_btn)
        tail_kinds: list[str] = []
        for index in range(export_index + 1, transfer_layout.count()):
            item = transfer_layout.itemAt(index)
            if item.widget() is not None:
                tail_kinds.append(item.widget().objectName())
            elif item.spacerItem() is not None:
                tail_kinds.append("spacing")
        self.assertIn("Divider", tail_kinds)
        self.assertGreaterEqual(tail_kinds.count("spacing"), 1)

    def test_no_expanding_spacer_between_file_actions_and_inspector(self) -> None:
        window = self._main_window()
        outer = window._right_panel.layout()
        self.assertEqual(_expanding_spacer_indices(outer), [])
        file_layout = window._right_file_actions_wrap.layout()
        self.assertEqual(_expanding_spacer_indices(file_layout), [])

    def test_hidden_file_action_buttons_do_not_reserve_height(self) -> None:
        window = self._main_window()
        self.assertFalse(window._reveal_btn.isVisible())
        self.assertFalse(window._copy_path_btn.isVisible())
        file_layout = window._right_file_actions_wrap.layout()
        visible_widgets = [
            file_layout.itemAt(index).widget()
            for index in range(file_layout.count())
            if file_layout.itemAt(index).widget() is not None
            and file_layout.itemAt(index).widget().isVisible()
        ]
        self.assertEqual(len(visible_widgets), 1)
        margins = file_layout.contentsMargins()
        title_height = visible_widgets[0].sizeHint().height()
        compact_hint = (
            margins.top()
            + margins.bottom()
            + title_height
        )
        self.assertLessEqual(
            window._right_file_actions_wrap.sizeHint().height(),
            compact_hint + 4,
        )

    def test_inspector_tabs_visible_when_single_selection_stack_active(self) -> None:
        window = self._main_window()
        window._asset_inspector.show_single(
            name="mesh.stl",
            path_str="C:/work/mesh.stl",
            extension=".STL",
            size_display="1 KB",
            modified_display="today",
            tags="",
            metadata_block="",
            metadata_copy_text="",
            pixmap=None,
            missing_file=False,
            can_generate_blender_thumbnail=True,
            has_blender_thumbnail=False,
            blender_thumbnail_path="",
        )
        QApplication.processEvents()
        tabs = window._asset_inspector._tabbed._tabs
        bar = tabs.tabBar()
        self.assertEqual(window._asset_inspector._stack.currentIndex(), 2)
        self.assertTrue(bar.isVisibleTo(window._asset_inspector._tabbed))
        self.assertEqual(bar.count(), 4)


class TestInspectorSignals(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _ensure_qapp()

    def test_actions_tab_emits_open_signal(self) -> None:
        tabs = InspectorTabbedPanel()
        received: list[str] = []
        tabs.open_file_clicked.connect(lambda: received.append("open"))
        tabs._actions._btn_open.click()
        self.assertEqual(received, ["open"])

    def test_metadata_copy_path_signal(self) -> None:
        tabs = InspectorTabbedPanel()
        received: list[str] = []
        tabs.copy_path_clicked.connect(lambda: received.append("path"))
        detail = InspectorSingleDetail(
            name="a.stl",
            path_str="C:/a.stl",
            extension=".STL",
            size_display="1 B",
            modified_display="—",
            folder_display="C:/",
            asset_mode_display="3D",
            metadata_source_display="stat",
            tags="",
            metadata_block="",
            metadata_copy_text="",
            pixmap=None,
            missing_file=False,
            can_generate_blender_thumbnail=True,
            has_blender_thumbnail=False,
            blender_thumbnail_path="",
        )
        tabs.apply_detail(detail)
        tabs._metadata._btn_copy_path.click()
        self.assertEqual(received, ["path"])

    def test_wrapper_preserves_generate_missing_signal(self) -> None:
        panel = AssetInspectorPanel()
        slot = MagicMock()
        panel.generate_missing_for_view_clicked.connect(slot)
        panel._btn_gen_missing.click()
        slot.assert_called_once()


if __name__ == "__main__":
    unittest.main()
