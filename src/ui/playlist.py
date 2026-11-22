"""
playlist.py – M3U-Playlist-Generator für VLC, Kodi und IPTV-Clients
===================================================================
Generiert standardkonforme #EXTM3U Playlisten inklusive TVG-Tags
für TV- und Radiosender des WISI Dongles.
"""
from __future__ import annotations

from models import Channel, ServiceEntry


def generate_m3u_playlist(
    channels: list[Channel],
    services: list[ServiceEntry],
    base_url: str,
) -> str:
    """Erzeugt eine vollständige M3U8/M3U Playlist mit Streaming-URLs."""
    lines = ["#EXTM3U"]
    channels_to_export = channels or [
        Channel(
            prog_idx=s.prog_idx,
            service_id=s.service_id,
            ts_id=1,
            freq=11362,
            pol="H",
            sym=22000,
            lcn=s.pat_index,
            name=s.name,
            fta=not s.is_encrypted,
            ch_type="RD" if s.is_radio else "TV",
        )
        for s in services
    ]
    for ch in sorted(channels_to_export, key=lambda c: (c.lcn if c.lcn > 0 else 999999, c.name.lower())):
        tvg_id = f"wisi.{ch.service_id}"
        group = "Radio" if ch.is_radio else "Fernsehen"
        lines.append(
            f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{ch.name}" '
            f'tvg-chno="{ch.lcn}" group-title="{group}",{ch.name}'
        )
        lines.append(f"{base_url.rstrip('/')}/api/stream/{ch.prog_idx}")
    return "\n".join(lines) + "\n"
