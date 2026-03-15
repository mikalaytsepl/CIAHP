#!/bin/bash

# checks if script has been started with root priv
if [[ $EUID -ne 0 ]]; then
    echo "Run this script with sudo"
    exit 1
fi

# prevent interacive prompting for apt stuff
export DEBIAN_FRONTEND=noninteractive

declare KUBE_VERSION="1.35"
declare CLUSTER_CID="192.168.123.0/16"



# switch swap off and distable it in fstab
swapoff -a 
sed -i '/^[^#]/s/^\(\S\+\s\+\S\+\s\+\)swap/\1swap/; /^[^#].*\s\+swap\s\+/s/^/# /' /etc/fstab


#tee overwrites the things anyway so no point checkng
tee /etc/modules-load.d/containerd.conf <<EOF
overlay
br_netfilter
EOF

# load added kernel modules
modprobe overlay
modprobe br_netfilter

#modify kubernetes conf file
tee /etc/sysctl.d/kubernetes.conf <<EOT
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOT
sysctl --system


# install and dearmor support packages for docker
apt update
apt install -y curl gnupg2 software-properties-common apt-transport-https ca-certificates
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/trusted.gpg.d/docker.gpg
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"

# and packages for containerd
apt update
apt install -y containerd.io

#make sure not to rerun that every time (idempotency or smth)
if [ ! -f /etc/containerd/config.toml ]; then
    containerd config default > /etc/containerd/config.toml
fi

sed -i 's/SystemdCgroup \= false/SystemdCgroup \= true/g' /etc/containerd/config.toml
systemctl restart containerd
systemctl enable containerd


# get install kubernetes based on the version provided or default
mkdir -p /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v$KUBE_VERSION/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v$KUBE_VERSION/deb/ /" | tee /etc/apt/sources.list.d/kubernetes.list
apt update
apt install -y kubelet kubeadm kubectl

systemctl enable kubelet # it's rare for it not to enable automatically but better safe then troubleshoot

# make sure not to run this thing 2 times if stuff exists already
if [ ! -f /etc/kubernetes/admin.conf ]; then
    kubeadm init --pod-network-cidr=$CLUSTER_CID
fi

# wait for the management plane to initiate in order to prevent race condition
until kubectl get nodes >/dev/null 2>&1; do
    sleep 2
done

# install and apply CNI (calico)
KUBECONFIG=/etc/kubernetes/admin.conf kubectl apply -f \
https://raw.githubusercontent.com/projectcalico/calico/v3.28.0/manifests/calico.yaml

# delegate ownership to the real user after the install 
REAL_USER=${SUDO_USER:-$USER}
REAL_HOME=$(eval echo "~$REAL_USER")

mkdir -p "$REAL_HOME/.kube"
cp /etc/kubernetes/admin.conf "$REAL_HOME/.kube/config"
chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.kube/config"

# lock versions after all the stuff is installed in order for the package updates not to break up the cluster
apt-mark hold kubelet kubeadm kubectl
