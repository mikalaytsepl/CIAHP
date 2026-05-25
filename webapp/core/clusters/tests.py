import os
import tempfile
import socket
import json
from django.test import TestCase, override_settings
from django.conf import settings
from unittest.mock import patch, MagicMock

from clusters.models import Cluster, Node
from clusters.services import add_node, remove_node, create_cluster
from runner.ansible_runner import _to_extra_vars_str
import sys
from pathlib import Path
scripts_dir = Path(settings.BASE_DIR).parent.parent / "scripts" / "integration_scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))
from inventory_manager import InventoryManager

# Create temporary file for inventory test
temp_dir = tempfile.mkdtemp()
temp_inventory_path = os.path.join(temp_dir, "test_inventory.yml")

@override_settings(INVENTORY_FILE=temp_inventory_path)
class CIAHPBackendTests(TestCase):
    def setUp(self):
        # Ensure clean file before each test
        if os.path.exists(temp_inventory_path):
            os.remove(temp_inventory_path)
        
        # Create a cluster
        self.cluster = create_cluster(
            name="testcluster",
            cluster_cidr="192.168.1.0/24",
            vip_address="192.168.1.10",
            kube_version="1.35"
        )

    def tearDown(self):
        if os.path.exists(temp_inventory_path):
            os.remove(temp_inventory_path)
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

    def test_create_cluster_initializes_inventory(self):
        # Verify inventory manager initialized it
        mgr = InventoryManager(temp_inventory_path)
        data = mgr._load()
        self.assertIn("all", data)
        self.assertIn("testcluster", data["all"]["children"]["clusters"]["children"])
        
        # Check HA vars
        cluster_vars = data["all"]["children"]["clusters"]["children"]["testcluster"]["vars"]
        self.assertEqual(cluster_vars["cluster_vip"], "192.168.1.10")
        self.assertEqual(cluster_vars["control_plane_endpoint"], "192.168.1.10:8443")

    def test_add_node_propagates_final_name(self):
        # Add a node without validation
        node = add_node(
            cluster=self.cluster,
            name="worker-node",
            ip="192.168.1.50",
            role="worker",
            validate_host=False
        )

        # Final name should have 5-char suffix and start with "worker-node-"
        self.assertTrue(node.name.startswith("worker-node-"))
        self.assertEqual(len(node.name), len("worker-node-") + 5)

        # Database should match exactly
        db_node = Node.objects.get(id=node.id)
        self.assertEqual(db_node.name, node.name)

        # Inventory file should have the final name
        mgr = InventoryManager(temp_inventory_path)
        inv_data = mgr._load()
        workers = inv_data["all"]["children"]["clusters"]["children"]["testcluster"]["children"]["testcluster_workers"]["hosts"]
        self.assertIn(node.name, workers)
        self.assertEqual(workers[node.name]["ansible_host"], "192.168.1.50")

    def test_remove_node_removes_from_inventory(self):
        node = add_node(
            cluster=self.cluster,
            name="manager-node",
            ip="192.168.1.60",
            role="manager",
            validate_host=False
        )
        
        # Verify it exists in inventory
        mgr = InventoryManager(temp_inventory_path)
        inv_data = mgr._load()
        managers = inv_data["all"]["children"]["clusters"]["children"]["testcluster"]["children"]["testcluster_managers"]["hosts"]
        self.assertIn(node.name, managers)

        # Remove the node
        remove_node(cluster=self.cluster, node=node)

        # Verify it is deleted from DB
        self.assertFalse(Node.objects.filter(id=node.id).exists())

        # Verify it is deleted from inventory
        inv_data = mgr._load()
        managers = inv_data["all"]["children"]["clusters"]["children"]["testcluster"]["children"]["testcluster_managers"]["hosts"]
        self.assertNotIn(node.name, managers)

    @patch("inventory_manager.sub.run")
    @patch("inventory_manager.socket.create_connection")
    def test_validate_host_success(self, mock_socket, mock_sub_run):
        # Mock success for ping and socket connect
        mock_sub_run.return_value = MagicMock(returncode=0)
        
        mgr = InventoryManager(temp_inventory_path)
        # Calling _validate_host directly should return True
        self.assertTrue(mgr._validate_host("192.168.1.100"))
        
        # Assert ping is called
        mock_sub_run.assert_called_once()
        # Assert socket connect is called on port 22
        mock_socket.assert_called_once_with(("192.168.1.100", 22), timeout=3)

    @patch("inventory_manager.sub.run")
    @patch("inventory_manager.socket.create_connection")
    def test_validate_host_ping_failure(self, mock_socket, mock_sub_run):
        # Mock failure for ping
        mock_sub_run.return_value = MagicMock(returncode=1)
        
        mgr = InventoryManager(temp_inventory_path)
        with self.assertRaises(ValueError) as context:
            mgr._validate_host("192.168.1.100")
        
        self.assertIn("ping failed", str(context.exception))

    @patch("inventory_manager.sub.run")
    @patch("inventory_manager.socket.create_connection")
    def test_validate_host_ssh_failure(self, mock_socket, mock_sub_run):
        # Mock success for ping but failure for socket
        mock_sub_run.return_value = MagicMock(returncode=0)
        mock_socket.side_effect = Exception("Connection refused")
        
        mgr = InventoryManager(temp_inventory_path)
        with self.assertRaises(ValueError) as context:
            mgr._validate_host("192.168.1.100")
        
        self.assertIn("SSH not reachable", str(context.exception))

    def test_ansible_extra_vars_json_serialization(self):
        test_vars = {
            "target_cluster": "my test cluster",
            "kube_version": "1.35",
            "paths": "/some path/with spaces"
        }
        res = _to_extra_vars_str(test_vars)
        
        # Verify it parses back to the exact dict
        parsed = json.loads(res)
        self.assertEqual(parsed, test_vars)
