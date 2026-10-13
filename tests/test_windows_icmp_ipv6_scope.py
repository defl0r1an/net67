import ctypes
import unittest
from unittest.mock import Mock, patch

from utils import windows_icmp as icmp


class IcmpScopeTests(unittest.TestCase):
    def test_explicit_interface_reaches_native_api(self):
        scopes = []

        def send(*args):
            destination = ctypes.cast(args[5], ctypes.POINTER(icmp.SOCKADDR_IN6)).contents
            scopes.append(destination.sin6_scope_id)
            reply = icmp.ICMPV6_ECHO_REPLY.from_buffer(args[9])
            reply.Status = 0
            reply.RoundTripTime = 2
            return 1

        with patch.object(icmp, "_Icmp6CreateFile", return_value=1), \
             patch.object(icmp, "_Icmp6SendEcho2", side_effect=send), \
             patch.object(icmp, "_IcmpCloseHandle") as close, \
             patch.object(icmp, "_GetLastError", return_value=0), \
             patch.object(icmp.socket, "if_nametoindex", return_value=15):
            self.assertTrue(icmp.ping_ipv6_winapi("fe80::1%7", count=1, timeout_ms=10).ok)
            self.assertTrue(icmp.ping_ipv6_winapi("fe80::1%Ethernet", count=1, timeout_ms=10).ok)
            self.assertTrue(icmp.ping_ipv6_winapi("::1", count=1, timeout_ms=10).ok)
            self.assertEqual(close.call_count, 3)
        self.assertEqual(scopes, [7, 15, 0])

    def test_unknown_interface_does_not_start_native_request(self):
        with patch.object(icmp, "_Icmp6CreateFile") as create, \
             patch.object(icmp, "_Icmp6SendEcho2", Mock()), \
             patch.object(icmp, "_IcmpCloseHandle", Mock()), \
             patch.object(icmp, "_GetLastError", Mock()), \
             patch.object(icmp.socket, "if_nametoindex", side_effect=OSError):
            result = icmp.ping_ipv6_winapi("fe80::1%missing", count=1, timeout_ms=10)
            self.assertEqual(result.error_code, "RESOLVE_ERR")
        create.assert_not_called()
