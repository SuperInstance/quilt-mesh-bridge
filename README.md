# quilt-mesh-bridge

> **Bridge Quilt cells across networks via a forwarding mesh.**
> Connect cells on different LANs (boat-lan, home-lan, work-lan) through a relay.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                       │
│                       Boat LAN                                       │
│                                                                       │
│    ┌──────────┐         ┌──────────────┐                             │
│    │ unoq-01  │         │ unoq-02      │                             │
│    │ (boat)   │         │ (boat)       │                             │
│    └────┬─────┘         └──────┬───────┘                             │
│         │ :7681               │ :7681                                │
│         │                     │                                      │
│         └──────────┬──────────┘                                      │
│                    │                                                 │
│              ┌─────▼─────┐                                           │
│              │ bridge A  │                                           │
│              │ :7790     │                                           │
│              └─────┬─────┘                                           │
│                    │                                                 │
└────────────────────┼────────────────────────────────────────────────┘
                     │  (relay over the WAN)
                     │
┌────────────────────┼────────────────────────────────────────────────┐
│                    │       Home LAN                                  │
│              ┌─────▼─────┐                                           │
│              │ bridge B  │                                           │
│              │ :7791     │                                           │
│              └─────┬─────┘                                           │
│                    │                                                 │
│         ┌──────────┴──────────┐                                      │
│         │                     │                                      │
│    ┌────▼─────┐         ┌────▼─────┐                                │
│    │ unoq-03  │         │ unoq-04  │                                │
│    │ (home)   │         │ (home)   │                                │
│    └──────────┘         └──────────┘                                │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## What this solves

Quilt cells (UNO Q nodes) communicate over WebSocket on their local
network. But vessels move. Boats, RVs, vehicles, ships cross between
LANs and WANs. Cells on different LANs can't see each other.

A **mesh bridge** is the relay between cells:

- Cells on LAN-A connect to bridge-A.
- Cells on LAN-B connect to bridge-B.
- Bridge-A and Bridge-B talk to each other over the WAN (or any
  relay-friendly transport).
- Cross-network messages flow: cell → bridge → bridge → cell.

The bridge:
- Maintains a routing table (node_id → peer ws://).
- Forwards messages between cells.
- Records every forwarding in a witness log.
- Handles broadcast (dst=None) by fanning out to known peers.

## Run

```bash
# Start a bridge:
python3 -m quilt_mesh_bridge.bridge --port 7790 \
    --peer ws://192.168.1.50:7791

# Send a message via the bridge:
# (use a websocket client, see examples/mesh_demo.py)
```

## Files

- `src/quilt_mesh_bridge/bridge.py` — the bridge node (MeshBridge + RoutingTable + MeshMessage)
- `examples/mesh_demo.py` — 2 sim nodes + 1 bridge + cross-cell message
- `tests/test_bridge.py` — 10/10 unit tests
- `DESIGN.md` — architecture

## Quick demo

```bash
python3 examples/mesh_demo.py
```

Output:
```
=== sim fleet: sim-boat-00 @ :7701 → sim-home-01 @ :7702 ===
=== bridge: b12f6969 @ :7790 ===

01 — send a message src → dst via bridge
  sent: {'op': 'heartbeat', 'from': 'mesh_demo'}
  ack:  (forwarded)

02 — bridge witness log
  in  peer=(127.0.0.1, 51926) hop=0
  out peer=ws://127.0.0.1:7702 hop=1

done
  bridge forwarded 4 messages
  routing table: 2 entries
```

## Doctrines

1. **Cells don't move; bridges do.** A cell on a vessel has a stable
   identity (network-keyed). When the vessel moves, the bridge
   re-routes the cell to its new peers.
2. **The bridge is itself a Quilt cell.** It has an identity,
   substrates (forwarding), compartments (routing table, witness
   log), and a PTO surface.
3. **Witness is composable.** Each bridge's witness log is appended
   to the cells' witness chains. The audit trail is end-to-end.
4. **Gossip over centralized.** A broadcast reaches everyone; you
   don't need a central registry. (We have one anyway, for canary
   aggregation, but the cells don't *need* it.)

## Cross-project doctrine

The "bridge" pattern generalizes:

- **Cells ↔ cells.** What we built here.
- **Cells ↔ cloud.** The same bridge forwards cells' state to a
  cloud aggregator.
- **Cloud ↔ cells.** The cloud can push updates to cells via the
  bridge.
- **Cells ↔ satellite.** A satellite uplink bridge has the same
  shape: identity + routing table + witness.

The bridge is *just another cell* with a different substrate zoo.

## Future work

- **Encryption.** All traffic is plain WebSocket today. Add TLS for
  the WAN.
- **Compression.** Long payload strings should be compressed
  before forwarding.
- **Store-and-forward.** A bridge should buffer messages for
  unreachable peers.
- **Routing protocols.** Implement a simple distance-vector
  protocol so bridges can find each other automatically.
