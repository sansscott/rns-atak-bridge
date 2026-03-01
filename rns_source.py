"""
rns_source.py — Reticulum peer data source

Two modes:
  native: Peers directly with an rnsd TCP server using the RNS Python library.
          More robust; works even if reticulum-mcp is down.
  rest:   Polls the reticulum-mcp HTTP REST API.
          Simpler; requires a running reticulum-mcp instance.

Both modes return a list of RNSPeer dicts:
  {
    "hash":      str,   # destination hash (full hex, e.g. "af60a4f4...")
    "hops":      int,   # hop count from path table (0 = direct)
    "interface": str,   # interface name or "unknown"
    "lat":       float, # GPS lat if available, else home_lat from config
    "lon":       float, # GPS lon if available, else home_lon from config
  }
"""

import logging
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

_rns_initialized = False
_rns_instance = None


# ---------------------------------------------------------------------------
# Native RNS mode
# ---------------------------------------------------------------------------

def _init_native_rns(peer_host: str, peer_port: int, config_dir: str = "/tmp/rns-atak-bridge"):
    """Initialize RNS and peer with the configured TCP server. Called once."""
    global _rns_initialized, _rns_instance
    if _rns_initialized:
        return

    import RNS
    import os
    import configparser

    os.makedirs(config_dir, exist_ok=True)

    # Write a minimal RNS config that connects to the target rnsd TCP server
    rns_config_path = os.path.join(config_dir, "config")
    config_content = f"""[main]
  share_instance = No
  enable_transport = No

[interfaces]

  [[TCPClientInterface]]
    type = TCPClientInterface
    interface_enabled = True
    target_host = {peer_host}
    target_port = {peer_port}
"""
    with open(rns_config_path, "w") as f:
        f.write(config_content)

    log.info(f"Initializing RNS, peering with {peer_host}:{peer_port}")
    _rns_instance = RNS.Reticulum(configdir=config_dir)
    _rns_initialized = True

    # Allow a moment for initial path table population
    time.sleep(2)
    log.info("RNS initialized")


def get_peers_native(cfg: dict) -> list[dict]:
    """Return peers from RNS path table via native RNS library."""
    import RNS

    peer_host = cfg["rns"]["peer_host"]
    peer_port = cfg["rns"]["peer_port"]
    home_lat = cfg["rns"]["home_lat"]
    home_lon = cfg["rns"]["home_lon"]

    _init_native_rns(peer_host, peer_port)

    try:
        path_table = RNS.Transport.get_path_table()
    except Exception as e:
        log.error(f"Failed to read RNS path table: {e}")
        return []

    peers = []
    for entry in path_table:
        # entry keys: hash (bytes or hex str), hops (int), expires (float), interface (str|None)
        dest_hash = entry.get("hash")
        if isinstance(dest_hash, bytes):
            dest_hash = dest_hash.hex()

        peers.append({
            "hash": dest_hash,
            "hops": entry.get("hops", 0),
            "interface": entry.get("interface") or "unknown",
            "lat": home_lat,
            "lon": home_lon,
        })

    log.info(f"[native] Found {len(peers)} peers in path table")
    return peers


# ---------------------------------------------------------------------------
# REST mode
# ---------------------------------------------------------------------------

def get_peers_rest(cfg: dict) -> list[dict]:
    """Return peers from the reticulum-mcp REST API."""
    base_url = cfg["rns"]["rest_url"].rstrip("/")
    home_lat = cfg["rns"]["home_lat"]
    home_lon = cfg["rns"]["home_lon"]
    timeout = 10

    peers = []
    try:
        resp = requests.get(f"{base_url}/paths", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        # Response: {"result": {"paths": [{destination_hash, next_hop, hops}], "count": N}}
        result = data.get("result", data)
        path_list = result.get("paths", [])

        for entry in path_list:
            dest_hash = entry.get("destination_hash") or entry.get("hash", "")
            if not dest_hash:
                continue
            peers.append({
                "hash": dest_hash,
                "hops": entry.get("hops", 0),
                "interface": entry.get("interface") or entry.get("next_hop") or "unknown",
                "lat": home_lat,
                "lon": home_lon,
            })

        log.info(f"[rest] Found {len(peers)} peers from {base_url}/paths")

    except requests.exceptions.ConnectionError:
        log.error(f"[rest] Cannot connect to reticulum-mcp at {base_url}")
    except requests.exceptions.Timeout:
        log.error(f"[rest] Timeout connecting to {base_url}")
    except Exception as e:
        log.error(f"[rest] Unexpected error: {e}")

    return peers


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_local_identity(cfg: dict) -> Optional[str]:
    """Return the local node's identity hash (for including self as a track)."""
    mode = cfg["rns"].get("mode", "native")
    if mode == "rest":
        try:
            base_url = cfg["rns"]["rest_url"].rstrip("/")
            resp = requests.get(f"{base_url}/status", timeout=5)
            resp.raise_for_status()
            result = resp.json().get("result", {})
            return result.get("transport_identity")
        except Exception as e:
            log.warning(f"Could not fetch local identity via REST: {e}")
            return None
    else:
        try:
            import RNS
            if _rns_initialized and _rns_instance:
                return RNS.prettyhex(RNS.Identity.full_hash(
                    _rns_instance.get_identity().get_public_key()
                ))[:32]
        except Exception:
            pass
        return None


def get_peers(cfg: dict) -> list[dict]:
    """Dispatch to native or REST mode based on config."""
    mode = cfg["rns"].get("mode", "native")
    if mode == "rest":
        return get_peers_rest(cfg)
    return get_peers_native(cfg)
