"""Палитра и геометрия оболочки net67.

Оформление перенесено из плеера Nora (MIT, © 2023 Sandakan Nipunajith).
Перенесены именно значения — цвета, отступы, скругления, — а не код:
Nora написана на Electron с React и Tailwind, и её компоненты в Qt не
вставляются. Уведомление об авторских правах лежит в
`THIRD_PARTY_LICENSES.md`, как того требует MIT.

Цвета взяты из `src/renderer/src/assets/styles/styles.css` и переведены
из HSL в шестнадцатеричный вид:

    --dark-background-color-1: 228 7% 14%   ->  #212226
    --dark-background-color-2: 225 8% 20%   ->  #2f3137
    --dark-side-bar-background: 228 7% 20%  ->  #2f3137
    --dark-context-menu-list-hover: 224 8% 28% -> #42454d
    --dark-text-color-highlight-2: 244 98% 80% -> #a19afe

Фон здесь не серый, а холодный графит с синим подтоном, и акцент
сиреневый. Это осознанное отступление от прежнего строгого монохрома:
взят чужой облик целиком, а не наполовину. Обесцветить всё до серого —
одна правка в этом файле.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShellPalette:
    """Цвета оболочки."""

    window: str
    surface: str
    surface_hover: str
    rail: str
    #: Фон правой половины. Отдельно от window: карточки должны лежать
    #: на своём слое, иначе они сливаются с рамкой окна.
    content: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_faint: str
    accent: str
    on_accent: str
    scrollbar_track: str
    scrollbar_handle: str
    scrollbar_handle_hover: str


#: Тёмная палитра. Лестница глубины, снизу вверх:
#:
#:     #101013  окно          — самый нижний слой, «стол»
#:     #17171a  содержимое    — лист, на котором лежат карточки
#:     #202024  карточка      — сама карточка
#:     #1b1b1f  панель        — боковая рейка
#:     #2c2c31  наведение     — единственный слой выше карточки
#:
#: Синий подтон убран целиком: просили «серо-бело-чёрный», а графит с
#: подтоном серым не является — синий канал был выше красного на четыре
#: единицы, и на большой площади это видно. Здесь у каждого цвета все
#: три канала равны, без исключений. Проверяется тестом: неравные каналы
#: уже давали лиловый налёт после того, как тёмная тема qfluentwidgets
#: осветляла акцент.
DARK = ShellPalette(
    window="#101010",
    surface="#202020",
    surface_hover="#2d2d2d",
    rail="#1a1a1a",
    content="#171717",
    border="#262626",
    border_strong="#3b3b3b",
    text="#f2f2f2",
    text_muted="#a8a8a8",
    text_faint="#767676",
    accent="#e9e9e9",
    on_accent="#101010",
    scrollbar_track="#171717",
    scrollbar_handle="#3b3b3b",
    scrollbar_handle_hover="#565656",
)

#: Палитра светлой темы — зеркало тёмной, а не отдельная выдумка.
#:
#: Название темы с большой буквы в этом файле не пишем намеренно: страж
#: архитектуры запрещает прежние человекочитаемые имена тем во всём src
#: и ищет их по подстроке, не разбирая, код это или примечание.
#:
#: Она была сломана целиком: цвета брались из Nora, где светлая тема
#: голубоватая, а текст задан чистым чёрным — на белом это режет глаза
#: и выглядит как незаконченная вёрстка. Здесь та же лестница слоёв, но
#: сверху вниз: окно самое светлое, панель темнее содержимого ровно
#: настолько же, насколько в тёмной теме была светлее.
LIGHT = ShellPalette(
    window="#ffffff",
    surface="#ffffff",
    surface_hover="#ededed",
    rail="#f2f2f2",
    content="#f7f7f7",
    border="#e6e6e6",
    border_strong="#c9c9c9",
    text="#1a1a1a",
    text_muted="#5c5c5c",
    text_faint="#8a8a8a",
    accent="#1a1a1a",
    on_accent="#ffffff",
    scrollbar_track="#f7f7f7",
    scrollbar_handle="#c9c9c9",
    scrollbar_handle_hover="#a5a5a5",
)


def palette(dark: bool = True) -> ShellPalette:
    return DARK if dark else LIGHT


#: Ширина рейки навигации.
#:
#: В Nora боковая панель занимает 30% ширины, но не больше 18rem —
#: `w-[30%] !max-w-[18rem]`. 18rem при базовом кегле 16 это 288 пикселей.
RAIL_WIDTH = 288

#: Скругление верхнего правого угла рейки.
#:
#: В Nora это `rounded-tr-2xl`, то есть 16 пикселей. Мелочь, но именно
#: она отличает её панель от обычного прямоугольного меню.
RAIL_CORNER_RADIUS = 16

#: Отступы и промежуток между пунктами: `pt-4 pb-2 gap-1`.
RAIL_PADDING_TOP = 16
RAIL_PADDING_BOTTOM = 8
RAIL_ITEM_GAP = 4

#: Скругления. Три ступени вместо двух: крупная для панелей, средняя для
#: карточек, мелкая для пунктов и кнопок. Числа заметно больше прежних
#: 8 и 12 — мягкие углы и есть половина ощущения «дорогого» интерфейса,
#: вторая половина это плавность.
PANEL_RADIUS = 20
CARD_RADIUS = 14
ITEM_RADIUS = 11

#: Кривая плавности для всего движения в оболочке.
#:
#: Резкий разгон и долгое затухание: движение начинается мгновенно, а
#: заканчивается почти незаметно. У встроенного OutCubic хвост короче, и
#: остановка читается как щелчок.
EASE_X1, EASE_Y1, EASE_X2, EASE_Y2 = 0.16, 1.0, 0.3, 1.0


def shell_easing():
    """Кривая плавности как объект Qt. None — если Qt недоступен."""
    try:
        from PyQt6.QtCore import QEasingCurve

        curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
        curve.addCubicBezierSegment(
            _point(EASE_X1, EASE_Y1), _point(EASE_X2, EASE_Y2), _point(1.0, 1.0)
        )
        return curve
    except Exception:
        return None


def _point(x: float, y: float):
    from PyQt6.QtCore import QPointF

    return QPointF(float(x), float(y))

#: Толщина полосы прокрутки.
SCROLLBAR_WIDTH = 8


# ──────────────────────────────────────────────────────────────────────
# Типографика
# ──────────────────────────────────────────────────────────────────────
#
# До этого кегли назначались на месте: 17 здесь, 12 там, где-то 13, а
# где-то умолчание Qt — «Sans Serif 9», то есть вообще не тот шрифт,
# которым набрана Windows. Отсюда и ощущение неряшливости: восемь разных
# размеров на одном экране и системный шрифт, не совпадающий ни с чем.
#
# Шкала ниже — четыре ступени с шагом примерно в 1,25 и три насыщенности.
# Больше не нужно: всё, что не помещается в четыре ступени, обычно
# означает, что на экране слишком много всего.

#: Гарнитура. Порядок важен: Segoe UI Variable — шрифт Windows 11, у него
#: отдельные начертания для мелкого и крупного кегля; Segoe UI — Windows
#: 10; остальное на случай, если приложение запустят не на Windows.
FONT_STACK = (
    "Segoe UI Variable Text",
    "Segoe UI",
    "Inter",
    "Noto Sans",
    "sans-serif",
)

#: Гарнитура для крупных заголовков. У Variable Display рисунок
#: рассчитан на большой кегль: уже, с меньшим межбуквенным просветом.
FONT_STACK_DISPLAY = ("Segoe UI Variable Display", *FONT_STACK)

#: Базовый кегль в пунктах. Windows по умолчанию набрана девятью, но в
#: окне на весь экран это мелко: строки идут длиннее, и глаз теряет
#: строку. Десять — то же, что в «Параметрах» Windows 11.
BASE_POINT_SIZE = 10

#: Ступени шкалы в пикселях.
FONT_DISPLAY = 26
FONT_TITLE = 20
FONT_SUBTITLE = 16
FONT_BODY = 14
FONT_CAPTION = 12

#: Насыщенности. Полужирный у нас 600, а не 700: в Segoe UI Variable
#: семисотое начертание на мелком кегле выглядит грубо.
WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_BOLD = 600


def font_family_css(display: bool = False) -> str:
    """Гарнитура для таблицы стилей, с запасными вариантами."""
    stack = FONT_STACK_DISPLAY if display else FONT_STACK
    return ", ".join(f'"{name}"' if " " in name else name for name in stack)


def typography_qss() -> str:
    """Единая шкала кеглей и насыщенностей для всего окна.

    Задаётся один раз на окне и наследуется вниз. Точечные кегли на
    отдельных виджетах после этого нужны только там, где элемент
    сознательно выпадает из шкалы, — например, счётчик времени внутри
    круглой кнопки.
    """
    return f"""
* {{ font-family: {font_family_css()}; }}

QWidget {{ font-size: {FONT_BODY}px; font-weight: {WEIGHT_REGULAR}; }}

QWidget TitleLabel, QWidget LargeTitleLabel {{
    font-family: {font_family_css(display=True)};
    font-size: {FONT_TITLE}px;
    font-weight: {WEIGHT_BOLD};
}}
QWidget SubtitleLabel {{ font-size: {FONT_SUBTITLE}px; font-weight: {WEIGHT_BOLD}; }}
QWidget StrongBodyLabel {{ font-size: {FONT_BODY}px; font-weight: {WEIGHT_MEDIUM}; }}
QWidget BodyLabel {{ font-size: {FONT_BODY}px; }}
QWidget CaptionLabel {{ font-size: {FONT_CAPTION}px; }}

QPushButton#net67NavItem {{ font-size: {FONT_BODY}px; font-weight: {WEIGHT_MEDIUM}; }}
QPushButton#net67GroupTab {{ font-size: {FONT_CAPTION + 1}px; font-weight: {WEIGHT_BOLD}; }}
QPushButton#net67PageTab {{ font-size: {FONT_CAPTION + 1}px; font-weight: {WEIGHT_MEDIUM}; }}
QPushButton#net67NavItem:checked {{ font-weight: {WEIGHT_BOLD}; }}
QLabel#net67SectionLabel {{
    font-size: {FONT_CAPTION - 1}px;
    font-weight: {WEIGHT_BOLD};
    text-transform: uppercase;
}}
QLabel#net67Title {{ font-size: {FONT_CAPTION + 1}px; font-weight: {WEIGHT_BOLD}; }}
"""


def apply_application_font(app) -> bool:
    """Ставит гарнитуру и базовый кегль приложению.

    Без этого Qt берёт «Sans Serif 9» — замерено, — и окно набрано не тем
    шрифтом, которым набрана сама Windows. В таблице стилей гарнитуру
    задать можно, но кегль в пунктах там не выражается, а именно от него
    зависят системные пересчёты под масштабирование экрана.
    """
    if app is None:
        return False
    try:
        from PyQt6.QtGui import QFont, QFontDatabase

        available = set(QFontDatabase.families())
        family = next((name for name in FONT_STACK if name in available), "")
        if not family:
            return False

        font = QFont(family)
        font.setPointSize(BASE_POINT_SIZE)
        font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
        app.setFont(font)
        return True
    except Exception:
        return False


def scrollbar_qss(colors: ShellPalette, *, width: int = SCROLLBAR_WIDTH) -> str:
    """Свои полосы прокрутки вместо системных.

    Системная полоса в Windows остаётся широкой и светлой независимо от
    темы приложения и в тёмном окне выглядит вставкой из другой
    программы. Кнопки со стрелками убираем: у них нулевая высота, иначе
    на концах полосы остаются пустые квадраты.
    """
    return f"""
QScrollBar:vertical {{
    background: {colors.scrollbar_track};
    width: {width}px;
    margin: 2px 2px 2px 0px;
    border-radius: {width // 2}px;
}}
QScrollBar::handle:vertical {{
    background: {colors.scrollbar_handle};
    min-height: 36px;
    border-radius: {width // 2}px;
}}
QScrollBar::handle:vertical:hover {{ background: {colors.scrollbar_handle_hover}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QScrollBar:horizontal {{
    background: {colors.scrollbar_track};
    height: {width}px;
    margin: 0px 2px 2px 2px;
    border-radius: {width // 2}px;
}}
QScrollBar::handle:horizontal {{
    background: {colors.scrollbar_handle};
    min-width: 36px;
    border-radius: {width // 2}px;
}}
QScrollBar::handle:horizontal:hover {{ background: {colors.scrollbar_handle_hover}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
"""


def content_qss(colors: ShellPalette) -> str:
    """Стиль правой части: карточки настроек, кнопки, поля.

    Правая часть собрана из виджетов qfluentwidgets, и каждый из них
    несёт собственную таблицу стилей — у обычной кнопки она на семь с
    половиной тысяч знаков. Стиль, заданный на самом виджете, побеждает
    унаследованный от предка при равной точности селектора.

    Поэтому селекторы здесь вложенные: `QWidget SettingCard` точнее, чем
    `SettingCard`, и потому берёт верх. Проверено замером цвета точки
    внутри карточки: без этого она оставалась светло-серой.
    """
    return f"""
QWidget SettingCardGroup {{ background: transparent; border: none; }}
QWidget SettingCardGroup > QLabel {{
    color: {colors.text};
    font-size: {FONT_SUBTITLE}px;
    font-weight: {WEIGHT_BOLD};
}}

QWidget SettingCard,
QWidget Win11ToggleRow,
QWidget Win11ComboRow,
QWidget CardWidget,
QWidget SimpleCardWidget,
QWidget ElevatedCardWidget {{
    background: {colors.surface};
    border: none;
    border-radius: {CARD_RADIUS}px;
}}
QWidget SettingCard:hover,
QWidget Win11ToggleRow:hover,
QWidget Win11ComboRow:hover {{ background: {colors.surface_hover}; }}

QWidget TitleLabel, QWidget SubtitleLabel, QWidget StrongBodyLabel {{ color: {colors.text}; }}
QWidget BodyLabel {{ color: {colors.text}; }}
QWidget CaptionLabel {{ color: {colors.text_muted}; }}

QWidget PushButton, QWidget ToolButton, QWidget TransparentPushButton {{
    background: {colors.surface_hover};
    color: {colors.text};
    border: none;
    border-radius: {ITEM_RADIUS}px;
    padding: 6px 14px;
}}
QWidget PushButton:hover, QWidget ToolButton:hover {{ background: {colors.border_strong}; }}
QWidget PushButton:pressed, QWidget ToolButton:pressed {{ background: {colors.border}; }}

QWidget PrimaryPushButton {{
    background: {colors.accent};
    color: {colors.on_accent};
    border: none;
    border-radius: {ITEM_RADIUS}px;
    font-weight: {WEIGHT_BOLD};
}}
QWidget PrimaryPushButton:hover {{ background: {colors.accent}; }}
QWidget PrimaryPushButton:pressed {{ background: {colors.text_muted}; }}

QWidget ComboBox, QWidget LineEdit, QWidget SearchLineEdit, QWidget SpinBox {{
    background: {colors.surface_hover};
    color: {colors.text};
    border: 1px solid {colors.border};
    border-radius: {ITEM_RADIUS}px;
    padding: 5px 10px;
}}
QWidget ComboBox:hover, QWidget LineEdit:hover {{ border: 1px solid {colors.border_strong}; }}

QListWidget#net67ServerList {{
    background: {colors.surface};
    color: {colors.text};
    border: none;
    border-radius: {CARD_RADIUS}px;
    padding: 4px;
}}
QListWidget#net67ServerList::item {{
    padding: 7px 10px;
    border-radius: {ITEM_RADIUS}px;
}}
QListWidget#net67ServerList::item:hover {{ background: {colors.surface_hover}; }}
QListWidget#net67ServerList::item:selected {{
    background: {colors.accent};
    color: {colors.on_accent};
}}

/* Переключатель вкладок внутри страницы — SegmentedWidget из
   qfluentwidgets. Цвет текста ему приходилось задавать здесь, потому
   что таблица стилей родителя каскадом перекрывает его собственную.

   Замер: та же полоса под родителем без стилей даёт 15742 светлых
   пикселя, под родителем с одной строкой `background:` — 69. То есть
   надписи «Amnezia» и «VPN» пропадали полностью, полоса выглядела
   пустым прямоугольником, и переключиться было не на что: человек
   оставался на первой вкладке и видел её тексты. */
QWidget SegmentedItem {{
    background: transparent;
    border: none;
    color: {colors.text_muted};
    padding: 6px 16px;
    font-weight: {WEIGHT_MEDIUM};
}}
QWidget SegmentedItem:hover {{
    background: {colors.surface_hover};
    color: {colors.text};
    border-radius: {ITEM_RADIUS}px;
}}
QWidget SegmentedItem:checked {{
    background: {colors.surface};
    color: {colors.text};
    border-radius: {ITEM_RADIUS}px;
    font-weight: {WEIGHT_BOLD};
}}
QWidget SegmentedItem:pressed {{ background: {colors.surface_hover}; }}
QWidget SegmentedWidget {{ background: transparent; }}

QWidget TableWidget, QWidget ListWidget, QWidget TreeWidget, QWidget TextEdit, QWidget PlainTextEdit {{
    background: {colors.surface};
    color: {colors.text};
    border: none;
    border-radius: {CARD_RADIUS}px;
}}
"""


def shell_qss(colors: ShellPalette) -> str:
    """Стиль оболочки целиком."""
    return f"""
#net67Window {{ background: {colors.window}; }}
#net67Rail {{
    background: {colors.rail};
    border: none;
    border-top-right-radius: {RAIL_CORNER_RADIUS}px;
}}
/* Полоса заголовка непрозрачная. Прозрачной она была ради свечения,
   но за прозрачным виджетом в безрамочном окне Windows нет ничего: при
   перерисовке там на кадр проступает неинициализированная поверхность —
   человек описал это как «белая полоса сверху при переходе во вкладку».
   Свечение до заголовка всё равно не доходит, пятна у краёв окна. */
#net67TitleBar {{ background: {colors.content}; border: none; }}
/* Прозрачное содержимое: под ним лежит слой свечения, и сплошная
   заливка перекрыла бы его целиком. Цену этой прозрачности слой
   отрабатывает четырьмя кадрами в секунду вместо шестидесяти —
   подробности в shell/ambient.py. */
#net67Content {{ background: transparent; }}
#net67Window {{ background: {colors.content}; }}

QLabel#net67Title {{ color: {colors.text}; }}
QLabel#net67SectionLabel {{ color: {colors.text_faint}; }}

QPushButton#net67NavItem {{
    background: transparent;
    border: none;
    border-radius: {ITEM_RADIUS}px;
    color: {colors.text_muted};
    text-align: left;
    padding: 10px 16px;
    margin: 0px 10px;
}}
QPushButton#net67NavItem:hover {{ background: {colors.surface_hover}; color: {colors.text}; }}
QPushButton#net67NavItem:checked {{
    background: {colors.accent};
    color: {colors.on_accent};
}}
/* Отклик на нажатие. Без него пункт меняется только после того, как
   страница уже переключилась, и палец не чувствует, что попал. */
QPushButton#net67NavItem:pressed {{
    background: {colors.border_strong};
    padding-left: 18px;
}}
QPushButton#net67NavItem:checked:pressed {{ background: {colors.accent}; }}

QPushButton#net67GroupTab {{
    background: transparent;
    border: none;
    color: {colors.text_muted};
    padding: 0px 13px;
    margin: 0px;
}}
QPushButton#net67GroupTab:hover {{ color: {colors.text}; }}
QPushButton#net67GroupTab:checked {{ color: {colors.text}; }}
/* Отклик на нажатие. Минимальный, но заметный: без него палец не
   чувствует, что попал, и человек жмёт второй раз. */
QPushButton#net67GroupTab:pressed {{ color: {colors.text_faint}; }}
QPushButton#net67PageTab:pressed {{ background: {colors.border_strong}; }}
QListWidget#net67ServerList::item:pressed {{ background: {colors.border_strong}; }}

#net67PageTabs {{ background: transparent; }}
QPushButton#net67PageTab {{
    background: transparent;
    border: none;
    border-radius: {ITEM_RADIUS}px;
    color: {colors.text_muted};
    padding: 5px 14px;
}}
QPushButton#net67PageTab:hover {{ background: {colors.surface}; color: {colors.text}; }}
QPushButton#net67PageTab:checked {{
    background: {colors.surface_hover};
    color: {colors.text};
}}

/* Кнопка режима обведена, а не залита. Заливка спорила с залитой
   вкладкой рядом: два пятна одного веса в одной строке заставляют глаз
   выбирать, какое из них главное. Тонкая рамка такого спора не
   создаёт, а «включено» показывает заливкой только нажатое состояние. */
QPushButton#net67AdvancedToggle {{
    background: transparent;
    border: 1px solid {colors.border_strong};
    border-radius: 13px;
    color: {colors.text_muted};
    padding: 4px 14px;
    margin: 0px 10px;
}}
QPushButton#net67AdvancedToggle:hover {{
    border: 1px solid {colors.text_faint};
    color: {colors.text};
}}
QPushButton#net67AdvancedToggle:pressed {{
    background: {colors.surface_hover};
}}
QPushButton#net67AdvancedToggle:checked {{
    background: {colors.accent};
    border: 1px solid {colors.accent};
    color: {colors.on_accent};
    font-weight: {WEIGHT_BOLD};
}}
QPushButton#net67AdvancedToggle:checked:pressed {{
    background: {colors.text_muted};
    border: 1px solid {colors.text_muted};
}}

QPushButton#net67WindowButton {{
    background: transparent; border: none; color: {colors.text_muted};
    font-size: {FONT_BODY}px; padding: 0px;
}}
QPushButton#net67WindowButton:hover {{ background: {colors.surface_hover}; color: {colors.text}; }}
QPushButton#net67CloseButton:hover {{ background: #c1121f; color: #ffffff; }}
""" + typography_qss() + scrollbar_qss(colors) + content_qss(colors)


__all__ = [
    "BASE_POINT_SIZE",
    "CARD_RADIUS",
    "EASE_X1",
    "EASE_X2",
    "EASE_Y1",
    "EASE_Y2",
    "PANEL_RADIUS",
    "shell_easing",
    "FONT_BODY",
    "FONT_CAPTION",
    "FONT_DISPLAY",
    "FONT_STACK",
    "FONT_STACK_DISPLAY",
    "FONT_SUBTITLE",
    "FONT_TITLE",
    "WEIGHT_BOLD",
    "WEIGHT_MEDIUM",
    "WEIGHT_REGULAR",
    "apply_application_font",
    "font_family_css",
    "typography_qss",
    "DARK",
    "ITEM_RADIUS",
    "LIGHT",
    "RAIL_CORNER_RADIUS",
    "RAIL_ITEM_GAP",
    "RAIL_PADDING_BOTTOM",
    "RAIL_PADDING_TOP",
    "RAIL_WIDTH",
    "SCROLLBAR_WIDTH",
    "ShellPalette",
    "content_qss",
    "palette",
    "scrollbar_qss",
    "shell_qss",
]
