"""Диагностика использует реальные пути net67, а не пути из фикстуры."""
import ast
from pathlib import Path
from unittest.mock import patch

from config.runtime_layout import ApplicationPaths


def test_registry_reads_missing_cache_with_real_application_paths(tmp_path):
    from diagnostics import registry

    paths = ApplicationPaths.from_root(tmp_path)
    with patch('config.runtime_layout.APPLICATION_PATHS', paths):
        folder = registry.default_folder()
        index = registry.load(folder)
    assert folder == paths.settings_dir / 'diagnostics' / 'registry'
    assert not index.hosts
    assert not folder.exists()


def test_diagnostics_application_path_attributes_exist():
    root = Path(__file__).resolve().parents[1] / 'src'
    for package in ('diagnostics', 'blockcheck', 'dns'):
        for path in (root / package).rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'APPLICATION_PATHS':
                    assert hasattr(ApplicationPaths, node.attr), f'{path}:{node.lineno}: {node.attr}'


def test_strategy_scan_starts_and_closes_real_log(tmp_path):
    from blockcheck import strategy_scan_logs
    from log.run_log_sessions import run_log_sessions
    with patch.object(strategy_scan_logs, '_resolve_log_dir', return_value=tmp_path):
        state = strategy_scan_logs.start_run_log(target='example.com', mode='smart', scan_protocol='tcp_https')
    try:
        assert state.created
        assert state.path.is_file()
        assert 'example.com' in state.path.read_text(encoding='utf-8')
    finally:
        run_log_sessions.close(state.path)


def test_strategy_scan_reports_log_creation_failure():
    from blockcheck import strategy_scan_logs
    with patch.object(strategy_scan_logs.run_log_sessions, 'start', return_value=False):
        state = strategy_scan_logs.start_run_log(target='example.com', mode='smart', scan_protocol='tcp_https')
    assert not state.created
    assert state.path is None


def test_result_card_can_be_replaced_while_its_dialog_is_open():
    from PyQt6 import sip
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    from blockcheck.ui.result_cards import ResultCard
    from blockcheck.ui.result_cards_model import build_cards
    from test_blockcheck_result_cards import _REPORT
    app = QApplication.instance() or QApplication([])
    widget = ResultCard(build_cards(_REPORT)[0])
    widget.resize(350, 200)
    widget.opened.connect(lambda _: sip.delete(widget))
    event = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(10, 10), QPointF(10, 10), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    widget.mouseReleaseEvent(event)
    assert sip.isdeleted(widget)


def test_old_report_is_read_but_new_report_uses_current_format(tmp_path):
    import json
    from blockcheck.commands import load_past_blockcheck_report
    from diagnostics.history import report_json
    from diagnostics.report_compat import LEGACY_BLOCKCHECK_FORMAT
    document = json.loads(report_json({'scope': 'main'}, {}))
    assert document['format'] == 'net67.blockcheck/1'
    document['format'] = LEGACY_BLOCKCHECK_FORMAT
    path = tmp_path / 'report.json'
    path.write_text(json.dumps(document), encoding='utf-8')
    assert load_past_blockcheck_report(str(path)) == {'scope': 'main'}
