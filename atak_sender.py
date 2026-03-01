"""
atak_sender.py — Send CoT XML to ATAK devices.

Supports two delivery methods:
  1. UDP multicast to 239.2.3.1:6969 (standard ATAK SA multicast, LAN only)
  2. TCP to a TAK Server (for cross-subnet delivery)

ATAK devices on the same LAN subnet listen on the multicast group by default.
No ATAK configuration is needed — just being on the same LAN is enough.

Notes:
  - Multicast TTL=32 allows traversal across up to 32 router hops (still LAN-scoped
    in practice since most networks block multicast at the router boundary).
  - TAK Server TCP uses raw CoT XML, newline-delimited.
"""

import logging
import socket
import struct
from typing import Optional

log = logging.getLogger(__name__)


class ATAKSender:
    def __init__(self, cfg: dict):
        self.multicast_addr = cfg["atak"]["multicast_addr"]
        self.multicast_port = cfg["atak"]["multicast_port"]
        self.tak_server = cfg["atak"].get("tak_server")  # "host:port" or null

        self._mcast_sock: Optional[socket.socket] = None
        self._tcp_sock: Optional[socket.socket] = None

        self._init_multicast()
        if self.tak_server:
            self._init_tak_server()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _init_multicast(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # TTL=32: enough for local networks, blocked at most WAN borders
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
        self._mcast_sock = sock
        log.info(f"Multicast sender ready → {self.multicast_addr}:{self.multicast_port}")

    def _init_tak_server(self):
        host, port_str = self.tak_server.rsplit(":", 1)
        port = int(port_str)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((host, port))
            self._tcp_sock = sock
            log.info(f"Connected to TAK Server at {host}:{port}")
        except Exception as e:
            log.warning(f"TAK Server connect failed ({self.tak_server}): {e}")
            self._tcp_sock = None

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(self, cot_xml: bytes):
        """Send a CoT event to all configured destinations."""
        self._send_multicast(cot_xml)
        if self._tcp_sock or self.tak_server:
            self._send_tak_server(cot_xml)

    def _send_multicast(self, cot_xml: bytes):
        try:
            self._mcast_sock.sendto(cot_xml, (self.multicast_addr, self.multicast_port))
            log.debug(f"Multicast sent {len(cot_xml)} bytes")
        except Exception as e:
            log.error(f"Multicast send failed: {e}")

    def _send_tak_server(self, cot_xml: bytes):
        if not self._tcp_sock:
            # Attempt reconnect
            self._init_tak_server()
            if not self._tcp_sock:
                return
        try:
            self._tcp_sock.sendall(cot_xml + b"\n")
            log.debug(f"TAK Server sent {len(cot_xml)} bytes")
        except Exception as e:
            log.warning(f"TAK Server send failed, will reconnect next cycle: {e}")
            try:
                self._tcp_sock.close()
            except Exception:
                pass
            self._tcp_sock = None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        if self._mcast_sock:
            self._mcast_sock.close()
        if self._tcp_sock:
            self._tcp_sock.close()
