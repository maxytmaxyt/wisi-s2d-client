"""
stream_engine.py – Live-Streaming-Engine für Browser (mpegts.js) und VLC
========================================================================
Empfängt decodierte MPEG-TS-Pakete vom WISI Dongle über UDP, verteilt sie
gepuffert an aktive HTTP-Clients und leitet Chunks an die Aufnahme weiter.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import TYPE_CHECKING, Any

from models import ServiceEntry
from stream import stream

if TYPE_CHECKING:
    from ui.streamer import DongleManager

log = logging.getLogger("wisi.ui.stream_engine")


class StreamEngine:
    """Verwaltet den aktiven UDP-Empfang und die Verteilung an HTTP-Clients."""

    def __init__(self, manager: DongleManager) -> None:
        self.manager = manager
        self.active_service: ServiceEntry | None = None
        self.stream_stop_event = threading.Event()
        self.stream_thread: threading.Thread | None = None
        self.stream_clients: list[queue.Queue[bytes]] = []
        self.stream_clients_lock = threading.Lock()
        self.stream_stats: dict[str, Any] = {
            "is_streaming": False,
            "channel_name": "",
            "prog_idx": 0,
            "kbps": 0.0,
            "bytes": 0,
            "blocks": 0,
            "elapsed": 0.0,
        }

    def start_stream(self, prog_idx: int) -> bool:
        if not self.manager.tcp_sock:
            ok, _ = self.manager.connect()
            if not ok:
                return False

        svc = next((s for s in self.manager.services if s.prog_idx == prog_idx), None)
        if svc is None:
            svc = ServiceEntry(
                pat_index=0,
                prog_idx=prog_idx,
                service_id=0,
                name=f"Kanal 0x{prog_idx:08X}",
            )

        if (
            self.active_service
            and self.active_service.prog_idx == prog_idx
            and self.stream_thread
            and self.stream_thread.is_alive()
        ):
            return True

        self.stop_stream()

        self.active_service = svc
        self.stream_stop_event.clear()
        self.stream_stats = {
            "is_streaming": True,
            "channel_name": svc.name,
            "prog_idx": svc.prog_idx,
            "kbps": 0.0,
            "bytes": 0,
            "blocks": 0,
            "elapsed": 0.0,
        }

        self.stream_thread = threading.Thread(
            target=self._run_stream_worker,
            args=(svc,),
            daemon=True,
        )
        self.stream_thread.start()
        return True

    def stop_stream(self) -> None:
        self.stream_stop_event.set()
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=3.0)
            self.stream_thread = None

        self.active_service = None
        self.stream_stats["is_streaming"] = False

        if self.manager.recording_active:
            self.manager.stop_recording()

        with self.stream_clients_lock:
            for q in self.stream_clients:
                try:
                    q.put_nowait(b"")
                except Exception:
                    pass
            self.stream_clients.clear()

    def _run_stream_worker(self, svc: ServiceEntry) -> None:
        def on_chunk(chunk: bytes) -> None:
            with self.stream_clients_lock:
                for q in list(self.stream_clients):
                    try:
                        if q.qsize() > 50:
                            try:
                                q.get_nowait()
                            except queue.Empty:
                                pass
                        q.put_nowait(chunk)
                    except Exception:
                        pass

            self.manager.scheduler.write_chunk(chunk)

        def on_status(stats: dict[str, object]) -> None:
            self.stream_stats.update(stats)
            if "elapsed_seconds" in stats:
                self.stream_stats["elapsed"] = stats["elapsed_seconds"]
            self.stream_stats["is_streaming"] = True

        try:
            stream(
                tcp_sock=self.manager.tcp_sock,
                lock=self.manager.lock,
                svc=svc,
                output_path="",
                duration_s=0.0,
                keepalive_active=True,
                decrypt_after=False,
                stop_event=self.stream_stop_event,
                chunk_callback=on_chunk,
                status_callback=on_status,
                live_decrypt=True,
            )
        except Exception as e:
            log.error("Streaming-Thread-Fehler: %s", e)
        finally:
            self.stream_stats["is_streaming"] = False

    def subscribe_client(self) -> queue.Queue[bytes]:
        q: queue.Queue[bytes] = queue.Queue(maxsize=100)
        with self.stream_clients_lock:
            self.stream_clients.append(q)
        return q

    def unsubscribe_client(self, q: queue.Queue[bytes]) -> None:
        with self.stream_clients_lock:
            if q in self.stream_clients:
                self.stream_clients.remove(q)
