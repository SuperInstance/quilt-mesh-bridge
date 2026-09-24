"""Tests for the mesh bridge."""
import json
import unittest
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, "/workspace/repos/quilt-edge-node/src")

from quilt_mesh_bridge.bridge import MeshBridge, MeshMessage, RoutingTable


class TestMeshMessage(unittest.TestCase):
    def test_serialize_roundtrip(self):
        m = MeshMessage(src_node_id="abc", dst_node_id="def",
                        hop_count=2, payload={"k": "v"},
                        ts=time.time(), msg_id="m1")
        s = m.to_json()
        m2 = MeshMessage.from_json(s)
        self.assertEqual(m.src_node_id, m2.src_node_id)
        self.assertEqual(m.dst_node_id, m2.dst_node_id)
        self.assertEqual(m.hop_count, m2.hop_count)
        self.assertEqual(m.payload, m2.payload)
        self.assertEqual(m.msg_id, m2.msg_id)


class TestRoutingTable(unittest.TestCase):
    def test_lookup_miss(self):
        rt = RoutingTable()
        self.assertIsNone(rt.lookup("unknown"))

    def test_lookup_hit(self):
        rt = RoutingTable()
        rt.update("node_x", "ws://host:1234")
        self.assertEqual(rt.lookup("node_x"), "ws://host:1234")

    def test_ttl_expiry(self):
        rt = RoutingTable(ttl_s=0.05)
        rt.update("node_x", "ws://host:1234")
        self.assertEqual(rt.lookup("node_x"), "ws://host:1234")
        time.sleep(0.1)
        self.assertIsNone(rt.lookup("node_x"))


class TestBridge(unittest.TestCase):
    def test_construct(self):
        bridge = MeshBridge(name="b1", port=7799)
        self.assertEqual(bridge.name, "b1")
        self.assertEqual(bridge.port, 7799)
        self.assertTrue(bridge.identity.node_id)

    def test_add_peer(self):
        bridge = MeshBridge(name="b2", port=7799)
        bridge.add_peer("ws://127.0.0.1:7701")
        self.assertEqual(len(bridge.peers), 1)
        bridge.add_peer("ws://127.0.0.1:7702", node_id="abc")
        self.assertEqual(len(bridge.peers), 2)
        self.assertEqual(len(bridge.routing.entries()), 1)

    def test_route_broadcast(self):
        bridge = MeshBridge(name="b3", port=7799)
        bridge.add_peer("ws://127.0.0.1:7701")
        msg = MeshMessage(src_node_id="src", dst_node_id=None)
        routed = bridge.route(msg)
        self.assertIsNotNone(routed)
        ws, fwd = routed
        self.assertEqual(ws, "ws://127.0.0.1:7701")
        self.assertEqual(fwd.hop_count, 1)

    def test_route_targeted(self):
        bridge = MeshBridge(name="b4", port=7799)
        bridge.add_peer("ws://127.0.0.1:7701", node_id="node_xyz")
        msg = MeshMessage(src_node_id="src", dst_node_id="node_xyz")
        routed = bridge.route(msg)
        self.assertIsNotNone(routed)
        ws, fwd = routed
        self.assertEqual(ws, "ws://127.0.0.1:7701")
        self.assertEqual(fwd.hop_count, 1)

    def test_route_no_route(self):
        bridge = MeshBridge(name="b5", port=7799)
        bridge.add_peer("ws://127.0.0.1:7701")
        msg = MeshMessage(src_node_id="src", dst_node_id="unknown_target")
        self.assertIsNone(bridge.route(msg))

    def test_record(self):
        bridge = MeshBridge(name="b6", port=7799)
        msg = MeshMessage(src_node_id="src", dst_node_id="dst", msg_id="m1")
        bridge.record(msg, "in", "ws://host:1")
        bridge.record(msg, "out", "ws://host:2")
        self.assertEqual(len(bridge.witness), 2)
        self.assertEqual(bridge.witness[0]["direction"], "in")
        self.assertEqual(bridge.witness[1]["direction"], "out")


if __name__ == "__main__":
    unittest.main()
