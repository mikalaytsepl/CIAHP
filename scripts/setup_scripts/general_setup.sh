#!/bin/bash

# privilege check
if [[ $EUID -ne 0 ]]; then
    echo "Run this script with sudo"
    exit 1
fi

# prevent interactive prompting
export DEBIAN_FRONTEND=noninteractive

# make it via arguments later on
declare KUBE_VERSION="1.35"

# switch swap off and modify fstab swap partition
swapoff -a 
sed -i '/^[^#]/s/^\(\S\+\s\+\S\+\s\+\)swap/\1swap/; /^[^#].*\s\+swap\s\+/s/^/# /' /etc/fstab

# kernel modules setup
mkdir -p /etc/modules-load.d
tee /etc/modules-load.d/containerd.conf <<EOF
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter

# modify kubernetes sysctl config
tee /etc/sysctl.d/kubernetes.conf <<EOT
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOT
sysctl --system

# Install support packages 
apt update
apt install -y curl gnupg2 software-properties-common apt-transport-https ca-certificates

# install and configure containerd
apt install -y containerd

mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
# make sure CRI is not disabed
sed -i 's/disabled_plugins = \["cri"\]//' /etc/containerd/config.toml

systemctl restart containerd
systemctl enable containerd

# install kubernetes components
mkdir -p /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v$KUBE_VERSION/deb/Release.key | gpg --yes --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v$KUBE_VERSION/deb/ /" | tee /etc/apt/sources.list.d/kubernetes.list

apt update
# Workers generally don't need kubectl, but keeping it for consistency/debugging
apt install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

systemctl enable kubelet

echo "Initial setup is complete"