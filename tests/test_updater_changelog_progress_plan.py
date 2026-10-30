from __future__ import annotations

import unittest

from updater.download_progress import DownloadProgress, progress_labels


class UpdaterChangelogProgressPlanTests(unittest.TestCase):
    def test_download_speed_and_eta_stay_visible_between_samples(self) -> None:
        now = [0.0]
        progress = DownloadProgress(clock=lambda: now[0])
        progress.set_stage("download", "Скачивание обновления…")
        progress.update(0, 0, 100 * 1024 * 1024)
        now[0] = 2.0
        progress.update(50, 50 * 1024 * 1024, 100 * 1024 * 1024)
        first = progress.snapshot()
        now[0] = 2.2
        second = progress.snapshot()
        labels = progress_labels(second)

        self.assertNotEqual(labels.speed, "Скорость: —")
        self.assertNotEqual(labels.eta, "Осталось: —")
        self.assertEqual(second.percent, first.percent)
        self.assertGreater(second.speed, 0)
        self.assertGreater(second.eta_seconds, 0)


if __name__ == "__main__":
    unittest.main()
