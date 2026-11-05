"""Состояние страницы VPN: выбор, проверка и отменяемое подключение."""

from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, QSize, Qt

from vpn.operation import VpnOperation, connection_marker
from vpn.view_state import VpnViewState, profile_id

ROW_STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 8


class VpnExperience(QObject):
    def __init__(self, page, root):
        super().__init__(page)
        self.page = page
        self.view = VpnViewState(root)
        self.operation = None
        self.checks = {}
        self.generation = 0
        self.verified_generation = -1
        self.active = None
        self.connected = False
        self.message = "Отключено"
        self.check_request = 0
        self.latest_requests = {}
        self.runtime_marker = connection_marker()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.sync_progress)

    def filter_changed(self, *_args):
        self.page._refill_combo()

    def accepts(self, profile):
        from vpn.country_names import ALL_COUNTRY_NAMES
        from vpn.flags import country_code
        from vpn.profiles import display_name

        page = self.page
        if page.favorites_btn.isChecked() and not self.view.is_favorite(profile):
            return False
        name = display_name(profile)
        aliases = ALL_COUNTRY_NAMES.get(country_code(name), ())
        haystack = " ".join((name, str(profile.endpoint), *aliases)).casefold()
        return all(word in haystack for word in page.search_edit.text().casefold().split())

    def toggle_favorite(self):
        profile = self.summary_profile()
        if profile is None:
            return
        try:
            self.view.toggle_favorite(profile)
        except OSError as exc:
            self.page._error(f"Не удалось сохранить избранное: {exc}")
            return
        self.page._refill_combo()

    def summary_profile(self):
        if self.operation is not None and not self.operation.disconnecting:
            return self.operation.profile
        return self.active if self.connected and self.active is not None else self.page._current_profile()

    def toggle_import(self):
        self.page.add_section.show()
        self.page.add_section.raise_()
        self.page.input_edit.setFocus()

    def decorate_item(self, item, profile):
        info = []
        if self.connected and self.active is not None and profile_id(profile) == profile_id(self.active):
            info.append("Подключён")
        checked = self.checks.get(profile_id(profile))
        if checked:
            result, kind, at, *_context = checked
            value = f"{int(result.latency_ms)} мс" if result.ok and result.latency_ms is not None else "Ошибка"
            info.append(value)
        item.setData(ROW_STATUS_ROLE, " · ".join(info))
        item.setSizeHint(QSize(0, 46))
        from ui.widgets.fluent_item_tooltip import set_fluent_item_tooltip
        tip = str(profile.endpoint)
        if checked:
            tip += f"\n{kind}, {at}: {result.message}"
        set_fluent_item_tooltip(item, tip)

    def sync(self):
        from vpn.flags import flag_icon, strip_country_prefix
        from vpn.link_runtime import active_connection, is_link_profile, tun_mode_enabled
        from vpn.profiles import display_name
        import qtawesome as qta
        from ui.theme import get_theme_tokens, token_to_qcolor

        page = self.page
        profile = page._current_profile()
        has = profile is not None
        shown = self.summary_profile()
        page.server_title.setText(strip_country_prefix(display_name(shown)) if shown is not None else "Добавьте первый сервер")
        selection = (f"Выбран для следующего подключения: {strip_country_prefix(display_name(profile))}"
                     if has and shown is not None and profile_id(profile) != profile_id(shown) else "")
        page.selection_label.setText(selection)
        page.selection_label.setVisible(bool(selection))
        icon = flag_icon(display_name(shown)) if shown is not None else None
        if icon is None:
            icon = qta.icon("fa5s.globe", color=token_to_qcolor(get_theme_tokens().fg_muted))
        page.server_flag.setPixmap(icon.pixmap(36, 36))
        page.favorite_btn.setEnabled(shown is not None)
        favored = shown is not None and self.view.is_favorite(shown)
        page.favorite_btn.setText("В избранном" if favored else "В избранное")
        page.favorite_btn.setIcon(qta.icon("fa5s.star",
                                           color=token_to_qcolor(get_theme_tokens().fg)))
        page.tun_mode_toggle.setVisible(shown is None or is_link_profile(shown))
        _active, scope = active_connection()
        if self.connected and self.active is not None and is_link_profile(self.active):
            applied = {"tun": "Сейчас: весь компьютер.", "proxy": "Сейчас: прокси приложений Windows.",
                       "local": "Сейчас: только локальный прокси; Windows не перенастроена."}.get(scope, "Охват не определён.")
            requested = "tun" if tun_mode_enabled() else "proxy"
            pending = " Новый режим применится при следующем подключении." if requested != scope else ""
            # Фактический охват важнее следующего выбора: при отказе Windows
            # локальный порт не означает, что приложения используют VPN.
            page.scope_label.setText("Только локальный прокси" if scope == "local" else
                                    "Сейчас: прокси приложений" if pending and scope == "proxy" else
                                    "Режим применится при переподключении" if pending else "")
            page.scope_label.setToolTip(applied + pending)
        elif shown is not None and not is_link_profile(shown):
            page.scope_label.setText("")
        else:
            page.scope_label.setText("")
        page.scope_label.setVisible(bool(page.scope_label.text()))
        if self.operation is not None:
            self.sync_progress()
        else:
            page.connect_button.setEnabled(has or self.connected)
            page._sync_connect_button(connected=self.connected)
            card_key = profile_id(shown) if shown is not None else ""
            checked = self.checks.get(card_key)
            expected = (self.generation, connection_marker(),
                        self.latest_requests.get(card_key, self.check_request))
            if checked is not None and checked[3:] != expected:
                checked = None
            if checked:
                result, kind, at, *_context = checked
                page.ping_label.setText(f"{int(result.latency_ms)} мс" if result.ok and result.latency_ms is not None else "Проверка не прошла")
                page.ping_label.setToolTip(f"{kind} · {at} · {result.message}")
            else:
                page.ping_label.setText("Канал ещё не проверен" if self.connected else "")
            page.ping_label.setVisible(bool(page.ping_label.text()))
        shown = sum(index >= 0 for index in page._row_profiles)
        empty = ("Ничего не найдено. Измените поиск или отключите фильтр избранного."
                 if page._visible_profiles else "Добавьте ссылку, подписку или конфигурацию VPN кнопкой «Добавить».")
        has_groups = any(index < 0 for index in page._row_profiles)
        page.empty_label.setText(empty if not shown and not has_groups else "")
        page.empty_label.setVisible(not shown and not has_groups)
        page.profile_list.setVisible(bool(shown) or has_groups)
        self.refresh_marks()

    def refresh_marks(self):
        page = self.page
        for row, index in enumerate(page._row_profiles):
            if index >= 0:
                self.decorate_item(page.profile_list.item(row), page._visible_profiles[index])
        page.profile_list.viewport().update()

    def sync_progress(self):
        operation = self.operation
        if operation is None:
            return
        cancelling = operation.should_stop()
        self.page.state_label.setText("Отменяем подключение…" if cancelling else operation.stage)
        self.page.connect_button.setEnabled(not operation.disconnecting and not cancelling)
        if cancelling:
            self.page.connect_button.setText("Отменяем…")
        self.page.connect_caption.setText(self.page.connect_button.title())

    def toggle(self):
        if self.operation is not None:
            if not self.operation.disconnecting:
                self.operation.cancelled.set()
                self.sync_progress()
            return
        profile = self.active if self.connected and self.active is not None else self.page._current_profile()
        if profile is not None:
            self.start(profile, disconnecting=self.connected)

    def start(self, profile, *, disconnecting=False):
        from vpn.link_runtime import check_core_available, is_link_profile
        from vpn.tunnel_runtime import check_client_files

        if self.operation is not None:
            return
        link = is_link_profile(profile)
        if not disconnecting:
            available, message = check_core_available() if link else check_client_files()
            if not available:
                self.page._error(message)
                return
        token = VpnOperation(profile, disconnecting=disconnecting)
        expected_marker = connection_marker()

        def run():
            if link:
                from vpn.link_runtime import connect, disconnect
                return disconnect(expected_serial=expected_marker[0]) if disconnecting else connect(profile, should_stop=token.should_stop,
                                                                    progress=token.report)
            from vpn.tunnel_runtime import connect, disconnect
            name = str(getattr(profile, "name", "") or "")
            return (disconnect(tunnel_name=name, expected_serial=expected_marker[1]) if disconnecting else
                    connect(profile, tunnel_name=name, should_stop=token.should_stop, progress=token.report))

        started = self.page._start_worker("_tunnel_worker", run, self.finished, self.failed)
        if started is None:
            return
        self.operation = token
        self.generation += 1
        self.verified_generation = -1
        self.page.ping_label.clear()
        self.page.ping_label.hide()
        self.page._stats_timer.stop()
        self.page.profile_list.setEnabled(False)
        self.page.tabs.setEnabled(False)
        self.page.ping_btn.setEnabled(False)
        self.page._sync_connect_button(busy=True, disconnecting=disconnecting)
        self.timer.start()
        self.sync()

    def _release(self):
        token, self.operation = self.operation, None
        self.timer.stop()
        self.page.profile_list.setEnabled(True)
        self.page.tabs.setEnabled(True)
        self.page.ping_btn.setEnabled(self.page._current_profile() is not None)
        return token

    def finished(self, result):
        from vpn.link_runtime import active_connection, is_connected, is_link_profile
        from vpn.tunnel import TunnelState

        token = self._release()
        if token is None:
            return
        if is_link_profile(token.profile):
            ok, message = result
            self.connected = is_connected()
            actual_profile = active_connection()[0] or token.profile
        else:
            self.page._tunnel_state = result.state
            self.connected = result.state is TunnelState.CONNECTED
            ok = result.state is not TunnelState.ERROR
            message = result.message or ("Туннель запущен; доступ к сайтам ещё не проверен." if self.connected else "Отключено")
            from vpn.tunnel_runtime import active_connection as active_tunnel
            actual_profile = active_tunnel()[0] or token.profile
        self.active = actual_profile if self.connected else None
        self.runtime_marker = connection_marker()
        self.message = message
        self.page.state_label.setText("Подключено" if ok and self.connected else "Отключено" if ok else self.message)
        self.page.ping_label.setText("Канал ещё не проверен" if self.connected else "")
        self.page._sync_stats_timer(self.connected)
        self.sync()
        if not ok and (not token.should_stop() or self.connected or message != "Подключение отменено"):
            self.page._error(message)
        if ok and self.connected and is_link_profile(token.profile) and not token.disconnecting:
            self.check()
        QTimer.singleShot(100, self.page._refresh_connection_state)

    def failed(self, message):
        self._release()
        self.page._error(f"Не удалось выполнить операцию: {message}")
        self.page.state_label.setText("Ошибка подключения. Можно повторить попытку.")
        self.sync()
        self.page._refresh_connection_state()

    def status_ready(self, payload):
        from vpn.tunnel import TunnelState, describe_state
        if self.operation is not None:
            return
        state, stats, active, _scope, link_connected, generation, marker = payload
        if generation != self.generation or marker != connection_marker():
            return
        if marker != self.runtime_marker:
            self.runtime_marker = marker
            self.verified_generation = -1
        self.connected = link_connected or state is TunnelState.CONNECTED
        if link_connected:
            self.active = active
            text = "Подключено"
            if self.verified_generation == self.generation:
                text = "Подключено · Проверено"
        else:
            self.active = active if self.connected else None
            text = describe_state(state)
            if stats is not None:
                from vpn.status import describe
                text += f" · {describe(stats)}"
        self.page._tunnel_state = state
        self.page._last_stats = stats
        self.page.state_label.setText(text)
        self.page._sync_stats_timer(self.connected)
        self.sync()

    def check(self):
        from vpn.link_runtime import is_connected, is_link_profile, local_proxy_address

        profile = self.page._current_profile()
        if profile is None or self.operation is not None:
            return
        generation = self.generation
        marker = connection_marker()
        request = self.check_request + 1
        active = self.active is not None and profile_id(self.active) == profile_id(profile)
        kind = "HTTPS" if is_link_profile(profile) else "Сервер"
        address = local_proxy_address() if active and is_connected() and is_link_profile(profile) else None
        stats = self.page._last_stats if active else None

        def probe():
            if address:
                from vpn.http_probe import check_through_proxy
                result = check_through_proxy(proxy_address=address)
            elif is_link_profile(profile):
                from vpn.probing import check_profile
                result = check_profile(profile)
            else:
                from vpn.ping import check_server
                result = check_server(profile.endpoint_host, profile.endpoint_port, stats=stats)
            return result, profile, kind, generation, bool(address), marker, request

        context = profile_id(profile), generation, marker, request
        if self.page._start_worker("_ping_worker", probe, self.checked,
                                    lambda message: self.check_failed(message, context)) is None:
            return
        self.check_request = request
        self.latest_requests[profile_id(profile)] = request
        self.page.ping_btn.setEnabled(False)
        self.page.ping_btn.setText("Проверяем…")
        shown = self.summary_profile()
        if shown is not None and profile_id(shown) == profile_id(profile):
            if address:
                self.verified_generation = -1
            self.page.ping_label.setText("Проверяем HTTPS через сервер…" if kind == "HTTPS" else "Проверяем сервер…")
            self.page.ping_label.show()

    def checked(self, payload):
        result, profile, kind, generation, active_probe, marker, request = payload
        at = datetime.now().strftime("%H:%M")
        key = profile_id(profile)
        previous = self.checks.get(key)
        if previous is None or request >= previous[5]:
            self.checks[key] = result, kind, at, generation, marker, request
        self.page.ping_btn.setEnabled(self.page._current_profile() is not None)
        self.page.ping_btn.setText("Проверить сервер")
        current = self.summary_profile()
        if (current is not None and profile_id(profile) == profile_id(current)
                and generation == self.generation and marker == connection_marker()
                and request == self.latest_requests.get(key, self.check_request)):
            self.page.ping_label.setText(f"{int(result.latency_ms)} мс" if result.ok and result.latency_ms is not None else "Проверка не прошла")
            self.page.ping_label.setToolTip(f"{kind} · {at} · {result.message}")
            self.page.ping_label.show()
            if active_probe and self.connected:
                self.verified_generation = generation if result.ok else -1
                self.page.state_label.setText("Подключено · Проверено" if result.ok else "Подключено · Ошибка проверки")
        self.refresh_marks()

    def check_failed(self, message, context=None):
        self.page.ping_btn.setEnabled(self.page._current_profile() is not None)
        self.page.ping_btn.setText("Проверить сервер")
        current = self.summary_profile()
        if context is not None:
            key, generation, marker, request = context
            from vpn.http_probe import HttpProbeResult
            previous = self.checks.get(key)
            if previous is None or request >= previous[5]:
                self.checks[key] = (HttpProbeResult(False, None, str(message)), "Проверка",
                                    datetime.now().strftime("%H:%M"), generation, marker, request)
            self.refresh_marks()
        if context is not None and (current is None or context !=
                (profile_id(current), self.generation, connection_marker(),
                 self.latest_requests.get(profile_id(current), self.check_request))):
            return
        self.page.ping_label.setText(f"Проверка не завершилась: {message}. Повторите попытку.")
        self.page.ping_label.show()

    def close(self):
        self.timer.stop()
        if self.operation is not None and not self.operation.disconnecting:
            self.operation.cancelled.set()
