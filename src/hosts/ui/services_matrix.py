"""Лёгкий список выбора DNS-профилей для Hosts page."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)
from qfluentwidgets import Action, RoundMenu

from ui.accessibility import set_control_accessibility, set_state_text
from ui.fluent_widgets import SettingsCard
from ui.theme import get_cached_qta_pixmap, get_theme_tokens, to_qcolor


@dataclass(slots=True)
class HostsServicesMatrixWidgets:
    card: SettingsCard
    view: "HostsServicesMatrixCanvas"
    model: "HostsServicesMatrixModel"


class HostsServicesMatrixModel(QAbstractTableModel):
    """Одна модель для всех DNS-сервисов вместо отдельных ComboBox."""

    KindRole = Qt.ItemDataRole.UserRole + 1
    ServiceNameRole = Qt.ItemDataRole.UserRole + 2
    ProfileNameRole = Qt.ItemDataRole.UserRole + 3
    AvailableRole = Qt.ItemDataRole.UserRole + 4
    SelectedRole = Qt.ItemDataRole.UserRole + 5
    IconNameRole = Qt.ItemDataRole.UserRole + 6
    IconColorRole = Qt.ItemDataRole.UserRole + 7

    def __init__(self, groups, *, off_label: str, parent=None):
        super().__init__(parent)
        self._off_label = str(off_label or "Откл.")
        self._profiles: list[tuple[str | None, str]] = [(None, self._off_label)]
        self._rows: list[dict[str, object]] = []
        self._selected_by_service: dict[str, str | None] = {}
        self._build(groups)

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return 2

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        kind = str(row.get("kind") or "")
        column = int(index.column())

        if role == self.KindRole:
            return kind

        if kind == "group":
            title = str(row.get("title") or "")
            count = int(row.get("count") or 0)
            if role == Qt.ItemDataRole.DisplayRole and column == 0:
                return f"{title}   {count}"
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return f"Группа hosts: {title}, сервисов: {count}"
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(get_theme_tokens().fg)
            return None

        row_plan = row.get("row_plan")
        if row_plan is None:
            return None
        service_name = str(getattr(row_plan, "service_name", "") or "")
        if role == self.ServiceNameRole:
            return service_name
        if role == self.IconNameRole:
            return str(getattr(row_plan, "icon_name", "") or "")
        if role == self.IconColorRole:
            return getattr(row_plan, "icon_color", None)

        if column == 0:
            if role == Qt.ItemDataRole.DisplayRole:
                return service_name
            if role == Qt.ItemDataRole.AccessibleTextRole:
                return f"Сервис hosts: {service_name}"
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(get_theme_tokens().fg)
            return None

        selected_profile = self._selected_by_service.get(service_name)
        selected_label = self._label_for_profile(selected_profile)

        if role == self.ProfileNameRole:
            return selected_profile
        if role == self.AvailableRole:
            return True
        if role == self.SelectedRole:
            return selected_profile is not None
        if role == Qt.ItemDataRole.DisplayRole:
            return selected_label
        if role == Qt.ItemDataRole.AccessibleTextRole:
            state = "отключено" if selected_profile is None else f"выбран профиль {selected_label}"
            return f"{service_name}: {state}"
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
        if role == Qt.ItemDataRole.ForegroundRole:
            tokens = get_theme_tokens()
            return QColor(tokens.accent_hex if selected_profile is not None else tokens.fg_muted)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if int(section) == 0:
            return "Сервис"
        if int(section) == 1:
            return "Профиль"
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled
        if self.is_group_row(index.row()):
            return base
        if index.column() == 1 and self.is_profile_available(index.row(), index.column()):
            return base | Qt.ItemFlag.ItemIsSelectable
        return base

    def is_group_row(self, row: int) -> bool:
        if row < 0 or row >= len(self._rows):
            return False
        return str(self._rows[row].get("kind") or "") == "group"

    def service_for_row(self, row: int) -> str:
        if row < 0 or row >= len(self._rows):
            return ""
        row_plan = self._rows[row].get("row_plan")
        return str(getattr(row_plan, "service_name", "") or "")

    def selected_profile_for_service(self, service_name: str) -> str | None:
        return self._selected_by_service.get(str(service_name or ""))

    def set_selected_profile_for_service(self, service_name: str, profile_name: str | None) -> None:
        service_name = str(service_name or "")
        if not service_name:
            return
        self._selected_by_service[service_name] = profile_name
        row = self._row_for_service(service_name)
        if row >= 0:
            self.dataChanged.emit(self.index(row, 1), self.index(row, 1))

    def update_selection(self, selection: dict[str, str]) -> None:
        normalized = {
            str(service_name): str(profile_name)
            for service_name, profile_name in dict(selection or {}).items()
            if str(service_name or "").strip() and str(profile_name or "").strip()
        }
        changed_rows: list[int] = []
        for row_idx, row in enumerate(self._rows):
            if str(row.get("kind") or "") != "service":
                continue
            row_plan = row.get("row_plan")
            service_name = str(getattr(row_plan, "service_name", "") or "")
            selected = normalized.get(service_name)
            if selected not in (getattr(row_plan, "available_profiles", []) or []):
                selected = None
            if self._selected_by_service.get(service_name) != selected:
                self._selected_by_service[service_name] = selected
                changed_rows.append(row_idx)
        for row in changed_rows:
            self.dataChanged.emit(self.index(row, 1), self.index(row, 1))

    def is_profile_available(self, row: int, column: int) -> bool:
        if row < 0 or row >= len(self._rows) or column != 1:
            return False
        item = self._rows[row]
        if str(item.get("kind") or "") != "service":
            return False
        return bool(self.profile_choices_for_row(row))

    def profile_choices_for_row(self, row: int) -> list[tuple[str | None, str, bool]]:
        if row < 0 or row >= len(self._rows):
            return []
        item = self._rows[row]
        if str(item.get("kind") or "") != "service":
            return []
        row_plan = item.get("row_plan")
        service_name = str(getattr(row_plan, "service_name", "") or "")
        selected = self._selected_by_service.get(service_name)
        choices: list[tuple[str | None, str, bool]] = [(None, self._off_label, selected is None)]
        available = set(getattr(row_plan, "available_profiles", []) or [])
        seen: set[str] = set()
        for profile_name, label in getattr(row_plan, "profile_items", []) or ():
            name = str(profile_name or "").strip()
            if not name or name in seen or name not in available:
                continue
            seen.add(name)
            choices.append((name, str(label or name).strip() or name, selected == name))
        return choices

    def _build(self, groups) -> None:
        profile_names: list[str] = []
        profile_labels: dict[str, str] = {}
        for group in groups or ():
            for profile_name, label in getattr(group, "common_profiles", []) or ():
                _append_profile(profile_names, profile_labels, profile_name, label)
            for row_plan in getattr(group, "rows", []) or ():
                for profile_name, label in getattr(row_plan, "profile_items", []) or ():
                    _append_profile(profile_names, profile_labels, profile_name, label)

        self._profiles.extend((name, profile_labels.get(name) or name) for name in profile_names)

        for group in groups or ():
            rows = list(getattr(group, "rows", []) or [])
            if not rows:
                continue
            self._rows.append(
                {
                    "kind": "group",
                    "title": str(getattr(group, "title", "") or ""),
                    "count": len(rows),
                }
            )
            for row_plan in rows:
                service_name = str(getattr(row_plan, "service_name", "") or "")
                selected = getattr(row_plan, "selected_profile", None)
                if selected not in (getattr(row_plan, "available_profiles", []) or []):
                    selected = None
                self._selected_by_service[service_name] = selected
                self._rows.append({"kind": "service", "row_plan": row_plan})

    def _label_for_profile(self, profile_name: str | None) -> str:
        for candidate, label in self._profiles:
            if candidate == profile_name:
                return label
        if profile_name is None:
            return self._off_label
        return str(profile_name or "").strip()

    def _row_supports_profile(self, row: int, profile_name: str | None) -> bool:
        if row < 0 or row >= len(self._rows):
            return False
        item = self._rows[row]
        if str(item.get("kind") or "") != "service":
            return False
        if profile_name is None:
            return True
        row_plan = item.get("row_plan")
        return profile_name in (getattr(row_plan, "available_profiles", []) or [])

    def _row_for_service(self, service_name: str) -> int:
        for row_idx, row in enumerate(self._rows):
            row_plan = row.get("row_plan")
            if str(getattr(row_plan, "service_name", "") or "") == service_name:
                return row_idx
        return -1


class HostsServicesMatrixDelegate(QStyledItemDelegate):
    """Лёгкая отрисовка строк: иконка, текст и выбранный профиль без QSS per-cell."""

    _ROW_HEIGHT = 38
    _GROUP_HEIGHT = 30

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        _ = option
        height = self._GROUP_HEIGHT if self._is_group(index) else self._ROW_HEIGHT
        return QSize(0, height)

    def _is_group(self, index: QModelIndex) -> bool:
        return str(index.data(HostsServicesMatrixModel.KindRole) or "") == "group"


class HostsServicesMatrixCanvas(QWidget):
    """Лёгкий список без QTableView: рисует только видимую часть."""

    _HEADER_HEIGHT = 38
    _SERVICE_COLUMN_MIN_WIDTH = 260
    _PROFILE_COLUMN_WIDTH = 220
    _ICON_SIZE = 18
    _SERVICE_LEFT_PADDING = 12

    def __init__(self, model: HostsServicesMatrixModel, *, on_profile_selected, on_bulk_profile_selected, parent=None):
        super().__init__(parent)
        self._model = model
        self._delegate = HostsServicesMatrixDelegate(self)
        self._on_profile_selected = on_profile_selected
        _ = on_bulk_profile_selected
        self._profile_menu = RoundMenu(parent=self)
        self._profile_menu.setObjectName("hostsServicesProfileMenu")
        self._row_tops: list[int] = []
        self._row_heights: list[int] = []
        self._hover_row = -1
        self._keyboard_row = -1
        self._total_height = self._HEADER_HEIGHT
        self.setObjectName("hostsServicesMatrix")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents, True)
        self._rebuild_geometry_cache()
        self._keyboard_row = self._first_service_row()
        self._model.dataChanged.connect(self._on_model_data_changed)

    def delegate(self) -> HostsServicesMatrixDelegate:
        return self._delegate

    def model(self) -> HostsServicesMatrixModel:
        return self._model

    def profile_column_width(self) -> int:
        return self._PROFILE_COLUMN_WIDTH

    def sizeHint(self) -> QSize:
        return QSize(self.minimumWidth(), self._total_height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def visible_rows_for_rect(self, rect: QRect) -> list[int]:
        if not rect.isValid() or not self._row_tops:
            return []
        top = int(rect.top())
        bottom = int(rect.bottom())
        rows: list[int] = []
        for row, row_top in enumerate(self._row_tops):
            row_bottom = row_top + self._row_heights[row] - 1
            if row_bottom < top:
                continue
            if row_top > bottom:
                break
            rows.append(row)
        return rows

    def paintEvent(self, event) -> None:  # noqa: N802
        tokens = get_theme_tokens()
        painter = QPainter(self)
        painter.fillRect(event.rect(), to_qcolor(tokens.surface_bg, "#343434"))
        if event.rect().intersects(QRect(0, 0, self.width(), self._HEADER_HEIGHT)):
            self._paint_header(painter, tokens)
        for row in self.visible_rows_for_rect(event.rect()):
            self._paint_row(painter, row, tokens, event.rect())
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        point = event.position().toPoint()
        column = self._column_at(point.x())
        if point.y() < self._HEADER_HEIGHT:
            return
        row = self._row_at(point.y())
        if row >= 0 and column == 1:
            self._set_keyboard_row(row)
            self._open_profile_menu(row, point)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            row = self._current_keyboard_row()
            if row >= 0:
                self._open_profile_menu(row, self._profile_menu_point_for_row(row))
                event.accept()
                return
        elif key == Qt.Key.Key_Down:
            self._move_keyboard_row(1)
            event.accept()
            return
        elif key == Qt.Key.Key_Up:
            self._move_keyboard_row(-1)
            event.accept()
            return
        elif key == Qt.Key.Key_Home:
            self._set_keyboard_row(self._first_service_row())
            event.accept()
            return
        elif key == Qt.Key.Key_End:
            self._set_keyboard_row(self._last_service_row())
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._set_keyboard_row(self._current_keyboard_row())
        super().focusInEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        point = event.position().toPoint()
        self._set_hover_row(self._row_at(point.y()) if point.y() >= self._HEADER_HEIGHT else -1)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._set_hover_row(-1)
        super().leaveEvent(event)

    def _set_hover_row(self, row: int) -> None:
        if row < 0 or row >= self._model.rowCount() or self._model.is_group_row(row):
            row = -1
        if self._hover_row == row:
            return
        old_row = self._hover_row
        self._hover_row = row
        for changed_row in (old_row, row):
            if 0 <= changed_row < len(self._row_tops):
                self.update(self._row_rect(changed_row))

    def _set_keyboard_row(self, row: int) -> None:
        if row < 0 or row >= self._model.rowCount() or self._model.is_group_row(row):
            row = self._first_service_row()
        if self._keyboard_row == row:
            return
        old_row = self._keyboard_row
        self._keyboard_row = row
        for changed_row in (old_row, row):
            if 0 <= changed_row < len(self._row_tops):
                self.update(self._row_rect(changed_row))

    def _current_keyboard_row(self) -> int:
        row = self._keyboard_row
        if 0 <= row < self._model.rowCount() and not self._model.is_group_row(row):
            return row
        return self._first_service_row()

    def _move_keyboard_row(self, step: int) -> None:
        service_rows = self._service_rows()
        if not service_rows:
            self._set_keyboard_row(-1)
            return
        current = self._current_keyboard_row()
        if current not in service_rows:
            self._set_keyboard_row(service_rows[0])
            return
        current_index = service_rows.index(current)
        next_index = min(max(current_index + int(step), 0), len(service_rows) - 1)
        self._set_keyboard_row(service_rows[next_index])

    def _first_service_row(self) -> int:
        rows = self._service_rows()
        return rows[0] if rows else -1

    def _last_service_row(self) -> int:
        rows = self._service_rows()
        return rows[-1] if rows else -1

    def _service_rows(self) -> list[int]:
        return [
            row
            for row in range(self._model.rowCount())
            if not self._model.is_group_row(row)
        ]

    def _rebuild_geometry_cache(self) -> None:
        self._row_tops = []
        self._row_heights = []
        y = self._HEADER_HEIGHT
        for row in range(self._model.rowCount()):
            height = self._delegate._GROUP_HEIGHT if self._model.is_group_row(row) else self._delegate._ROW_HEIGHT
            self._row_tops.append(y)
            self._row_heights.append(height)
            y += height
        self._total_height = y + 6
        min_width = self._SERVICE_COLUMN_MIN_WIDTH + self._PROFILE_COLUMN_WIDTH
        self.setMinimumWidth(min_width)
        self.setMinimumHeight(self._total_height)
        self.setMaximumHeight(self._total_height)

    def _row_rect(self, row: int) -> QRect:
        if row < 0 or row >= len(self._row_tops):
            return QRect()
        return QRect(0, self._row_tops[row], self.width(), self._row_heights[row])

    def _on_model_data_changed(self, top_left: QModelIndex, bottom_right: QModelIndex) -> None:
        if not top_left.isValid() or not bottom_right.isValid():
            self.update()
            return
        top = self._row_tops[max(0, top_left.row())] if self._row_tops else 0
        bottom_row = min(bottom_right.row(), len(self._row_tops) - 1)
        bottom = self._row_tops[bottom_row] + self._row_heights[bottom_row] if bottom_row >= 0 else self.height()
        self.update(QRect(0, top, self.width(), max(1, bottom - top)))

    def _service_column_width(self) -> int:
        return max(self._SERVICE_COLUMN_MIN_WIDTH, self.width() - self._PROFILE_COLUMN_WIDTH)

    def _column_rect(self, column: int) -> QRect:
        service_width = self._service_column_width()
        if column <= 0:
            return QRect(0, 0, service_width, self.height())
        if column == 1:
            x = service_width
            return QRect(x, 0, self._PROFILE_COLUMN_WIDTH, self.height())
        x = service_width + self._PROFILE_COLUMN_WIDTH
        return QRect(x, 0, self._PROFILE_COLUMN_WIDTH, self.height())

    def _column_at(self, x: int) -> int:
        service_width = self._service_column_width()
        if x < service_width:
            return 0
        if x < service_width + self._PROFILE_COLUMN_WIDTH:
            return 1
        return -1

    def _profile_menu_point_for_row(self, row: int):
        rect = QRect(
            self._column_rect(1).left(),
            self._row_tops[row],
            self._PROFILE_COLUMN_WIDTH,
            self._row_heights[row],
        )
        return rect.center()

    def _row_at(self, y: int) -> int:
        for row, row_top in enumerate(self._row_tops):
            if row_top <= y < row_top + self._row_heights[row]:
                return row
            if row_top > y:
                break
        return -1

    def _paint_header(self, painter: QPainter, tokens) -> None:
        rect = QRect(0, 0, self.width(), self._HEADER_HEIGHT)
        painter.fillRect(rect, to_qcolor(tokens.surface_bg, "#343434"))
        painter.setPen(to_qcolor(tokens.fg_muted, "#d7dde7"))
        metrics = QFontMetrics(painter.font())
        for column in range(self._model.columnCount()):
            column_rect = self._column_rect(column)
            header_rect = QRect(column_rect.left(), 0, column_rect.width(), self._HEADER_HEIGHT).adjusted(8, 0, -8, 0)
            text = str(self._model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole) or "")
            painter.drawText(
                header_rect,
                int(Qt.AlignmentFlag.AlignCenter),
                metrics.elidedText(text, Qt.TextElideMode.ElideRight, header_rect.width()),
            )

    def _paint_row(self, painter: QPainter, row: int, tokens, dirty_rect: QRect) -> None:
        row_rect = self._row_rect(row)
        if self._model.is_group_row(row):
            self._paint_group_row(painter, row, row_rect, tokens)
            return
        if row == self._hover_row or (self.hasFocus() and row == self._keyboard_row):
            self._paint_hover_row_background(painter, row_rect, tokens)
        self._paint_service_cell(painter, row, row_rect, tokens, dirty_rect)
        profile_rect = QRect(
            self._column_rect(1).left(),
            row_rect.top(),
            self._PROFILE_COLUMN_WIDTH,
            row_rect.height(),
        )
        if profile_rect.intersects(dirty_rect):
            self._paint_profile_cell(painter, row, profile_rect, tokens)

    def _paint_hover_row_background(self, painter: QPainter, row_rect: QRect, tokens) -> None:
        hover_rect = row_rect.adjusted(6, 2, -6, -2)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(to_qcolor(tokens.surface_bg_hover, tokens.surface_bg))
        painter.drawRoundedRect(hover_rect, 6, 6)
        painter.restore()

    def _paint_group_row(self, painter: QPainter, row: int, row_rect: QRect, tokens) -> None:
        text = str(self._model.data(self._model.index(row, 0), Qt.ItemDataRole.DisplayRole) or "")
        if not text:
            return
        original_font = painter.font()
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(8, font.pointSize() - 1))
        painter.setFont(font)
        painter.setPen(to_qcolor(tokens.fg_muted, "#d7dde7"))
        painter.drawText(
            row_rect.adjusted(self._SERVICE_LEFT_PADDING, 0, -8, 0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            text,
        )
        painter.setFont(original_font)

    def _paint_service_cell(self, painter: QPainter, row: int, row_rect: QRect, tokens, dirty_rect: QRect) -> None:
        service_rect = QRect(0, row_rect.top(), self._service_column_width(), row_rect.height())
        if not service_rect.intersects(dirty_rect):
            return
        index = self._model.index(row, 0)
        rect = service_rect.adjusted(self._SERVICE_LEFT_PADDING, 0, -8, 0)
        center_y = rect.center().y()
        icon_name = str(self._model.data(index, HostsServicesMatrixModel.IconNameRole) or "fa5s.globe")
        icon_color = self._model.data(index, HostsServicesMatrixModel.IconColorRole) or tokens.icon_fg_faint
        icon_rect = QRect(rect.left(), center_y - self._ICON_SIZE // 2, self._ICON_SIZE, self._ICON_SIZE)
        pixmap = get_cached_qta_pixmap(icon_name, color=icon_color, size=self._ICON_SIZE)
        if not pixmap.isNull():
            painter.drawPixmap(icon_rect, pixmap)
        else:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(to_qcolor(icon_color, tokens.icon_fg_faint))
            painter.drawEllipse(icon_rect.adjusted(3, 3, -3, -3))
            painter.restore()

        text_rect = QRect(icon_rect.right() + 10, rect.top(), max(0, rect.right() - icon_rect.right() - 10), rect.height())
        text = str(self._model.data(index, Qt.ItemDataRole.DisplayRole) or "")
        metrics = QFontMetrics(painter.font())
        painter.setPen(to_qcolor(tokens.fg, "#f5f5f5"))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width()),
        )

    def _paint_profile_cell(self, painter: QPainter, row: int, rect: QRect, tokens) -> None:
        index = self._model.index(row, 1)
        text = str(self._model.data(index, Qt.ItemDataRole.DisplayRole) or "")
        if not text:
            return
        selected = bool(self._model.data(index, HostsServicesMatrixModel.SelectedRole))
        text_color = to_qcolor(tokens.fg if selected else tokens.fg_muted, tokens.fg_muted)
        content_rect = rect.adjusted(12, 0, -12, 0)

        metrics = QFontMetrics(painter.font())
        arrow = "▾"
        arrow_width = metrics.horizontalAdvance(arrow) + 2
        text_rect = content_rect.adjusted(0, 0, -(arrow_width + 10), 0)
        painter.setPen(text_color)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width()),
        )
        painter.drawText(
            content_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            arrow,
        )

    def _open_profile_menu(self, row: int, point) -> None:
        if self._model.is_group_row(row):
            return
        service_name = self._model.service_for_row(row)
        if not service_name:
            return
        choices = self._model.profile_choices_for_row(row)
        if not choices:
            return

        menu = self._profile_menu
        menu.clear()
        tokens = get_theme_tokens()
        for profile_name, label, selected in choices:
            action = Action(label, menu)
            action.setCheckable(True)
            action.setChecked(bool(selected))
            if selected:
                action.setIcon(_selected_profile_menu_icon(tokens))
            action.setData(profile_name)
            action.triggered.connect(
                lambda _checked=False, s=service_name, p=profile_name: self._on_profile_selected(s, p)
            )
            menu.addAction(action)
            menu_item = menu.view.item(menu.view.count() - 1)
            if menu_item is not None:
                state = "выбран" if selected else "не выбран"
                accessible_text = f"{service_name}: {label}, {state}"
                menu_item.setData(Qt.ItemDataRole.AccessibleTextRole, accessible_text)
                menu_item.setData(Qt.ItemDataRole.AccessibleDescriptionRole, accessible_text)
        menu.exec(self.mapToGlobal(point))


def build_hosts_services_matrix(
    groups,
    *,
    off_label: str,
    on_profile_selected,
    on_bulk_profile_selected,
    title: str = "DNS-службы",
) -> HostsServicesMatrixWidgets:
    card = SettingsCard()
    model = HostsServicesMatrixModel(groups, off_label=off_label)
    view = HostsServicesMatrixCanvas(
        model,
        on_profile_selected=on_profile_selected,
        on_bulk_profile_selected=on_bulk_profile_selected,
    )

    _apply_matrix_style(view)
    set_control_accessibility(
        view,
        name=title,
        description=(
            "Список выбора DNS-профиля для каждого сервиса. "
            "Слева сервисы, справа текущий профиль."
        ),
    )
    set_state_text(view, title)
    _apply_matrix_focus_policy(view)

    card.add_widget(view)
    return HostsServicesMatrixWidgets(card=card, view=view, model=model)


def _selected_profile_menu_icon(tokens=None) -> QIcon:
    tokens = tokens or get_theme_tokens()
    pixmap = QPixmap(14, 18)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(to_qcolor(tokens.accent_hex, tokens.accent_hex))
    painter.drawRoundedRect(QRect(5, 3, 3, 12), 2, 2)
    painter.end()
    return QIcon(pixmap)


def _apply_matrix_focus_policy(view: QWidget) -> None:
    view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def _append_profile(profile_names: list[str], profile_labels: dict[str, str], profile_name: str, label: str) -> None:
    name = str(profile_name or "").strip()
    if not name or name in profile_labels:
        return
    profile_names.append(name)
    profile_labels[name] = str(label or name).strip() or name


def _apply_matrix_style(view: QWidget) -> None:
    tokens = get_theme_tokens()
    view.setStyleSheet(
        f"""
        QWidget#hostsServicesMatrix {{
            background: {tokens.surface_bg};
            border: none;
            outline: none;
            color: {tokens.fg};
        }}
        """
    )


__all__ = [
    "HostsServicesMatrixCanvas",
    "HostsServicesMatrixDelegate",
    "HostsServicesMatrixModel",
    "HostsServicesMatrixWidgets",
    "build_hosts_services_matrix",
]
