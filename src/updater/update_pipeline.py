"""Поэтапный конвейер загрузки и передачи обновления установщику.

Главный принцип: worker-ы этого модуля не получают runtime, окно или другие
QObject-ы приложения. Они выполняют только сеть, файлы и внешний PowerShell.
Переходами между стадиями и жизненным циклом DPI владеет UpdatePageRuntime.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

from config.build_info import APP_VERSION, CHANNEL
from config.runtime_layout import APPLICATION_PATHS
from log.log import log

from .download_transfer import (
    CHUNK_SIZE,
    CancellationToken,
    DownloadSource,
    ThrottledProgress,
    UpdateCancelled,
    UpdateIntegrityError,
    UpdatePipelineError,
    _make_session,
    download_source,
)
from .github_release import normalize_version
from .release_manager import get_latest_release
from .update import compare_versions, launch_installer_winapi


SHA256_HEX_LENGTH = 64


class UpdateStage(StrEnum):
    CHECK = "check"
    RESOLVE = "resolve"
    CONNECTIVITY = "connectivity"
    DOWNLOAD = "download"
    VERIFY = "verify"
    HANDOFF = "handoff"
    INSTALLER = "installer"


@dataclass(frozen=True, slots=True)
class UpdateArtifact:
    version: str
    file_name: str
    expected_size: int
    expected_sha256: str
    sources: tuple[DownloadSource, ...]


@dataclass(frozen=True, slots=True)
class UpdatePreflightResult:
    artifact: UpdateArtifact
    connectivity_ok: bool


@dataclass(frozen=True, slots=True)
class InstallerHandoff:
    version: str
    installer_path: str
    arguments: tuple[str, ...]
    #: Куда записать номер процесса установщика — для окна-продолжения.
    pid_file: str = ""


def quiet_installer_arguments(arguments) -> tuple[str, ...]:
    """/SILENT → /VERYSILENT: ход установки показывает окно-продолжение.

    Своё окно установщика под ним только мешало бы: две полосы одного и того же.
    Ошибки установщика /VERYSILENT не прячет.
    """
    return tuple("/VERYSILENT" if str(item).upper() == "/SILENT" else str(item) for item in arguments)


def _emit_stage(
    callback: Callable[[str, str], None] | None,
    stage: UpdateStage,
    message: str,
) -> None:
    log(f"Стадия обновления {stage.value}: {message}", "🔁 UPDATE")
    if callback is not None:
        callback(stage.value, message)


def normalize_sha256(value: object) -> str:
    """Принимает чистый SHA-256 или GitHub digest ``sha256:...``."""
    normalized = str(value or "").strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized.split(":", 1)[1].strip()
    if len(normalized) != SHA256_HEX_LENGTH:
        return ""
    try:
        int(normalized, 16)
    except ValueError:
        return ""
    return normalized


def file_sha256(path: str | os.PathLike[str], token: CancellationToken) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        while True:
            token.checkpoint()
            chunk = file_obj.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _release_sha256(release_info: dict) -> str:
    return normalize_sha256(
        release_info.get("sha256")
        or release_info.get("digest")
        or release_info.get("checksum")
    )


def _matching_github_integrity(release_info: dict) -> tuple[str, int]:
    """При необходимости получает SHA-256 из метаданных GitHub-релиза."""
    expected_sha256 = _release_sha256(release_info)
    expected_size = int(release_info.get("file_size") or 0)
    if expected_sha256 and expected_size > 0:
        return expected_sha256, expected_size

    try:
        from .github_release import get_latest_release as get_github_release

        github_info = get_github_release(CHANNEL)
    except Exception as exc:
        log(f"Не удалось получить контрольную сумму GitHub: {exc}", "WARNING")
        github_info = None

    if not github_info:
        return expected_sha256, expected_size

    try:
        same_version = normalize_version(str(github_info.get("version") or "")) == normalize_version(
            str(release_info.get("version") or "")
        )
    except ValueError:
        same_version = False
    if not same_version:
        return expected_sha256, expected_size

    return (
        expected_sha256 or _release_sha256(github_info),
        expected_size or int(github_info.get("file_size") or 0),
    )


def build_download_sources(release_info: dict) -> tuple[DownloadSource, ...]:
    """Собирает зеркала один раз и удаляет повторы."""
    update_url = str(release_info.get("update_url") or "").strip()
    verify_ssl = bool(release_info.get("verify_ssl", True))
    file_name = str(release_info.get("file_name") or "").strip()
    if not file_name and update_url and not update_url.startswith("telegram://"):
        file_name = update_url.rsplit("/", 1)[-1]
    if not file_name:
        from .channel_utils import get_channel_installer_name

        file_name = get_channel_installer_name(CHANNEL)

    candidates: list[DownloadSource] = []
    if update_url and not update_url.startswith("telegram://"):
        candidates.append(DownloadSource(update_url, verify_ssl))

    if "github.com" not in update_url:
        try:
            from .github_release import get_latest_release as get_github_release

            github_info = get_github_release(CHANNEL)
            if github_info and github_info.get("update_url"):
                candidates.append(DownloadSource(str(github_info["update_url"]), True))
        except Exception as exc:
            log(f"Не удалось добавить зеркало GitHub: {exc}", "WARNING")

    try:
        from .server_config import VPS_SERVERS, should_verify_ssl

        for server in VPS_SERVERS:
            candidates.append(
                DownloadSource(
                    f"https://{server['host']}:{server['https_port']}/download/{file_name}",
                    bool(should_verify_ssl()),
                )
            )
        for server in VPS_SERVERS:
            candidates.append(
                DownloadSource(
                    f"http://{server['host']}:{server['http_port']}/download/{file_name}",
                    False,
                )
            )
    except Exception as exc:
        log(f"Не удалось добавить зеркала VPS: {exc}", "WARNING")

    unique: list[DownloadSource] = []
    seen: set[str] = set()
    for source in candidates:
        if not source.url or source.url in seen:
            continue
        seen.add(source.url)
        unique.append(source)
    return tuple(unique)


def test_connectivity(source: DownloadSource, token: CancellationToken) -> bool:
    token.checkpoint()
    session = _make_session(source.verify_ssl)
    try:
        response = session.head(
            source.url,
            timeout=(5, 5),
            verify=source.verify_ssl,
            allow_redirects=True,
        )
        token.checkpoint()
        return response.status_code < 500
    except Exception:
        return False
    finally:
        session.close()


def prepare_update(
    *,
    requested_version: str,
    token: CancellationToken,
    on_stage: Callable[[str, str], None] | None = None,
) -> UpdatePreflightResult:
    """Выполняет check → resolve → connectivity."""
    token.checkpoint()
    _emit_stage(on_stage, UpdateStage.CHECK, "Проверка выпуска…")
    release_info = get_latest_release(CHANNEL, use_cache=False)
    if not release_info:
        raise UpdatePipelineError("Не удалось получить данные выпуска")

    remote_version = normalize_version(str(release_info.get("version") or ""))
    if compare_versions(APP_VERSION, remote_version) >= 0:
        raise UpdatePipelineError(f"Обновление v{remote_version} уже не требуется")
    if requested_version and compare_versions(remote_version, requested_version) < 0:
        raise UpdatePipelineError("Сервер вернул более старый выпуск")

    token.checkpoint()
    _emit_stage(on_stage, UpdateStage.RESOLVE, "Подготовка источников и проверки файла…")
    sources = build_download_sources(release_info)
    if not sources:
        raise UpdatePipelineError("Нет доступных источников обновления")

    expected_sha256, expected_size = _matching_github_integrity(release_info)
    if not expected_sha256:
        raise UpdateIntegrityError("В метаданных выпуска нет SHA-256")
    if expected_size <= 0:
        raise UpdateIntegrityError("В метаданных выпуска нет размера файла")

    file_name = str(release_info.get("file_name") or "").strip() or "Zapret2Setup.exe"
    artifact = UpdateArtifact(
        version=remote_version,
        file_name=file_name,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        sources=sources,
    )

    token.checkpoint()
    _emit_stage(on_stage, UpdateStage.CONNECTIVITY, "Проверка соединения с сервером…")
    connectivity_ok = test_connectivity(sources[0], token)
    return UpdatePreflightResult(artifact=artifact, connectivity_ok=connectivity_ok)


def verify_artifact(
    artifact: UpdateArtifact,
    installer_path: str,
    token: CancellationToken,
) -> None:
    token.checkpoint()
    actual_size = os.path.getsize(installer_path)
    if actual_size != artifact.expected_size:
        raise UpdateIntegrityError(
            f"Размер установщика не совпадает: {actual_size} вместо {artifact.expected_size}"
        )

    actual_sha256 = file_sha256(installer_path, token)
    if actual_sha256 != artifact.expected_sha256:
        raise UpdateIntegrityError("SHA-256 установщика не совпадает с метаданными выпуска")
    log(f"✅ SHA-256 установщика проверен: {actual_sha256}", "🔁 UPDATE")


def prepare_handoff(
    artifact: UpdateArtifact,
    downloaded_path: str,
    token: CancellationToken,
) -> InstallerHandoff:
    """Копирует уже проверенный файл в устойчивый каталог приложения."""
    token.checkpoint()
    persistent_dir = Path(APPLICATION_PATHS.update_cache_dir)
    persistent_dir.mkdir(parents=True, exist_ok=True)
    persistent_path = persistent_dir / "Zapret2Setup.exe"
    temporary_path = persistent_path.with_suffix(".exe.new")

    try:
        temporary_path.unlink(missing_ok=True)
        shutil.copy2(downloaded_path, temporary_path)
        token.checkpoint()
        os.replace(temporary_path, persistent_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    setup_log = persistent_dir / "setup.log"
    # /SILENT, а не /VERYSILENT: окно с ходом установки видно. Молчаливая
    # установка выглядела так, будто программа просто исчезла; владелец
    # попросил показывать установщик. Вопросов и кнопок «Далее» при этом
    # нет — только полоса и подпись «откроется сама».
    #
    # Если встало окно-продолжение (updater/install_splash.py), ход
    # установки показывает оно, и установщик идёт с /VERYSILENT —
    # quiet_installer_arguments. Не встало — остаётся /SILENT.
    arguments = (
        "/AUTOUPDATE",
        "/SILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/NOCANCEL",
        "/CLOSEAPPLICATIONS",
        f"/DIR={APPLICATION_PATHS.root}",
        f"/LOG={setup_log}",
    )
    return InstallerHandoff(
        version=artifact.version,
        installer_path=str(persistent_path),
        arguments=arguments,
    )


def _partial_download_dir(artifact: UpdateArtifact) -> Path:
    # Имя выпуска не используется как путь; новый размер или SHA никогда не
    # подхватят части предыдущего файла, даже при том же номере версии.
    identity = f"{artifact.version}\0{artifact.expected_size}\0{artifact.expected_sha256}"
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    root = Path(APPLICATION_PATHS.update_cache_dir) / "downloads"
    root.mkdir(parents=True, exist_ok=True)
    current = root / f"partial-{key}"
    current.mkdir(exist_ok=True)
    if current.is_symlink() or current.is_junction() or current.resolve().parent != root.resolve():
        raise UpdatePipelineError("Не удалось безопасно открыть каталог докачки")
    for child in root.iterdir():
        suffix = child.name.removeprefix("partial-")
        if (child != current and child.name.startswith("partial-") and len(suffix) == 64
                and all(char in "0123456789abcdef" for char in suffix)
                and child.is_dir() and not child.is_symlink() and not child.is_junction()
                and child.resolve().parent == root.resolve()):
            # Оставляем части только нужного выпуска: десятки старых обновлений
            # иначе занимали бы место после многократных обрывов связи.
            shutil.rmtree(child, ignore_errors=True)
    return current


class UpdatePipeline:
    """Единый сетевой/файловый конвейер без зависимостей от GUI и runtime."""

    def __init__(
        self,
        *,
        token: CancellationToken,
        on_stage: Callable[[str, str], None] | None = None,
        on_progress: Callable[[int, int, int], None] | None = None,
        silent: bool = True,
    ) -> None:
        self._token = token
        self._on_stage = on_stage
        self._on_progress = on_progress
        self._silent = bool(silent)

    def preflight(self, *, requested_version: str) -> UpdatePreflightResult:
        return prepare_update(
            requested_version=requested_version,
            token=self._token,
            on_stage=self._on_stage,
        )

    def download_and_prepare(self, artifact: UpdateArtifact) -> InstallerHandoff:
        cache_dir = _partial_download_dir(artifact)
        destination = str(cache_dir / "installer.part")
        progress = ThrottledProgress(self._on_progress or (lambda *_args: None))
        completed = False
        try:
            _emit_stage(self._on_stage, UpdateStage.DOWNLOAD, "Скачивание обновления…")
            self._download_from_mirrors(artifact, destination, progress)

            self._token.checkpoint()
            _emit_stage(self._on_stage, UpdateStage.VERIFY, "Проверка SHA-256…")
            verify_artifact(artifact, destination, self._token)

            self._token.checkpoint()
            _emit_stage(self._on_stage, UpdateStage.HANDOFF, "Подготовка установщика…")
            handoff = prepare_handoff(artifact, destination, self._token)
            completed = True
            return handoff
        except UpdateIntegrityError:
            # Повтор с повреждённым префиксом не исправил бы контрольную сумму.
            shutil.rmtree(cache_dir, ignore_errors=True)
            raise
        finally:
            if completed:
                shutil.rmtree(cache_dir, ignore_errors=True)

    def _download_from_mirrors(
        self,
        artifact: UpdateArtifact,
        destination: str,
        progress: ThrottledProgress,
    ) -> None:
        last_error: Exception | None = None
        for index, source in enumerate(artifact.sources):
            self._token.checkpoint()
            try:
                log(
                    f"Источник обновления #{index + 1}: {source.url} "
                    f"(SSL={source.verify_ssl})",
                    "🔁 UPDATE",
                )
                download_source(
                    source,
                    destination,
                    token=self._token,
                    progress=progress,
                    max_retries=3,
                    expected_size=artifact.expected_size,
                    on_status=lambda message: _emit_stage(self._on_stage, UpdateStage.DOWNLOAD, message),
                )
                return
            except UpdateCancelled:
                raise
            except Exception as exc:
                last_error = exc
                log(f"Источник #{index + 1} не подошёл: {exc}", "WARNING")
        raise UpdatePipelineError(str(last_error or "Нет доступных источников обновления"))


class UpdatePreflightWorker(QObject):
    stage_changed = pyqtSignal(str, str)
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    finished = pyqtSignal(bool)

    def __init__(self, requested_version: str) -> None:
        super().__init__()
        self._requested_version = str(requested_version or "")
        self._token = CancellationToken()

    def stop(self) -> None:
        self._token.cancel()

    def run(self) -> None:
        try:
            result = UpdatePipeline(
                token=self._token,
                on_stage=self.stage_changed.emit,
            ).preflight(requested_version=self._requested_version)
        except UpdateCancelled:
            self.cancelled.emit()
            self.finished.emit(False)
            return
        except Exception as exc:
            log(f"Подготовка обновления не удалась: {exc}", "🔁❌ ERROR")
            self.failed.emit(str(exc))
            self.finished.emit(False)
            return
        self.ready.emit(result)
        self.finished.emit(True)


class UpdateDownloadWorker(QObject):
    stage_changed = pyqtSignal(str, str)
    progress_bytes = pyqtSignal(int, int, int)
    ready = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    finished = pyqtSignal(bool)

    def __init__(self, artifact: UpdateArtifact, *, silent: bool = True) -> None:
        super().__init__()
        self._artifact = artifact
        self._silent = bool(silent)
        self._token = CancellationToken()

    def stop(self) -> None:
        self._token.cancel()

    def run(self) -> None:
        try:
            handoff = UpdatePipeline(
                token=self._token,
                on_stage=self.stage_changed.emit,
                on_progress=self.progress_bytes.emit,
                silent=self._silent,
            ).download_and_prepare(self._artifact)
        except UpdateCancelled:
            self.cancelled.emit()
            self.finished.emit(False)
            return
        except Exception as exc:
            log(f"Загрузка обновления не удалась: {exc}", "🔁❌ ERROR")
            self.failed.emit(str(exc))
            self.finished.emit(False)
            return
        self.ready.emit(handoff)
        self.finished.emit(True)


class UpdateInstallerWorker(QObject):
    stage_changed = pyqtSignal(str, str)
    launched = pyqtSignal()
    failed = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, handoff: InstallerHandoff) -> None:
        super().__init__()
        self._handoff = handoff
        self._stop_requested = threading.Event()

    def stop(self) -> None:
        self._stop_requested.set()

    def run(self) -> None:
        if self._stop_requested.is_set():
            self.finished.emit(False)
            return
        _emit_stage(
            self.stage_changed.emit,
            UpdateStage.INSTALLER,
            "Запуск установщика…",
        )
        launched = launch_installer_winapi(
            self._handoff.installer_path,
            self._handoff.arguments,
            pid_file=self._handoff.pid_file,
        )
        if not launched:
            self.failed.emit("Не удалось запустить установщик")
            self.finished.emit(False)
            return
        self.launched.emit()
        self.finished.emit(True)


__all__ = [
    "CancellationToken",
    "DownloadSource",
    "InstallerHandoff",
    "ThrottledProgress",
    "UpdateArtifact",
    "UpdateCancelled",
    "UpdateDownloadWorker",
    "UpdateInstallerWorker",
    "UpdateIntegrityError",
    "UpdatePipelineError",
    "UpdatePipeline",
    "UpdatePreflightResult",
    "UpdatePreflightWorker",
    "UpdateStage",
    "build_download_sources",
    "download_source",
    "file_sha256",
    "normalize_sha256",
    "prepare_handoff",
    "prepare_update",
    "test_connectivity",
    "verify_artifact",
]
