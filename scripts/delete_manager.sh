#!/bin/bash

# ensure script runs as root
if [[ $EUID -ne 0 ]]; then
    echo "Run this script with sudo"
    exit 1
fi

REAL_USER=${SUDO_USER:-$USER}
REAL_HOME=$(eval echo "~$REAL_USER")

echo "Checking cluster state..."

# ensure kubernetes exists before checking
if [ -f /etc/kubernetes/admin.conf ]; then

    # count nodes in cluster
    NODE_COUNT=$(KUBECONFIG=/etc/kubernetes/admin.conf kubectl get nodes --no-headers 2>/dev/null | wc -l)

    if [ "$NODE_COUNT" -gt 1 ]; then
        echo "Cluster still has worker nodes."
        echo "Please remove or drain them before deleting the manager."
        echo "Nodes currently in cluster:"
        KUBECONFIG=/etc/kubernetes/admin.conf kubectl get nodes
        exit 1
    fi

fi

echo "Resetting kubeadm cluster..."

kubeadm reset -f

echo "Removing Kubernetes directories..."

rm -rf /etc/kubernetes
rm -rf /var/lib/etcd
rm -rf /var/lib/kubelet
rm -rf /etc/cni
rm -rf /opt/cni

echo "Cleaning networking rules..."

# no iptebles on instances for now
# iptables -F
# iptables -t nat -F
# iptables -t mangle -F
# iptables -X


echo "Removing kubeconfig from user..."

rm -rf "$REAL_HOME/.kube"

echo "Removing containerd configuration..."

rm -rf /etc/containerd
systemctl stop containerd
systemctl disable containerd

echo "Removing Kubernetes packages..."

apt-mark unhold kubelet kubeadm kubectl 2>/dev/null
apt remove -y kubelet kubeadm kubectl kubernetes-cni containerd
apt autoremove -y 

echo "Removing Kubernetes apt repository..."

rm -f /etc/apt/sources.list.d/kubernetes.list
rm -f /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo "Reloading systemd..."

systemctl daemon-reload

echo "Cleanup complete."
echo "Node is now back to a clean state."