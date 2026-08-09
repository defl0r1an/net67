# winws_runtime/health/post_mortem.py
"""Diagnosis of an unexpected winws/winws2 exit while DPI was running.

At start time the launch flow already has rich diagnostics; this module gives
the same quality of answer for the "process died mid-session" case: the dead
`Popen` still holds the exit code, and (for winws2) the child's output keeps
streaming into the startup-output file until death.
"""

from __future__ import annotations

from dataclasses import dataclass

from log.log import log
from winws_runtime.runners.spawn_failure import SpawnFailureKind, classify_spawn_failure


_STATUS_ACCESS_VIOLATION = 0xC0000005
_STATUS_STACK_BUFFER_OVERRUN = 0xC0000409


@dataclass(frozen=True)
class PostMortemDiagnosis:
    message: str
    kind: str


@dataclass(frozen=True)
class PostMortemResolution:
    """Full resolution of one unexpected death: what to tell the user and
    whether an automatic restart is worth trying."""

    message: str
    kind: str
    transient: bool
    exit_code: int


def _first_relevant_output_line(output: str) -> str:
    lines = [line.strip() for line in str(output or "").splitlines() if line.strip()]
    for line in reversed(lines):
        lower = line.lower()
        if "windivert:" in lower or "error opening filter" in lower:
            return line
    for line in reversed(lines):
        lower = line.lower()
        if "error" in lower or "ошибка" in lower:
            return line
    return lines[-1] if lines else ""


def _format_exit_code(exit_code: int) -> str:
    code = int(exit_code)
    if code < 0 or code > 0xFFFF:
        return f"{code} / 0x{code & 0xFFFFFFFF:08X}"
    return str(code)


def diagnose_unexpected_winws_exit(exit_code, output: str = "", *, exe_name: str) -> PostMortemDiagnosis:
    """Builds a user-facing cause for a process that died while DPI was running."""
    try:
        code = int(exit_code)
    except Exception:
        code = -1
    output_text = str(output or "")
    exe = str(exe_name or "winws").strip() or "winws"
    prefix = f"{exe} неожиданно завершился во время работы"

    # 1. The start-time diagnosis parses windivert stderr text; it also covers
    # "driver was unloaded/disabled externally" because winws logs a windivert
    # error right before dying.
    from winws_runtime.health.process_health_check import diagnose_winws_exit

    try:
        diag = diagnose_winws_exit(code, output_text)
    except Exception:
        diag = None
    if diag is not None:
        cause = str(getattr(diag, "cause", "") or "").strip()
        solution = str(getattr(diag, "solution", "") or "").strip()
        if cause:
            message = f"{prefix}: {cause}"
            if solution:
                message = f"{message}. {solution}"
            return PostMortemDiagnosis(message=message, kind="diagnosed")

    # 2. Mid-session specials the start-time diagnosis does not know about.
    if code == 1 and not output_text.strip():
        return PostMortemDiagnosis(
            message=(
                f"{prefix} (код 1): процесс был принудительно завершён извне — "
                "возможно, антивирусом, оптимизатором или другой программой. "
                "Проверьте карантин и исключения антивируса."
            ),
            kind="external_kill",
        )
    if code in (_STATUS_ACCESS_VIOLATION, _STATUS_STACK_BUFFER_OVERRUN):
        return PostMortemDiagnosis(
            message=(
                f"{prefix}: аварийное завершение (код {_format_exit_code(code)}). "
                "Если повторяется — сохраните лог и сообщите о проблеме."
            ),
            kind="crash",
        )

    classification = classify_spawn_failure(code, output_text)
    if classification.kind == SpawnFailureKind.TRANSIENT_DLL_INIT:
        return PostMortemDiagnosis(
            message=(
                f"{prefix}: Windows не смогла инициализировать DLL "
                f"(код {_format_exit_code(code)}). Попробуйте запустить снова."
            ),
            kind=classification.kind.value,
        )
    if classification.kind == SpawnFailureKind.WINDIVERT_SYSTEM:
        detail = _first_relevant_output_line(output_text)
        message = f"{prefix}: системная ошибка WinDivert (код {_format_exit_code(code)})"
        if detail:
            message = f"{message}: {detail[:200]}"
        return PostMortemDiagnosis(message=message, kind=classification.kind.value)

    # 3. Generic fallback with the most relevant output line.
    detail = _first_relevant_output_line(output_text)
    message = f"{prefix} (код {_format_exit_code(code)})"
    if detail:
        message = f"{message}: {detail[:200]}"
    return PostMortemDiagnosis(message=message, kind="unknown")


def resolve_unexpected_exit() -> PostMortemResolution | None:
    """Structured post-mortem for the current runner's dead process.

    Returns None (and stays completely silent) when:
    - an external winws scan (BlockCheck) is active — the scanner owns the
      winws lifecycle for that window;
    - there is no runner instance;
    - the tracked process object is absent or still alive.
    No logging side effects: publication is the caller's decision.
    """
    from winws_runtime.runtime.scan_guard import is_external_winws_scan_active

    if is_external_winws_scan_active():
        return None

    try:
        from winws_runtime.runners.runner_factory import get_current_runner

        runner = get_current_runner()
    except Exception:
        runner = None
    if runner is None:
        return None

    try:
        snapshot = runner.build_post_mortem_snapshot()
    except Exception as exc:
        log(f"Post-mortem snapshot failed: {exc}", "DEBUG")
        snapshot = None
    if not snapshot:
        return None

    import os

    exit_code = snapshot.get("exit_code")
    output = snapshot.get("output") or ""
    exe_name = os.path.basename(str(getattr(runner, "winws_exe", "") or "")) or "winws"
    diagnosis = diagnose_unexpected_winws_exit(exit_code, output, exe_name=exe_name)
    strategy_name = str(snapshot.get("strategy_name") or "").strip()
    if strategy_name:
        log(f"Unexpected exit of '{strategy_name}' diagnosed as: {diagnosis.kind}", "INFO")

    try:
        code = int(exit_code)
    except Exception:
        code = -1
    transient = (
        diagnosis.kind not in ("external_kill", "crash")
        and classify_spawn_failure(code, output).retryable
    )
    return PostMortemResolution(
        message=diagnosis.message,
        kind=diagnosis.kind,
        transient=transient,
        exit_code=code,
    )


def resolve_unexpected_exit_message() -> str:
    """Diagnoser hook for LaunchRuntimeService (poll-path detection).

    Returns "" when no post-mortem data is available — the caller then keeps
    its generic message and no ERROR is logged.
    """
    resolution = resolve_unexpected_exit()
    if resolution is None:
        return ""
    # The single user-facing publication for this death event (ERROR → toast).
    log(resolution.message, "ERROR")
    return resolution.message
