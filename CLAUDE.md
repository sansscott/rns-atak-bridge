# rns-atak-bridge

## Overview
Open-source Python bridge that converts Reticulum Network Stack (RNS) peer data to ATAK Cursor-on-Target (CoT) XML, making Reticulum mesh nodes visible as Situational Awareness tracks in ATAK, iTAK, WinTAK, and TAK Server. The first public Reticulum → ATAK integration.

## Purpose
Portfolio project for ATAK contract work and Palantir/Anduril job applications. To be published as a public GitHub repo and posted to Reticulum and TAK.gov communities.

## Tech Stack
- **Language**: Python 3.11+
- **Key libs**: `rns` (Reticulum), `lxml` (CoT XML), `requests`, `pyyaml`
- **Protocol**: CoT (Cursor-on-Target) over UDP multicast
- **Deployment**: Runs on node4 or Mac Studio, no Docker required (simple CLI tool)

## Directory Structure
```
rns-atak-bridge/
├── bridge.py              # Entry point: poll loop orchestrator
├── rns_source.py          # Mode A: REST (port 8023) | Mode B: native RNS lib
├── cot_encoder.py         # RNS peer → CoT XML (lxml)
├── atak_sender.py         # UDP multicast 239.2.3.1:6969 + optional TAK Server TCP
├── config.yaml            # All settings
├── requirements.txt
├── Dockerfile             # Optional container deployment on node4
├── README.md
└── examples/
    └── config.yaml.example
```

## Key Files
- `bridge.py` — Entry point, main poll loop
- `rns_source.py` — Two data modes for Reticulum
- `cot_encoder.py` — CoT XML generation (ATAK protocol)
- `atak_sender.py` — UDP multicast delivery
- `config.yaml` — Runtime configuration

## Reticulum Integration

### Node4 Endpoints
- **REST API** (reticulum-mcp): `http://192.168.1.204:8023`
  - `GET /status` → identity, uptime, version
  - `GET /paths` → known peer destination hashes + hop counts
  - `GET /interfaces` → interface names, link states
  - **Status**: UNHEALTHY (fix health check before using)
- **Native RNS** (preferred): peer with `192.168.1.204:4242`
  - `import RNS; RNS.Reticulum(); RNS.Transport.get_path_table()`
  - Works independently of reticulum-mcp

### Identity
- Node4 identity: `af60a4f4863c9bff05a9871359d67e1f`
- Frankfurt testnet peer: `frankfurt.rns.unsigned.io:4965`

## ATAK CoT Format
```xml
<event version="2.0" uid="RNS-af60a4f4" type="a-f-G-U-C"
       time="..." start="..." stale="..." how="m-g">
  <point lat="41.7001" lon="-74.0" hae="100" ce="50" le="50"/>
  <detail>
    <contact callsign="RNS-af60a4f4"/>
    <remarks>Reticulum | hops: 2 | iface: TCPClient</remarks>
  </detail>
</event>
```
- Multicast target: `239.2.3.1:6969` (standard ATAK SA multicast)
- Stale: 5 minutes (track auto-removes if bridge stops)
- Type: `a-f-G-U-C` (friendly ground unit = standard blue icon)

## Configuration

### config.yaml
```yaml
rns:
  mode: native            # 'native' (recommended) or 'rest'
  rest_url: http://192.168.1.204:8023
  peer_host: 192.168.1.204
  peer_port: 4242
  home_lat: 41.7001       # Fallback lat when no GPS in announce
  home_lon: -74.0

atak:
  multicast_addr: 239.2.3.1
  multicast_port: 6969
  tak_server: null        # Optional: 192.168.1.x:8087
  poll_interval_sec: 30
  stale_minutes: 5

callsign_prefix: "RNS-"
```

## Running the Bridge

### Local (Mac Studio or node4)
```bash
cd /mnt/storage/rns-atak-bridge
pip install -r requirements.txt
python bridge.py --config config.yaml
```

### Docker (node4)
```bash
ssh -i ~/.ssh/id_ed25519_truenas root@192.168.1.204
cd /mnt/storage/rns-atak-bridge
docker compose up -d
docker logs -f rns-atak-bridge
```

### Verify in ATAK
1. Open iTAK/ATAK on phone connected to same LAN
2. Enable SA multicast receive (default: on)
3. Track `RNS-af60a4f4` should appear as blue icon

## GitHub
- **Repo**: sansscott/rns-atak-bridge (**PUBLIC**)
- **Purpose**: Open-source community tool — not private
- **Create**: `gh repo create sansscott/rns-atak-bridge --public --description "Reticulum Network Stack → ATAK CoT bridge"`

## Deployment on node4
- Path: `/mnt/storage/rns-atak-bridge/`
- Clone: `git clone https://github.com/sansscott/rns-atak-bridge /mnt/storage/rns-atak-bridge`
- No DB required — stateless tool

## Related Projects
- **Reticulum stack**: `/mnt/storage/reticulum/` — rnsd + nomadnet + reticulum-mcp
- **THR-Manet**: `sansscott/THR-Manet` (private) — Reticulum field deployment docs
- **Sycamore Mesh**: `/mnt/storage/sycamore-mesh/` — tactical dashboard (same domain)

## Reticulum MCP Container Fix
The `reticulum-mcp` container is UNHEALTHY. Before using REST mode:
```bash
ssh -i ~/.ssh/id_ed25519_truenas root@192.168.1.204
docker logs reticulum-mcp --tail 30
# Check health check path — likely hitting wrong port or endpoint
# Server listens on 8020 internally, mapped to 8023 externally
```
If fix takes >15 min, skip and use `mode: native` instead.

## Publish Checklist
- [ ] GitHub repo created (public)
- [ ] README with install instructions + demo screenshot
- [ ] Posted to Reticulum Discord: https://reticulum.network/community
- [ ] Posted to TAK.gov community forum
- [ ] Posted to r/amateurradio
- [ ] Linked from Sycamore Mesh README

## Known Gotchas
- ATAK multicast requires bridge and ATAK device on same LAN subnet (or TAK Server relay for cross-subnet)
- RNS path table only shows destinations that have sent announces recently — may be sparse on testnet
- If using native RNS mode, the bridge creates its own RNS identity (store in config dir)
- `lxml` requires system libxml2 — on Alpine Docker: `apk add libxml2-dev libxslt-dev`

---
*Credentials: See master CLAUDE.md (`~/.claude/CLAUDE.md`)*
*Obsidian note: [[RNS-ATAK Bridge Project]]*
