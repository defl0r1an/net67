"""Туннель для всего трафика системы, а не только для браузера.

## Зачем он понадобился

Ядро Xray поднимает локальный SOCKS-прокси и больше ничего не делает.
Чтобы через него кто-то пошёл, программа правит ветку реестра
``HKCU\\...\\Internet Settings`` — ту же, что и «Параметры → Сеть и
Интернет → Прокси».

Эту ветку читают Chromium, Edge и IE. Больше почти никто. Приложения на
Electron, Node, .NET, Go и Python ходят в сеть своим стеком и в реестр
не заглядывают. Отсюда жалоба, с которой всё началось: в браузере адрес
сменился, а установщик Claude Desktop «не может достучаться до
серверов» — он идёт напрямую, мимо VPN, и упирается в блокировку.

Починить это настройкой прокси нельзя: приложение само решает, читать
её или нет. Нужен туннель — виртуальный сетевой адаптер, в который
уходит весь трафик системы. Так работает Happ и любой клиент, у которого
«VPN» означает VPN, а не «прокси для браузера».

## Как он устроен

Три части, и ни одна не заменяет другие:

1. ``wintun.dll`` — драйвер виртуального адаптера. Уже лежит в поставке,
   его использует клиент AmneziaWG.
2. ``tun2socks.exe`` — читает пакеты из адаптера и отдаёт их в SOCKS
   ядра Xray. Именно он превращает «прокси» в «туннель».
3. Таблица маршрутов — говорит Windows слать всё через адаптер. Кроме
   одного адреса: самого VPN-сервера, иначе трафик к нему пошёл бы
   через туннель, который на нём же и держится.

Третий пункт — то место, где ошибка стоит дорого. Маршрут по умолчанию
перехватывает вообще всё, включая соединение с сервером. Без исключения
для сервера туннель обрывает сам себя, а машина остаётся без сети до
перезагрузки. Поэтому исключение ставится первым, а снимается последним.

## Чего здесь нет

Здесь нет запуска процессов и вызовов WinAPI — только команды, проверки
и решения. Так модуль проверяется без Windows и без прав администратора,
как и ``vpn/tunnel.py`` для AmneziaWG.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path


#: Имя виртуального адаптера. Видно в «Сетевых подключениях».
TUN_ADAPTER_NAME = "net67"

#: Адрес самого адаптера и маска. Сеть выбрана из диапазона, который
#: почти не встречается у домашних роутеров: 192.168.0.x и 192.168.1.x
#: заняты у большинства, и совпадение увело бы в туннель локальную сеть.
TUN_ADDRESS = "10.67.0.2"
TUN_NETMASK = "255.255.255.0"
TUN_GATEWAY = "10.67.0.1"

#: Метрика маршрута по умолчанию через туннель. Меньше — приоритетнее.
#: Ноль не берём: Windows относится к нему особо, а нам нужно лишь
#: обойти обычный маршрут провайдера с метрикой около 25.
TUN_ROUTE_METRIC = 5

#: MTU виртуального адаптера. Задаётся с двух сторон одним числом.
#:
#: Обе стороны — это обязательное условие, а не аккуратность. tun2socks
#: читает пакеты буфером своего MTU, а Windows отправляет их по тому
#: MTU, который видит у адаптера. Пока числа не заданы, каждая сторона
#: берёт своё умолчание, и при расхождении крупные пакеты просто
#: исчезают: мелкое проходит, крупное — нет.
#:
#: Наружу это выглядит как «сайты грузятся, но без стилей и картинок»:
#: HTML умещается в первые пакеты, остальное встаёт. Замер на одном и
#: том же сервере и одном и том же ядре: через туннель 0 байт/с, мимо
#: туннеля 3,9 МБ/с.
#:
#: 1420 — с запасом под заголовки внешнего соединения. Столько же по
#: умолчанию берёт WireGuard, и это значение обкатано на плохих каналах.
TUN_MTU = 1420

#: Подробность журнала tun2socks.
#:
#: Держим на `warning`: на `debug` он пишет строку на каждое соединение,
#: и с открытым браузером журнал становится нечитаемым за минуту.
#:
#: Но помнить стоит вот что. Разбирая неработающий туннель, я дважды
#: упирался в его молчание — и когда маршруты не добавлялись, и когда
#: пакеты DNS отбрасывались по несовпадению адреса. Оба раза причина
#: нашлась за минуту, стоило поднять уровень до `debug`. Так что при
#: следующей жалобе вида «подключено, а сети нет» начинать надо отсюда:
#: поменять одно слово и пересобрать.
TUN_LOG_LEVEL = "warning"

#: DNS внутри туннеля. Системный DNS провайдера в туннеле бесполезен:
#: запрос уйдёт через сервер, а ответ вернёт адреса ближайшего к
#: провайдеру узла — и подмена DNS, ради обхода которой всё затевалось,
#: останется на месте.
TUN_DNS = ("1.1.1.1", "8.8.8.8")

#: Сети, которые в туннель не заворачиваются.
#:
#: Две половинки `0.0.0.0/1` и `128.0.0.0/1` покрывают всё адресное
#: пространство, включая частные сети. На машине в домене это значит,
#: что обращения к своим же серверам уходят за границу. В журнале
#: туннеля это видно прямо:
#:
#:     [TCP] 10.67.0.2:60274 <-> 192.168.2.5:445     — файловая шара
#:     [UDP] 10.67.0.2:59939 <-> 192.168.100.3:389   — контроллер домена
#:     [UDP] 10.67.0.2:58853 <-> 192.168.100.2:53    — корпоративный DNS
#:
#: Ломается при этом не только вход в домен. Ни одно из таких
#: соединений не может состояться — на том конце туннеля этих машин
#: нет, — и каждое честно ждёт своего таймаута, занимая место. Пока
#: сотни таких висят, обычный запрос наружу ждёт вместе с ними: пустой
#: `https://1.1.1.1/` без всякого DNS отвечал 12 секунд.
#:
#: 10.0.0.0/8 включает и нашу 10.67.0.0/24, но у той маска длиннее, и
#: Windows выбирает более точное совпадение, а не меньшую метрику.
LOCAL_NETWORKS = (
    ("10.0.0.0", "255.0.0.0"),
    ("172.16.0.0", "255.240.0.0"),
    ("192.168.0.0", "255.255.0.0"),
    ("169.254.0.0", "255.255.0.0"),
)


class TunModeError(RuntimeError):
    """Туннель поднять не удалось. Текст показывается человеку."""


@dataclass(frozen=True, slots=True)
class TunPlan:
    """Что и в каком порядке сделать, чтобы поднять туннель."""

    executable: Path
    adapter: str
    proxy_address: str
    server_ips: tuple[str, ...]
    gateway_ip: str

    @property
    def needs_server_exception(self) -> bool:
        """Нужен ли отдельный маршрут к серверу мимо туннеля.

        Не нужен ровно в одном случае: сервер и так недостижим через
        туннель — например, это локальный адрес для проверки.
        """
        return bool(self.server_ips)


def tun2socks_path(root: str | Path | None = None) -> Path:
    """Где лежит tun2socks. Рядом с xray, в той же папке bin."""
    if root is not None:
        return Path(root) / "bin" / "tun2socks" / "tun2socks.exe"

    from config.runtime_layout import APPLICATION_PATHS

    return Path(APPLICATION_PATHS.bin_dir) / "tun2socks" / "tun2socks.exe"


def wintun_path(root: str | Path | None = None) -> Path:
    """Где лежит драйвер адаптера. Он общий с клиентом AmneziaWG."""
    if root is not None:
        return Path(root) / "exe" / "wintun.dll"

    from config.runtime_layout import APPLICATION_PATHS

    return Path(APPLICATION_PATHS.exe_dir) / "wintun.dll"


def ensure_wintun_next_to_tool(root: str | Path | None = None) -> bool:
    """Кладёт wintun.dll рядом с tun2socks, если его там нет.

    tun2socks грузит драйвер по имени, то есть ищет его рядом с собой и
    в системных путях — в папку `exe` нашей поставки он не заглядывает.
    Без драйвера он запускается молча и не создаёт адаптер: со стороны
    это выглядит как «адаптер net67 не появился» без единого намёка на
    причину. Именно так оно и выглядело.

    Копия, а не перенос: тот же файл нужен клиенту AmneziaWG на прежнем
    месте, и забрать его оттуда значит сломать соседний туннель.
    """
    tool_dir = tun2socks_path(root).parent
    target = tool_dir / "wintun.dll"
    if target.is_file():
        return True

    source = wintun_path(root)
    if not source.is_file():
        return False

    try:
        import shutil

        tool_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return True
    except Exception:
        return False


def check_available(root: str | Path | None = None) -> tuple[bool, str]:
    """Можно ли поднять туннель. Возвращает (можно, что сказать человеку).

    Разделять причины важно: отсутствие ``tun2socks`` человек может
    исправить сам, положив файл, а отсутствие ``wintun.dll`` означает
    испорченную поставку — и совет там другой.
    """
    tool = tun2socks_path(root)
    if not tool.is_file():
        return (
            False,
            "Для режима «весь трафик» нужен tun2socks. Положите tun2socks.exe "
            f"в папку {tool.parent} и повторите.",
        )

    driver = wintun_path(root)
    if not driver.is_file():
        return (
            False,
            f"Не найден драйвер адаптера {driver.name} — поставка повреждена. "
            "Восстановите программу через страницу обновлений.",
        )

    # Драйвер должен лежать рядом с tun2socks: он ищет его по имени, а в
    # папку `exe` нашей поставки не заглядывает.
    if not ensure_wintun_next_to_tool(root):
        return (
            False,
            f"Не удалось положить {driver.name} рядом с tun2socks "
            f"({tool.parent}). Скопируйте файл туда вручную.",
        )

    return (True, "")


def is_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(str(value or "").strip())
    except ValueError:
        return False
    return True


def build_plan(
    *,
    proxy_address: str,
    server_ips,
    root: str | Path | None = None,
    adapter: str = TUN_ADAPTER_NAME,
    gateway_ip: str = TUN_GATEWAY,
) -> TunPlan:
    """Собирает план запуска. Проверки — здесь, чтобы не падать позже.

    ``server_ips`` — все адреса сервера, а не один.

    Одного не хватает. У имени сервера может быть несколько A-записей, и
    выдаются они по кругу: три подключения подряд дали 212.46.33.95,
    212.46.33.92 и 212.46.33.96. Исключение из туннеля ставилось по
    одному адресу, а ядро Xray разрешает имя само — и попадало в другой.
    Тогда соединение ядра с сервером уходило в туннель, который на этом
    соединении и держится: пакет к серверу шёл в tun2socks, тот отдавал
    его в SOCKS ядра, ядро снова слало к серверу. Петля без единой
    ошибки в журнале — ни tun2socks, ни ядру жаловаться не на что,
    просто ничего не движется. Снаружи: «подключено, интернета нет».

    Совпадёт адрес или нет — решала случайность, отсюда и «то работает,
    то не работает» между запусками.
    """
    available, message = check_available(root)
    if not available:
        raise TunModeError(message)

    address = str(proxy_address or "").strip()
    if not address:
        raise TunModeError("Не задан адрес локального прокси Xray")

    if isinstance(server_ips, str):
        server_ips = [server_ips]

    servers: list[str] = []
    for item in server_ips or ():
        server = str(item or "").strip()
        if not server:
            continue
        if not is_ip_address(server):
            # Домен здесь бесполезен: маршрут ставится по адресу, а не по
            # имени. Разрешать имя должен вызывающий — у него есть сеть,
            # которая ещё не завёрнута в туннель.
            raise TunModeError(f"Адрес сервера должен быть IP, а не именем: {server}")
        if server not in servers:
            servers.append(server)

    return TunPlan(
        executable=tun2socks_path(root),
        adapter=str(adapter or TUN_ADAPTER_NAME),
        proxy_address=address,
        server_ips=tuple(servers),
        gateway_ip=str(gateway_ip or TUN_GATEWAY),
    )


def build_tun2socks_command(plan: TunPlan) -> list[str]:
    """Командная строка tun2socks.

    Длинные имена флагов пишутся с двумя дефисами: разбор аргументов там
    сделан на pflag, и одиночный дефис он оставляет коротким именам.
    С одним дефисом программа не ругается на неизвестный ключ, а печатает
    справку и выходит — и в окне появлялось «Адаптер не появился», а
    следом кусок этой справки вместо причины.
    """
    return [
        str(plan.executable),
        "--device",
        f"tun://{plan.adapter}",
        "--proxy",
        f"socks5://{plan.proxy_address}",
        # Тот же MTU ставится адаптеру через netsh. Значение здесь и там
        # обязано совпадать, см. пояснение к TUN_MTU.
        "--mtu",
        str(TUN_MTU),
        "--loglevel",
        TUN_LOG_LEVEL,
    ]


def build_adapter_setup_commands(plan: TunPlan) -> list[list[str]]:
    """Настройка адреса адаптера и DNS.

    Адрес назначается статически: DHCP в туннеле некому обслуживать.
    """
    commands = [
        [
            "netsh", "interface", "ip", "set", "address",
            f"name={plan.adapter}", "static", TUN_ADDRESS, TUN_NETMASK, plan.gateway_ip,
            str(TUN_ROUTE_METRIC),
        ],
        # MTU — тем же числом, что получил tun2socks. Расхождение здесь
        # стоит дороже всего: соединение устанавливается, а данные не
        # идут, и в журналах об этом ни слова.
        [
            "netsh", "interface", "ipv4", "set", "subinterface",
            plan.adapter, f"mtu={TUN_MTU}", "store=active",
        ],
    ]
    for index, server in enumerate(TUN_DNS):
        commands.append(
            [
                "netsh", "interface", "ip",
                "set" if index == 0 else "add",
                "dnsservers",
                f"name={plan.adapter}",
                "static" if index == 0 else server,
                server if index == 0 else f"index={index + 1}",
            ]
        )
    return commands


def build_route_commands(plan: TunPlan, *, default_gateway: str) -> list[list[str]]:
    """Маршруты: сервер — мимо туннеля, всё остальное — в туннель.

    Порядок в списке — это порядок выполнения, и он не случаен. Сначала
    исключение для сервера, только потом маршрут по умолчанию: между
    этими двумя командами трафик к серверу уже может уйти в туннель,
    который на нём же и держится, и соединение оборвётся само.
    """
    commands: list[list[str]] = []

    if plan.needs_server_exception and default_gateway:
        # По исключению на каждый адрес имени. Пропустить хоть один
        # значит оставить ядру шанс выбрать именно его — и задушить
        # туннель, см. пояснение в build_plan().
        for server_ip in plan.server_ips:
            commands.append(
                ["route", "add", server_ip, "mask", "255.255.255.255", default_gateway, "metric", "1"]
            )

    if default_gateway:
        # Локальные сети остаются локальными. Тоже до маршрута по
        # умолчанию: между командами трафик к своим уже уходил бы в
        # туннель. Подробности — у LOCAL_NETWORKS.
        for network, mask in LOCAL_NETWORKS:
            commands.append(
                ["route", "add", network, "mask", mask, default_gateway, "metric", "1"]
            )

    # Две половины вместо одного 0.0.0.0/0: так родной маршрут
    # провайдера остаётся в таблице нетронутым, и отключение туннеля
    # не требует его восстанавливать — достаточно убрать наши две
    # записи. Приём известный, им пользуются все клиенты с TUN.
    commands.append(
        ["route", "add", "0.0.0.0", "mask", "128.0.0.0", plan.gateway_ip,
         "metric", str(TUN_ROUTE_METRIC)]
    )
    commands.append(
        ["route", "add", "128.0.0.0", "mask", "128.0.0.0", plan.gateway_ip,
         "metric", str(TUN_ROUTE_METRIC)]
    )
    return commands


def build_route_cleanup_commands(plan: TunPlan) -> list[list[str]]:
    """Снятие маршрутов. Исключение для сервера убирается последним."""
    commands = [
        ["route", "delete", "0.0.0.0", "mask", "128.0.0.0", plan.gateway_ip],
        ["route", "delete", "128.0.0.0", "mask", "128.0.0.0", plan.gateway_ip],
    ]
    for network, mask in LOCAL_NETWORKS:
        commands.append(["route", "delete", network, "mask", mask])
    for server_ip in plan.server_ips:
        commands.append(["route", "delete", server_ip])
    return commands


def describe_mode(*, tun_enabled: bool) -> str:
    """Что написать человеку про охват соединения.

    Разница между режимами не косметическая, и молчать о ней нельзя:
    в режиме прокси половина программ идёт мимо VPN, и человек узнаёт
    об этом, когда у него не ставится приложение.
    """
    if tun_enabled:
        return "Весь трафик системы идёт через сервер."
    return (
        "Через сервер идёт только браузер. Приложения ходят напрямую — "
        "включите режим «весь трафик», если нужен полный охват."
    )


__all__ = [
    "TUN_ADAPTER_NAME",
    "TUN_ADDRESS",
    "TUN_DNS",
    "TUN_GATEWAY",
    "LOCAL_NETWORKS",
    "TUN_LOG_LEVEL",
    "TUN_MTU",
    "TUN_NETMASK",
    "TUN_ROUTE_METRIC",
    "TunModeError",
    "TunPlan",
    "build_adapter_setup_commands",
    "build_plan",
    "build_route_cleanup_commands",
    "build_route_commands",
    "build_tun2socks_command",
    "check_available",
    "describe_mode",
    "is_ip_address",
    "tun2socks_path",
    "wintun_path",
]
