"""Probe TiViCon cloud endpoints (WMS, HWMS, CDMS, HDMS) for dongle updates.

Uses IPv4-only sockets and rate-limit-friendly pacing to test release/debug
updateTypes, older SW versions, and OEM customer IDs without triggering HTTP 429.
"""

from __future__ import annotations

import argparse
import json
import socket
import time
import urllib.error
import urllib.request

KEYS = {
    "primary": "NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB",
    "secondary": "QhC6rpwfYIe7TlMTNDnoArEkWy3vXlGRvjnoGjXiy7RIWBQBwpj4t9yGlPZ8",
}

DEFAULT_HOSTS = (
    "wms.tiviconsolutions.com",
    "hwms.tiviconsolutions.com",
)


def force_ipv4() -> None:
    """Filter getaddrinfo results to IPv4 addresses to avoid unreachable IPv6 routes."""
    orig = socket.getaddrinfo

    def _ipv4(*args, **kwargs):
        return [row for row in orig(*args, **kwargs) if row[0] == socket.AF_INET]

    socket.getaddrinfo = _ipv4


def request_json(method: str, url: str, api_key: str, payload: dict | None = None) -> tuple[int, str]:
    headers = {
        "User-Agent": "okhttp/4.9.0",
        "Accept": "application/json",
        "X-Api-Key": api_key,
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return resp.status, resp.read(1000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(1000).decode("utf-8", errors="replace")
    except Exception as exc:
        return -1, str(exc)


def probe_endpoints(delay: float) -> None:
    print("=== Protected / Auxiliary Endpoints ===")
    checks = [
        ("POST", "https://cdms.tiviconsolutions.com/api/updater/updates/fw", KEYS["primary"], {"dongle_customer_id": 6174, "dongle_sw_version": 1, "dongle_hw_type": "0"}),
        ("POST", "https://cdms.tiviconsolutions.com/api/updater/updates/fw", KEYS["secondary"], {"dongle_customer_id": 6174, "dongle_sw_version": 1, "dongle_hw_type": "0"}),
        ("POST", "https://hdms.tiviconsolutions.com/api/updater/updates/fw", KEYS["primary"], {"api_key": KEYS["primary"], "si_id": 6174}),
        ("POST", "https://hdms.tiviconsolutions.com/api/updater/updates/fw", KEYS["secondary"], {"api_key": KEYS["secondary"], "si_id": 6174}),
        ("GET", "https://wms.tiviconsolutions.com/api/channel-manager/version?dongle_chip_id=9000000035a2a52b", KEYS["primary"], None),
        ("GET", "https://wms.tiviconsolutions.com/api/bouquets/version?dongle_chip_id=9000000035a2a52b", KEYS["primary"], None),
        ("POST", "https://wms.tiviconsolutions.com/api/dongles/check-dongle", KEYS["primary"], {"dongle_chip_id": "9000000035a2a52b"}),
    ]
    for method, url, key, body in checks:
        code, resp = request_json(method, url, key, body)
        print(f"  [{method}] {url} -> {code} | {resp[:200]}")
        time.sleep(delay)


def sweep_updates(hosts: tuple[str, ...], cids: list[int | str], update_types: tuple[str, ...], delay: float) -> None:
    print(f"\n=== Sweeping {len(hosts)} hosts x {len(cids)} CIDs x {len(update_types)} updateTypes ===")
    hits: list[tuple[str, int | str, str, int, str]] = []
    total = 0
    for host in hosts:
        url = f"https://{host}/api/updater/updates/upd"
        for cid in cids:
            for utype in update_types:
                payload = {
                    "dongle_customer_id": cid,
                    "dongle_sw_version": "1",
                    "dongle_hw_type": "0",
                    "dongle_chip_id": "9000000035a2a52b",
                    "updateType": utype,
                }
                code, resp = request_json("POST", url, KEYS["primary"], payload)
                total += 1
                if code == 429:
                    time.sleep(5)
                    code, resp = request_json("POST", url, KEYS["primary"], payload)
                if code != 200 or "NO_UPDATE" not in resp:
                    hits.append((host, cid, utype, code, resp))
                    print(f"  [HIT] {host} cid={cid} updateType={utype} -> {code} | {resp[:200]}")
                time.sleep(delay)
    print(f"Finished: {total} requests, {len(hits)} non-NO_UPDATE responses.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=0.22, help="Delay between requests in seconds")
    parser.add_argument("--max-cid", type=int, default=260, help="Highest sequential CID to probe")
    args = parser.parse_args()

    force_ipv4()
    probe_endpoints(args.delay)

    cids: list[int | str] = list(range(0, args.max_cid + 1)) + [6174, "181E", "0000181E"]
    sweep_updates(DEFAULT_HOSTS, cids, ("release", "debug"), args.delay)


if __name__ == "__main__":
    main()
