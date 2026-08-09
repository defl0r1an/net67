"""Helper'ы содержимого DPI summary для Blockcheck page."""

from __future__ import annotations

from dataclasses import dataclass


DPI_BADGE_COLORS = {
    "none": ("#52c477", "#1a3a24"),
    "dns_fake": ("#e0a854", "#3a2e1a"),
    "http_inject": ("#e07854", "#3a221a"),
    "isp_page": ("#e05454", "#3a1a1a"),
    "tls_dpi": ("#e05454", "#3a1a1a"),
    "tls_mitm": ("#e05454", "#3a1a1a"),
    "tcp_reset": ("#e07854", "#3a221a"),
    "tcp_16_20": ("#e0a854", "#3a2e1a"),
    "stun_block": ("#e0a854", "#3a2e1a"),
    "full_block": ("#e05454", "#3a1a1a"),
}

DPI_LABELS_RU = {
    "none": "DPI не обнаружен",
    "dns_fake": "DNS подмена",
    "http_inject": "HTTP инъекция",
    "isp_page": "Страница-заглушка ISP",
    "tls_dpi": "TLS DPI (RST/EOF)",
    "tls_mitm": "TLS MITM прокси",
    "tcp_reset": "TCP RST",
    "tcp_16_20": "TCP блок 16-20KB",
    "stun_block": "STUN/UDP блокировка",
    "full_block": "Полная блокировка",
}


@dataclass(slots=True)
class BlockcheckDpiSummaryContent:
    badge_label: str
    badge_fg: str
    badge_bg: str
    detail_text: str
    dns_summary_text: str
    recommendation_text: str


def generate_recommendations(report) -> str:
    from blockcheck.models import DPIClassification, TestStatus, TestType

    recommendations = []
    classifications = {target.classification for target in report.targets}

    if DPIClassification.DNS_FAKE in classifications:
        recommendations.append("DNS подменяется — используйте DoH/DoT или шифрованный DNS")
    if DPIClassification.TLS_DPI in classifications:
        recommendations.append("TLS DPI обнаружен — включите обход DPI (zapret)")
    if DPIClassification.TLS_MITM in classifications:
        recommendations.append("MITM прокси — проверьте сертификаты и VPN/прокси настройки")
    if DPIClassification.ISP_PAGE in classifications or DPIClassification.HTTP_INJECT in classifications:
        recommendations.append("HTTP инъекция/страница ISP — используйте HTTPS и обход DPI")
    if DPIClassification.TCP_16_20 in classifications:
        recommendations.append("TCP блок 16-20KB — включите фрагментацию пакетов")
    if DPIClassification.STUN_BLOCK in classifications:
        recommendations.append("STUN/UDP заблокирован — голосовые звонки могут не работать")
    if DPIClassification.FULL_BLOCK in classifications:
        recommendations.append("Полная блокировка — попробуйте VPN или прокси")

    tls12_fail_13_ok = False
    for target in report.targets:
        tls12 = [test for test in target.tests if test.test_type == TestType.TLS_12]
        tls13 = [test for test in target.tests if test.test_type == TestType.TLS_13]
        if tls12 and tls13 and tls12[0].status != TestStatus.OK and tls13[0].status == TestStatus.OK:
            tls12_fail_13_ok = True
            break
    if tls12_fail_13_ok:
        recommendations.append("TLS 1.2 блокируется (DPI видит SNI), но TLS 1.3 работает — сайты доступны через современные браузеры")

    if not recommendations:
        core_https_has_failures = False
        for target in report.targets:
            for test in target.tests:
                if test.test_type in (TestType.HTTP, TestType.TLS_12, TestType.TLS_13) and test.status != TestStatus.OK:
                    core_https_has_failures = True
                    break
            if core_https_has_failures:
                break

        if core_https_has_failures:
            recommendations.append(
                "Есть проблемы доступа (TIMEOUT/FAIL), но сигнатура DPI не определена — "
                "проверьте сеть/VPN/прокси и повторите тест"
            )
        else:
            recommendations.append("Блокировки не обнаружены — всё работает нормально")

    return "\n".join(f"• {item}" for item in recommendations)


def build_dpi_summary_content(*, report, is_dark: bool, no_dpi_text: str) -> BlockcheckDpiSummaryContent:
    from blockcheck.models import DPIClassification

    all_classifications = [target.classification for target in report.targets]
    dpi_types = [classification for classification in all_classifications if classification != DPIClassification.NONE]

    if not dpi_types:
        cls_value = "none"
    else:
        priority = [
            DPIClassification.FULL_BLOCK,
            DPIClassification.TLS_MITM,
            DPIClassification.TLS_DPI,
            DPIClassification.ISP_PAGE,
            DPIClassification.HTTP_INJECT,
            DPIClassification.TCP_16_20,
            DPIClassification.TCP_RESET,
            DPIClassification.DNS_FAKE,
            DPIClassification.STUN_BLOCK,
        ]
        worst = DPIClassification.NONE
        for candidate in priority:
            if candidate in dpi_types:
                worst = candidate
                break
        cls_value = worst.value if worst != DPIClassification.NONE else dpi_types[0].value

    badge_label = DPI_LABELS_RU.get(cls_value, cls_value)
    fg, bg = DPI_BADGE_COLORS.get(cls_value, ("#e0a854", "#3a2e1a"))
    badge_bg = bg if is_dark else fg
    badge_fg = "#ffffff"

    details = []
    for target in report.targets:
        if target.classification != DPIClassification.NONE:
            details.append(f"{target.name}: {DPI_LABELS_RU.get(target.classification.value, target.classification.value)}")

    if report.preflight:
        pf_passed = sum(1 for item in report.preflight if item.verdict.value == "passed")
        pf_warned = sum(1 for item in report.preflight if item.verdict.value == "warning")
        pf_failed = sum(1 for item in report.preflight if item.verdict.value == "failed")
        pf_text = f"Preflight: {pf_passed} OK"
        if pf_warned:
            pf_text += f", {pf_warned} предупр."
        if pf_failed:
            pf_text += f", {pf_failed} ошибок"
            failed_domains = [item.domain for item in report.preflight if item.verdict.value == "failed"]
            if failed_domains:
                pf_text += f"\nПроблемные: {', '.join(failed_domains[:5])}"
                if len(failed_domains) > 5:
                    pf_text += f" (+{len(failed_domains) - 5})"
        details.append(pf_text)

    detail_text = "\n".join(details) if details else no_dpi_text

    dns_summary_text = ""
    if report.dns_integrity:
        dns_total = len(report.dns_integrity)
        comparable = [
            item for item in report.dns_integrity
            if item.is_comparable or bool(item.udp_ips and item.doh_ips)
        ]
        dns_ok = sum(1 for item in comparable if item.is_consistent and not item.is_stub)
        dns_fake = [item for item in comparable if (not item.is_consistent) or item.is_stub]
        dns_stubs = [item for item in report.dns_integrity if item.is_stub]
        dns_unknown = dns_total - len(comparable)

        if comparable:
            dns_summary_text = f"DNS: {dns_ok}/{len(comparable)} OK (сравнимо)"
            if dns_fake:
                dns_summary_text += f"\nDNS подмена/аномалия: {len(dns_fake)}"
        else:
            dns_summary_text = "DNS: нет сравнимых результатов (DoH недоступен)"

        if dns_unknown > 0:
            dns_summary_text += f"\nБез сравнения DoH: {dns_unknown}"
        if dns_stubs:
            dns_summary_text += f"\nDNS заглушки: {', '.join(item.domain for item in dns_stubs)}"

    recommendation_text = generate_recommendations(report)

    return BlockcheckDpiSummaryContent(
        badge_label=badge_label,
        badge_fg=badge_fg,
        badge_bg=badge_bg,
        detail_text=detail_text,
        dns_summary_text=dns_summary_text,
        recommendation_text=recommendation_text,
    )
