#!/bin/bash
set -euo pipefail

# ─── Config ──────────────────────────────────────────────────────────────────
KUBE_VERSION="${1:-1.35}"
JOIN_CMD=""
JOIN_FILE=""
LOG_FILE="/var/log/k8s-worker-setup.log"
INSTALL_KUBECTL="false"  # workers don't need kubectl

# ─── Argument parsing ────────────────────────────────────────────────────────
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --join-cmd)  JOIN_CMD="$2";  shift 2 ;;
    --join-file) JOIN_FILE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# ─── Common node setup (swap, modules, sysctl, containerd, k8s packages) ─────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=setup_node.sh
source "${SCRIPT_DIR}/setup_node.sh"

# ─── Banner ───────────────────────────────────────────────────────────────────
log "════════════════════════════════════════════════════════"
log "  Worker setup  |  k8s v${KUBE_VERSION}"
log "════════════════════════════════════════════════════════"

# ─── 6. Resolve join command ─────────────────────────────────────────────────
step "resolve-join-cmd"
if [[ -n "${JOIN_CMD}" ]]; then
  log "Using join command from --join-cmd argument."
elif [[ -n "${JOIN_FILE}" ]]; then
  [[ -f "${JOIN_FILE}" ]] || die "Join file not found: ${JOIN_FILE}"
  JOIN_CMD=$(grep -E '^kubeadm join' "${JOIN_FILE}" | head -n1)
  [[ -n "${JOIN_CMD}" ]] || die "No 'kubeadm join' line found in ${JOIN_FILE}"
  ok "Join command read from ${JOIN_FILE}."
else
  log "No join command provided — interactive fallback."
  log "(On the manager: kubeadm token create --print-join-command)"
  echo ""
  read -rp "kubeadm join command: " JOIN_CMD
  [[ "${JOIN_CMD}" == kubeadm\ join* ]] \
    || die "Invalid join command — must start with 'kubeadm join'."
fi

# ─── 7. Join the cluster ─────────────────────────────────────────────────────
step "kubeadm-join"
if [[ -f /etc/kubernetes/kubelet.conf ]] \
    && systemctl is-active --quiet kubelet; then
  skip "Node already joined (kubelet.conf present and kubelet is active)."
else
  if [[ -f /etc/kubernetes/kubelet.conf ]]; then
    log "Stale kubelet.conf found but kubelet is not active — resetting before retry."
    kubeadm reset -f >> "$LOG_FILE" 2>&1 \
      || die "kubeadm reset failed — manual cleanup required."
    ok "kubeadm reset complete."
  fi

  eval "${JOIN_CMD}" 2>&1 | tee -a "$LOG_FILE" \
    || die "kubeadm join failed — check the token hasn't expired and manager is reachable."

  sleep 3
  systemctl is-active --quiet kubelet \
    || die "kubelet is not active after join — run: journalctl -u kubelet"
  ok "Node joined cluster and kubelet is active."
fi

# ─── Done ────────────────────────────────────────────────────────────────────
log ""
log "════════════════════════════════════════════════════════"
log "  Worker setup complete!"
log "  Verify from the manager node:"
log "    kubectl get nodes"
log "════════════════════════════════════════════════════════"