"""Карточки DNS-провайдера для страницы Network."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)

from qfluentwidgets import (
    CaptionLabel,
    StrongBodyLabel,
)

from ui.fluent_widgets import set_tooltip
from ui.accessibility import set_control_accessibility, set_state_text
from ui.theme import get_cached_qta_pixmap, get_theme_tokens
from ui.theme_refresh import ThemeRefreshBinding
from app.ui_texts import tr as tr_catalog


class DNSChoiceCard(QWidget):
    """Единая лёгкая строка выбора DNS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_selected = False
        self.setObjectName("dnsCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_card_style()

    def _apply_card_style(self, tokens=None) -> None:
        theme_tokens = tokens or get_theme_tokens()
        accent = theme_tokens.accent_hex
        transparent_left = "rgba(0, 0, 0, 0)"
        if self._is_selected:
            bg = theme_tokens.accent_soft_bg
            bg_hover = theme_tokens.accent_soft_bg_hover
            left = accent
        else:
            bg = theme_tokens.surface_bg
            bg_hover = theme_tokens.surface_bg_hover
            left = transparent_left
        hover_left = left if self._is_selected else transparent_left
        self.setStyleSheet(
            f"""
            QWidget#dnsCard {{
                background-color: {bg};
                border-left: 4px solid {left};
                border-top: none;
                border-right: none;
                border-bottom: none;
                border-radius: 10px;
            }}
            QWidget#dnsCard:hover {{
                background-color: {bg_hover};
                border-left: 4px solid {hover_left};
            }}
            """
        )

    def set_selected(self, selected: bool):
        self._is_selected = bool(selected)
        self.setProperty("selected", self._is_selected)
        self._on_selected_changed()
        self._apply_card_style()
        style = self.style()
        if style is not None:
            try:
                style.unpolish(self)
                style.polish(self)
            except Exception:
                pass
        self.update()

    def _on_selected_changed(self) -> None:
        pass


class DNSProviderCard(DNSChoiceCard):
    """Лёгкая карточка DNS-провайдера."""

    selected = pyqtSignal(str, dict)

    @staticmethod
    def indicator_off() -> str:
        tokens = get_theme_tokens()
        return f"""
            background-color: {tokens.toggle_off_bg};
            border: 2px solid {tokens.toggle_off_border};
            border-radius: 8px;
        """

    @staticmethod
    def indicator_on() -> str:
        tokens = get_theme_tokens()
        return f"""
            background-color: {tokens.accent_hex};
            border: 2px solid {tokens.accent_hex};
            border-radius: 8px;
        """

    def __init__(
        self,
        name: str,
        data: dict,
        is_current: bool = False,
        show_ipv6: bool = False,
        show_doh: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.name = name
        self.data = data
        self.is_current = is_current
        self.show_ipv6 = bool(show_ipv6)
        self.show_doh = bool(show_doh)
        self._icon_label = None
        self._name_label = None
        self._desc_label = None
        self._doh_label = None
        self._ip_label = None
        self._setup_ui()
        self._refresh_accessibility()
        self._theme_refresh = ThemeRefreshBinding(self, self._apply_theme_refresh)

    @staticmethod
    def _normalize_ip_list(value) -> list[str]:
        if isinstance(value, str):
            return [x.strip() for x in value.replace(',', ' ').split() if x.strip()]
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                item_s = str(item).strip()
                if item_s:
                    out.append(item_s)
            return out
        return []

    def _provider_ip_text(self) -> str:
        ipv4 = self._normalize_ip_list(self.data.get('ipv4', []))
        primary_v4 = ipv4[0] if ipv4 else ""

        if not self.show_ipv6:
            return primary_v4 or "-"

        ipv6 = self._normalize_ip_list(self.data.get('ipv6', []))
        primary_v6 = ipv6[0] if ipv6 else ""

        if primary_v4 and primary_v6:
            return f"v4 {primary_v4} | v6 {primary_v6}"
        if primary_v4:
            return primary_v4
        if primary_v6:
            return primary_v6
        return "-"

    def _setup_ui(self):
        tokens = get_theme_tokens()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 12, 3)
        layout.setSpacing(10)

        icon_color = self.data.get('color') or tokens.accent_hex
        icon_label = QLabel()
        self._icon_label = icon_label
        icon_label.setPixmap(
            get_cached_qta_pixmap(
                self.data.get('icon', 'fa5s.server'),
                color=icon_color,
                size=18,
            )
        )
        icon_label.setFixedSize(20, 20)
        layout.addWidget(icon_label)

        name_label = StrongBodyLabel(self.name)
        self._name_label = name_label
        layout.addWidget(name_label)

        desc_label = CaptionLabel(f"· {self.data.get('desc', '')}")
        self._desc_label = desc_label
        layout.addWidget(desc_label)

        if self.show_doh and self.data.get("doh"):
            doh_label = QLabel(tr_catalog(
                "page.network.dns.doh_supported", default="DoH",
            ))
            self._doh_label = doh_label
            set_tooltip(doh_label, "DNS over HTTPS — зашифрованный DNS")
            layout.addWidget(doh_label)

        layout.addStretch()

        ip_text = self._provider_ip_text()
        ip_label = CaptionLabel(ip_text)
        self._ip_label = ip_label
        layout.addWidget(ip_label)

        self._apply_theme_styles(tokens)

    def _apply_theme_styles(self, tokens=None) -> None:
        theme_tokens = tokens or get_theme_tokens()
        self._apply_card_style(theme_tokens)
        try:
            if self._icon_label is not None:
                icon_color = self.data.get('color') or theme_tokens.accent_hex
                self._icon_label.setPixmap(
                    get_cached_qta_pixmap(
                        self.data.get('icon', 'fa5s.server'),
                        color=icon_color,
                        size=18,
                    )
                )
        except Exception:
            pass
        try:
            pass
        except Exception:
            pass
        try:
            pass
        except Exception:
            pass
        try:
            if self._doh_label is not None:
                self._doh_label.setStyleSheet(
                    f"""
                    color: {theme_tokens.accent_hex};
                    background-color: {theme_tokens.accent_soft_bg};
                    border-radius: 6px;
                    padding: 1px 6px;
                    font-size: 9px;
                    font-weight: 600;
                    """
                )
        except Exception:
            pass
        try:
            pass
        except Exception:
            pass

    def _on_selected_changed(self) -> None:
        self._refresh_accessibility()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.name, self.data)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.selected.emit(self.name, self.data)
            event.accept()
            return
        super().keyPressEvent(event)

    def _refresh_accessibility(self) -> None:
        selected_text = "выбран" if self._is_selected else "не выбран"
        description = str(self.data.get("desc", "") or "").strip()
        ip_text = self._provider_ip_text()
        parts = [f"DNS {self.name}", selected_text]
        if description:
            parts.append(description)
        if ip_text and ip_text != "-":
            parts.append(ip_text)
        state_text = ", ".join(parts)
        set_state_text(self, state_text)
        set_control_accessibility(
            self,
            name=state_text,
            description="Нажмите Enter или пробел, чтобы выбрать этого DNS-провайдера.",
        )

    def _apply_theme_refresh(self, tokens=None, force: bool = False) -> None:
        _ = force
        self._apply_theme_styles(tokens)
