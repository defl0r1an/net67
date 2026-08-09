from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from log.log import log


class OrchestraManagedSnapshotLoadWorker(QThread):
    loaded = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)

    def __init__(self, request_id: int, load_snapshot, parent=None):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._load_snapshot = load_snapshot

    def run(self) -> None:
        try:
            snapshot = self._load_snapshot()
        except Exception as exc:
            log(f"Orchestra managed snapshot worker: ошибка загрузки: {exc}", "ERROR")
            self.failed.emit(self._request_id, str(exc))
            return
        self.loaded.emit(self._request_id, snapshot)


class OrchestraManagedActionWorker(QThread):
    loaded = pyqtSignal(int, str, object, object)
    failed = pyqtSignal(int, str, str, object)

    def __init__(
        self,
        request_id: int,
        load_snapshot,
        change_strategy=None,
        remove_strategy=None,
        add_strategy=None,
        clear_user_strategies=None,
        is_blocked_strategy=None,
        current_strategy=None,
        clear_strategies=None,
        *,
        action: str,
        hostname: str = "",
        domain: str = "",
        strategy: int = 0,
        old_strategy: int = 0,
        new_strategy: int = 0,
        askey: str = "",
        user_count: int = 0,
        total: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._load_snapshot = load_snapshot
        self._change_strategy = change_strategy
        self._remove_strategy = remove_strategy
        self._add_strategy = add_strategy
        self._clear_user_strategies = clear_user_strategies
        self._is_blocked_strategy = is_blocked_strategy
        self._current_strategy = current_strategy
        self._clear_strategies = clear_strategies
        self._action = str(action or "").strip()
        self._hostname = str(hostname or "").strip().lower()
        self._domain = str(domain or "").strip().lower()
        self._strategy = int(strategy or 0)
        self._old_strategy = int(old_strategy or 0)
        self._new_strategy = int(new_strategy or 0)
        self._askey = str(askey or "").strip().lower()
        self._user_count = int(user_count or 0)
        self._total = int(total or 0)

    def run(self) -> None:
        context = {
            "hostname": self._hostname,
            "domain": self._domain,
            "strategy": self._strategy,
            "old_strategy": self._old_strategy,
            "new_strategy": self._new_strategy,
            "askey": self._askey,
            "user_count": self._user_count,
            "total": self._total,
        }
        try:
            if self._action == "blocked_change":
                result = self._change_strategy(
                    hostname=self._hostname,
                    old_strategy=self._old_strategy,
                    new_strategy=self._new_strategy,
                    askey=self._askey,
                )
            elif self._action == "blocked_remove":
                result = self._remove_strategy(
                    hostname=self._hostname,
                    strategy=self._strategy,
                    askey=self._askey,
                )
            elif self._action == "blocked_add":
                result = self._add_strategy(
                    domain=self._domain,
                    strategy=self._strategy,
                    askey=self._askey,
                )
            elif self._action == "blocked_clear_user":
                result = self._clear_user_strategies(user_count=self._user_count)
            elif self._action == "locked_change":
                if self._is_blocked_strategy(
                    domain=self._domain,
                    strategy=self._new_strategy,
                ):
                    payload = {
                        "result": None,
                        "snapshot": None,
                        "blocked_by_policy": True,
                        "current_strategy": self._current_strategy(
                            domain=self._domain,
                            askey=self._askey,
                        ),
                    }
                    self.loaded.emit(self._request_id, self._action, payload, context)
                    return
                result = self._change_strategy(
                    domain=self._domain,
                    new_strategy=self._new_strategy,
                    askey=self._askey,
                )
            elif self._action == "locked_remove":
                result = self._remove_strategy(
                    domain=self._domain,
                    askey=self._askey,
                )
            elif self._action == "locked_add":
                if self._is_blocked_strategy(
                    domain=self._domain,
                    strategy=self._strategy,
                ):
                    payload = {
                        "result": None,
                        "snapshot": None,
                        "blocked_by_policy": True,
                        "current_strategy": self._current_strategy(
                            domain=self._domain,
                            askey=self._askey,
                        ),
                    }
                    self.loaded.emit(self._request_id, self._action, payload, context)
                    return
                result = self._add_strategy(
                    domain=self._domain,
                    strategy=self._strategy,
                    askey=self._askey,
                )
            elif self._action == "locked_clear":
                result = self._clear_strategies(total=self._total)
            else:
                raise ValueError(f"Неизвестное действие managed-списка: {self._action}")
            snapshot = self._load_snapshot()
        except Exception as exc:
            log(f"Orchestra managed action worker: ошибка действия {self._action}: {exc}", "ERROR")
            self.failed.emit(self._request_id, self._action, str(exc), context)
            return
        self.loaded.emit(self._request_id, self._action, {"result": result, "snapshot": snapshot}, context)


class OrchestraWhitelistSnapshotLoadWorker(QThread):
    loaded = pyqtSignal(int, bool, object)
    failed = pyqtSignal(int, bool, str)

    def __init__(self, request_id: int, load_snapshot, *, refresh: bool, parent=None):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._load_snapshot = load_snapshot
        self._refresh = bool(refresh)

    def run(self) -> None:
        try:
            snapshot = self._load_snapshot(refresh=self._refresh)
        except Exception as exc:
            log(f"Orchestra whitelist snapshot worker: ошибка загрузки: {exc}", "ERROR")
            self.failed.emit(self._request_id, self._refresh, str(exc))
            return
        self.loaded.emit(self._request_id, self._refresh, snapshot)


class OrchestraWhitelistActionWorker(QThread):
    loaded = pyqtSignal(int, str, object, object)
    failed = pyqtSignal(int, str, str, object)

    def __init__(
        self,
        request_id: int,
        add_domain,
        remove_domain,
        clear_user_domains,
        load_snapshot,
        *,
        action: str,
        domain: str = "",
        user_domains: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._add_domain = add_domain
        self._remove_domain = remove_domain
        self._clear_user_domains = clear_user_domains
        self._load_snapshot = load_snapshot
        self._action = str(action or "").strip()
        self._domain = str(domain or "").strip().lower()
        self._user_domains = list(user_domains or [])

    def run(self) -> None:
        context = {
            "domain": self._domain,
            "user_domains": tuple(self._user_domains),
        }
        try:
            if self._action == "add":
                result = self._add_domain(domain=self._domain)
            elif self._action == "remove":
                result = self._remove_domain(domain=self._domain)
            elif self._action == "clear_user":
                result = self._clear_user_domains(user_domains=self._user_domains)
            else:
                raise ValueError(f"Неизвестное действие whitelist: {self._action}")
            snapshot = self._load_snapshot(refresh=True)
        except Exception as exc:
            log(f"Orchestra whitelist action worker: ошибка действия {self._action}: {exc}", "ERROR")
            self.failed.emit(self._request_id, self._action, str(exc), context)
            return
        self.loaded.emit(self._request_id, self._action, {"result": result, "snapshot": snapshot}, context)


__all__ = [
    "OrchestraManagedActionWorker",
    "OrchestraManagedSnapshotLoadWorker",
    "OrchestraWhitelistActionWorker",
    "OrchestraWhitelistSnapshotLoadWorker",
]
