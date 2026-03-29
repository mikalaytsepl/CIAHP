#!/bin/bash

# checks if script has been started with root priv
if [[ $EUID -ne 0 ]]; then
    echo "Run this script with sudo"
    exit 1
fi

# prevent interacive prompting for apt stuff
export DEBIAN_FRONTEND=noninteractive

# cluster address range 
declare CLUSTER_CID="192.168.123.0/16"


# Check if initial setup script has been done and finished correctly
# Verify the binary exists
if ! command -v kubelet &> /dev/null; then
    echo "Kubelet binary not found!"
    echo "R u sure intial setup was executed?"
    exit 1
fi

# Verify the service is enabled (will start on next boot/trigger)
if systemctl is-enabled --quiet kubelet; then
    echo "Base components ready for kubeadm."
else
    echo "Service not enabled."
    echo "Check setup! It may have failed!"
    exit 1
fi

# make sure not to run this thing 2 times if stuff exists already
if [ ! -f /etc/kubernetes/admin.conf ]; then
    kubeadm init --pod-network-cidr=$CLUSTER_CID
fi

# delegate ownership to the real user after the install 
REAL_USER=${SUDO_USER:-$USER}
REAL_HOME=$(eval echo "~$REAL_USER")

mkdir -p "$REAL_HOME/.kube"
cp /etc/kubernetes/admin.conf "$REAL_HOME/.kube/config"
chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.kube/config"

# wait for the management plane to initiate in order to prevent race condition
until sudo -u $REAL_USER kubectl get nodes >/dev/null 2>&1; do
    sleep 2
done

# install and apply CNI (calico)
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f \
https://raw.githubusercontent.com/projectcalico/calico/v3.28.0/manifests/calico.yaml

# lock versions after all the stuff is installed in order for the package updates not to break up the cluster
# apt-mark hold kubelet kubeadm kubectl

echo "Waiting for control plane pods..."

# Control plane (static pods)
sudo -u $REAL_USER kubectl wait --for=condition=Ready pod -l component=etcd -n kube-system --timeout=300s
sudo -u $REAL_USER kubectl wait --for=condition=Ready pod -l component=kube-apiserver -n kube-system --timeout=300s
sudo -u $REAL_USER kubectl wait --for=condition=Ready pod -l component=kube-controller-manager -n kube-system --timeout=300s
sudo -u $REAL_USER kubectl wait --for=condition=Ready pod -l component=kube-scheduler -n kube-system --timeout=300s

echo "Control plane is ready"

echo "Waiting for CNI ..."

# Calico
sudo -u $REAL_USER kubectl wait --for=condition=Ready pod -l k8s-app=calico-node -n kube-system --timeout=300s
sudo -u $REAL_USER kubectl wait --for=condition=Ready pod -l k8s-app=calico-kube-controllers -n kube-system --timeout=300s

echo "CNI is ready"

echo "Waiting for DNS ..."

# CoreDNS
sudo -u $REAL_USER kubectl wait --for=condition=Ready pod -l k8s-app=kube-dns -n kube-system --timeout=300s

echo "DNS is ready"

echo "All systems ready. Cluster is operational"
