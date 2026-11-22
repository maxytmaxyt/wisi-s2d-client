from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import channels as wisi_channels
from decrypt import DEFAULT_TS_KEY, decrypt_ts_file, descramble_ts_block
from models import Channel, channel_to_service
import protocol as wisi_protocol
from scan import (
    parse_dongle_info_phase1,
    parse_dongle_info_phase2,
    parse_dongle_info_phase3,
)
from ui.app import _HTML_PAGE, app
from ui.streamer import DongleManager


class ChannelParsingFixTests(unittest.TestCase):
    def test_hex_prog_idx_without_prefix(self) -> None:
        xml = b'<ch_List><ch prog_idx="40de0110" s_id="28800" ts_id="1" freq="12188" pol="H" sym="27500" lcn="4" s_name="RTL Austria" fta="1" type="TV" /></ch_List>'
        chs = wisi_channels.parse_chlist_xml(xml)
        self.assertEqual(len(chs), 1)
        ch = chs[0]
        self.assertEqual(ch.prog_idx, 0x40DE0110)
        self.assertEqual(ch.service_id, 28800)
        self.assertEqual(ch.name, "RTL Austria")
        self.assertTrue(ch.fta)
        self.assertFalse(ch.is_radio)
        self.assertFalse(ch.is_encrypted)

    def test_hex_prog_idx_with_prefix(self) -> None:
        xml = b'<ch_List><ch prog_idx="0x48C000A5" s_id="28400" ts_id="1093" freq="12266" pol="H" sym="27500" lcn="491" s_name="hr1" fta="1" type="RD" /></ch_List>'
        chs = wisi_channels.parse_chlist_xml(xml)
        self.assertEqual(len(chs), 1)
        ch = chs[0]
        self.assertEqual(ch.prog_idx, 0x48C000A5)
        self.assertTrue(ch.is_radio)
        self.assertFalse(ch.is_encrypted)

    def test_decimal_prog_idx(self) -> None:
        # 1083375616 = 0x40920000
        xml = b'<ch_List><ch prog_idx="1083375616" s_id="28721" ts_id="1051" freq="10744" pol="H" sym="22000" lcn="69" s_name="tagesschau24" fta="1" type="TV" /></ch_List>'
        chs = wisi_channels.parse_chlist_xml(xml)
        self.assertEqual(len(chs), 1)
        self.assertEqual(chs[0].prog_idx, 1083375616)
        self.assertEqual(chs[0].name, "tagesschau24")

    def test_html_entities_and_unclosed_tags(self) -> None:
        xml = b'<ch_List><ch prog_idx="40d600de" s_id="20002" ts_id="1" freq="12051" pol="V" sym="27500" lcn="5" s_name="ProSieben &amp; SAT.1" fta="1" type="TV"></ch></ch_List>'
        chs = wisi_channels.parse_chlist_xml(xml)
        self.assertEqual(len(chs), 1)
        self.assertEqual(chs[0].name, "ProSieben & SAT.1")

    def test_channel_to_service_preserves_channel(self) -> None:
        ch = Channel(
            prog_idx=0x40B7008F,
            service_id=11110,
            ts_id=1010,
            freq=11362,
            pol="H",
            sym=22000,
            lcn=1,
            name="ZDF HD",
            fta=True,
            ch_type="TV",
        )
        svc = channel_to_service(ch, 0)
        self.assertEqual(svc.prog_idx, 0x40B7008F)
        self.assertEqual(svc.service_id, 11110)
        self.assertIsNotNone(svc.channel)
        self.assertEqual(svc.channel.freq, 11362)
        self.assertEqual(svc.channel.pol, "H")


class DongleInfoParserTests(unittest.TestCase):
    def test_parse_dongle_info_phase1(self) -> None:
        payload = bytearray(64)
        payload[0] = 0xFA
        payload[1] = 0x00
        payload[2] = 26  # DVB-S2
        struct.pack_into(">H", payload, 3, 0x0102)
        struct.pack_into(">H", payload, 5, 0x0201)
        struct.pack_into(">H", payload, 7, 0x0304)
        payload[9] = 5
        payload[30] = 0x02
        payload[31] = 0x01
        payload[12:20] = b"\x01\x02\x03\x04\x05\x06\x07\x08"

        info = parse_dongle_info_phase1(bytes(payload))
        self.assertEqual(info["tuner_type"], 26)
        self.assertEqual(info["tuner_name"], "DVB-S2")
        self.assertEqual(info["customer_id"], 0x0102)
        self.assertEqual(info["hw_version"], 0x0201)
        self.assertEqual(info["sw_version"], 0x0304)
        self.assertEqual(info["loader_version"], 5)
        self.assertEqual(info["usb_proto_ver"], 2)
        self.assertTrue(info["has_phase2"])
        self.assertEqual(info["chip_id"], "0102030405060708")

    def test_parse_dongle_info_phase2(self) -> None:
        payload = bytearray(51)
        payload[0] = 0xFA
        payload[1] = 0x07
        model = b"TC711CXD"
        payload[3 : 3 + len(model)] = model
        struct.pack_into(">I", payload, 35, 14280)

        info = parse_dongle_info_phase2(bytes(payload))
        self.assertEqual(info["model_name"], "TC711CXD")
        self.assertEqual(info["svn_revision"], 14280)

    def test_parse_dongle_info_phase3(self) -> None:
        payload = bytearray(480)
        payload[0] = 0xFA
        payload[1] = 0x08
        payload[2:8] = bytes((0x00, 0x11, 0x22, 0x33, 0x44, 0x55))
        payload[8:12] = bytes((192, 168, 178, 32))
        payload[12:16] = bytes((192, 168, 178, 10))
        payload[19] = 1
        payload[21] = 1
        payload[24] = 1

        info = parse_dongle_info_phase3(bytes(payload))
        self.assertEqual(info["dongle_mac"], "00:11:22:33:44:55")
        self.assertEqual(info["dongle_ip"], "192.168.178.32")
        self.assertEqual(info["client_ip"], "192.168.178.10")
        self.assertEqual(info["clear_fta_stream"], 1)


class DongleManagerTests(unittest.TestCase):
    def test_manager_initialization_and_cached_epg(self) -> None:
        dm = DongleManager()
        self.assertFalse(dm.is_connected())
        self.assertGreater(len(dm.channels), 0)
        self.assertGreater(len(dm.epg_data), 0)
        info = dm.get_dongle_info()
        self.assertIsInstance(info, dict)
        self.assertEqual(info.get("model_name"), "WISI OR S2D")

    def test_generate_m3u(self) -> None:
        dm = DongleManager()
        m3u = dm.generate_m3u("http://127.0.0.1:8888")
        self.assertTrue(m3u.startswith("#EXTM3U"))
        self.assertIn("http://127.0.0.1:8888/api/stream/", m3u)
        self.assertIn("ZDF HD", m3u)

    def test_recordings_list(self) -> None:
        dm = DongleManager()
        recs = dm.list_recordings()
        self.assertIsInstance(recs, list)

    def test_timers_crud(self) -> None:
        dm = DongleManager()
        ok, msg, entry = dm.add_timer(
            prog_idx=0x40B7008F,
            title="Test Tagesschau",
            start_time=1800000000.0,
            duration_minutes=15,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.title, "Test Tagesschau")
        self.assertEqual(entry.duration_minutes, 15)

        timers = dm.list_timers()
        found = any(t["id"] == entry.id for t in timers)
        self.assertTrue(found)

        ok_del, _ = dm.delete_timer(entry.id)
        self.assertTrue(ok_del)
        timers_after = dm.list_timers()
        self.assertFalse(any(t["id"] == entry.id for t in timers_after))

    def test_delete_recording(self) -> None:
        dm = DongleManager()
        from ui.streamer import RECORDINGS_DIR
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        test_file = RECORDINGS_DIR / "test_temp_recording.ts"
        test_file.write_bytes(b"\x47" * 188)
        self.assertTrue(test_file.is_file())

        ok, _ = dm.delete_recording("test_temp_recording.ts")
        self.assertTrue(ok)
        self.assertFalse(test_file.is_file())

    def test_stream_engine_subscribe_unsubscribe(self) -> None:
        dm = DongleManager()
        q = dm.engine.subscribe_client()
        self.assertIn(q, dm.engine.stream_clients)
        dm.engine.unsubscribe_client(q)
        self.assertNotIn(q, dm.engine.stream_clients)


class WebAppStructureTests(unittest.TestCase):
    def test_html_page_contains_ui_components(self) -> None:
        self.assertIn("WISI OR S2D", _HTML_PAGE)
        self.assertIn("videoElement", _HTML_PAGE)
        self.assertIn("mpegts.min.js", _HTML_PAGE)
        self.assertIn("gaugeAgc", _HTML_PAGE)
        self.assertIn("gaugeSnr", _HTML_PAGE)
        self.assertIn("tab-tv", _HTML_PAGE)
        self.assertIn("tab-epg", _HTML_PAGE)
        self.assertIn("tab-tuner", _HTML_PAGE)
        self.assertIn("tab-recordings", _HTML_PAGE)
        self.assertIn("timerChannelSelect", _HTML_PAGE)
        self.assertIn("timersList", _HTML_PAGE)
        self.assertIn("tab-info", _HTML_PAGE)
        self.assertNotIn("tab-tools", _HTML_PAGE)

    def test_app_routes_registered(self) -> None:
        paths = [route.path for route in app.routes if hasattr(route, "path")]
        self.assertIn("/", paths)
        self.assertIn("/playlist.m3u", paths)
        self.assertIn("/api/status", paths)
        self.assertIn("/api/channels", paths)
        self.assertIn("/api/stream/{prog_idx}", paths)
        self.assertIn("/api/recordings", paths)
        self.assertIn("/api/timers", paths)
        self.assertIn("/api/tuner/tune", paths)
        self.assertIn("/api/tuner/scan/start", paths)


if __name__ == "__main__":
    unittest.main()
