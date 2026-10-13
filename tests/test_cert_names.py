from __future__ import annotations

import socket
import unittest
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID
from utils import cert_names


def certificate(*, names=(), issuer_cns=("Issuer CA",), subject_cns=("site.example",), extra=None):
    key = Ed25519PrivateKey.generate()
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name) for name in issuer_cns])
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name) for name in subject_cns])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().issuer_name(issuer).subject_name(subject)
               .public_key(key.public_key()).serial_number(1)
               .not_valid_before(now).not_valid_after(now + timedelta(days=1)))
    if names:
        builder = builder.add_extension(x509.SubjectAlternativeName(list(names)), critical=True)
    if extra:
        builder = builder.add_extension(extra, critical=False)
    return builder.sign(key, None).public_bytes(Encoding.DER)


class CertNamesTests(unittest.TestCase):
    def test_dns_names_and_addresses_are_read(self):
        der = certificate(names=[x509.DNSName("Example.com"), x509.DNSName("*.example.com"),
                                 x509.IPAddress(ip_address("1.2.3.4")), x509.RFC822Name("mail@example.com")])
        self.assertEqual(cert_names.subject_alt_names(der), ("example.com", "*.example.com", "1.2.3.4"))

    def test_critical_flag_and_long_lists(self):
        der = certificate(names=[x509.DNSName(f"host{i}.example.com") for i in range(40)])
        self.assertEqual(len(cert_names.subject_alt_names(der)), 40)
        self.assertEqual(cert_names.subject_alt_names(der)[-1], "host39.example.com")

    def test_broken_certificate_gives_empty_list(self):
        der = certificate(names=[x509.DNSName("example.com")])
        self.assertEqual(cert_names.subject_alt_names(der[:-4]), ())
        self.assertEqual(cert_names.subject_alt_names(b""), ())

    def test_common_name_is_owner_not_issuer(self):
        self.assertEqual(cert_names.common_name(certificate()), "site.example")
        self.assertEqual(cert_names.common_name(certificate(issuer_cns=("CA1", "CA2"))), "site.example")
        self.assertEqual(cert_names.common_name(certificate(subject_cns=())), "")
        self.assertEqual(cert_names.common_name(certificate(issuer_cns=())), "site.example")
        self.assertEqual(cert_names.common_name(b"\x00"), "")

    def test_oid_bytes_inside_another_extension_are_not_site_names(self):
        fake = b"\x06\x03\x55\x04\x03\x0c\x0cwrong.testxx"
        der = certificate(subject_cns=(), extra=x509.UnrecognizedExtension(x509.ObjectIdentifier("1.2.3.4.5"), fake))
        self.assertEqual(cert_names.common_name(der), "")
        self.assertEqual(cert_names.subject_alt_names(der), ())

    def test_closed_port_is_reported_not_raised(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        result = cert_names.fetch_cert_names("127.0.0.1", port=port, timeout_s=1)
        self.assertFalse(result.ok)
        self.assertIn(result.kind, (cert_names.KIND_REFUSED, cert_names.KIND_TIMEOUT))

    def test_bad_address_is_reported(self):
        self.assertEqual(cert_names.fetch_cert_names("nope").kind, cert_names.KIND_ERROR)
