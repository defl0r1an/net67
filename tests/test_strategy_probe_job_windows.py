"""Проверяет Windows Job на безвредном дочернем процессе, без драйвера и обхода."""
import subprocess
import sys

from winws_runtime.engine import winapi


def test_closing_probe_job_terminates_its_child_process():
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"],
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.PIPE,
    )
    job = None
    try:
        assert process.stdout.readline().strip() == b"ready"
        job = winapi.create_kill_on_close_job()
        winapi.assign_process_to_job(job, int(process._handle))
        assert process.poll() is None
        winapi.close_handle(job)
        job = None
        # Закрытие Job вправе завершить процесс с кодом 0; важен выход до конца паузы.
        assert process.wait(timeout=5) is not None
    finally:
        if job is not None:
            winapi.close_handle(job)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
