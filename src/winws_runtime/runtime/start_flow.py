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


def _schedule_in_main_thread(delay_ms: int, callback) -> None:
    """Откладывает вызов, привязав таймер к главному потоку.

    Голый `QTimer.singleShot(ms, cb)` заводит таймер в том потоке, откуда
    его позвали. Запуск обхода приходит и из окна, и из рабочего потока
    оркестратора — а у рабочего потока цикла событий нет, и таймер там
    не сработал бы никогда. Отложенный запуск тихо потерялся бы, что
    ровно та беда, которую эта отсрочка и лечит.

    Поэтому таймер привязываем к объекту приложения: он живёт в главном
    потоке, и вызов приходит туда же.
    """
    from PyQt6.QtCore import QCoreApplication, QTimer

    app = QCoreApplication.instance()
    if app is None:
        # Приложения нет — значит и откладывать некуда. Зовём сразу:
        # хуже молчания не будет.
        callback()
        return

    QTimer.singleShot(int(delay_ms), app, callback)


def _stop_in_progress(runtime_owner) -> bool:
    try:
        thread = getattr(runtime_owner, "_dpi_stop_thread", None)
        return bool(thread is not None and thread.isRunning())
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
    try:
        if runtime_owner._dpi_start_thread and runtime_owner._dpi_start_thread.isRunning():
            log("Запуск DPI уже выполняется", "DEBUG")
            return False
    except RuntimeError:
        runtime_owner._dpi_start_thread = None

    if not skip_conflict_prompt and not handle_conflicting_processes_before_start(
        runtime_owner,
        selected_mode,
        launch_method,
    ):
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
