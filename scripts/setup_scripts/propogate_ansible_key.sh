#!/bin/bash

REMOTE_USER="$1"
REMOTE_HOST="$2"
KEY_FILE="${3:-$HOME/.ssh/id_rsa.pub}"

if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
    echo "Usage: $0 <remote_sudo_user> <host> [key_file]"
    exit 1
fi

if [[ ! -f "$KEY_FILE" ]]; then
    echo "Error: key not found at ${KEY_FILE}"
    exit 1
fi

# read pubkey into variable
PUB_KEY=$(cat "$KEY_FILE")

echo "Connecting to ${REMOTE_HOST} to setup ansible user..."

# -t forcing a terminal to ask for a sudo password 
ssh -t "${REMOTE_USER}@${REMOTE_HOST}" "sudo bash -c '
    # Create user if missing
    if ! id \"ansible\" &>/dev/null; then
        adduser --disabled-password --gecos \"\" ansible
        usermod -aG sudo ansible
        echo \"ansible ALL=(ALL) NOPASSWD:ALL\" > /etc/sudoers.d/ansible
    fi

    # Manual injection of ssh key into the right place
    mkdir -p /home/ansible/.ssh
    echo \"$PUB_KEY\" > /home/ansible/.ssh/authorized_keys
    
    # Set permissions right
    chown -R ansible:ansible /home/ansible/.ssh
    chmod 700 /home/ansible/.ssh
    chmod 600 /home/ansible/.ssh/authorized_keys
    
    echo \"Bootstrap complete. User ansible is ready with NOPASSWD sudo.\"
'"