from __future__ import annotations

import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wisi_s2d.core import channels as wisi_channels
from wisi_s2d.core.decrypt import DEFAULT_TS_KEY, decrypt_ts_file, descramble_ts_block
from wisi_s2d.core.models import Channel, channel_to_service
from wisi_s2d.protocol import protocol as wisi_protocol
from wisi_s2d.core.scan import (
    parse_dongle_info_phase1,
    parse_dongle_info_phase2,
    parse_dongle_info_phase3,
)
from wisi_s2d.web.app import _HTML_PAGE, app
from wisi_s2d.web.streamer import DongleManager


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
        from wisi_s2d.web.streamer import RECORDINGS_DIR
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


class BugfixRegressionTests(unittest.TestCase):
    def test_ts_sync_wraparound_and_duplicate_seq_zero(self) -> None:
        from wisi_s2d.core.ts_sync import align_ts_packets
        from wisi_s2d.protocol import protocol

        ts_block = (b"\x47" + bytes(187)) * 256
        assert len(ts_block) == protocol.UDP_REQUEST_LEN

        def make_udp_pkt(seq: int) -> bytes:
            extra = bytearray(64)
            extra[12] = seq
            return ts_block + bytes(extra) + (b"USBS" + bytes(9))

        chunk1, seq1, retry1 = align_ts_packets(make_udp_pkt(255), 254)
        self.assertFalse(retry1)
        self.assertEqual(seq1, 255)
        self.assertEqual(len(chunk1), protocol.UDP_REQUEST_LEN)

        # Normal wraparound 255 -> 0
        chunk2, seq2, retry2 = align_ts_packets(make_udp_pkt(0), seq1)
        self.assertFalse(retry2)
        self.assertEqual(seq2, 0)

        # Duplicate seq=0 must be rejected
        chunk_dup, seq_dup, retry_dup = align_ts_packets(make_udp_pkt(0), seq2)
        self.assertTrue(retry_dup)
        self.assertEqual(seq_dup, 0)
        self.assertEqual(chunk_dup, b"")

        # Backward out-of-order seq=255 after seq=1 must be rejected
        chunk_old, seq_old, retry_old = align_ts_packets(make_udp_pkt(255), 1)
        self.assertTrue(retry_old)
        self.assertEqual(seq_old, 1)
        self.assertEqual(chunk_old, b"")

    def test_epg_mjd_date_normalization(self) -> None:
        from wisi_s2d.cli.epg import normalize_epg_date

        self.assertEqual(normalize_epg_date("61358"), "2026-11-14")
        self.assertEqual(normalize_epg_date("2026-11-14"), "2026-11-14")
        self.assertEqual(normalize_epg_date("12/10/2026"), "12/10/2026")

    def test_connection_connect_resolves_protocol_import(self) -> None:
        from unittest.mock import MagicMock, patch
        from wisi_s2d.protocol import connection

        fake_sock = MagicMock()
        fake_sock.recv.side_effect = [
            b"\xF6\x16\x01\xAA\xBB\xCC\xDD\xEE" + bytes(4) + b"USBS" + bytes(9),
            b"\xF6\x17\x01\x00" + b"USBS" + bytes(9),
        ]
        with patch.object(connection.socket, "socket", return_value=fake_sock):
            sock = connection.connect("192.168.178.32")
        self.assertIs(sock, fake_sock)

    def test_find_ffmpeg_does_not_return_windows_exe_on_posix(self) -> None:
        import os
        from wisi_s2d.web.transcoder import find_ffmpeg

        if os.name != "nt":
            found = find_ffmpeg()
            if found is not None:
                self.assertFalse(found.lower().endswith(".exe"))

    def test_scheduler_excludes_timeshift_from_list_recordings(self) -> None:
        from wisi_s2d.web.scheduler import RECORDINGS_DIR
        dm = DongleManager()
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        ts_buf = RECORDINGS_DIR / "_timeshift.ts"
        ts_buf.write_bytes(b"\x47" * 188)
        try:
            recs = dm.list_recordings()
            self.assertFalse(any(r["filename"] == "_timeshift.ts" for r in recs))
        finally:
            if ts_buf.exists():
                ts_buf.unlink()

    def test_web_api_endpoints_and_scan_params(self) -> None:
        import asyncio
        from unittest.mock import patch
        from starlette.requests import Request
        from wisi_s2d.web import api_record, api_stream, state
        from wisi_s2d.web.app import index as web_index

        def make_request(method: str = "GET", path: str = "/", body: bytes = b"") -> Request:
            scope = {
                "type": "http",
                "method": method,
                "path": path,
                "headers": [(b"content-type", b"application/json")],
                "query_string": b"",
            }

            async def receive() -> dict[str, object]:
                return {"type": "http.request", "body": body, "more_body": False}

            return Request(scope, receive)

        res_root = asyncio.run(web_index(make_request()))
        self.assertEqual(res_root.status_code, 200)
        self.assertIn("WISI OR S2D", res_root.body.decode("utf-8"))

        res_status = asyncio.run(api_stream.api_status(make_request(path="/api/status")))
        self.assertEqual(res_status.status_code, 200)
        status_json = json.loads(res_status.body.decode("utf-8"))
        self.assertIn("ffmpeg_available", status_json)
        self.assertIn("signal", status_json)

        with patch.object(state.manager, "start_scan", return_value=(True, "OK")) as mock_scan:
            res_scan = asyncio.run(
                api_record.api_tuner_scan_start(
                    make_request(
                        method="POST",
                        path="/api/tuner/scan/start",
                        body=json.dumps({"scan_type": 2, "search_range": 1, "network_scan": True}).encode(),
                    )
                )
            )
            self.assertEqual(res_scan.status_code, 200)
            mock_scan.assert_called_once_with(scan_type=2, network_scan=True, search_range=1)

        res_dec = asyncio.run(
            api_record.api_recordings_decrypt(
                make_request(
                    method="POST",
                    path="/api/recordings/decrypt",
                    body=json.dumps({"path": "/etc/passwd"}).encode(),
                )
            )
        )
        self.assertEqual(res_dec.status_code, 404)

    def test_discovery_dhcp_leases_and_auto_connect_flag(self) -> None:
        import tempfile
        from unittest.mock import patch
        from wisi_s2d.cli import discovery, ui

        with tempfile.TemporaryDirectory() as tmp:
            lease_file = Path(tmp) / "dnsmasq-enp1s0.leases"
            lease_file.write_text("1732700000 00:11:22:33:44:55 10.42.0.55 wisi-dongle *\n", encoding="utf-8")
            with patch.object(discovery, "Path", side_effect=lambda p: Path(tmp) if p == "/var/lib/NetworkManager" else Path(p)):
                ips = discovery._get_dhcp_lease_ips()
            self.assertIn("10.42.0.55", ips)

        with patch.object(ui, "run_ui") as mock_run_ui:
            rc = ui.main(["--no-browser", "--auto-connect", "--port", "8899"])
            self.assertEqual(rc, 0)
            mock_run_ui.assert_called_once_with(
                host="0.0.0.0",
                port=8899,
                dongle_ip="192.168.178.32",
                open_browser=False,
                auto_connect=True,
            )

    def test_transcoder_vaapi_and_cpu_fallback(self) -> None:
        from unittest.mock import patch
        from wisi_s2d.web import transcoder

        with (
            patch.object(transcoder, "find_vaapi_device", return_value="/dev/dri/renderD128"),
            patch.object(transcoder.subprocess, "Popen") as mock_popen,
        ):
            transcoder.start_ffmpeg_process("/usr/bin/ffmpeg")
            cmd = mock_popen.call_args[0][0]
            self.assertIn("h264_vaapi", cmd)
            self.assertIn("/dev/dri/renderD128", cmd)

        with (
            patch.object(transcoder, "find_vaapi_device", return_value=None),
            patch.object(transcoder.subprocess, "Popen") as mock_popen,
        ):
            transcoder.start_ffmpeg_process("/usr/bin/ffmpeg")
            cmd = mock_popen.call_args[0][0]
            self.assertIn("libx264", cmd)


if __name__ == "__main__":
    unittest.main()
