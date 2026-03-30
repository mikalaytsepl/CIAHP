#!/bin/bash

# # privilege check
if [[ $EUID -ne 0 ]]; then
    echo "Run this script with sudo"
    exit 1
fi

# prevent interactive prompting
export DEBIAN_FRONTEND=noninteractive

# check if general setup succeeded
if [ -f /etc/kubernetes/kubelet.conf ]; then
    echo "Node is already part of the cluster (/etc/kubernetes/kubelet.conf exists)."
    echo "Skipping join command."
    exit 0 # Exit with 0 (Success) so Ansible doesn't register a failure!
fi

if ! command -v kubelet &> /dev/null; then
    echo "Kubelet binary not found! Was initial setup executed?"
    exit 1
fi

if ! systemctl is-enabled --quiet kubelet; then
    echo "Kubelet service not enabled. Check setup logs!"
    exit 1
fi

# connectivity check
declare MANAGER_IP="$1"

if ping -q -c 5 -w 10 "$MANAGER_IP" > /dev/null; then
    echo "Ping to manager successful"
else
    echo "Can't reach manager at $MANAGER_IP, aborting"
    exit 1
fi

echo "Base components ready. Waiting for Ansible to provide join command."

JOIN_COMMAND="$2"

if [ -z "$JOIN_COMMAND" ]; then
    echo "Error: No join command provided!"
    exit 1
fi

echo "Executing join command..."
eval "$JOIN_COMMAND"