"""Состояние страницы VPN: выбор, проверка и отменяемое подключение."""

from dataclasses import dataclass, field
from datetime import datetime
from threading import Event

from PyQt6.QtCore import QObject, QTimer, QSize, Qt

from ui.fluent_widgets import set_tooltip
from vpn.operation import VpnOperation, connection_marker
from vpn.profiles import profile_id

ROW_STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 8


def _check_caption(result, failure):
    if not result.ok:
        return failure
    if result.latency_ms is not None:
        return f"{int(result.latency_ms)} мс"
    # Молчание UDP не доказывает, что сервер недоступен.
    return "Без ответа" if getattr(result, "method", None) == "udp" else "Отвечает"


@dataclass(slots=True)
class _GroupCheck:
    key: tuple[str, str]
    total: int
    completed: int = 0
    cancelled: Event = field(default_factory=Event)


class VpnExperience(QObject):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.operation = None
        self.checking = False
        self.group_check = None
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
        name = display_name(profile)
        aliases = ALL_COUNTRY_NAMES.get(country_code(name), ())
        haystack = " ".join((name, str(profile.endpoint), *aliases)).casefold()
        return all(word in haystack for word in page.search_edit.text().casefold().split())

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
            info.append(_check_caption(result, "Ошибка"))
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
            set_tooltip(page.scope_label, applied + pending)
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
                page.ping_label.setText(_check_caption(result, "Проверка не прошла"))
                set_tooltip(page.ping_label, f"{kind} · {at} · {result.message}")
            else:
                page.ping_label.setText("Канал ещё не проверен" if self.connected else "")
            page.ping_label.setVisible(bool(page.ping_label.text()))
        shown = sum(index >= 0 for index in page._row_profiles)
        empty = ("Ничего не найдено. Измените поиск."
                 if page._visible_profiles else "Добавьте ссылку, подписку или конфигурацию VPN кнопкой «Добавить».")
        has_groups = any(index < 0 for index in page._row_profiles)
        page.empty_label.setText(empty if not shown and not has_groups else "")
        page.empty_label.setVisible(not shown and not has_groups)
        page.profile_list.setVisible(bool(shown) or has_groups)
        self.refresh_marks()
        self._sync_check_actions()

    def refresh_marks(self, key=None):
        page = self.page
        for row, index in enumerate(page._row_profiles):
            if index >= 0:
                profile = page._visible_profiles[index]
                if key is None or profile_id(profile) == key:
                    self.decorate_item(page.profile_list.item(row), profile)
        page.profile_list.viewport().update()

    def _sync_check_actions(self):
        batch = self.group_check
        busy = self.operation is not None or self.checking or batch is not None
        self.page.ping_btn.setEnabled(self.summary_profile() is not None and not busy)
        self.page.ping_btn.setText("Проверяем…" if self.checking else "Пинг")
        for key, button in self.page._group_check_buttons.items():
            current = batch is not None and key == batch.key
            if current:
                cancelling = batch.cancelled.is_set()
                button.setText("Отмена…" if cancelling else f"Стоп · {batch.completed}/{batch.total}")
                set_tooltip(button, "Остановить проверку группы")
                button.setEnabled(not cancelling and self.operation is None)
            else:
                button.setText("Пинг всех")
                set_tooltip(button, "Проверить все серверы этой группы")
                button.setEnabled(not busy)

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
        self.cancel_group_check()
        self.generation += 1
        self.verified_generation = -1
        self.page.ping_label.clear()
        self.page.ping_label.hide()
        self.page._stats_timer.stop()
        self.page.profile_list.setEnabled(False)
        self.page.tabs.setEnabled(False)
        self.page._sync_connect_button(busy=True, disconnecting=disconnecting)
        self.timer.start()
        self.sync()

    def _release(self):
        token, self.operation = self.operation, None
        self.timer.stop()
        self.page.profile_list.setEnabled(True)
        self.page.tabs.setEnabled(True)
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
        from vpn.probing import probe_server

        profile = self.summary_profile()
        if profile is None or self.operation is not None or self.checking or self.group_check is not None:
            return
        generation = self.generation
        marker = connection_marker()
        request = self.check_request + 1
        active = self.active is not None and profile_id(self.active) == profile_id(profile)
        address = local_proxy_address() if active and is_connected() and is_link_profile(profile) else None
        stats = self.page._last_stats if active else None

        def probe():
            result, kind = probe_server(profile, address=address, stats=stats)
            return result, profile, kind, generation, bool(address), marker, request

        context = profile_id(profile), generation, marker, request
        if self.page._start_worker("_ping_worker", probe, self.checked,
                                    lambda message: self.check_failed(message, context)) is None:
            return
        self.check_request = request
        self.latest_requests[profile_id(profile)] = request
        self.checking = True
        self._sync_check_actions()
        shown = self.summary_profile()
        if shown is not None and profile_id(shown) == profile_id(profile):
            if address:
                self.verified_generation = -1
            self.page.ping_label.setText("Проверяем сервер…")
            self.page.ping_label.show()

    def check_group(self, key, profiles):
        from vpn.probing import check_group as probe_group

        if self.group_check is not None:
            if self.group_check.key == key:
                self.cancel_group_check()
            return
        if not profiles or self.operation is not None or self.checking:
            return

        batch = _GroupCheck(key, len(profiles))
        generation, marker = self.generation, connection_marker()
        request = self.check_request + 1

        def run(publish):
            probe_group(profiles, should_stop=batch.cancelled.is_set, on_result=publish)

        def progress(payload):
            if self.group_check is not batch or batch.cancelled.is_set():
                return
            profile, result, kind = payload
            batch.completed += 1
            self._record_check((result, profile, kind, generation, False, marker, request))
            self._sync_check_actions()

        def finish(message=""):
            if self.group_check is not batch:
                return
            self.group_check = None
            self._sync_check_actions()
            if message and not batch.cancelled.is_set():
                self.page._error(f"Не удалось проверить группу. {message}")

        if self.page._start_worker("_ping_worker", run, lambda _: finish(), finish,
                                    on_progress=progress) is None:
            return
        self.group_check = batch
        self.check_request = request
        self.latest_requests.update((profile_id(profile), request) for profile in profiles)
        self._sync_check_actions()

    def cancel_group_check(self):
        if self.group_check is not None:
            self.group_check.cancelled.set()
            self._sync_check_actions()

    def checked(self, payload):
        self.checking = False
        self._sync_check_actions()
        self._record_check(payload)

    def _record_check(self, payload):
        result, profile, kind, generation, active_probe, marker, request = payload
        at = datetime.now().strftime("%H:%M")
        key = profile_id(profile)
        previous = self.checks.get(key)
        if previous is None or request >= previous[5]:
            self.checks[key] = result, kind, at, generation, marker, request
        current = self.summary_profile()
        if (current is not None and profile_id(profile) == profile_id(current)
                and generation == self.generation and marker == connection_marker()
                and request == self.latest_requests.get(key, self.check_request)):
            self.page.ping_label.setText(_check_caption(result, "Проверка не прошла"))
            set_tooltip(self.page.ping_label, f"{kind} · {at} · {result.message}")
            self.page.ping_label.show()
            if active_probe and self.connected:
                self.verified_generation = generation if result.ok else -1
                self.page.state_label.setText("Подключено · Проверено" if result.ok else "Подключено · Ошибка проверки")
        self.refresh_marks(key)

    def check_failed(self, message, context=None):
        self.checking = False
        self._sync_check_actions()
        current = self.summary_profile()
        if context is not None:
            key, generation, marker, request = context
            from vpn.http_probe import HttpProbeResult
            previous = self.checks.get(key)
            if previous is None or request >= previous[5]:
                self.checks[key] = (HttpProbeResult(False, None, str(message)), "Проверка",
                                    datetime.now().strftime("%H:%M"), generation, marker, request)
            self.refresh_marks(key)
        if context is not None and (current is None or context !=
                (profile_id(current), self.generation, connection_marker(),
                 self.latest_requests.get(profile_id(current), self.check_request))):
            return
        self.page.ping_label.setText(f"Проверка не завершилась: {message}. Повторите попытку.")
        self.page.ping_label.show()

    def close(self):
        self.timer.stop()
        if self.group_check is not None:
            self.group_check.cancelled.set()
        if self.operation is not None and not self.operation.disconnecting:
            self.operation.cancelled.set()
