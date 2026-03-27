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
    def __init__(self, path_to_inventory:str):
        self.inv_path_ = Path(path_to_inventory)
        
        # if path exists, do nothing. if not, mkdir -p basically
        self.inv_path_.parent.mkdir(parents=True,exist_ok=True)

        # same but for file at the end 
        self.inv_path_.touch(exist_ok=True)

        # if file is empty, initialize the structure: 
        if self.inv_path_.stat().st_size == 0:
            self._save({
                "all": {
                    "children": {
                        "managers": {"hosts": {}},
                        "workers": {"hosts": {}}
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
                ["nc", "-z", "-w", str(sub), ip, "22"],
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
            return yaml.safe_load(file)
    
    def _save(self, data):
        with open(self.inv_path_, 'w') as file:
            return yaml.safe_dump(data, file, sort_keys=False)
        
    def _get_group(self, inv, group):
        return inv["all"]["children"].setdefault(group, {"hosts": {}})["hosts"]
    # CRUD logic 

    def add_host(self, name: str, ip: str, group: Literal["managers", "workers"]):
            inv = self._load()

            hosts = self._get_group(inv, group)

            if name in hosts:
                raise ValueError(f"Host '{name}' already exists in {group}")

            hosts[name] = {"ansible_host": ip}

            self._save(inv)

    def delete_host(self, name: str):
        inv = self._load()

        for group in ["managers", "workers"]:
            hosts = self._get_group(inv, group)
            if name in hosts:
                del hosts[name]
                self._save(inv)
                return

        raise ValueError(f"Host '{name}' not found")

    def update_host(
        self,
        name: str,
        new_name: str | None = None,
        new_ip: str | None = None,
        new_group: Literal["managers", "workers"] | None = None
    ):
        inv = self._load()

        # Find host
        for group in ["managers", "workers"]:
            hosts = self._get_group(inv, group)

            if name in hosts:
                host_data = hosts[name]

                # Remove old entry
                del hosts[name]

                # Apply updates
                updated_name = new_name or name
                updated_ip = new_ip or host_data["ansible_host"]
                target_group = new_group or group

                target_hosts = self._get_group(inv, target_group)

                if updated_name in target_hosts:
                    raise ValueError(f"Host '{updated_name}' already exists in {target_group}")

                target_hosts[updated_name] = {"ansible_host": updated_ip}

                self._save(inv)
                return

        raise ValueError(f"Host '{name}' not found")
    

inventory = InventoryManager(path_to_inventory="/home/miko/CIAHP/ansible/inventory.yml")
inventory.delete_host("manager_test_1")
