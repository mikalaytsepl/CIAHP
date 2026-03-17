#!/bin/bash

#regex to match 
ipv4_regex='^([0-9]{1,3}\.){3}[0-9]{1,3}$' 

try_propagate(){
    kubeadm token create --print-join-command
}

while getopts "h:" flag; do
    case $flag in
        h)
            if [[ $OPTARG =~ $ipv4_regex ]]; then
                try_propagate "$OPTARG"
            else
                echo "wrong ip address format"
                exit 1
            fi
        ;;
        *)
            echo "please provide IP address of the host"
            exit 1
        ;;
    esac
done
