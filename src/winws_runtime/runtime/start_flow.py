from __future__ import annotations

from log.log import log
from settings.mode import normalize_launch_method
from winws_runtime.flow.start_preparation import resolve_method_name, resolve_mode_name

from .conflict_flow import handle_conflicting_processes_before_start
from .lifecycle_feedback import show_launch_error_top
from .status_feedback import runtime_owner_status_callback, set_runtime_owner_status
from .start_workers import PresetLaunchStartWorker
from .thread_runtime import start_worker_thread


def fail_start_preparation(runtime_owner, message: str) -> None:
    text = str(message or "").strip() or "Не удалось подготовить запуск DPI"
    log(f"Ошибка подготовки запуска: {text}", "❌ ERROR")
    set_runtime_owner_status(runtime_owner, f"❌ {text}")
    show_launch_error_top(runtime_owner, text)
    runtime_owner._mark_runtime_failed(text)


#: Сколько ждём завершения остановки, прежде чем начинать запуск.
#:
#: Остановка снимает winws и выгружает драйвер; на это уходят единицы
#: секунд. Ждать дольше незачем: если за это время она не закончилась,
#: значит застряла, и запуск всё равно надо пробовать — иначе кнопка
#: замолчит навсегда.
STOP_WAIT_TIMEOUT_MS = 12_000

#: Как часто перепроверяем, закончилась ли остановка.
STOP_WAIT_RETRY_MS = 200


#: Переносчики вызова в главный поток, ждущие срабатывания.
#:
#: Держим ссылку на время ожидания: у объекта без родителя единственная
#: ссылка — локальная переменная, и сборщик мусора уносит его вместе с
#: отложенным запуском ещё до того, как таймер сработает.
_PENDING_MAIN_THREAD_PUMPS: set = set()


def _build_main_thread_pump():
    """Создаёт объект-переносчик вызова в главный поток.

    Класс объявлен внутри функции намеренно: модуль не должен требовать
    PyQt6 на импорте — его тянут и те части, что работают без окна.
    """
    from PyQt6.QtCore import QObject, QTimer, pyqtSignal

    class _MainThreadPump(QObject):
        requested = pyqtSignal(int, object)

        def fire(self, delay_ms: int, callback) -> None:
            _PENDING_MAIN_THREAD_PUMPS.discard(self)
            QTimer.singleShot(int(delay_ms), callback)

    return _MainThreadPump()


def _schedule_in_main_thread(delay_ms: int, callback) -> None:
    """Откладывает вызов так, чтобы он произошёл в главном потоке.

    Голый `QTimer.singleShot(ms, cb)` заводит таймер в том потоке, откуда
    его позвали. Запуск обхода приходит и из окна, и из рабочего потока
    оркестратора — а у рабочего потока цикла событий нет, и таймер там
    не сработал бы никогда. Отложенный запуск тихо потерялся бы, что
    ровно та беда, которую эта отсрочка и лечит.

    Раньше здесь стояло `QTimer.singleShot(ms, app, cb)` — форма с
    объектом-контекстом. В PyQt6 6.11 её нет: `singleShot.__doc__`
    перечисляет только `(msec, slot)` и `(msec, timerType, slot)`.
    Вызов падал с «arguments did not match any overloaded call», и
    кнопка «Включить» отвечала «не удалось запустить обход».

    Из главного потока таймер заводится напрямую. Из рабочего — через
    объект, переселённый в поток приложения: сигнал с очередью
    доставляется туда, и таймер заводится уже там.

    Порядок здесь важен, и он проверен опытом: `connect` делается
    ПОСЛЕ `moveToThread`. Соединение, заведённое до переезда, ставит
    вызов в очередь прежнего потока — сигнал уходит впустую, а запуск
    молча теряется.
    """
    from PyQt6.QtCore import QCoreApplication, Qt, QThread, QTimer

    app = QCoreApplication.instance()
    if app is None:
        # Приложения нет — значит и откладывать некуда. Зовём сразу:
        # хуже молчания не будет.
        callback()
        return

    delay = int(delay_ms)

    if QThread.currentThread() == app.thread():
        QTimer.singleShot(delay, callback)
        return

    pump = _build_main_thread_pump()
    pump.moveToThread(app.thread())
    pump.requested.connect(pump.fire, Qt.ConnectionType.QueuedConnection)
    _PENDING_MAIN_THREAD_PUMPS.add(pump)
    pump.requested.emit(delay, callback)


def _stop_in_progress(runtime_owner) -> bool:
    """Идёт ли ещё остановка обхода.

    Смотрим на работника, а не на поток. Разница не формальная: поток
    после окончания работы живёт в своём цикле событий, пока до него не
    дойдёт `quit()`, и `isRunning()` всё это время возвращает True.
    Работник же обнуляется сразу, как только закончил.

    По потоку и выходила беда «включить → выключить → включить»:
    остановка давно закончилась («DPI успешно остановлен» в журнале), а
    поток числился живым. Запуск честно ждал двенадцать секунд, потом
    шёл напролом — и упирался в проверку, которая молча возвращала
    отказ. В журнале оставалось «Остановка не завершилась за 12000 мс»,
    после чего не происходило ничего, а окно писало «Обход не запустился
    за 40 секунд».
    """
    try:
        worker = getattr(runtime_owner, "_dpi_stop_worker", None)
        if worker is not None:
            return True

        thread = getattr(runtime_owner, "_dpi_stop_thread", None)
        if thread is None:
            return False

        # Работника нет, а поток остался — он уже сворачивается.
        # Ждать его незачем, но и ссылку держать больше не за чем.
        if not thread.isRunning():
            runtime_owner._dpi_stop_thread = None
        return False
    except RuntimeError:
        # Поток уже удалён на стороне C++ — значит не выполняется.
        runtime_owner._dpi_stop_thread = None
        return False
    except Exception:
        return False


def _defer_start_until_stop_finishes(
    runtime_owner,
    *,
    selected_mode,
    launch_method,
    skip_conflict_prompt: bool,
    startup_autostart: bool,
    waited_ms: int = 0,
) -> None:
    """Откладывает запуск, пока не закончится остановка.

    ## Зачем

    Выключить обход и тут же включить обратно — самое обычное действие,
    и оно не работало: появлялось «Обход не запустился за 40 секунд».

    Причина в том, что проверки перед стартом и перед остановкой
    смотрели каждая только на свой поток. Старт не знал про идущую
    остановку и уходил работать рядом с ней. Дальше как повезёт:
    остановка снимала winws, который старт только что поднял, и ждущий
    оркестратор сорок секунд не видел ни одного процесса. Формально
    запуск «прошёл» — фактически его убили свои же.

    ## Почему откладываем, а не отказываем

    Отказ вернул бы ту же ошибку, только быстрее. Человек нажал
    «включить» — значит включить и надо, вопрос лишь в том, чтобы
    дождаться конца уборки. Ровно так уже сделан перезапуск
    (`_schedule_pending_restart_retry`), здесь тот же приём.
    """
    if waited_ms >= STOP_WAIT_TIMEOUT_MS:
        log(
            f"Остановка не завершилась за {STOP_WAIT_TIMEOUT_MS} мс — запускаем как есть",
            "⚠ WARNING",
        )
        start_dpi_async(
            runtime_owner,
            selected_mode,
            launch_method,
            skip_conflict_prompt=skip_conflict_prompt,
            startup_autostart=startup_autostart,
            _force_after_stop_wait=True,
        )
        return

    def _retry() -> None:
        start_dpi_async(
            runtime_owner,
            selected_mode,
            launch_method,
            skip_conflict_prompt=skip_conflict_prompt,
            startup_autostart=startup_autostart,
            _stop_wait_elapsed_ms=waited_ms + STOP_WAIT_RETRY_MS,
        )

    _schedule_in_main_thread(STOP_WAIT_RETRY_MS, _retry)


def prepare_start_preflight(
    runtime_owner,
    *,
    selected_mode=None,
    launch_method=None,
    skip_conflict_prompt: bool = False,
) -> bool:
    """Выполняет раннюю проверку перед построением launch request."""
    # Тот же счёт, что и у остановки: занят, пока жив работник, а не
    # пока жив поток. Поток после работы досиживает в своём цикле
    # событий, и по нему запуск считался идущим, когда он давно кончился.
    #
    # Отказ здесь писался в DEBUG, а DEBUG в файл не попадает. Со стороны
    # это выглядело так: человек жмёт «включить», в журнале ни строчки,
    # окно через сорок секунд пишет, что обход не запустился. Поэтому
    # уровень поднят: немой отказ — худший из возможных.
    try:
        worker = getattr(runtime_owner, "_dpi_start_worker", None)
        thread = getattr(runtime_owner, "_dpi_start_thread", None)
        if worker is not None and thread is not None and thread.isRunning():
            log("Запуск DPI уже выполняется — повторное нажатие пропущено", "INFO")
            return False
        if worker is None and thread is not None and not thread.isRunning():
            runtime_owner._dpi_start_thread = None
    except RuntimeError:
        runtime_owner._dpi_start_thread = None

    # Пока идёт проверка стратегий, движок принадлежит ей.
    #
    # Сканер снимает все процессы winws перед проверкой и поднимает свои
    # по ходу — это его работа. Кнопка «Включить» при этом оставалась
    # доступной, и запущенный ею процесс сканер убивал через несколько
    # секунд. В журнале это выглядело так:
    #
    #     14:46:34  Starting: пресет Ростелеком
    #     14:46:38  Завершено 1 процессов winws2.exe
    #     14:46:38  winws2 завершился сразу (код 1)
    #
    # Человеку показывали «winws2 завершился сразу» или «обход не
    # запустился за 40 секунд» — и то, и другое уводит в сторону: с
    # пресетом и движком всё в порядке, просто их снял сканер.
    try:
        from winws_runtime.runtime.scan_guard import is_external_winws_scan_active

        if is_external_winws_scan_active():
            fail_start_preparation(
                runtime_owner,
                "Идёт проверка стратегий — она сама поднимает и останавливает движок. "
                "Дождитесь её окончания или остановите её.",
            )
            return False
    except ImportError:
        pass

    if not skip_conflict_prompt and not handle_conflicting_processes_before_start(
        runtime_owner,
        selected_mode,
        launch_method,
    ):
        # Отказ отсюда тоже был немым. Разбор конфликтов сам показывает
        # человеку окно, но если он вернул отказ без окна — в журнале не
        # оставалось ни следа, и запуск обрывался в тишине.
        log("Запуск отменён на разборе конфликтующих процессов", "INFO")
        return False

    runtime_owner._pending_launch_warnings = []
    return True


def _requested_launch_method(runtime_owner, launch_method=None) -> str:
    explicit = normalize_launch_method(launch_method, default="")
    if explicit:
        return explicit
    try:
        snapshot = runtime_owner._runtime_service().snapshot()
        return normalize_launch_method(getattr(snapshot, "launch_method", ""), default="")
    except Exception:
        return ""


def start_dpi_async(
    runtime_owner,
    selected_mode=None,
    launch_method=None,
    *,
    skip_conflict_prompt: bool = False,
    startup_autostart: bool = False,
    _stop_wait_elapsed_ms: int = 0,
    _force_after_stop_wait: bool = False,
) -> bool:
    """Запускает DPI через общий асинхронный pipeline.

    Возвращает True, если запуск принят — начат сейчас или отложен до
    конца остановки. False означает отказ: запускать никто не будет.

    Раньше функция ничего не возвращала, а вызывающий код всё равно
    считал запуск принятым. Отказ поэтому выглядел как молчание: кнопка
    гасла, оркестратор сорок секунд ждал процесс, которого никто не
    собирался поднимать, и писал «Обход не запустился за 40 секунд».
    """
    # Сначала дожидаемся конца остановки, если она идёт.
    #
    # Проверка стоит до всего остального: и до разбора конфликтов, и до
    # set_busy. Иначе состояние окна успевало смениться на «запускаем»
    # раньше, чем запуск действительно начинался.
    if not _force_after_stop_wait and _stop_in_progress(runtime_owner):
        log("Идёт остановка DPI — запуск подождёт её конца", "DEBUG")
        _defer_start_until_stop_finishes(
            runtime_owner,
            selected_mode=selected_mode,
            launch_method=launch_method,
            skip_conflict_prompt=skip_conflict_prompt,
            startup_autostart=startup_autostart,
            waited_ms=_stop_wait_elapsed_ms,
        )
        return True

    if not prepare_start_preflight(
        runtime_owner,
        selected_mode=selected_mode,
        launch_method=launch_method,
        skip_conflict_prompt=skip_conflict_prompt,
    ):
        return False

    requested_method = _requested_launch_method(runtime_owner, launch_method)
    if not requested_method:
        fail_start_preparation(runtime_owner, "Не выбран способ запуска DPI")
        return False

    mode_name = resolve_mode_name(selected_mode)
    if selected_mode is None or selected_mode == "default":
        mode_name = "Пресет"
    method_name = resolve_method_name(requested_method)

    if isinstance(selected_mode, tuple) and len(selected_mode) == 2:
        strategy_id, strategy_name = selected_mode
        log(f"Обработка встроенной стратегии: {strategy_name} (ID: {strategy_id})", "DEBUG")
    elif isinstance(selected_mode, dict):
        log(f"Обработка стратегии: {mode_name}", "DEBUG")
    elif isinstance(selected_mode, str):
        log(f"Обработка строковой стратегии: {mode_name}", "DEBUG")

    set_runtime_owner_status(runtime_owner, f"🚀 Запуск DPI ({method_name}): {mode_name}")

    if not startup_autostart:
        runtime_owner._runtime_service().set_busy(True, "Запуск net67...")

    runtime_owner._begin_runtime_start(requested_method, selected_mode)

    start_worker_thread(
        runtime_owner,
        thread_attr="_dpi_start_thread",
        worker_attr="_dpi_start_worker",
        worker=PresetLaunchStartWorker(
            selected_mode,
            requested_method,
            runtime_feature=runtime_owner._runtime_feature,
            runtime_api=runtime_owner._runtime_api(),
            startup_autostart=bool(startup_autostart),
            prepare_request=True,
        ),
        finished_slot=runtime_owner._on_dpi_start_finished,
        progress_slot=runtime_owner_status_callback(runtime_owner),
        cleanup_log_label="потока запуска",
    )

    log(f"Запуск асинхронного старта DPI: {mode_name} (метод: {method_name})", "INFO")
    return True
