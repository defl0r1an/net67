"""BlockCheck data models — pure Python, no Qt dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class TestStatus(Enum):
    OK = "ok"
    FAIL = "fail"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class DPIClassification(Enum):
    NONE = "none"
    DNS_FAKE = "dns_fake"
    HTTP_INJECT = "http_inject"
    ISP_PAGE = "isp_page"
    TLS_DPI = "tls_dpi"
    TLS_MITM = "tls_mitm"
    TCP_RESET = "tcp_reset"
    TCP_16_20 = "tcp_16_20"
    STUN_BLOCK = "stun_block"
    FULL_BLOCK = "full_block"


class TestType(Enum):
    HTTP = "http"
    TLS_12 = "tls12"
    TLS_13 = "tls13"
    STUN = "stun"
    PING = "ping"
    DNS_UDP = "dns_udp"
    DNS_DOH = "dns_doh"
    ISP_PAGE = "isp_page"
    TCP_16_20 = "tcp_16_20"
    PREFLIGHT_DNS = "preflight_dns"
    PREFLIGHT_TCP = "preflight_tcp"
    PREFLIGHT_HTTP = "preflight_http"
    PREFLIGHT_PING = "preflight_ping"


@dataclass
class SingleTestResult:
    target_name: str
    test_type: TestType
    status: TestStatus
    time_ms: float | None = None
    error_code: str | None = None
    detail: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TargetResult:
    name: str
    value: str
    tests: list[SingleTestResult] = field(default_factory=list)
    classification: DPIClassification = DPIClassification.NONE
    classification_detail: str = ""


@dataclass
class DNSIntegrityResult:
    domain: str
    udp_ips: list[str] = field(default_factory=list)
    doh_ips: list[str] = field(default_factory=list)
    is_comparable: bool = False
    is_consistent: bool = True
    is_stub: bool = False
    stub_ip: str | None = None


class PreflightVerdict(Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass
class PreflightResult:
    domain: str
    resolved_ips: list[str] = field(default_factory=list)
    is_block_ip: bool = False
    block_ip_detail: str = ""
    ping: SingleTestResult | None = None
    tcp_443: SingleTestResult | None = None
    dns_result: SingleTestResult | None = None
    http_check: SingleTestResult | None = None
    verdict: PreflightVerdict = PreflightVerdict.PASSED
    verdict_detail: str = ""


@dataclass
class BlockcheckReport:
    preflight: list[PreflightResult] = field(default_factory=list)
    targets: list[TargetResult] = field(default_factory=list)
    dns_integrity: list[DNSIntegrityResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    cancelled: bool = False
