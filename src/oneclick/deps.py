"""Сборка реальных зависимостей оркестратора.

Единственное место, где «одна кнопка» встречается с системой. Всё остальное
(plans.py, runner.py) её не знает и тестируется без Windows.

Каждая операция возвращает (успех, сообщение) и не выбрасывает исключений
наружу: их ловит runner и превращает в состояние «Ошибка».
"""

from __future__ import annotations

from typing import Any

from log.log import log
from oneclick.runner import OneClickDeps

#: Домены самопроверки. Намеренно немного: проверка идёт в UI-потоке
#: ожидания и не должна растягиваться.
SELFCHECK_URLS: tuple[str, ...] = (
    "https://www.youtube.com",
    "https://discord.com",
)

#: DNS, назначаемый при обнаруженной подмене.
FALLBACK_DNS_PRIMARY = "1.1.1.1"
FALLBACK_DNS_SECONDARY = "8.8.8.8"


def _backup_root():
    from config.runtime_layout import APPLICATION_PATHS

    return APPLICATION_PATHS.settings_dir


# ──────────────────────────────────────────────────────────────────────
# Обратимые операции
# ──────────────────────────────────────────────────────────────────────

def _make_check_conflicts(runtime_feature: Any):
    def check_conflicts() -> tuple[bool, str]:
        # Другой активный обход DPI сделает запуск бессмысленным: кнопка
        # отработает, а интернет не починится.
        try:
            probe = getattr(runtime_feature, "is_any_running", None)
            if callable(probe) and probe(silent=True):
                return (True, "Обнаружен уже запущенный процесс, он будет перезапущен")
        except Exception as exc:
            log(f"Проверка конфликтов не удалась: {exc}", "DEBUG")
        return (True, "")

    return check_conflicts


def _make_start_dpi(runtime_feature: Any):
    def start_dpi() -> tuple[bool, str]:
        """Запускает DPI и дожидается, пока поднимется НОВЫЙ процесс.

        runtime_feature.start() только ставит запуск в очередь: внутри
        создаётся рабочий поток, а True возвращается сразу. Без ожидания
        оркестратор бежал дальше и правил hosts с прокси, пока DPI ещё
        стартовал.

        Ловушка в самой проверке. Перед запуском winws почти всегда уже
        работает — его поднял автозапуск, — и проба «есть ли процесс»
        видела старый экземпляр и рапортовала о готовности мгновенно. В
        логе это выглядело так: ссылка Telegram и правка hosts в 10:38:42,
        а сам winws2 стартовал только в 10:38:43.

        Поэтому если процесс был до запуска, сначала ждём, пока он
        исчезнет: preset launch останавливает предыдущий экземпляр перед
        стартом нового.
        """
        import time

        probe = getattr(runtime_feature, "is_any_running", None)

        def _running() -> bool:
            try:
                return bool(probe(silent=True))
            except Exception as exc:
                log(f"Проверка процесса DPI: {exc}", "DEBUG")
                return False

        was_running = _running() if callable(probe) else False

        if not bool(runtime_feature.start(skip_conflict_prompt=True)):
            return (False, "Не удалось запустить обход")

        if not callable(probe):
            # Проверить нечем — не выдумываем результат.
            return (True, "")

        deadline = time.monotonic() + 40.0

        if was_running:
            # Ждём остановки прежнего экземпляра. Если он почему-то не
            # останавливается, это не повод считать запуск неудачным:
            # ниже всё равно проверим, что процесс есть.
            stop_deadline = time.monotonic() + 15.0
            while time.monotonic() < stop_deadline and _running():
                time.sleep(0.2)

        while time.monotonic() < deadline:
            if _running():
                return (True, "")
            time.sleep(0.3)

        return (False, "Обход не запустился за 40 секунд")

    return start_dpi


def _make_stop_dpi(runtime_feature: Any):
    def stop_dpi() -> tuple[bool, str]:
        stopped = bool(runtime_feature.stop())
        return (stopped, "" if stopped else "Не удалось остановить обход")

    return stop_dpi


def _check_telegram_ready() -> tuple[bool, str]:
    """Есть ли смысл поднимать прокси прямо сейчас.

    Прокси нужен ради одного действия: открыть ссылку tg://, чтобы
    мессенджер сам предложил подключиться. Если Telegram не запущен,
    обработать ссылку некому — прокси повис бы на порту, человек считал
    бы, что всё сработало, а Telegram о нём даже не узнал.

    Это не ошибка включения: обход соединения работает и без Telegram,
    поэтому шаг помечается пропущенным, а не проваленным.
    """
    from telegram_proxy.presence import (
        NOT_RUNNING_MESSAGE,
        REDIRECT_NOTICE,
        is_telegram_running,
    )

    if is_telegram_running():
        # Предупреждение о переадресации. Telegram выпрыгивает поверх
        # работы и спрашивает про прокси — без предупреждения это
        # выглядит так, будто программа полезла куда не просили.
        return (True, REDIRECT_NOTICE)

    log("Telegram Desktop не запущен, прокси не поднимаем", "INFO")
    return (False, NOT_RUNNING_MESSAGE)


def _is_telegram_proxy_running() -> bool:
    try:
        from telegram_proxy.manager import get_proxy_manager

        return bool(get_proxy_manager().is_running)
    except Exception:
        return False


def _start_telegram_proxy() -> tuple[bool, str]:
    """Включает прокси и дожидается, пока он действительно поднимется.

    Тут было сразу две ошибки. Во-первых, start_proxy_if_enabled_async
    лишь ставит запуск в отдельный поток — её True означает «отправлено»,
    а не «работает». Во-вторых, она возвращает False, если прокси уже
    запущен, и это принималось за неудачу.

    Отсюда и брался вечный «Не удалось запустить прокси для Telegram»:
    к моменту проверки поток ещё не успевал поднять слушатель, а после
    нажатия «Повторить» он уже работал.
    """
    import time

    from telegram_proxy.public import set_enabled, start_proxy_if_enabled_async

    if not _is_telegram_proxy_running():
        set_enabled(True)
        start_proxy_if_enabled_async()

        # Слушатель поднимается за десятки миллисекунд; пять секунд —
        # запас на медленную машину, а не ожидание сети.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not _is_telegram_proxy_running():
            time.sleep(0.1)

        if not _is_telegram_proxy_running():
            return (False, "Прокси для Telegram не запустился за 5 секунд")

    _open_telegram_proxy_deeplink()
    return (True, "")


def _open_telegram_proxy_deeplink() -> None:
    """Открывает ссылку tg://, чтобы Telegram сам предложил включить прокси.

    Иначе прокси поднят, а мессенджер о нём не знает: человеку пришлось бы
    руками лезть в настройки сети Telegram и вбивать адрес с портом.

    Ссылку показываем один раз: consume_auto_deeplink_request() запоминает
    факт открытия, и при каждом следующем «Включить» Telegram уже не
    выпрыгивает поверх работы.
    """
    try:
        from telegram_proxy.config.settings import (
            build_proxy_url,
            consume_auto_deeplink_request,
        )
        from settings.store import (
            get_tg_proxy_fake_tls_domain,
            get_tg_proxy_host,
            get_tg_proxy_mode,
            get_tg_proxy_mtproxy_secret,
            get_tg_proxy_port,
        )

        if not consume_auto_deeplink_request():
            return

        url = build_proxy_url(
            get_tg_proxy_host(),
            get_tg_proxy_port(),
            mode=get_tg_proxy_mode(),
            mtproxy_secret=get_tg_proxy_mtproxy_secret(),
            fake_tls_domain=get_tg_proxy_fake_tls_domain(),
        )
        if not url:
            return

        import webbrowser

        webbrowser.open(url)
        log(f"Открыта ссылка подключения Telegram: {url}", "INFO")
    except Exception as exc:
        log(f"Не удалось открыть ссылку Telegram: {exc}", "DEBUG")


def _stop_telegram_proxy() -> tuple[bool, str]:
    from telegram_proxy.public import set_enabled

    set_enabled(False)
    try:
        from telegram_proxy.manager import get_proxy_manager

        manager = get_proxy_manager()
        stop_proxy = getattr(manager, "stop_proxy", None)
        if callable(stop_proxy):
            stop_proxy()
    except Exception as exc:
        log(f"Остановка Telegram-прокси: {exc}", "DEBUG")
    return (True, "")


# ──────────────────────────────────────────────────────────────────────
# Персистентные операции
# ──────────────────────────────────────────────────────────────────────

def _backup_hosts() -> tuple[bool, str]:
    from hosts.public import read_hosts_file
    from oneclick.hosts_backup import create_backup

    return create_backup(root=_backup_root(), read_hosts=read_hosts_file)


def _apply_hosts(entries: dict[str, str]) -> tuple[bool, str]:
    """Переписывает блок hosts под то, что выбрано на странице «Сервисы».

    Раньше сюда приходили готовые пары «домен -> адрес», собранные из
    категорий мастера, — 501 запись. Запись в hosts не дописывает, а
    заменяет весь управляемый блок целиком, поэтому «Включить» стирал
    остальные полторы тысячи записей, которые ставятся по умолчанию при
    первой установке: на странице «Сервисы» тумблеры дружно гасли.

    Источник истины теперь один — сохранённый выбор пользователя. Он же
    показан тумблерами, поэтому «Включить» больше не может ни сузить
    список, ни вернуть то, что человек выключил руками.
    """
    _ = entries
    from hosts.public import apply_service_profiles, create_hosts_runtime, load_user_selection

    selection = dict(load_user_selection() or {})
    if not selection:
        # Первый запуск: страницу ещё не открывали, сохранять было нечего.
        try:
            from hosts.defaults import load_default_selection

            selection = load_default_selection()
        except Exception as exc:
            return (False, f"Не удалось прочитать каталог сервисов: {exc}")

    if not selection:
        return (True, "")

    result = apply_service_profiles(create_hosts_runtime(), selection)
    return (bool(result.success), str(result.message or ""))


def _restore_hosts(*, use_original: bool = False) -> tuple[bool, str]:
    from hosts.public import write_hosts_file
    from oneclick.hosts_backup import restore_backup

    return restore_backup(
        root=_backup_root(),
        write_hosts=write_hosts_file,
        use_original=use_original,
    )


def restore_hosts_to_original() -> tuple[bool, str]:
    """Кнопка «Вернуть hosts как было» в расширенных настройках."""
    return _restore_hosts(use_original=True)


def _check_dns_integrity() -> list:
    from blockcheck.dns_integrity import check_dns_integrity

    return list(check_dns_integrity() or [])


def _active_adapters() -> list[str]:
    from dns.dns_force import DNSForceManager

    manager = DNSForceManager()
    # include_disconnected=False — трогаем только работающий адаптер.
    # Смена DNS на всех сразу это главный источник жалоб «после программы
    # отвалились внутренние адреса и VPN».
    return list(manager.get_network_adapters(include_disconnected=False) or [])


def _apply_dns() -> tuple[bool, str]:
    from dns.dns_force import DNSForceManager

    adapters = _active_adapters()
    if not adapters:
        return (False, "Не найден активный сетевой адаптер")

    manager = DNSForceManager()
    changed = [
        name
        for name in adapters
        if manager.set_dns_for_adapter(name, FALLBACK_DNS_PRIMARY, FALLBACK_DNS_SECONDARY)
    ]
    if not changed:
        return (False, "Не удалось назначить DNS")
    return (True, f"DNS назначен ({', '.join(changed)})")


def _restore_dns() -> tuple[bool, str]:
    from dns.dns_force import DNSForceManager

    manager = DNSForceManager()
    ok, message = manager.disable_force_dns(reset_to_auto=True, adapters=_active_adapters())
    return (bool(ok), str(message or ""))


# ──────────────────────────────────────────────────────────────────────
# Самопроверка
# ──────────────────────────────────────────────────────────────────────

def probe_domain_over_https(url: str, *, timeout: float = 6.0) -> bool:
    """Открывается ли сайт по-настоящему.

    Проверять TCP-коннект недостаточно, и это не теория. Записи в hosts
    уводят домен на чужой адрес; тот адрес охотно принимает TCP-соединение,
    проверка радуется — а в браузере сайт не открывается. Именно так
    приложение и рапортовало «обход работает» при неработающем интернете.

    TLS такое отличает: сертификат чужого сервера не подойдёт к имени
    домена, и проверка честно провалится. Поэтому доводим рукопожатие до
    конца и запрашиваем страницу.
    """
    import http.client
    import ssl
    from urllib.parse import urlparse

    parsed = urlparse(str(url or ""))
    host = parsed.hostname or ""
    if not host:
        return False

    port = parsed.port or (443 if parsed.scheme != "http" else 80)
    connection = None
    try:
        if parsed.scheme == "http":
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
        else:
            # Проверка имени в сертификате обязательна — ради неё всё и
            # затевалось. Отключать её здесь нельзя ни при каких условиях.
            context = ssl.create_default_context()
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            connection = http.client.HTTPSConnection(
                host, port, timeout=timeout, context=context
            )

        connection.request("HEAD", parsed.path or "/", headers={"User-Agent": "net67"})
        response = connection.getresponse()
        # Любой ответ сервера годится: 200, редирект, даже 403 значат,
        # что мы дошли до настоящего сайта. Важно отсутствие обрыва.
        return int(response.status) > 0
    except Exception:
        return False
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _probe_domains() -> tuple[int, tuple[str, ...]]:
    from urllib.parse import urlparse

    failed: list[str] = []
    for url in SELFCHECK_URLS:
        if not probe_domain_over_https(url):
            failed.append(urlparse(url).netloc or url)

    return (len(SELFCHECK_URLS), tuple(failed))


# ──────────────────────────────────────────────────────────────────────
# Сборка
# ──────────────────────────────────────────────────────────────────────

def build_oneclick_deps(*, runtime_feature: Any, report=None) -> OneClickDeps:
    """Собирает зависимости для OneClickRunner.

    runtime_feature — узкий набор ControlRuntimeActions со страницы
    управления: start, stop и is_any_running. Целиком RuntimeFeature сюда
    передавать нельзя, это запрещает архитектурный контракт страниц.
    """
    return OneClickDeps(
        check_conflicts=_make_check_conflicts(runtime_feature),
        start_dpi=_make_start_dpi(runtime_feature),
        stop_dpi=_make_stop_dpi(runtime_feature),
        check_telegram_ready=_check_telegram_ready,
        start_telegram_proxy=_start_telegram_proxy,
        stop_telegram_proxy=_stop_telegram_proxy,
        backup_hosts=_backup_hosts,
        apply_hosts=_apply_hosts,
        restore_hosts=_restore_hosts,
        check_dns_integrity=_check_dns_integrity,
        apply_dns=_apply_dns,
        restore_dns=_restore_dns,
        probe_domains=_probe_domains,
        report=report,
    )


__all__ = [
    "FALLBACK_DNS_PRIMARY",
    "FALLBACK_DNS_SECONDARY",
    "SELFCHECK_URLS",
    "build_oneclick_deps",
    "restore_hosts_to_original",
]
