"""Общий запуск справочных ссылок не задерживает окно и сообщает об ошибках."""

from __future__ import annotations

from qfluentwidgets import HyperlinkButton

from utils import site_links

__all__ = ["SiteLinkButton"]


class SiteLinkButton(HyperlinkButton):
    """Ссылка открывается тем же способом, что и остальные внешние действия net67."""

    def _onClicked(self) -> None:
        url = self.getUrl()
        if url.isValid():
            site_links.open_in_browser(url.toString())
