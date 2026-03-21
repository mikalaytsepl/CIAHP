#!/bin/bash

# set -euo pipefail # TODO: Remake cheking part to work with this line

REMOTE_USER="$1"
REMOTE_HOST="$2"
KEY_FILE="${3:-$HOME/.ssh/ansible.pub}" # Default key location

# Checks
if [[ ! -f "$KEY_FILE" ]]; then
    echo "Public Key not found: ${KEY_FILE}"
    exit 1
fi

PUB_KEY=$(cat "$KEY_FILE")

ssh -q "$REMOTE_USER@$REMOTE_HOST" "grep -qF '$PUB_KEY' ~/.ssh/authorized_keys 2>/dev/null"

LAST_STATUS=$?

if [[ "$LAST_STATUS" -eq 0 ]]; then
    echo "The public key is already present on $REMOTE_HOST"
else
    echo "Key not found. Propagating to $REMOTE_HOST"

    cat "$KEY_FILE" | ssh "$REMOTE_USER@$REMOTE_HOST" "
        mkdir -p ~/.ssh &&
        chmod 700 ~/.ssh &&
        cat >> ~/.ssh/authorized_keys &&
        chmod 600 ~/.ssh/authorized_keys
    "

    if [[ $? -eq 0 ]]; then
        echo "Key successfully added to $REMOTE_HOST"
    else
        echo "Failed to add the key to $REMOTE_HOST. Please check your password or connection"
        exit 1
    fi
fi