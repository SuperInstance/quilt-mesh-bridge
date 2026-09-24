"""
mesh_demo.py — minimal mesh bridge demo.

Steps:
1. Spin up 2 sim nodes on :7701, :7702.
2. Spin up a bridge on :7790 that knows about both.
3. Send a "hello" from one to the other via the bridge.
4. Show the bridge's witness log.

Run:
    python3 examples/mesh_demo.py
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, "/workspace/repos/quilt-mesh-bridge/src")
sys.path.insert(0, "/workspace/repos/quilt-fleet-sim/src")
sys.path.insert(0, "/workspace/repos/quilt-edge-node/src")

from quilt_mesh_bridge.bridge import MeshBridge, MeshMessage
from quilt_fleet_sim.fleet import SimFleet
import quilt_node_identity as qni


def banner(label):
    print("\n" + "─" * 60)
    print(f"  {label}")
    print("─" * 60)


async def main():
    # Start a 2-node sim fleet.
    fleet = SimFleet(n_nodes=2, base_port=7701, ssid="mesh-lan")
    await fleet.start()
    src = fleet.nodes[0]
    dst = fleet.nodes[1]
    print(f"=== sim fleet: {src.name} @ :{src.port} → {dst.name} @ :{dst.port} ===")

    # Start a bridge.
    bridge = MeshBridge(name="demo", port=7790)
    bridge.add_peer(f"ws://127.0.0.1:{src.port}", node_id=src.identity.node_id)
    bridge.add_peer(f"ws://127.0.0.1:{dst.port}", node_id=dst.identity.node_id)
    print(f"=== bridge: {qni.short_id(bridge.identity.node_id)} @ :{bridge.port} ===")
    print(f"  known peers: {list(bridge.peers.keys())}")

    # Start the bridge server in background.
    bridge_task = asyncio.create_task(bridge.serve())
    await asyncio.sleep(0.5)

    banner("01 — send a message src → dst via bridge")
    import websockets
    msg = MeshMessage(
        src_node_id=src.identity.node_id,
        dst_node_id=dst.identity.node_id,
        msg_id=f"hello-{int(time.time())}",
        payload={"op": "heartbeat", "from": "mesh_demo"},
    )
    async with websockets.connect(f"ws://127.0.0.1:{bridge.port}") as ws:
        await ws.send(msg.to_json())
        ack = await ws.recv()
        print(f"  sent: {msg.payload}")
        print(f"  ack:  {ack[:200]}")

    banner("02 — bridge witness log")
    for w in bridge.witness[-5:]:
        print(f"  {w['direction']} peer={w['peer']} hop={w['hop_count']}")

    banner("03 — broadcast (dst=None)")
    msg2 = MeshMessage(
        src_node_id=src.identity.node_id,
        dst_node_id=None,
        msg_id=f"broadcast-{int(time.time())}",
        payload={"op": "broadcast", "note": "hello mesh"},
    )
    async with websockets.connect(f"ws://127.0.0.1:{bridge.port}") as ws:
        await ws.send(msg2.to_json())
        ack = await ws.recv()
        print(f"  sent: {msg2.payload}")
        print(f"  ack:  {ack[:200]}")

    banner("done")
    print(f"  bridge forwarded {len(bridge.witness)} messages")
    print(f"  routing table: {len(bridge.routing.entries())} entries")

    bridge_task.cancel()
    await fleet.stop()


if __name__ == "__main__":
    asyncio.run(main())
