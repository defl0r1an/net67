from __future__ import annotations

import sys
import time
from typing import Callable

from log.log import log


def run_cpu_diagnostic() -> None:
    import threading as _threads
    import traceback as _traceback
    import time as _time

    _time.sleep(15)
    try:
        import psutil as _psutil

        this_proc = _psutil.Process()
        this_proc.cpu_percent(interval=None)
        _time.sleep(1)

        log("=== CPU DIAGNOSTIC: начало ===", "INFO")
        log(f"Активных тредов Python: {_threads.active_count()}", "INFO")

        frames = sys._current_frames()
        for tid, frame in frames.items():
            thread = next((item for item in _threads.enumerate() if item.ident == tid), None)
            name = thread.name if thread else f"tid-{tid}"
            stack = "".join(_traceback.format_stack(frame)).strip()
            log(f"[STACK '{name}']\n{stack[-1200:]}", "INFO")

        samples_gui = []
        for idx in range(5):
            cpu_gui = this_proc.cpu_percent(interval=2.0)
            samples_gui.append(cpu_gui)
            winws_parts = []
            for proc in _psutil.process_iter(["name", "cpu_percent"]):
                try:
                    proc_name = (proc.info.get("name") or "").lower()
                    from settings.mode import ALL_WINWS_EXE_NAME_SET

                    if proc_name in ALL_WINWS_EXE_NAME_SET:
                        winws_parts.append(f"{proc_name}={proc.cpu_percent():.1f}%")
                except Exception:
                    pass
            winws_str = ", ".join(winws_parts) if winws_parts else "не запущен"
            log(f"[CPU {idx + 1}/5] Python GUI: {cpu_gui:.1f}%  |  winws: {winws_str}", "INFO")

        avg = sum(samples_gui) / len(samples_gui) if samples_gui else 0
        log(f"=== CPU DIAGNOSTIC DONE: avg Python GUI = {avg:.1f}% ===", "INFO")

        if avg > 20:
            try:
                from collections import Counter

                sample_counts: dict = Counter()
                for _ in range(50):
                    _time.sleep(0.1)
                    frames2 = sys._current_frames()
                    for tid2, frame2 in frames2.items():
                        thread2 = next((item for item in _threads.enumerate() if item.ident == tid2), None)
                        thread_name = thread2.name if thread2 else f"tid-{tid2}"
                        stack2 = _traceback.extract_stack(frame2)
                        key = thread_name + " | " + " -> ".join(
                            f"{frame.filename.split('/')[-1].split(chr(92))[-1]}:{frame.lineno}:{frame.name}"
                            for frame in stack2[-4:]
                        )
                        sample_counts[key] += 1
                top = sample_counts.most_common(15)
                report = "\n".join(f"  {count:3d}x  {key}" for key, count in top)
                log(f"[SAMPLING top-15 hotspots (50 samples x 100ms)]\n{report}", "INFO")
            except Exception as exc:
                log(f"Sampling error: {exc}", "WARNING")
    except Exception as exc:
        log(f"CPU diagnostic error: {exc}", "WARNING")


def build_global_exception_handler() -> Callable[[type[BaseException], BaseException, object], None]:
    def _global_exception_handler(exctype, value, tb_obj) -> None:
        import traceback as tb

        try:
            error_msg = "".join(tb.format_exception(exctype, value, tb_obj))
        except Exception as format_error:
            try:
                base_error = "".join(tb.format_exception_only(exctype, value)).strip()
            except Exception:
                base_error = f"{getattr(exctype, '__name__', exctype)}: {value!r}"
            error_msg = f"{base_error}\n[traceback formatting failed: {format_error!r}]"
        log(f"UNCAUGHT EXCEPTION: {error_msg}", level="❌ CRITICAL")

    return _global_exception_handler
