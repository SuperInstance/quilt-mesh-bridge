import unittest
import sys
sys.path.insert(0, "src")
import quilt_mesh_bridge


class TestSmoke(unittest.TestCase):
    def test_version(self):
        self.assertTrue(hasattr(quilt_mesh_bridge, "__version__"))


if __name__ == "__main__":
    unittest.main()
