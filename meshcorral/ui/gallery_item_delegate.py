"""Paints gallery cards: large thumbnail, file name, extension, and formatted size."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QModelIndex, Qt, QRect, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from meshcorral.ui.gallery_list_model import GALLERY_RECORD_ROLE
from meshcorral.ui.thumbnails.badge_paint import paint_gallery_badge
from meshcorral.ui.thumbnails.badge_styles import BADGE_MARGIN
from meshcorral.utils.filesize_display import format_file_size_display

if TYPE_CHECKING:
    from meshcorral.ui.thumbnail_controller import ThumbnailViewController


class GalleryItemDelegate(QStyledItemDelegate):
    """
    Renders a centered icon, file name, extension, and size; supports zoomed thumbnail size.
    """

    def __init__(self, thumb: "ThumbnailViewController", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._thumb = thumb

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        if not index.isValid():
            return
        record = index.data(GALLERY_RECORD_ROLE)
        if record is None:
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        rect = option.rect

        if option.state & QStyle.StateFlag.State_Selected:
            highlight = option.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight
            )
            fill = QColor(highlight)
            fill.setAlpha(115)
            painter.fillRect(rect, fill)
            border = QPen(highlight, 2)
            painter.setPen(border)
            painter.drawRect(rect.adjusted(1, 1, -2, -2))
            painter.setPen(
                option.palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Text)
            )

        px = self._thumb.display_pixel_size()
        w = rect.width()
        x = rect.x()
        y = rect.y()

        im = self._thumb.gallery_paint_pixmap(record, px)
        if im is None or im.isNull():
            icon = self._thumb.resolve_default_icon()
            im = icon.pixmap(px, px)
        ix = x + (w - im.width()) // 2
        iy = y + 4
        painter.drawPixmap(ix, iy, im)

        badge = self._thumb.health_badge_icon(record)
        paint_gallery_badge(painter, ix, iy, im.width(), im.height(), badge)

        text_y = iy + im.height() + 10
        margin = max(8, BADGE_MARGIN + 4)
        text_w = w - 2 * margin
        font_name = QFont(option.font)
        font_name.setBold(True)
        font_name.setPointSizeF(max(7.0, option.font.pointSizeF()))
        painter.setFont(font_name)
        fm = painter.fontMetrics()
        name_elided = fm.elidedText(
            str(record.name),
            Qt.TextElideMode.ElideRight,
            text_w,
        )
        painter.setPen(
            option.palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Text)
        )
        painter.drawText(
            QRect(x + margin, text_y, text_w, 20),
            int(Qt.AlignHCenter | Qt.AlignTop),
            name_elided,
        )
        line2 = f"{record.extension}  {format_file_size_display(record.size_bytes)}"
        small = QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.9))
        painter.setFont(small)
        fm2 = painter.fontMetrics()
        line2 = fm2.elidedText(
            line2,
            Qt.TextElideMode.ElideRight,
            text_w,
        )
        # Secondary line should look muted, not disabled.
        try:
            muted = option.palette.color(
                QPalette.ColorGroup.Active, QPalette.ColorRole.PlaceholderText
            )
        except Exception:  # noqa: BLE001
            muted = option.palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        painter.setPen(muted)
        painter.drawText(
            QRect(x + margin, text_y + 20, text_w, 32),
            int(Qt.AlignHCenter | Qt.AlignTop),
            line2,
        )

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        sh = index.data(Qt.ItemDataRole.SizeHintRole)
        if sh is not None:
            return sh
        return QSize(180, 220)
