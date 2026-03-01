# rns-atak-bridge

**The first public Reticulum → ATAK integration.**

Bridges [Reticulum Network Stack](https://reticulum.network) peer data to [ATAK](https://tak.gov) (Android Team Awareness Kit) via [Cursor-on-Target (CoT)](https://www.mitre.org/sites/default/files/pdf/09_4937.pdf) XML. Reticulum mesh nodes appear as live blue SA tracks in ATAK, iTAK, WinTAK, and TAK Server.

```
Reticulum mesh ──► bridge.py ──► CoT XML ──► UDP multicast ──► iTAK / ATAK / WinTAK
  (path table)                   (lxml)       239.2.3.1:6969
```

## What It Does

- Polls the Reticulum path table for known peer destination hashes
- Encodes each peer as a CoT event (`type="a-f-G-U-C"`, blue friendly ground unit)
- Sends CoT events via UDP multicast to any ATAK device on the same LAN
- Optionally forwards to a TAK Server for cross-subnet delivery
- Auto-expires tracks after a configurable stale time (default: 5 min)

## Requirements

- Python 3.11+
- A running [rnsd](https://reticulum.network/manual/gettingstarted.html) instance (local or reachable via TCP)
- ATAK, iTAK, WinTAK, or TAK Server on the same LAN

## Installation

```bash
git clone https://github.com/sansscott/rns-atak-bridge
cd rns-atak-bridge
pip install -r requirements.txt
cp examples/config.yaml.example config.yaml
# Edit config.yaml with your rnsd address and home coordinates
python bridge.py
```

## Configuration

Copy `examples/config.yaml.example` to `config.yaml` and edit:

```yaml
rns:
  mode: native            # 'native' (recommended) or 'rest'
  peer_host: 192.168.1.x  # IP of your rnsd TCP server
  peer_port: 4242
  home_lat: 41.7001       # Fallback coords when peer has no GPS
  home_lon: -74.0

atak:
  multicast_addr: 239.2.3.1
  multicast_port: 6969
  tak_server: null        # Optional: "host:port" for TAK Server TCP
  poll_interval_sec: 30
  stale_minutes: 5

callsign_prefix: "RNS-"
```

### Modes

**`mode: native`** (recommended) — Uses the `rns` Python library to connect directly to an rnsd instance via TCP and read its path table. No extra services required.

**`mode: rest`** — Polls the [reticulum-mcp](https://github.com/markqvist/reticulum-mcp) HTTP REST API (`/paths`, `/status`). Requires a running reticulum-mcp instance.

## Running

### Local

```bash
python bridge.py --config config.yaml
python bridge.py --config config.yaml --debug  # verbose logging
```

### Docker (node4 / TrueNAS)

```bash
# network_mode: host is required for multicast to reach LAN devices
docker compose up -d
docker logs -f rns-atak-bridge
```

## Verification

1. Start the bridge on a machine connected to the same LAN as your ATAK device
2. Open iTAK or ATAK → SA Multicast should be enabled by default
3. Peer(s) appear as blue icons with callsigns like `RNS-af60a4f4`
4. Tap a track to see: full hash, hop count, interface name
5. Stop the bridge → tracks disappear after `stale_minutes`

## CoT Event Format

```xml
<event version="2.0"
       uid="RNS-af60a4f4"
       type="a-f-G-U-C"
       time="2026-03-01T16:00:00.000000Z"
       start="2026-03-01T16:00:00.000000Z"
       stale="2026-03-01T16:05:00.000000Z"
       how="m-g">
  <point lat="41.700100" lon="-74.000000" hae="100" ce="50" le="50"/>
  <detail>
    <contact callsign="RNS-af60a4f4"/>
    <remarks>Reticulum | hash: af60a4f4863c9bff... | hops: 2 | iface: TCPClient</remarks>
    <__group name="Blue" role="Team Member"/>
  </detail>
</event>
```

- **uid**: `RNS-{first 8 chars of destination hash}` — stable, unique per peer
- **type**: `a-f-G-U-C` — Atom / Friendly / Ground / Unit / Combat (blue icon in ATAK)
- **lat/lon**: GPS if available in RNS announce, else `home_lat`/`home_lon` from config
- **stale**: Auto-removes track if bridge stops sending (configurable, default 5 min)

## Architecture

```
bridge.py               # Entry point, poll loop, signal handling
rns_source.py           # get_peers() → native RNS or REST API
cot_encoder.py          # peer_to_cot() → lxml CoT XML bytes
atak_sender.py          # ATAKSender → UDP multicast + optional TAK Server TCP
config.yaml             # All runtime settings
```

## Related Projects

- [Reticulum Network Stack](https://reticulum.network) — encrypted mesh networking
- [ATAK / TAK.gov](https://tak.gov) — tactical situational awareness platform
- [Sycamore Mesh](https://github.com/sansscott/sycamore-mesh) — tactical mesh comms dashboard

## License

MIT
