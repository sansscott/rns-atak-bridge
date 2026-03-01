"""
cot_encoder.py — Convert an RNS peer dict to a CoT (Cursor-on-Target) XML event.

CoT is the wire protocol used by ATAK, iTAK, WinTAK, and TAK Server for
situational awareness (SA) tracks. Each event is a self-contained XML element.

References:
  MIL-STD-2525C    — symbology type codes
  ATAK CoT spec    — https://www.mitre.org/sites/default/files/pdf/09_4937.pdf
  Type "a-f-G-U-C" — Atom / Friendly / Ground / Unit / Combat
"""

import math
from datetime import datetime, timezone, timedelta

from lxml import etree


# CoT time format (ISO 8601 with milliseconds, Z suffix)
_COT_DT_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _cot_time(dt: datetime) -> str:
    return dt.strftime(_COT_DT_FMT)


def peer_to_cot(peer: dict, cfg: dict) -> bytes:
    """
    Build a CoT event XML for a single RNS peer.

    Args:
        peer: dict with keys: hash, hops, interface, lat, lon
        cfg:  full bridge config dict

    Returns:
        UTF-8 encoded CoT XML bytes, ready to send over UDP.
    """
    now = datetime.now(timezone.utc)
    stale_minutes = cfg["atak"].get("stale_minutes", 5)
    stale = now + timedelta(minutes=stale_minutes)
    prefix = cfg.get("callsign_prefix", "RNS-")

    dest_hash = peer["hash"]
    short_hash = dest_hash[:8]
    uid = f"{prefix}{short_hash}"
    callsign = uid

    lat = peer.get("lat", 0.0)
    lon = peer.get("lon", 0.0)
    hops = peer.get("hops", 0)
    iface = peer.get("interface", "unknown")

    # Root <event> element
    event = etree.Element("event")
    event.set("version", "2.0")
    event.set("uid", uid)
    event.set("type", "a-f-G-U-C")   # Friendly Ground Unit Combat
    event.set("time", _cot_time(now))
    event.set("start", _cot_time(now))
    event.set("stale", _cot_time(stale))
    event.set("how", "m-g")           # Machine-generated

    # <point> — location (CE/LE = circular/linear error in meters)
    point = etree.SubElement(event, "point")
    point.set("lat", f"{lat:.6f}")
    point.set("lon", f"{lon:.6f}")
    point.set("hae", "100")    # Height above ellipsoid (m) — unknown, use 100
    point.set("ce", "50")      # Circular error (m)
    point.set("le", "50")      # Linear error (m)

    # <detail> — human-readable metadata shown in ATAK info panel
    detail = etree.SubElement(event, "detail")

    contact = etree.SubElement(detail, "contact")
    contact.set("callsign", callsign)

    remarks = etree.SubElement(detail, "remarks")
    remarks.text = f"Reticulum | hash: {dest_hash[:16]}... | hops: {hops} | iface: {iface}"

    # Optional: __group for ATAK team color (blue = friendly)
    group = etree.SubElement(detail, "__group")
    group.set("name", "Blue")
    group.set("role", "Team Member")

    return etree.tostring(event, xml_declaration=True, encoding="UTF-8", pretty_print=False)


def local_node_cot(identity_hash: str, cfg: dict) -> bytes:
    """
    Build a CoT event for the local RNS node itself (hops=0, home coords).
    Useful so the bridge's own node appears in ATAK alongside remote peers.
    """
    home_lat = cfg["rns"]["home_lat"]
    home_lon = cfg["rns"]["home_lon"]

    peer = {
        "hash": identity_hash,
        "hops": 0,
        "interface": "local",
        "lat": home_lat,
        "lon": home_lon,
    }
    return peer_to_cot(peer, cfg)
