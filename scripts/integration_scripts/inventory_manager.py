import re
import subprocess as sub
from pathlib import Path
from enum import Enum
from typing import Literal

import yaml

class HostType(str,Enum):
    MANAGER="manager"
    WORKER="worker"

class InventoryManager():
    def __init__(self, path_to_inventory: str):
        self.inv_path_ = Path(path_to_inventory)
        self.inv_path_.parent.mkdir(parents=True, exist_ok=True)
        self.inv_path_.touch(exist_ok=True)

        if self.inv_path_.stat().st_size == 0:
            self._save({
                "all": {
                    "children": {
                        "global_managers": {"children": {}},
                        "global_workers": {"children": {}},
                        "clusters": {"children": {}}
                    }
                }
            })

    # Help funcitons 
    @staticmethod
    def _validate_host(ip: str) -> bool:
        # validate if IP has the correct format in the first place
        IP_REGEX = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
        if not re.match(IP_REGEX,ip):
            raise ValueError(f"Invalid IP format: {ip}")
        
        # check if the host pings
        try:
            result = sub.run(
                ["ping", "-c", "1", "-W", '3', ip],
                stdout=sub.DEVNULL,
                stderr=sub.DEVNULL,
            )
            if result.returncode != 0:
                raise ValueError(f"Host {ip} is not reachable (ping failed)")
        except Exception as e:
            raise ValueError(f"Ping check failed: {e}")
        
        # check if ssh port is open 
        try: 
            result = sub.run(
                ["nc", "-z", "-w", str(3), ip, "22"],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise ValueError(f"SSH not reachable on {ip}")
        except Exception as e:
            raise ValueError(f'SSH check failed: {e}')
        
        # once all 3 checks pass, host is good to run scripts against
        return True

    def _load(self):
            with open(self.inv_path_, 'r') as file:
                return yaml.safe_load(file) or {}

    def _save(self, data):
        with open(self.inv_path_, 'w') as file:
            # sort keys false is to keep yaml human readable
            yaml.safe_dump(data, file, sort_keys=False, indent=4)

    # CRUD logic 

    def add_host(self, name: str, ip: str, cluster_name: str, role: Literal["managers", "workers"]):
            inv = self._load()
            
            # ensure global role exists 
            global_role_group = f"global_{role}"
            all_children = inv["all"]["children"]
            
            # setup chierarchy
            cluster_root = all_children["clusters"]["children"].setdefault(cluster_name, {"children": {}})
            role_group_name = f"{cluster_name}_{role}"
            
            # add specific rule group to the cluster
            cluster_root["children"].setdefault(role_group_name, {"hosts": {}})
            
            # link role group to the global group
            all_children[global_role_group]["children"].setdefault(role_group_name, {})

            # Add the actual host data
            host_list = cluster_root["children"][role_group_name]["hosts"]
            if name in host_list:
                print(f"Warning: Host {name} already exists in {role_group_name}. Updating IP.")
            
            host_list[name] = {"ansible_host": ip}

            self._save(inv)
            print(f"Successfully added {name} ({ip}) to {cluster_name} as a {role[:-1]}.")

    def delete_host(self, name: str, cluster_name: str, role: Literal["managers", "workers"]):
            inv = self._load()
            role_group = f"{cluster_name}_{role}"
            
            try:
                hosts = inv["all"]["children"]["clusters"]["children"][cluster_name]["children"][role_group]["hosts"]
                if name in hosts:
                    del hosts[name]
                    self._save(inv)
                    print(f"Deleted {name} from {cluster_name}")
                    return
            except KeyError:
                pass

            raise ValueError(f"Host '{name}' not found in {cluster_name} {role}")

    # get all hosts 
    def _find_host_location(self, inv, name):
        """Returns (cluster, role) if host exists, else (None, None)"""
        clusters = inv["all"]["children"]["clusters"]["children"]
        for c_name, c_data in clusters.items():
            for r_group, r_data in c_data["children"].items():
                if name in r_data.get("hosts", {}):
                    # derive role from a group name
                    role = "managers" if "managers" in r_group else "workers"
                    return c_name, role
        return None, None
    
    # gets full inventory and cluster name as arguments
    def get_cluster_resouces(self, inv, cluster_name: str) -> dict:
        try:
            # just scopes to children of a specific clsuter (the main goal is to do that IN PLACE)
            return inv["all"]["children"]["clusters"]["children"][cluster_name]["children"]
        except KeyError:
            raise ValueError(f"Cluster '{cluster_name}' not found")
        
    def truncate_cluster_resources(self,cluster_name:str) -> None:
        inv = self._load()
        cluster_resources = self.get_cluster_resouces(inv,cluster_name)
        
        # clear out resources of managers and workers hosts
        cluster_resource_groups = (f"{cluster_name}_managers",f"{cluster_name}_workers")
        for resoruce_group in cluster_resource_groups:
            cluster_resources[resoruce_group]['hosts'].clear()
        self._save(inv)

    

if __name__ == '__main__':
    inventory = InventoryManager('/home/miko/CIAHP/ansible/inventory.yml')

    inventory.truncate_cluster_resources("my-cluster")

    inventory.add_host("new-worker","172.16.86.131","my-cluster","workers")
    inventory.add_host("new-manager","172.16.86.130","my-cluster","managers")
