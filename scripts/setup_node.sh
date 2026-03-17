# Guard: prevent accidental direct execution.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "setup_node.sh is a shared library — source it from create_manager.sh or create_worker.sh."
  exit 1
fi

# ─── Helpers ─────────────────────────────────────────────────────────────────
CURRENT_STEP="init"

log()  { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
skip() { log "  SKIP — $*"; }
ok()   { log "  OK   — $*"; }
die()  { log "  ERR  — $*"; exit 1; }
warn() { log "  WARN — $*"; }

trap 'log "FAILED at step: ${CURRENT_STEP} (line ${LINENO}) — check ${LOG_FILE}"' ERR

step() { CURRENT_STEP="$1"; log "──── Step: ${CURRENT_STEP}"; }

check_root()     { [[ $EUID -eq 0 ]] || die "Run this script as root (sudo)."; }
pkg_installed()  { dpkg -l "$1" 2>/dev/null | grep -q '^ii'; }
pkg_version_ok() { dpkg -l "$1" 2>/dev/null | awk '/^ii/{print $3}' | grep -q "^${2}"; }

# ─── Preflight ───────────────────────────────────────────────────────────────
check_root
mkdir -p "$(dirname "$LOG_FILE")"

# ─── Version validation and resolution ───────────────────────────────────────
step "validate-version"
if ! [[ "${KUBE_VERSION}" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
  die "KUBE_VERSION '${KUBE_VERSION}' is not a valid semver (expected e.g. 1.35 or 1.35.0)."
fi

# Repo URLs always use the X.Y minor path.
KUBE_MINOR=$(echo "${KUBE_VERSION}" | cut -d. -f1,2)
RELEASE_URL="https://pkgs.k8s.io/core:/stable:/v${KUBE_MINOR}/deb/Release"

# -L follows redirects; the repo returns 302 -> CDN for valid versions.
HTTP_STATUS=$(curl -L -o /dev/null -s -w "%{http_code}" --max-time 15 "${RELEASE_URL}" || echo "000")
if [[ "${HTTP_STATUS}" == "200" ]]; then
  ok "Version v${KUBE_MINOR} confirmed available in apt repo."
elif [[ "${HTTP_STATUS}" == "000" ]]; then
  die "Could not reach ${RELEASE_URL} (network error or timeout). Check connectivity."
else
  LATEST=$(curl -fsSL --max-time 10 https://dl.k8s.io/release/stable.txt 2>/dev/null \
    | sed 's/^v//' | cut -d. -f1,2 || echo "unknown")
  die "Version v${KUBE_MINOR} not found in apt repo (HTTP ${HTTP_STATUS})." \
      " Latest stable minor: ${LATEST}. Re-run with: sudo bash $0 ${LATEST}"
fi

# Resolve X.Y -> X.Y.Z — kubeadm init --kubernetes-version rejects bare minor versions.
if [[ "${KUBE_VERSION}" =~ ^[0-9]+\.[0-9]+$ ]]; then
  KUBE_VERSION_FULL=$(curl -fsSL --max-time 10 \
    "https://dl.k8s.io/release/stable-${KUBE_VERSION}.txt" 2>/dev/null \
    | sed 's/^v//' || echo "")
  [[ -n "${KUBE_VERSION_FULL}" ]] \
    || die "Could not resolve full patch version for ${KUBE_VERSION} from dl.k8s.io."
  ok "Resolved v${KUBE_VERSION} -> v${KUBE_VERSION_FULL}."
  KUBE_VERSION="${KUBE_VERSION_FULL}"
fi

# ─── 1. Disable swap ─────────────────────────────────────────────────────────
step "disable-swap"
if swapon --show | grep -q .; then
  swapoff -a
  ok "Swap turned off."
else
  skip "Swap already inactive."
fi

if grep -qE '^\s*[^#].*\bswap\b' /etc/fstab; then
  sed -i '/^\s*[^#].*\bswap\b/ s/^/# /' /etc/fstab
  ok "Swap commented out in /etc/fstab."
else
  skip "/etc/fstab swap already disabled."
fi

# ─── 2. Kernel modules ───────────────────────────────────────────────────────
step "kernel-modules"
MODULES_CONF=/etc/modules-load.d/containerd.conf
EXPECTED_MODULES=$'overlay\nbr_netfilter'

if [[ ! -f "$MODULES_CONF" ]] || [[ "$(cat "$MODULES_CONF")" != "$EXPECTED_MODULES" ]]; then
  printf '%s\n' overlay br_netfilter > "$MODULES_CONF"
  ok "Module persistence file written."
else
  skip "Module persistence file already correct."
fi

for mod in overlay br_netfilter; do
  if lsmod | grep -q "^${mod}"; then
    skip "Module ${mod} already loaded."
  else
    modprobe "$mod"
    ok "Loaded module: ${mod}."
  fi
done

# ─── 3. Sysctl ───────────────────────────────────────────────────────────────
step "sysctl"
cat > /etc/sysctl.d/kubernetes.conf <<EOF
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables  = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system >> "$LOG_FILE" 2>&1
ok "Sysctl params applied."

# ─── 4. Containerd ───────────────────────────────────────────────────────────
step "containerd-repo"
if [[ ! -f /etc/apt/trusted.gpg.d/docker.gpg ]]; then
  apt-get install -y -qq curl gnupg2 software-properties-common \
    apt-transport-https ca-certificates >> "$LOG_FILE" 2>&1
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmour -o /etc/apt/trusted.gpg.d/docker.gpg
  add-apt-repository -y \
    "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    >> "$LOG_FILE" 2>&1
  apt-get update -qq
  ok "Docker apt repo added."
else
  skip "Docker apt repo already present."
fi

step "containerd-install"
if pkg_installed containerd.io; then
  skip "containerd.io already installed."
else
  apt-get install -y containerd.io >> "$LOG_FILE" 2>&1
  ok "containerd.io installed."
fi

step "containerd-config"
if [[ ! -f /etc/containerd/config.toml ]] \
    || ! grep -q 'SystemdCgroup = true' /etc/containerd/config.toml; then
  containerd config default | tee /etc/containerd/config.toml > /dev/null
  sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
  systemctl restart containerd
  ok "containerd config regenerated with SystemdCgroup=true."
else
  skip "containerd already configured with SystemdCgroup=true."
fi

systemctl enable containerd >> "$LOG_FILE" 2>&1
systemctl is-active --quiet containerd \
  || die "containerd failed to start — run: journalctl -u containerd"
ok "containerd is active."

# ─── 5. Kubernetes packages ──────────────────────────────────────────────────
step "k8s-repo"
K8S_KEYRING=/etc/apt/keyrings/kubernetes-apt-keyring.gpg
K8S_SOURCES=/etc/apt/sources.list.d/kubernetes.list

if [[ ! -f "$K8S_KEYRING" ]]; then
  mkdir -p /etc/apt/keyrings
  curl -fsSL "https://pkgs.k8s.io/core:/stable:/v${KUBE_MINOR}/deb/Release.key" \
    | gpg --dearmor -o "$K8S_KEYRING"
  ok "Kubernetes apt keyring added."
else
  skip "Kubernetes apt keyring already present."
fi

if [[ ! -f "$K8S_SOURCES" ]]; then
  echo "deb [signed-by=${K8S_KEYRING}] \
https://pkgs.k8s.io/core:/stable:/v${KUBE_MINOR}/deb/ /" \
    | tee "$K8S_SOURCES" > /dev/null
  apt-get update -qq
  ok "Kubernetes apt source added."
else
  skip "Kubernetes apt source already present."
fi

step "k8s-packages"
# Manager needs kubectl; workers don't. Caller sets INSTALL_KUBECTL=true to opt in.
INSTALL_KUBECTL="${INSTALL_KUBECTL:-false}"
PKGS_TO_CHECK=(kubelet kubeadm)
PKGS_TO_INSTALL=("kubelet=${KUBE_VERSION}*" "kubeadm=${KUBE_VERSION}*")
PKGS_TO_HOLD=(kubelet kubeadm)
if [[ "${INSTALL_KUBECTL}" == "true" ]]; then
  PKGS_TO_CHECK+=(kubectl)
  PKGS_TO_INSTALL+=("kubectl=${KUBE_VERSION}*")
  PKGS_TO_HOLD+=(kubectl)
fi

NEED_INSTALL=false
for pkg in "${PKGS_TO_CHECK[@]}"; do
  if pkg_version_ok "$pkg" "${KUBE_VERSION}"; then
    skip "${pkg} already at v${KUBE_VERSION}."
  else
    NEED_INSTALL=true
  fi
done

if [[ "${NEED_INSTALL}" == true ]]; then
  apt-mark unhold "${PKGS_TO_HOLD[@]}" 2>/dev/null || true
  apt-get install -y "${PKGS_TO_INSTALL[@]}" >> "$LOG_FILE" 2>&1
  ok "Kubernetes packages installed at v${KUBE_VERSION}."
fi
apt-mark hold "${PKGS_TO_HOLD[@]}" >> "$LOG_FILE" 2>&1
ok "${PKGS_TO_HOLD[*]} held at v${KUBE_VERSION}."