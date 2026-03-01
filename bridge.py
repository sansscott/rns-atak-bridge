#!/usr/bin/env python3
"""
bridge.py — RNS-ATAK Bridge entry point

Polls Reticulum peer data and sends CoT XML to ATAK devices via UDP multicast.

Usage:
    python bridge.py [--config config.yaml] [--debug]
"""

import argparse
import logging
import signal
import sys
import time

import yaml

from rns_source import get_peers, get_local_identity
from cot_encoder import peer_to_cot, local_node_cot
from atak_sender import ATAKSender


log = logging.getLogger("rns-atak-bridge")


def load_config(path: str) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)

    # Apply defaults
    cfg.setdefault("callsign_prefix", "RNS-")
    cfg["rns"].setdefault("mode", "native")
    cfg["rns"].setdefault("home_lat", 0.0)
    cfg["rns"].setdefault("home_lon", 0.0)
    cfg["atak"].setdefault("multicast_addr", "239.2.3.1")
    cfg["atak"].setdefault("multicast_port", 6969)
    cfg["atak"].setdefault("poll_interval_sec", 30)
    cfg["atak"].setdefault("stale_minutes", 5)
    cfg["atak"].setdefault("tak_server", None)

    return cfg


def run_poll_loop(cfg: dict, sender: ATAKSender):
    interval = cfg["atak"]["poll_interval_sec"]
    mode = cfg["rns"]["mode"]
    log.info(f"Starting poll loop — mode={mode}, interval={interval}s")

    # Include local node as a track if we can get its identity
    local_id = get_local_identity(cfg)
    if local_id:
        log.info(f"Local node identity: {local_id}")

    while True:
        peers = get_peers(cfg)

        # Optionally include local node
        sent = 0
        if local_id:
            cot = local_node_cot(local_id, cfg)
            sender.send(cot)
            sent += 1

        for peer in peers:
            try:
                cot = peer_to_cot(peer, cfg)
                sender.send(cot)
                sent += 1
                log.debug(f"  → {peer['hash'][:16]}... hops={peer['hops']} iface={peer['interface']}")
            except Exception as e:
                log.error(f"Failed to encode/send peer {peer.get('hash', '?')}: {e}")

        log.info(f"Poll complete: {len(peers)} remote peers + {'1 local' if local_id else '0 local'} = {sent} CoT events sent")

        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="RNS → ATAK CoT bridge")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    cfg = load_config(args.config)
    sender = ATAKSender(cfg)

    def _shutdown(sig, frame):
        log.info("Shutting down...")
        sender.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        run_poll_loop(cfg, sender)
    except KeyboardInterrupt:
        pass
    finally:
        sender.close()


if __name__ == "__main__":
    main()
