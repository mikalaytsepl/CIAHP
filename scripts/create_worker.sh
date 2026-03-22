#!/bin/bash

# # privilege check
if [[ $EUID -ne 0 ]]; then
    echo "Run this script with sudo"
    exit 1
fi

# prevent interactive prompting
export DEBIAN_FRONTEND=noninteractive

# check if general setup succeeded 
if ! command -v kubelet &> /dev/null; then
    echo "Kubelet binary not found! Was initial setup executed?"
    exit 1
fi

if ! systemctl is-enabled --quiet kubelet; then
    echo "Kubelet service not enabled. Check setup logs!"
    exit 1
fi

# connectivity check
declare MANAGER_IP="192.168.100.12"

if ping -q -c 5 -w 10 "$MANAGER_IP" > /dev/null; then
    echo "Ping to manager successful"
else
    echo "Can't reach manager at $MANAGER_IP, aborting"
    exit 1
fi

echo "Base components ready. Waiting for Ansible to provide join command."