"""
bridge.py — bridge Quilt cells over a mesh network.

A Quilt cell exposes a PTO surface over WebSocket (per quilt-edge-node).
This module is the *bridge* that connects cells that aren't on the
same LAN.

Three transport modes:
- direct: a peer connection (host:port)
- relay: a server that forwards messages
- broadcast: gossip (each peer tells its peers)

Each bridge node has:
- A list of known peers (host:port + node_id).
- A routing table mapping target_node_id → next_hop_peer.
- A witness log of forwarded messages.

Run:
    python3 -m quilt_mesh_bridge.bridge --port 7790 --peer host:7789
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field

sys.path.insert(0, "/workspace/repos/quilt-edge-node/src")

import quilt_node_identity as qni


log = logging.getLogger("mesh-bridge")


# === Message ================================================================

@dataclass
class MeshMessage:
    src_node_id: str
    dst_node_id: str | None         # None = broadcast
    hop_count: int = 0
    payload: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    msg_id: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "MeshMessage":
        return cls(**json.loads(raw))


# === Routing table ==========================================================

class RoutingTable:
    """Maps node_id → peer address."""

    def __init__(self, ttl_s: float = 300.0):
        self.ttl_s = ttl_s
        self.routes: dict[str, tuple[str, float]] = {}   # node_id → (peer, last_seen)

    def update(self, node_id: str, peer: str) -> None:
        self.routes[node_id] = (peer, time.time())

    def lookup(self, node_id: str) -> str | None:
        rec = self.routes.get(node_id)
        if rec is None:
            return None
        peer, ts = rec
        if time.time() - ts > self.ttl_s:
            del self.routes[node_id]
            return None
        return peer

    def entries(self) -> list[dict]:
        return [{"node_id": k, "peer": v[0], "age_s": time.time() - v[1]}
                for k, v in self.routes.items()]


# === Bridge ==================================================================

class MeshBridge:
    """A node in the mesh; forwards messages between cells."""

    def __init__(self, name: str, port: int, peers: list[str] | None = None):
        self.name = name
        self.port = port
        # Identity: derive from name + port for determinism.
        fake_serial = f"mesh-bridge-{name}-{port}"
        self.identity = qni.bond(fake_serial, ssid="mesh", bssid="00:00:00:00:00:00")
        self.peers: dict[str, str] = {}       # short_id → ws_url
        self.routing = RoutingTable()
        self.witness: list[dict] = []
        self._server = None

    def add_peer(self, ws_url: str, node_id: str | None = None) -> None:
        short = (node_id or qni.short_id(qni.derive_node_id(
            qni.derive_network_salt("mesh", "00:00:00:00:00:00"),
            ws_url)))[:8]
        self.peers[short] = ws_url
        if node_id:
            self.routing.update(node_id, ws_url)

    def route(self, msg: MeshMessage) -> tuple[str, MeshMessage] | None:
        """Pick a peer for `msg.dst_node_id` and prepare the forwarded message."""
        if msg.dst_node_id is None:
            # Broadcast: pick first peer (or all).
            if not self.peers:
                return None
            peer_ws = next(iter(self.peers.values()))
            msg.hop_count += 1
            return peer_ws, msg
        # Lookup.
        peer_ws = self.routing.lookup(msg.dst_node_id)
        if peer_ws is None:
            log.warning("no route for %s", msg.dst_node_id)
            return None
        msg.hop_count += 1
        return peer_ws, msg

    def record(self, msg: MeshMessage, direction: str, peer: str) -> None:
        self.witness.append({
            "ts": time.time(),
            "direction": direction,
            "peer": peer,
            "msg_id": msg.msg_id,
            "src": msg.src_node_id[:12] if msg.src_node_id else None,
            "dst": msg.dst_node_id[:12] if msg.dst_node_id else "(broadcast)",
            "hop_count": msg.hop_count,
        })
        # Keep witness bounded.
        if len(self.witness) > 1000:
            self.witness = self.witness[-1000:]

    async def serve(self):
        try:
            import websockets
        except ImportError:
            raise SystemExit("pip install websockets")

        async def handler(ws):
            async for raw in ws:
                try:
                    msg = MeshMessage.from_json(raw)
                except (json.JSONDecodeError, TypeError) as e:
                    await ws.send(json.dumps({"error": f"bad json: {e}"}))
                    continue
                self.record(msg, direction="in", peer=str(ws.remote_address))
                # Forward if we can.
                routed = self.route(msg)
                if routed is None:
                    await ws.send(json.dumps({"status": "no_route"}))
                    continue
                peer_ws, forwarded = routed
                try:
                    # Different websockets versions have different connect signatures.
                    try:
                        async with websockets.connect(peer_ws) as fwd_ws:
                            await fwd_ws.send(forwarded.to_json())
                            ack = await asyncio.wait_for(fwd_ws.recv(), timeout=5)
                    except TypeError:
                        async with websockets.connect(peer_ws, timeout=5) as fwd_ws:
                            await fwd_ws.send(forwarded.to_json())
                            ack = await asyncio.wait_for(fwd_ws.recv(), timeout=5)
                    self.record(forwarded, direction="out", peer=peer_ws)
                    await ws.send(ack)
                except Exception as e:
                    await ws.send(json.dumps({"error": f"forward failed: {e}"}))

        self._server = await websockets.serve(handler, "0.0.0.0", self.port)
        log.info("mesh bridge %s listening on :%d (node_id=%s)",
                 self.name, self.port, qni.short_id(self.identity.node_id))
        await asyncio.Future()  # run forever


def main():
    p = argparse.ArgumentParser(description="Quilt mesh bridge")
    p.add_argument("--name", default="bridge")
    p.add_argument("--port", type=int, default=7790)
    p.add_argument("--peer", action="append", default=[],
                   help="peer ws://host:port to forward to (repeatable)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    bridge = MeshBridge(name=args.name, port=args.port)
    for p_ws in args.peer:
        bridge.add_peer(p_ws)
    asyncio.run(bridge.serve())


if __name__ == "__main__":
    main()
