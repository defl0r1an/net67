from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, QObject, QThread, Qt

from log.log import log
from ui.ui_thread_guard import build_background_worker_launcher


#: Уборщики живых потоков. Держим ссылки сами: больше их никто не хранит,
#: а без ссылки Python удалил бы уборщика раньше, чем поток закончит.
_JANITORS: set["_ThreadJanitor"] = set()


class _ThreadJanitor(QObject):
    """Убирает за служебным потоком — всегда в потоке окна.

    Уборку делали два замыкания, подключённые к сигналам. Замыкание
    исполняется в потоке, где его подключили, — и пока потоки запускало
    окно, это был поток окна. Но главная кнопка включает и выключает
    обход из своего фонового потока, и уборка вставала в очередь к нему.
    Тот поток к этому времени уже кончился: очередь никто не разбирал.

    Команда «завершись» до служебного потока не доходила, и он оставался
    «выполняющимся» навсегда. Остановка обхода проверяла именно это и
    молча выходила — «остановка уже идёт». Первый раз за сеанс обход
    выключался, дальше — нет, ни кругом, ни меткой в заголовке; круг при
    этом писал «Обход выключен» при работающем обходе.

    Уборщик — объект, и живёт он в потоке окна, откуда бы поток ни
    запустили. Сигналы приходят к нему через очередь окна, а её
    разбирают всегда.
    """

    def __init__(self, owner, thread: QThread, *, thread_attr: str, worker_attr: str, label: str) -> None:
        super().__init__()
        self._owner = owner
        self._thread = thread
        self._thread_attr = thread_attr
        self._worker_attr = worker_attr
        self._label = label

    def on_worker_finished(self, *_args) -> None:
        try:
            self._thread.quit()
            worker = getattr(self._owner, self._worker_attr, None)
            if worker is not None:
                worker.deleteLater()
                setattr(self._owner, self._worker_attr, None)
        except Exception as e:
            log(f"Ошибка при очистке {self._label}: {e}", "❌ ERROR")

    def on_thread_finished(self, *_args) -> None:
        try:
            if getattr(self._owner, self._thread_attr, None) is self._thread:
                setattr(self._owner, self._thread_attr, None)
            self._thread.deleteLater()
        except Exception as e:
            log(f"Ошибка при очистке {self._label}: {e}", "❌ ERROR")
        finally:
            _JANITORS.discard(self)
            self.deleteLater()


def _window_thread() -> QThread | None:
    app = QCoreApplication.instance()
    return app.thread() if app is not None else None


def start_worker_thread(
    owner,
    *,
    thread_attr: str,
    worker_attr: str,
    worker,
    finished_slot=None,
    progress_slot=None,
    cleanup_log_label: str = "worker thread",
) -> QThread:
    thread = QThread()
    setattr(owner, thread_attr, thread)
    setattr(owner, worker_attr, worker)

    janitor = _ThreadJanitor(
        owner,
        thread,
        thread_attr=thread_attr,
        worker_attr=worker_attr,
        label=cleanup_log_label,
    )
    window_thread = _window_thread()
    if window_thread is not None:
        # Уборщика и сам объект потока отдаём потоку окна: запусти их не
        # из окна — их сигналы и deleteLater ждали бы очереди, которую
        # никто не разбирает. Из окна это ничего не меняет.
        janitor.moveToThread(window_thread)
        thread.moveToThread(window_thread)
    _JANITORS.add(janitor)

    worker.moveToThread(thread)
    # В Nuitka обычный AutoConnection уже возвращал тяжёлый run() в GUI-поток.
    # QThread.started испускается новым потоком, поэтому прямое соединение здесь
    # гарантирует выполнение worker-а вне интерфейса.
    thread.started.connect(
        build_background_worker_launcher(worker, worker.run, "run"),
        Qt.ConnectionType.DirectConnection,
    )

    progress_signal = getattr(worker, "progress", None)
    if progress_slot is not None and progress_signal is not None:
        progress_signal.connect(progress_slot)

    finished_signal = getattr(worker, "finished", None)
    if finished_signal is None:
        _JANITORS.discard(janitor)
        raise RuntimeError(f"{type(worker).__name__} does not expose finished signal")

    if finished_slot is not None:
        finished_signal.connect(finished_slot)

    # Уборка — после обработчика результата: тот ещё читает работника.
    finished_signal.connect(janitor.on_worker_finished)
    thread.finished.connect(janitor.on_thread_finished)
    thread.start()
    return thread
