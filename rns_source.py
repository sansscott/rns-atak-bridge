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

Note on first-poll latency (native mode):
  RNS populates its path table by receiving announces from peers. After startup
  it may take 30–120 seconds before remote peers appear. The first poll often
  returns 0 peers — this is normal. Subsequent polls fill in as announces arrive.
"""

import logging
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

_rns_initialized = False
_rns_instance = None

# How long to wait after RNS init before the first path-table read.
# Announcements take time to arrive; 15s catches the first wave on a busy network.
# Subsequent polls (every poll_interval_sec) will see more peers as they announce.
_RNS_INIT_WAIT_SEC = 15


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

    os.makedirs(config_dir, exist_ok=True)

    # Write a minimal RNS config that connects to the target rnsd TCP server.
    # share_instance=No so we don't interfere with a running system rnsd.
    # enable_transport=No: we are a client, not a relay node.
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

    log.info(f"Initializing RNS — peering with {peer_host}:{peer_port}")
    _rns_instance = RNS.Reticulum(configdir=config_dir)
    _rns_initialized = True

    # Wait for announces to arrive and populate the path table.
    # 15 seconds catches the first wave; subsequent polls see more peers.
    log.info(f"Waiting {_RNS_INIT_WAIT_SEC}s for path table to populate (normal on first start)...")
    for i in range(_RNS_INIT_WAIT_SEC):
        time.sleep(1)
        n = len(RNS.Transport.path_table)
        if n > 0 and i >= 4:
            # Have at least some peers and waited at least 5s — good enough
            log.info(f"Path table has {n} entries after {i+1}s — starting")
            return

    n = len(RNS.Transport.path_table)
    log.info(f"RNS ready — {n} path table entries (more will arrive on subsequent polls)")


def get_peers_native(cfg: dict) -> list[dict]:
    """Return peers from RNS path table via native RNS library."""
    import RNS

    peer_host = cfg["rns"]["peer_host"]
    peer_port = cfg["rns"]["peer_port"]
    home_lat = cfg["rns"]["home_lat"]
    home_lon = cfg["rns"]["home_lon"]

    _init_native_rns(peer_host, peer_port)

    # path_table: {hash_bytes: [timestamp, next_hop, hops, expires, blobs, interface_obj, pkt_hash]}
    # Indices confirmed against RNS Transport.py constants:
    #   IDX_PT_HOPS=2, IDX_PT_RVCD_IF=5
    path_table = RNS.Transport.path_table

    if not path_table:
        log.info("[native] Path table empty — peers not yet announced. Will retry next poll.")
        return []

    peers = []
    for dest_hash_bytes, entry in path_table.items():
        try:
            dest_hash = dest_hash_bytes.hex()
            hops = entry[2] if len(entry) > 2 else 0
            iface_obj = entry[5] if len(entry) > 5 else None
            iface_name = str(iface_obj.name) if iface_obj and hasattr(iface_obj, "name") else "unknown"

            peers.append({
                "hash": dest_hash,
                "hops": hops,
                "interface": iface_name,
                "lat": home_lat,
                "lon": home_lon,
            })
        except Exception as e:
            log.warning(f"Skipping malformed path_table entry: {e}")

    log.info(f"[native] {len(peers)} peers in path table")
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

        log.info(f"[rest] {len(peers)} peers from {base_url}/paths")

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
    """
    Return the local node identity hash for including self as a track in ATAK.

    Native mode: reads node_identity from config.yaml (recommended — set this to
    your rnsd transport identity, found via `rnstatus`). Falls back to the bridge's
    own RNS instance identity, which may be None if transport is disabled.

    REST mode: queries /status on the reticulum-mcp API.
    """
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
        # Prefer config-supplied identity — always works, no RNS init required.
        # Set node_identity in config.yaml to your rnsd identity hash (run `rnstatus`).
        identity_hash = cfg["rns"].get("node_identity")
        if identity_hash and identity_hash.strip():
            log.debug(f"Using config-supplied node identity: {identity_hash[:16]}...")
            return identity_hash.strip()

        # Fallback: bridge's own RNS instance identity.
        # May be None when enable_transport=No (common case).
        try:
            import RNS
            if _rns_initialized and RNS.Transport.identity:
                return RNS.Transport.identity.hash.hex()
        except Exception:
            pass

        log.debug("No local identity available — self-track disabled. Set node_identity in config.yaml to enable.")
        return None


def get_peers(cfg: dict) -> list[dict]:
    """Dispatch to native or REST mode based on config."""
    mode = cfg["rns"].get("mode", "native")
    if mode == "rest":
        return get_peers_rest(cfg)
    return get_peers_native(cfg)
