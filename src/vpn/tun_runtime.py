"""Поднять и опустить туннель: процессы, маршруты, откат.

Решения о том, что делать, живут в ``vpn/tun_mode.py`` — он проверяется
без Windows. Здесь только исполнение: запуск tun2socks, вызовы netsh и
route, ожидание адаптера.

## Главное правило этого модуля

Любой отказ на середине обязан вернуть систему в исходное состояние.

Туннель перехватывает весь трафик. Брошенный на полпути, он оставляет
машину без интернета: маршрут по умолчанию ведёт в адаптер, а в адаптере
никого нет. Причём человек об этом узнает не сразу и свяжет это с чем
угодно, только не с нами.

Поэтому каждый шаг записывается в список отката, и при любой ошибке
список проигрывается в обратном порядке. Тот же список используется при
обычном отключении — чтобы путь выхода был один, проверенный, а не два
разных.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from log.log import log

from vpn.tun_mode import (
    TUN_ADDRESS,
    TunModeError,
    TunPlan,
    build_adapter_setup_commands,
    build_route_cleanup_commands,
    build_route_commands,
    build_tun2socks_command,
)


#: Сколько ждём появления адаптера после запуска tun2socks.
#:
#: Драйвер wintun создаёт адаптер не мгновенно, а настраивать его до
#: появления бесполезно: netsh ответит «элемент не найден». Полторы
#: секунды хватает с запасом, дольше ждать незачем — если адаптера нет,
#: значит tun2socks не стартовал, и это видно по самому процессу.
ADAPTER_WAIT_SECONDS = 1.5
ADAPTER_POLL_SECONDS = 0.1

#: Сколько ждём, пока адрес адаптера начнёт действовать.
#:
#: netsh возвращает управление раньше, чем Windows успевает подключить
#: адрес: сети 10.67.0.0/24 в таблице ещё нет, значит шлюз 10.67.0.1
#: недостижим. Все `route add` через него в этот момент отвечают
#: «Сбой добавления маршрута: Сетевая папка недоступна» — и при этом
#: возвращают код 0, то есть выглядят как успех.
#:
#: Так обе половинки маршрута по умолчанию не добавлялись никогда, а
#: трафик в туннель уводил побочный маршрут, который netsh ставит вместе
#: с адресом. Пяти секунд хватает с большим запасом: обычно адрес готов
#: за две-три десятых.
ADDRESS_WAIT_SECONDS = 5.0

#: Чем route.exe сообщает об отказе, возвращая при этом ноль.
#:
#: Код возврата у неё бесполезен: и «ОК», и «Сбой добавления маршрута»
#: приходят с нулём. Единственный признак — текст ответа.
ROUTE_FAILURE_MARKERS = ("сбой", "failed", "ошибка", "error")

#: Сколько последних строк вывода tun2socks держим для разбора.
#:
#: Держим не ради истории, а ради того, чтобы вывод вообще кто-то читал.
#: Труба процесса не бездонная: на Windows это 64 КБ, и когда она
#: заполняется, tun2socks встаёт на записи в собственный лог — вместе со
#: всем трафиком. Симптом получается издевательский: адаптер на месте,
#: маршруты на месте, соединение устанавливается, а страницы не грузятся,
#: и в журнале про это ни строчки.
#:
#: Раньше вывод читался ровно один раз — в ветке «адаптер не появился».
#: То есть при удачном запуске не читался никогда, а на `--loglevel
#: warning` пары сотен неудачных соединений хватает, чтобы упереться в
#: потолок за время обычного рабочего сеанса.
OUTPUT_TAIL_LINES = 200

#: Сколько строк вывода tun2socks попадает в журнал приложения.
#:
#: Уровень поднят до `debug`, а он пишет по строке на соединение — с
#: открытым браузером это тысячи строк за минуту, и журнал перестаёт
#: быть читаемым ровно тогда, когда нужен. Первых сотен хватает, чтобы
#: увидеть, что происходит при подключении; дальше вывод продолжает
#: вычитываться (иначе процесс встанет на переполненной трубе), но в
#: журнал не идёт.
OUTPUT_LOG_LIMIT = 400

_LOG = "🌐 TUN"


@dataclass(slots=True)
class TunSession:
    """Поднятый туннель и всё, что нужно, чтобы его свернуть."""

    plan: TunPlan
    process: subprocess.Popen | None = None
    rollback: list[list[str]] = field(default_factory=list)
    output: deque = field(default_factory=lambda: deque(maxlen=OUTPUT_TAIL_LINES))

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


def _drain_output(process: subprocess.Popen, sink: deque) -> None:
    """Вычитывает вывод tun2socks, пока процесс жив.

    Смысл в самом чтении, а не в том, что накопится: непрочитанная труба
    рано или поздно останавливает процесс. Хвост сохраняем попутно — он
    пригодится, если туннель не поднимется.
    """
    stream = getattr(process, "stdout", None)
    if stream is None:
        return
    logged = 0
    try:
        for line in stream:
            text = line.rstrip()
            if not text:
                continue
            sink.append(text)
            # Пишем в журнал, а не только копим: это единственное место,
            # где видно, доходят ли соединения до прокси. Ни таблица
            # маршрутов, ни адаптер об этом не знают ничего.
            if logged < OUTPUT_LOG_LIMIT:
                log(f"tun2socks: {text}", _LOG)
                logged += 1
                if logged == OUTPUT_LOG_LIMIT:
                    log(
                        f"tun2socks: дальше молчу, набрано {OUTPUT_LOG_LIMIT} строк; "
                        "вывод продолжает вычитываться",
                        _LOG,
                    )
    except Exception:
        # Труба закрылась вместе с процессом. Это обычное завершение, а
        # не повод писать в журнал при каждом отключении.
        pass


def _console_encoding() -> str:
    """Кодировка, в которой печатают консольные утилиты Windows.

    route и netsh пишут в OEM-кодировке — на русской Windows это cp866.
    Python при ``text=True`` берёт кодировку локали, то есть ANSI cp1251.
    Байта 0x98 в cp1251 нет вовсе, и первая же русская буква в ответе
    утилиты роняла поток чтения вывода:

        File "subprocess.py", line 1614, in _readerthread
        UnicodeDecodeError: 'charmap' codec can't decode byte 0x98

    Наружу это выглядело не так, как читалось в отчёте. Падал поток, а не
    вызов: ``subprocess.run`` возвращался с пустым выводом, и
    ``default_gateway()`` честно докладывал, что шлюза нет, — на любой
    русской системе, всегда. При ``needs_server_exception`` это обрывало
    подключение сообщением «не удалось определить шлюз провайдера», хотя
    шлюз был на месте. Плюс отчёт о падении на каждое «Подключить».
    """
    try:
        import ctypes

        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"  # type: ignore[attr-defined]
    except Exception:
        # Не Windows или урезанный ctypes — тогда utf-8 не хуже прочего.
        return "utf-8"


def _run(command: list[str], *, check: bool = True) -> tuple[int, str]:
    """Выполняет системную команду без окна консоли."""
    creation_flags = 0
    try:
        creation_flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    except AttributeError:
        pass

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding=_console_encoding(),
            # Один неожиданный байт не должен стоить нам всего вывода:
            # из него нужны IP-адреса и имя адаптера, а это ASCII.
            errors="replace",
            timeout=15,
            creationflags=creation_flags,
        )
    except Exception as exc:
        if check:
            raise TunModeError(f"Не удалось выполнить {command[0]}: {exc}") from exc
        return (-1, str(exc))

    output = f"{completed.stdout}\n{completed.stderr}".strip()
    if check and completed.returncode != 0:
        raise TunModeError(f"{' '.join(command[:3])} завершилась с кодом {completed.returncode}: {output[:200]}")
    return (completed.returncode, output)


def default_gateway(*, exclude: str = "") -> str:
    """Шлюз провайдера — через него пойдёт исключение для сервера.

    Берём из таблицы маршрутов, а не из настроек адаптера: у машины
    может быть несколько адаптеров, а нужен тот, через который сейчас
    ходит трафик.

    ``exclude`` — шлюз самого туннеля. К моменту вызова адаптер уже
    настроен, и netsh успел поставить через него маршрут по умолчанию,
    так что в таблице лежат две строки `0.0.0.0 0.0.0.0`: провайдерская
    и наша. Какая окажется первой, решает Windows, и без отбора мы
    однажды пропишем исключение для сервера через туннель — то есть
    завернём в туннель то самое соединение, на котором он держится.
    Это не гипотеза про будущее: порядок строк уже наблюдался разный.
    """
    code, output = _run(["route", "print", "0.0.0.0"], check=False)
    if code != 0:
        return ""
    skip = str(exclude or "").strip()
    for line in output.splitlines():
        parts = line.split()
        # Строка вида: 0.0.0.0  0.0.0.0  192.168.1.1  192.168.1.50  25
        if len(parts) >= 3 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
            candidate = parts[2]
            if not candidate or candidate.lower() == "on-link":
                continue
            if skip and candidate == skip:
                continue
            return candidate
    return ""


def adapter_exists(name: str) -> bool:
    code, output = _run(
        ["netsh", "interface", "show", "interface", f"name={name}"],
        check=False,
    )
    return code == 0 and name.lower() in output.lower()


def wait_for_adapter(name: str, *, timeout: float = ADAPTER_WAIT_SECONDS) -> bool:
    deadline = time.monotonic() + max(0.1, float(timeout))
    while time.monotonic() < deadline:
        if adapter_exists(name):
            return True
        time.sleep(ADAPTER_POLL_SECONDS)
    return False


def address_ready(name: str) -> bool:
    """Действует ли уже статический адрес на адаптере.

    Проверяем именно адрес, а не наличие адаптера: маршруту нужен не
    адаптер, а подключённая сеть 10.67.0.0/24, без которой шлюз
    10.67.0.1 для Windows не существует.
    """
    code, output = _run(
        ["netsh", "interface", "ipv4", "show", "addresses", f"name={name}"],
        check=False,
    )
    return code == 0 and TUN_ADDRESS in output


def wait_for_address(name: str, *, timeout: float = ADDRESS_WAIT_SECONDS) -> bool:
    deadline = time.monotonic() + max(0.1, float(timeout))
    while time.monotonic() < deadline:
        if address_ready(name):
            return True
        time.sleep(ADAPTER_POLL_SECONDS)
    return False


def _route_failed(answer: str) -> bool:
    """Отказ ли это. Смотрим текст: код возврата route.exe всегда ноль."""
    low = str(answer or "").lower()
    return any(marker in low for marker in ROUTE_FAILURE_MARKERS)


def _spawn_tun2socks(plan: TunPlan) -> subprocess.Popen:
    creation_flags = 0
    try:
        creation_flags = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    except AttributeError:
        pass

    command = build_tun2socks_command(plan)
    # Командная строка в журнал: разбирать «туннель поднят, а сети нет»
    # без неё нечем — половина причин видна прямо в аргументах.
    log(f"Запуск tun2socks: {' '.join(command)}", _LOG)

    # tun2socks написан на Go и печатает в UTF-8 независимо от кодовой
    # страницы консоли — в отличие от route и netsh, которым нужен OEM.
    # Поэтому кодировка тут задана явно, а не через _console_encoding().
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )


def _log_route_summary(plan: TunPlan) -> None:
    """Кладёт в журнал те строки таблицы маршрутов, которые нас касаются.

    Снимок делается сразу после поднятия, когда состояние ещё то самое.
    Просить человека выполнить `route print` в этот момент — значит
    получить таблицу через минуту и не ту.
    """
    code, output = _run(["route", "print", "-4"], check=False)
    if code != 0:
        log(f"Таблицу маршрутов прочитать не удалось: {output[:160]}", _LOG)
        return

    interesting = (plan.gateway_ip, "0.0.0.0", *plan.server_ips)
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4 and any(token and token in parts for token in interesting):
            log(f"маршрут: {' '.join(parts)}", _LOG)


def start(plan: TunPlan, *, spawn=None) -> TunSession:
    """Поднимает туннель. При любой ошибке откатывает сделанное."""
    session = TunSession(plan=plan)

    launcher = spawn or _spawn_tun2socks
    session.process = launcher(plan)

    # Читатель запускается сразу и работает всё время жизни туннеля.
    # Отложить его до ошибки нельзя: к моменту ошибки труба уже могла
    # переполниться и остановить процесс — то есть стать причиной.
    reader = threading.Thread(
        target=_drain_output,
        args=(session.process, session.output),
        name="tun2socks-output",
        daemon=True,
    )
    reader.start()

    try:
        if not wait_for_adapter(plan.adapter):
            # Процесс мог умереть сразу — тогда причина в его выводе.
            reason = ""
            if session.process is not None and session.process.poll() is not None:
                # Даём читателю добрать хвост уже закрытой трубы.
                reader.join(timeout=0.5)
                reason = " ".join(session.output).strip()[:200]
            raise TunModeError(
                f"Адаптер «{plan.adapter}» не появился. {reason}".strip()
            )

        for command in build_adapter_setup_commands(plan):
            code, answer = _run(command)
            log(f"{' '.join(command)} → код {code}, ответ: {answer or 'пусто'}", _LOG)

        # Ждём, пока адрес заработает, и только потом трогаем маршруты.
        # Без этой паузы `route add` через 10.67.0.1 отвечает «Сетевая
        # папка недоступна»: сети ещё нет, шлюза для Windows не
        # существует. Ответ приходит с нулевым кодом, поэтому раньше
        # отказ проходил незамеченным.
        if not wait_for_address(plan.adapter):
            raise TunModeError(
                f"Адрес {TUN_ADDRESS} на адаптере «{plan.adapter}» не поднялся "
                f"за {ADDRESS_WAIT_SECONDS:.0f} с — маршруты ставить некуда."
            )

        gateway = default_gateway(exclude=plan.gateway_ip)
        log(
            f"Шлюз провайдера: {gateway or 'не определён'}; "
            f"исключения для сервера: {', '.join(plan.server_ips) or 'не требуются'}",
            _LOG,
        )
        if plan.needs_server_exception and not gateway:
            raise TunModeError(
                "Не удалось определить шлюз провайдера — без него маршрут к "
                "серверу уйдёт в туннель, и соединение оборвётся."
            )

        # Каждая команда с её ответом.
        #
        # route.exe отвечает «ОК» и кодом 0 в том числе тогда, когда
        # маршрут не добавился, — а именно этот случай и разбираем:
        # обеих половинок `0.0.0.0/1` в таблице не оказалось, хотя обе
        # команды прошли без ошибки.
        for command in build_route_commands(plan, default_gateway=gateway):
            code, answer = _run(command)
            log(f"{' '.join(command)} → код {code}, ответ: {answer or 'пусто'}", _LOG)
            session.rollback.append(command)
            if _route_failed(answer):
                # Молча продолжать нельзя. Туннель без своих маршрутов
                # либо не работает вовсе, либо работает через побочный
                # маршрут от netsh — и то и другое человек видит как
                # «подключено, а интернета нет», без причины в журнале.
                raise TunModeError(f"Маршрут не добавился: {answer[:160]}")

        log(f"Туннель поднят: весь трафик идёт через {plan.proxy_address}", _LOG)
        _log_route_summary(plan)
        return session

    except Exception:
        stop(session)
        raise


def stop(session: TunSession | None) -> None:
    """Сворачивает туннель. Безопасно вызывать сколько угодно раз."""
    if session is None:
        return

    # Маршруты снимаем первыми и всегда.
    #
    # Если сначала убить процесс, а потом упасть на маршрутах, система
    # останется с маршрутом по умолчанию в мёртвый адаптер — то есть
    # без интернета вовсе.
    for command in build_route_cleanup_commands(session.plan):
        _run(command, check=False)
    session.rollback.clear()

    process = session.process
    session.process = None
    if process is None:
        return

    try:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
    except Exception as exc:
        log(f"tun2socks не остановился штатно: {exc}", _LOG)

    log("Туннель свёрнут, маршруты возвращены", _LOG)


__all__ = [
    "ADAPTER_WAIT_SECONDS",
    "TunSession",
    "adapter_exists",
    "default_gateway",
    "start",
    "stop",
    "wait_for_adapter",
]
