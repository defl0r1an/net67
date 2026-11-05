"""Совместная отмена между окном и системным вызовом, без terminate()."""

import threading


# Операция старой страницы может ещё завершаться после её закрытия. Новый
# сеанс не должен вклиниться между запуском старого и его отменой.
CONNECTION_LOCK = threading.RLock()


def connection_marker():
    from vpn import link_runtime, tunnel_runtime
    return link_runtime.connection_serial(), tunnel_runtime.connection_serial()


class VpnOperation:
    def __init__(self, profile, *, disconnecting=False):
        self.profile = profile
        self.disconnecting = disconnecting
        self.cancelled = threading.Event()
        self.stage = "Отключаем…" if disconnecting else "Запускаем ядро…"

    def report(self, stage):
        self.stage = str(stage)

    def should_stop(self):
        return self.cancelled.is_set()
