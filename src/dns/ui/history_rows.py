"""Общий список прошлых проверок DNS: открывается только по нажатию."""
from dataclasses import dataclass, replace
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout
from qfluentwidgets import StrongBodyLabel
from blockcheck.ui.brand_icons import BrandIcon
from blockcheck.ui.result_cards import TilesGrid, plain_tile
from blockcheck.ui.result_cards_model import Line
from ui.accessibility import set_state_text
TILE_MIN_WIDTH=260

@dataclass(frozen=True)
class Row:
    state: str
    name: str
    text: str

@dataclass(frozen=True)
class RowGroup:
    title: str
    rows: tuple

def history_groups(runs):
    from diagnostics.history import history_rows
    rows=tuple(Row(*row) for row in history_rows(runs))
    return (RowGroup("Прошлые проверки",rows),) if rows else ()


class _TilesGroup(QWidget):
    """Группа строк: заголовок со значком и сетка плиток, которую рисует один виджет."""

    def __init__(self, group, icon: str, parent=None, *, clickable: bool = False) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(BrandIcon(icon, "", self, size=15), 0, Qt.AlignmentFlag.AlignVCenter)
        self.title_label = StrongBodyLabel(group.title, self)
        header.addWidget(self.title_label, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)
        tiles = [plain_tile(Line(row.state, row.name, row.text)) for row in group.rows]
        if clickable:
            tiles = [replace(tile, hint=f"{tile.hint}\nНажмите, чтобы открыть эту проверку") for tile in tiles]
        self.grid = TilesGrid(tiles, self, clickable=clickable, min_width=TILE_MIN_WIDTH)
        layout.addWidget(self.grid)


class RowsView(QWidget):
    """Группы строк плитками: значок состояния, подпись и значение; полный текст — в подсказке.

    Плитки группы рисует один виджет. Строка-виджет на каждую запись (а их
    десятки) делала вкладку тяжёлой: долго строилась и дёргалась при прокрутке.
    """

    # Нажали плитку: (номер группы, номер строки в ней).
    opened = pyqtSignal(int, int)

    def __init__(self, parent=None, *, icon: str = "fa5s.list-ul", clickable: bool = False) -> None:
        super().__init__(parent)
        self._icon = icon
        self._clickable = clickable
        self._shown: tuple = ()
        self._blocks: list[QWidget] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)

    def groups(self) -> tuple:
        return self._shown

    def blocks(self) -> list[QWidget]:
        return list(self._blocks)

    def show_groups(self, groups) -> None:
        groups = tuple(groups)
        if groups == self._shown:
            return
        # Перестраивается только то, что изменилось: строка — это несколько виджетов,
        # и пересборка всех групп на каждый новый ответ подвешивала окно.
        same = 0
        while same < min(len(groups), len(self._shown)) and groups[same] == self._shown[same]:
            same += 1
        for block in self._blocks[same:]:
            self._layout.removeWidget(block)
            block.deleteLater()
        self._blocks = self._blocks[:same]
        self._shown = groups
        for group in groups[same:]:
            block = _TilesGroup(group, self._icon, self, clickable=self._clickable)
            block.grid.opened.connect(lambda row, order=len(self._blocks): self.opened.emit(order, row))
            self._layout.addWidget(block)
            self._blocks.append(block)
        set_state_text(self, "; ".join(f"{group.title}: строк {len(group.rows)}" for group in groups) or "нет данных")
