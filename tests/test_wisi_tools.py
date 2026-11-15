from __future__ import annotations

import json
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import channels as wisi_channels_mod
import protocol as wisi_protocol
import stream as wisi_stream
import wisi.client as wisi_client
import wisi.common as wisi_common
import wisi.epg as wisi_epg
from wisi.discovery import DISCOVERY_REQUEST, MAGIC, VERSION, build_request, parse_response
from wisi.pcap import analyze, run_service_db


def _f9_0a_reply() -> bytes:
    return b"\xF9\x0A" + bytes(26 + 32 + 128)


def _ethernet_ipv4_udp(payload: bytes, source_port: int, destination_port: int) -> bytes:
    udp = struct.pack(">HHHH", source_port, destination_port, len(payload) + 8, 0) + payload
    ip_length = len(udp) + 20
    ip = (
        b"\x45\x00"
        + struct.pack(">H", ip_length)
        + b"\x00\x01\x00\x00\x40\x11\x00\x00"
        + bytes((192, 168, 178, 10, 192, 168, 178, 32))
    )
    ethernet = bytes(12) + b"\x08\x00"
    return ethernet + ip + udp


def _write_pcap(path: Path, frames: list[bytes]) -> None:
    with path.open("wb") as capture:
        capture.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for frame in frames:
            capture.write(struct.pack("<IIII", 0, 0, len(frame), len(frame)))
            capture.write(frame)


class DiscoveryTests(unittest.TestCase):
    def test_request_and_response(self) -> None:
        request = build_request(123)
        magic, version, opcode, sequence, payload_length = struct.unpack_from(">IHHII", request)
        self.assertEqual(
            (magic, version, opcode, sequence),
            (MAGIC, VERSION, DISCOVERY_REQUEST, 123),
        )
        self.assertEqual(payload_length, len(request) - 16)
        self.assertEqual(json.loads(request[16:])["cmd"], "DISCOVER_DONGLE")

        body = b'{"status":"OK"}'
        response = struct.pack(">IHHII", MAGIC, VERSION, DISCOVERY_REQUEST, 123, len(body)) + body
        self.assertEqual(parse_response(response), {"status": "OK"})
        self.assertIsNone(parse_response(response[:-1]))


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


class PcapTests(unittest.TestCase):
    def test_counts_only_f9_0a_replies_from_dongle(self) -> None:
        command = b"USBC" + bytes(4) + struct.pack(">I", 0) + bytes((0x80, 0, 16))
        command += bytes((0xF9,)) + b"APIX" + bytes((0x0A,)) + bytes(10)
        request_payload = b"\xF9\x0A" + bytes(29)
        reply = _f9_0a_reply()
        frames = [
            _ethernet_ipv4_udp(command, 40000, 8800),
            _ethernet_ipv4_udp(request_payload, 40000, 8800),
            _ethernet_ipv4_udp(reply, 8800, 40000),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "capture.pcap"
            _write_pcap(path, frames)
            result = analyze(path)

        self.assertEqual(result["apiX_commands"].get("0xF9/0x0A"), 1)
        self.assertEqual(result["f9_0a_device_replies"], 1)
        self.assertEqual(result["largest_f9_0a_device_reply_bytes"], len(reply))

    def test_legacy_f9_0a_service_db_decode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "speedtest"):
            run_service_db("unused.bin")


class ServiceDatabaseTests(unittest.TestCase):
    def test_load_services_fetches_tcp_channel_list_and_closes_resources(self) -> None:
        events: list[str] = []
        control = object()

        class KeepaliveThread:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            def start(self) -> None:
                events.append("keepalive")

            def join(self, timeout: float) -> None:
                events.append("join")

        def fake_connect(ip: str) -> object:
            events.append("tcp")
            return control, b"\x12\x34"

        def fake_fetch(
            sock: object, lock: object, session_token: bytes, timeout: float
        ) -> list[wisi_client.Channel]:
            events.append("channels")
            return [wisi_client.Channel(
                prog_idx=0x40B40089,
                service_id=4914,
                ts_id=33079,
                freq=10744,
                pol="H",
                sym=22000,
                lcn=1,
                name="Testkanal",
                fta=True,
                ch_type="TV",
            )]

        with (
            patch.object(wisi_common, "connect", side_effect=fake_connect),
            patch.object(
                wisi_common, "disconnect", side_effect=lambda sock: events.append("close-tcp")
            ),
            patch.object(wisi_common, "fetch_channel_list", side_effect=fake_fetch),
            patch.object(wisi_common.threading, "Thread", KeepaliveThread),
        ):
            services = wisi_common.load_services("192.168.178.32")

        self.assertEqual(events, ["tcp", "keepalive", "channels", "join", "close-tcp"])
        self.assertEqual(len(services), 1)
        self.assertEqual(services[0].name, "Testkanal")

    def test_legacy_service_db_fetch_is_disabled(self) -> None:
        udp = MagicMock()

        services = wisi_client.fetch_service_db(udp, "192.168.178.32")

        self.assertEqual(services, [])
        udp.sendto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
