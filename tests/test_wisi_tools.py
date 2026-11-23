from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wisi_s2d.core import channels as wisi_channels_mod
from wisi_s2d.protocol import protocol as wisi_protocol
from wisi_s2d.core import stream as wisi_stream
import wisi_s2d.cli.client as wisi_client
import wisi_s2d.cli.epg as wisi_epg


class ProtocolFrameTests(unittest.TestCase):
    def test_command_builder_matches_31_byte_apix_request(self) -> None:
        request = wisi_client._cmd_16()

        self.assertEqual(len(request), 31)
        self.assertEqual(request[:8], b"USBC\xA0\xCB\x03\x37")
        self.assertEqual(struct.unpack_from(">I", request, 8)[0], 12)
        self.assertEqual(request[15:21], b"\xF6APIX\x16")

    def test_send_recv_consumes_13_byte_usbs_suffix(self) -> None:
        payload = b"response"
        suffix = b"USBS\xA0\xCB\x03\x37\x00\x00\x00\x00\x40"

        class ResponseSocket:
            def __init__(self) -> None:
                self.remaining = bytearray(payload + suffix)
                self.sent = b""

            def settimeout(self, timeout: float | None) -> None:
                pass

            def sendall(self, data: bytes) -> None:
                self.sent += data

            def recv(self, size: int) -> bytes:
                chunk = bytes(self.remaining[:size])
                del self.remaining[:size]
                return chunk

        response_socket = ResponseSocket()

        result = wisi_client._send_recv(response_socket, b"request", len(payload))

        self.assertEqual(result, payload)
        self.assertEqual(response_socket.remaining, b"")
        self.assertEqual(response_socket.sent, b"request")

    def test_prog_idx_commands_match_apk_and_pcap_offsets(self) -> None:
        prog_idx = 0x40DE0110
        prep = wisi_protocol.cmd_prepare(prog_idx)
        self.assertEqual(len(prep), 31)
        self.assertEqual(prep[15:21], b"\xF6APIX\x03")
        self.assertEqual(prep[21:25], b"\x00\x00\x00\x02")
        self.assertEqual(struct.unpack_from(">I", prep, 25)[0], prog_idx)

        epg_sz = wisi_protocol.cmd_epg_size(prog_idx)
        self.assertEqual(epg_sz[15:21], b"\xF6APIX\x30")
        self.assertEqual(epg_sz[21:25], b"\x00\x00\x00\x00")
        self.assertEqual(struct.unpack_from(">I", epg_sz, 25)[0], prog_idx)

        epg_dat = wisi_protocol.cmd_epg_data(prog_idx, 0, 1234)
        self.assertEqual(struct.unpack_from(">I", epg_dat, 8)[0], 1234)
        self.assertEqual(epg_dat[15:21], b"\xF6APIX\x31")
        self.assertEqual(struct.unpack_from(">I", epg_dat, 25)[0], prog_idx)

        evt_sz = wisi_protocol.cmd_evtdesc_size(prog_idx, 0x05CA)
        self.assertEqual(evt_sz[15:21], b"\xF6APIX\x35")
        self.assertEqual(evt_sz[21:23], b"\x00\x00")
        self.assertEqual(struct.unpack_from(">HI", evt_sz, 23), (0x05CA, prog_idx))

        rel = wisi_protocol.cmd_stream_release()
        self.assertEqual(len(rel), 35)
        self.assertEqual(struct.unpack_from(">I", rel, 8)[0], 4)
        self.assertEqual(rel[15:21], b"\xF8APIX\x07")
        self.assertEqual(rel[31:35], b"\x01\x00\x00\x00")

        ack = wisi_channels_mod._cmd_chlist_ack(250550)
        self.assertEqual(struct.unpack_from(">I", ack, 8)[0], 8)
        self.assertEqual(ack[15:21], b"\xF6APIX\x22")

        ts_ok = wisi_protocol.cmd_udp_ts_block(first=True)
        ts_retry = wisi_protocol.cmd_udp_ts_block(first=False)
        self.assertEqual(ts_ok[21], 0x00)
        self.assertEqual(ts_retry[21], 0x01)

    def test_epg_strips_2_byte_apix_response_prefix(self) -> None:
        svc = wisi_client.Channel(
            prog_idx=0x40DE0110,
            service_id=28800,
            ts_id=1,
            freq=12188,
            pol="H",
            sym=27500,
            lcn=1,
            name="RTL Austria",
            fta=True,
            ch_type="TV",
        )
        xml_body = (
            b"\xF6\x31<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            b"<epg_Data><ch prog_idx=\"40de0110\" name=\"RTL Austria\">"
            b"<evt id=\"1482\" date=\"12/10/2026\" time=\"20:15\" dur=\"01:00\" des=\"Testsendung\"/>"
            b"</ch></epg_Data>\n\x00\x00"
        )
        responses = [
            b"\xF6\x30" + struct.pack(">I", len(xml_body)),
            xml_body,
        ]
        with patch.object(wisi_protocol, "send_recv", side_effect=responses):
            events = wisi_epg._fetch_epg_for_service(object(), threading.Lock(), svc)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title"], "Testsendung")
        self.assertEqual(events[0]["event_id"], 1482)

    def test_descramble_ts_block_decrypts_aes_ecb_payload_and_clears_tsc_bit(self) -> None:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        clear_payload = b"\x00\x00\x01\xE0" + bytes(range(180))
        encryptor = Cipher(algorithms.AES(wisi_stream.DEFAULT_TS_KEY), modes.ECB()).encryptor()
        enc_len = (184 // 16) * 16
        encrypted_payload = (
            encryptor.update(clear_payload[:enc_len])
            + clear_payload[enc_len:]
        )
        scrambled_pkt = b"\x47\x40\xC9\x90" + encrypted_payload
        descrambled = wisi_stream.descramble_ts_block(scrambled_pkt)
        self.assertEqual(descrambled[:4], b"\x47\x40\xC9\x10")
        self.assertEqual(descrambled[4:], clear_payload)

        with tempfile.TemporaryDirectory() as folder:
            ts_path = Path(folder) / "sample.ts"
            ts_path.write_bytes(scrambled_pkt * 2)
            out_path = wisi_stream.decrypt_ts_file(ts_path)
            self.assertEqual(out_path, ts_path)
            self.assertEqual(ts_path.read_bytes(), (b"\x47\x40\xC9\x10" + clear_payload) * 2)

    def test_0x48_radio_channels_are_not_misclassified_as_encrypted(self) -> None:
        from wisi_s2d.core.models import Channel, channel_to_service

        fta_radio = Channel(
            prog_idx=0x48C000A5,
            service_id=28400,
            ts_id=1093,
            freq=12266,
            pol="H",
            sym=27500,
            lcn=491,
            name="hr1",
            fta=True,
            ch_type="RD",
        )
        self.assertTrue(fta_radio.is_radio)
        self.assertFalse(fta_radio.is_encrypted)
        svc_radio = channel_to_service(fta_radio, 490)
        self.assertTrue(svc_radio.is_radio)
        self.assertFalse(svc_radio.is_encrypted)

        pay_tv = Channel(
            prog_idx=0x40DE0110,
            service_id=28800,
            ts_id=1089,
            freq=12188,
            pol="H",
            sym=27500,
            lcn=4,
            name="RTL HD",
            fta=False,
            ch_type="TV",
        )
        self.assertFalse(pay_tv.is_radio)
        self.assertTrue(pay_tv.is_encrypted)
        svc_pay = channel_to_service(pay_tv, 3)
        self.assertTrue(svc_pay.is_encrypted)

    def test_dvbs2_scan_and_sac_builders_match_apk_specifications(self) -> None:
        lnb = wisi_protocol.cmd_dvbs2_lnb_set(9750, 10600, 11700, 0, 0)
        self.assertEqual(lnb[15:21], b"\xF6APIX\x07")
        self.assertEqual(struct.unpack_from(">HHHBHB", lnb, 21), (9750, 10600, 11700, 0, 0, 0))

        diseqc = wisi_protocol.cmd_dvbs2_diseqc_set(1, 2, 192, 130, 0, 0)
        self.assertEqual(diseqc[15:21], b"\xF6APIX\x08")
        self.assertEqual(struct.unpack_from(">BBHHHH", diseqc, 21), (1, 2, 192, 130, 0, 0))

        sat = wisi_protocol.cmd_dvbs2_satellite_set(192, west=False, pol="AUTO", khz_22="AUTO")
        self.assertEqual(sat[15:21], b"\xF6APIX\x09")
        self.assertEqual(sat[21:24], b"\x00\xC0\x04")

        tune = wisi_protocol.cmd_dvbs2_tuner_set(
            freq_khz=11362, sr_khz=22000, pol="H", sat_lon_tenths=192, west=False, khz_22="AUTO"
        )
        self.assertEqual(struct.unpack_from(">I", tune, 8)[0], 32)
        self.assertEqual(tune[15:21], b"\xF6APIX\x01")
        self.assertEqual(tune[21], 0x14)  # 0x04 (DVBS2) | 0x10 (H/18V)
        self.assertEqual(struct.unpack_from(">HH", tune, 22), (192, 22000))
        self.assertEqual(tune[26:29], struct.pack(">I", 11362)[1:])

        scan = wisi_protocol.cmd_scan_start_stop(
            scan_type=wisi_protocol.SCAN_MANUAL,
            network_scan=True,
            order_by=1,
            search_range=1,
            sort_mode=0,
        )
        self.assertEqual(scan[15:21], b"\xF6APIX\x10")
        self.assertEqual(scan[21], 0x00)
        self.assertEqual(scan[22], 1 | (1 << 1) | (1 << 3))

        raw_status = bytes([
            0xF6, 0x02,
            0x01,  # lock=1, tune_fail=0
            84,    # agc
            92,    # snr
            0x01,  # scan_in_progress
            65,    # progress 65%
            0x00, 0x2C, 0x62,  # freq = 11362
            0x55, 0xF0,        # sr = 22000
            0x04,              # mode = DVBS2
            0x01, 0xEC,        # tv_count = 492
            0x00, 0x9D,        # radio_count = 157
        ])
        st = wisi_protocol.parse_tuner_scan_status(raw_status)
        self.assertTrue(st.lock)
        self.assertFalse(st.tune_fail)
        self.assertEqual((st.agc, st.snr, st.progress), (84, 92, 65))
        self.assertTrue(st.scan_in_progress)
        self.assertEqual((st.freq, st.symbol_rate, st.tv_count, st.radio_count), (11362, 22000, 492, 157))

        info1 = wisi_protocol.cmd_dongle_info_phase1()
        info2 = wisi_protocol.cmd_dongle_info_phase2()
        info3 = wisi_protocol.cmd_dongle_info_phase3()
        self.assertEqual((info1[15:21], struct.unpack_from(">I", info1, 8)[0]), (b"\xFAAPIX\x00", 64))
        self.assertEqual((info2[15:21], struct.unpack_from(">I", info2, 8)[0]), (b"\xFAAPIX\x07", 51))
        self.assertEqual((info3[15:21], struct.unpack_from(">I", info3, 8)[0]), (b"\xFAAPIX\x08", 480))

        sac_w = wisi_protocol.cmd_sac_write(b"\xAA\xBB\xCC\xDD", sac_embedded=True)
        self.assertEqual(len(sac_w), 35)
        self.assertEqual(sac_w[15:22], b"\xFAAPIX\x03\x01")
        self.assertEqual(sac_w[31:], b"\xAA\xBB\xCC\xDD")
        self.assertEqual(wisi_protocol.SAC_ROOT_SEED, b"LukeRanDolphCI+1")


if __name__ == "__main__":
    unittest.main()
