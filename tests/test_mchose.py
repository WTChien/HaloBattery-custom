"""Tests for the MCHOSE K7 V2 Ultra+ QHW battery exchange."""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers import mchose as P  # noqa: E402


def qhw_reply(level=99, charge=0, sequence=0, include_report_id=True):
    header = bytes([P.QHW_VERSION, P.QHW_FLAGS, 2, 0x04, 0x09, 0, sequence])
    body = header + bytes([charge, level])
    check = 0
    for byte in body[1:]:
        check ^= byte
    packet = (body + bytes([check])).ljust(P.QHW_PACKET_LEN, b"\x00")
    return (bytes([P.QHW_REPORT]) if include_report_id else b"") + packet


class FakeBus:
    def __init__(self):
        self.writes = []

    def device(self):
        bus = self

        class Device:
            def open_path(self, path):
                self.path = path

            def write(self, data):
                bus.writes.append((self.path, bytes(data)))
                return len(data)

            def read(self, length, timeout_ms=0):
                if self.path == b"qhw":
                    return list(qhw_reply())
                return []

            def close(self):
                pass

        return Device()


class QhwFrames(unittest.TestCase):
    def test_live_k7_v2_ultra_plus_capture(self):
        # 3837:1018 on its 2.4 GHz receiver; MCHOSE's web driver displayed 99%.
        captured = bytes.fromhex(
            "4d 01 01 02 04 09 00 00 00 63 6d 00 00 00 00 00 "
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
        )
        self.assertEqual(P.parse_qhw_battery(captured), (99, False))

    def test_request_is_the_official_0904_read(self):
        request = P.make_qhw_battery_request(0x2A)
        self.assertEqual(len(request), P.QHW_PACKET_LEN + 1)
        self.assertEqual(request[:8], bytes([0x4D, 1, 3, 0, 0x04, 0x09, 0, 0x2A]))
        self.assertEqual(request[8], 3 ^ 0x04 ^ 0x09 ^ 0x2A)

    def test_reply_with_or_without_report_id(self):
        self.assertEqual(P.parse_qhw_battery(qhw_reply(99, 0, include_report_id=True)),
                         (99, False))
        self.assertEqual(P.parse_qhw_battery(qhw_reply(42, 1, include_report_id=False)),
                         (42, True))
        self.assertEqual(P.parse_qhw_battery(qhw_reply(100, 2)), (100, False))

    def test_bad_frames_are_refused(self):
        self.assertIsNone(P.parse_qhw_battery(b""))
        self.assertIsNone(P.parse_qhw_battery(qhw_reply(101)))
        bad = bytearray(qhw_reply())
        bad[4] = 0x05
        self.assertIsNone(P.parse_qhw_battery(bad))


class QhwPolling(unittest.TestCase):
    def setUp(self):
        self.bus = FakeBus()
        self.old_hid, self.old_enumerate = P.hid, P.hidlist.enumerate
        P.hid = types.SimpleNamespace(device=self.bus.device)
        P.hidlist.enumerate = lambda vid: ([
            {"vendor_id": 0x3837, "product_id": 0x1018,
             "product_string": "MCHOSE K7 V2 Ultra+", "interface_number": 2,
             "usage_page": 0xFF01, "usage": 1, "path": b"silent"},
            {"vendor_id": 0x3837, "product_id": 0x1018,
             "product_string": "MCHOSE K7 V2 Ultra+", "interface_number": 2,
             "usage_page": 0xFF0B, "usage": 0x00C4, "path": b"qhw"},
        ] if vid == 0x3837 else [])

    def tearDown(self):
        P.hid, P.hidlist.enumerate = self.old_hid, self.old_enumerate

    def test_finds_the_answer_on_the_qhw_collection(self):
        result = P.MchoseProvider().poll()
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0].name, result[0].level, result[0].charging),
                         ("MCHOSE K7 V2 Ultra+", 99, False))
        self.assertTrue(all(frame[0] == P.QHW_REPORT for _, frame in self.bus.writes))
        self.assertFalse(any(frame[1] in (P.SHORT_REPORT, P.LONG_REPORT)
                             for _, frame in self.bus.writes))


if __name__ == "__main__":
    unittest.main()
