# rns-atak-bridge

**The first public Reticulum → ATAK integration.**

A lightweight Python bridge that makes [Reticulum Network Stack](https://reticulum.network) mesh peers visible as live Situational Awareness (SA) tracks in [ATAK](https://tak.gov), iTAK, WinTAK, and TAK Server — without any ATAK plugins, SDKs, or accounts.

```
Reticulum mesh ──► bridge.py ──► CoT XML ──► UDP multicast ──► iTAK / ATAK / WinTAK
  (path table)                   (lxml)       239.2.3.1:6969
```

Every Reticulum peer in the path table becomes a blue SA track. When the bridge stops, tracks expire automatically.

---

## Why This Exists

[Reticulum](https://reticulum.network) is an encrypted, infrastructure-free networking stack that runs over LoRa, packet radio, WiFi, and TCP. It has no central servers, no accounts, and works in denied/degraded environments.

[ATAK](https://tak.gov) is the standard tactical awareness platform used by military, emergency management, SAR, and field teams globally. It has a rich ecosystem but is closed off from external networks.

This bridge connects them: Reticulum mesh peers appear as tracks on ATAK's map, giving mesh operators real-time situational awareness of who is on the network and (if GPS is available) where they are.

---

## Features

- Polls the Reticulum path table every N seconds
- Emits one CoT event per peer — stable UID, blue friendly icon, hop count in remarks
- UDP multicast delivery — works with any ATAK device on the same LAN, no config needed
- Optional TAK Server TCP for cross-subnet / WAN delivery
- Two data modes: native RNS library or REST API (reticulum-mcp)
- Docker support for headless / server deployment
- Tracks auto-expire if the bridge stops (configurable stale time)

---

## Requirements

- Python 3.11+
- A running [rnsd](https://reticulum.network/manual/gettingstarted.html) instance reachable via TCP
- ATAK, iTAK, WinTAK, or TAK Server on the same LAN (or TAK Server for remote)

---

## Quick Start

```bash
git clone https://github.com/sansscott/rns-atak-bridge
cd rns-atak-bridge
pip install -r requirements.txt
cp examples/config.yaml.example config.yaml
# Edit config.yaml — set peer_host, home_lat, home_lon
python bridge.py
```

Open ATAK on a device on the same LAN. After the first poll you'll see blue `RNS-*` tracks appear.

---

## Configuration

```yaml
rns:
  mode: native            # 'native' (direct RNS lib) or 'rest' (reticulum-mcp API)
  peer_host: 127.0.0.1   # Your rnsd TCP server
  peer_port: 4242
  home_lat: 0.0           # Fallback coords when peer has no GPS in announce
  home_lon: 0.0

atak:
  multicast_addr: 239.2.3.1
  multicast_port: 6969
  tak_server: null        # Optional: "host:port" for TAK Server
  poll_interval_sec: 30
  stale_minutes: 5

callsign_prefix: "RNS-"
```

### Modes

| Mode | How it works | When to use |
|------|-------------|-------------|
| `native` | Connects to rnsd via TCP using the RNS Python library, reads path table directly | Standalone deployments, development |
| `rest` | Polls a running [reticulum-mcp](https://github.com/markqvist/reticulum-mcp) HTTP API (`/paths`) | When rnsd is remote or shared |

---

## Running

### Local

```bash
python bridge.py                       # uses config.yaml by default
python bridge.py --config /path/to/config.yaml --debug
```

### Docker

```bash
# network_mode: host is required for UDP multicast to reach LAN devices
docker compose up -d
docker logs -f rns-atak-bridge
```

---

## CoT Event Format

Each Reticulum peer becomes a CoT event:

```xml
<event version="2.0"
       uid="RNS-af60a4f4"
       type="a-f-G-U-C"
       time="2026-03-01T17:00:00.000000Z"
       start="2026-03-01T17:00:00.000000Z"
       stale="2026-03-01T17:05:00.000000Z"
       how="m-g">
  <point lat="41.700100" lon="-74.000000" hae="100" ce="50" le="50"/>
  <detail>
    <contact callsign="RNS-af60a4f4"/>
    <remarks>Reticulum | hash: af60a4f4863c9bff... | hops: 2 | iface: TCPClient</remarks>
    <__group name="Blue" role="Team Member"/>
  </detail>
</event>
```

| Field | Value | Notes |
|-------|-------|-------|
| `uid` | `RNS-{first 8 chars of hash}` | Stable and unique per peer |
| `type` | `a-f-G-U-C` | Friendly Ground Unit — blue icon in ATAK |
| `how` | `m-g` | Machine-generated |
| `lat`/`lon` | GPS from RNS announce, or `home_lat`/`home_lon` | Most peers will use fallback coords |
| `stale` | `now + stale_minutes` | Track auto-removes when bridge stops |

---

## Architecture

```
bridge.py        — Entry point. Loads config, starts poll loop, handles SIGINT/SIGTERM.
rns_source.py    — get_peers() dispatches to native RNS or REST mode.
                   Native: uses RNS.Transport.path_table (dict of hash→[ts, rcvd, hops, exp, blobs, iface, pkt]).
                   REST:   GET /paths from reticulum-mcp, parses destination_hash + hops.
cot_encoder.py   — peer_to_cot() builds lxml CoT XML. local_node_cot() for self-track.
atak_sender.py   — ATAKSender sends UDP multicast + optional TAK Server TCP with auto-reconnect.
```

---

## Connecting to the Reticulum Testnet

The official testnet has moved. Use community hubs — pick any that are reachable from your location:

```yaml
# In your rnsd config (~/.reticulum/config):
[[noDNS2 Hub]]
  type = TCPClientInterface
  enabled = yes
  target_host = 193.26.158.230
  target_port = 4965

[[Beleth RNS Hub]]
  type = TCPClientInterface
  enabled = yes
  target_host = rns.beleth.net
  target_port = 4242
```

Full community node list: [github.com/markqvist/Reticulum/wiki/Community-Node-List](https://github.com/markqvist/Reticulum/wiki/Community-Node-List)

---

## Verification

1. Start the bridge on a machine on the same LAN as your ATAK device
2. Open ATAK → SA multicast receive is enabled by default on `239.2.3.1:6969`
3. After the first poll (may take up to 60s on a quiet network), blue `RNS-*` icons appear on the map
4. Tap a track → info panel shows full hash, hop count, interface
5. Stop the bridge → tracks disappear after `stale_minutes` (default: 5 min)

> **First poll shows 0 peers?** This is normal. RNS populates its path table by receiving
> announces from remote nodes — this takes 30–120 seconds after startup. Wait for the
> second or third poll (every `poll_interval_sec`, default 30s). The log will say
> `"Path table empty — peers not yet announced. Will retry next poll."` until peers arrive.

---

## Self-Track (Your Node in ATAK)

To make your own RNS node appear as a track in ATAK, set `node_identity` in `config.yaml`:

```bash
# Find your rnsd transport identity:
rnstatus
# Look for the line: "Transport Identity : af60a4f4863c9bff..."
```

Then in `config.yaml`:

```yaml
rns:
  node_identity: "af60a4f4863c9bff05a9871359d67e1f"  # your full hash here
```

Your node will appear with 0 hops and the label `RNS-af60a4f4` at your `home_lat`/`home_lon` coordinates.

---

## Limitations

- **Location**: Reticulum doesn't include GPS in path announcements. All peers fall back to the `home_lat`/`home_lon` from your config unless location is embedded in LXMF announces (future work).
- **Identity vs. destination**: The path table contains destination hashes, not identity hashes. One node may have multiple destinations.
- **Multicast scope**: UDP multicast is LAN-only. Use TAK Server for cross-subnet or WAN delivery.

---

## Suite

This project is part of a three-tool open-source Reticulum→ATAK integration suite:

| Project | What it does |
|---------|-------------|
| **rns-atak-bridge** (this repo) | Reticulum path table peers → ATAK SA tracks |
| [rns-lxmf-atak-chat](https://github.com/sansscott/rns-lxmf-atak-chat) | LXMF messages → ATAK GeoChat window |
| [rns-mesh-observer](https://github.com/sansscott/rns-mesh-observer) | REST + WebSocket API for live Reticulum topology |

## Related Projects

- [Reticulum Network Stack](https://reticulum.network) — the encrypted mesh networking layer
- [ATAK / TAK.gov](https://tak.gov) — tactical situational awareness platform
- [NomadNet](https://github.com/markqvist/NomadNet) — Reticulum-based mesh messenger
- [ATAK Forwarder](https://github.com/paulmandal/atak-forwarder) — similar bridge for Meshtastic/LoRa → ATAK

---

## License

MIT
