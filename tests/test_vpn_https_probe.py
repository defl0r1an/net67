"""Порт и запуск процесса не заменяют HTTPS; сертификат проверяется всегда."""

from unittest.mock import MagicMock, patch

from vpn.http_probe import check_through_proxy, PROBE_URL, PROBE_URL_FALLBACK


def test_probe_uses_verified_https_and_explicit_remote_dns_proxy():
    session = MagicMock()
    session.get.return_value.status_code = 204
    with patch("requests.Session") as factory:
        factory.return_value.__enter__.return_value = session
        result = check_through_proxy(proxy_address="127.0.0.1:18080")
    assert result.ok
    assert PROBE_URL.startswith("https://") and PROBE_URL_FALLBACK.startswith("https://")
    kwargs = session.get.call_args.kwargs
    assert kwargs["verify"] is True and kwargs["allow_redirects"] is False
    assert kwargs["proxies"]["https"] == "socks5h://127.0.0.1:18080"
    assert session.trust_env is False
    session.get.return_value.close.assert_called_once()


def test_nonstandard_https_status_tries_second_target_without_claiming_interception():
    from vpn.http_probe import HttpProbeResult
    with patch("vpn.http_probe._probe_once", side_effect=[HttpProbeResult(False, 9, "Ответ HTTPS 403", 403),
                                                          HttpProbeResult(True, 12, "HTTPS работает", 204)]) as probe:
        result = check_through_proxy(proxy_address="127.0.0.1:18080")
    assert result.ok and probe.call_count == 2


def test_cancellation_does_not_make_a_network_request():
    with patch("vpn.http_probe._probe_once") as probe:
        result = check_through_proxy(proxy_address="127.0.0.1:18080", should_stop=lambda: True)
    assert not result.ok
    probe.assert_not_called()


def test_isolated_probe_never_reconfigures_the_working_connection(tmp_path):
    from vpn.probing import check_profile
    from vpn.http_probe import HttpProbeResult
    runtime = MagicMock(port=19345)
    with (patch("vpn.xray.XrayRuntime", return_value=runtime),
          patch("vpn.http_probe.check_through_proxy", return_value=HttpProbeResult(True, 15, "HTTPS работает")) as probe,
          patch("vpn.link_runtime.connect") as connect,
          patch("vpn.link_runtime.disconnect") as disconnect,
          patch("vpn.system_proxy.enable") as system_proxy):
        assert check_profile(object()).ok
    connect.assert_not_called()
    disconnect.assert_not_called()
    system_proxy.assert_not_called()
    runtime.stop.assert_called_once()
    probe.assert_called_once()
    directory = runtime.start.call_args.kwargs["settings_dir"]
    assert not directory.exists()


def test_isolated_probe_stops_its_process_on_failure():
    from vpn.probing import check_profile
    runtime = MagicMock()
    runtime.start.side_effect = RuntimeError("не запущен")
    with patch("vpn.xray.XrayRuntime", return_value=runtime):
        assert not check_profile(object()).ok
    runtime.stop.assert_called_once()
