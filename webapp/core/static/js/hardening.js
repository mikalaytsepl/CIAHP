/* CIAHP — hardening.js */

document.addEventListener('DOMContentLoaded', () => {

  /* ── CSRF ── */
  function getCsrf() {
    const t = document.querySelector('[name=csrfmiddlewaretoken]');
    return t ? t.value : '';
  }

  const clusterSel = document.getElementById('hd-cluster');
  const nodeSel    = document.getElementById('hd-node');
  const nodeHint   = document.getElementById('hd-node-hint');

  const statusEl   = document.getElementById('hd-status');
  const metaEl     = document.getElementById('hd-meta');
  const consoleEl  = document.getElementById('hd-console');

  let pollTimer = null;

  /* ── CLUSTER → NODE FILTERING ── */
  function refreshNodes() {
    const cluster = clusterSel.value;
    let visible = 0;
    nodeSel.querySelectorAll('option[data-cluster]').forEach(opt => {
      const match = opt.dataset.cluster === cluster;
      opt.hidden = !match;
      if (match) visible++;
    });
    nodeSel.value = '';   // default back to "whole cluster"
    nodeHint.textContent = visible
      ? `${visible} węzł(ów) w klastrze · puste = cały klaster`
      : 'Brak węzłów w tym klastrze';
  }

  clusterSel.addEventListener('change', refreshNodes);

  /* ── RESULT PANEL HELPERS ── */
  function setStatus(text, kind) {
    if (!kind) { statusEl.hidden = true; return; }
    statusEl.hidden = false;
    statusEl.dataset.status = kind;
    statusEl.textContent = text;
  }

  function showError(msg) {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    setStatus(null);
    metaEl.style.color = 'var(--red)';
    metaEl.textContent = msg;
    consoleEl.hidden = true;
  }

  function showInfo(msg) {
    metaEl.style.color = '';
    metaEl.textContent = msg;
  }

  function markInvalid(el) {
    el.classList.add('invalid');
    setTimeout(() => el.classList.remove('invalid'), 1500);
  }

  /* ── OPERATION POLLING ── */
  function pollOperation(opId, label) {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    setStatus('Running', 'running');
    showInfo(`${label} — operacja w toku (ID: ${opId})`);
    consoleEl.hidden = false;
    consoleEl.textContent = 'Oczekiwanie na pierwsze logi…';

    const tick = async () => {
      try {
        const r = await fetch(`/api/operations/${opId}/`);
        if (!r.ok) return;
        const op = await r.json();

        const out = (op.stdout || '').trimEnd();
        const err = (op.stderr || '').trimEnd();
        consoleEl.textContent =
          (out || '(brak stdout)') + (err ? `\n\n── STDERR ──\n${err}` : '');
        consoleEl.scrollTop = consoleEl.scrollHeight;

        if (op.status === 'success' || op.status === 'failed') {
          clearInterval(pollTimer); pollTimer = null;
          if (op.status === 'success') {
            setStatus('Success', 'success');
            showInfo(`${label} — zakończono pomyślnie (rc=${op.return_code}).`);
          } else {
            setStatus('Failed', 'failed');
            showInfo(`${label} — zakończono błędem (rc=${op.return_code}). Sprawdź logi poniżej.`);
          }
        }
      } catch (e) {
        /* transient network error — keep polling */
      }
    };

    tick();
    pollTimer = setInterval(tick, 2000);
  }

  /* ── DISPATCH ── */
  async function runAction(btn) {
    const cluster  = clusterSel.value;
    const endpoint = btn.dataset.endpoint;
    const nodeReq  = btn.dataset.node;        // optional | required | none
    const userId   = btn.dataset.user;        // id of target_user input (optional)
    const label    = btn.dataset.label || endpoint;
    const node     = nodeSel.value;

    if (!cluster) { showError('Najpierw wybierz klaster.'); markInvalid(clusterSel); return; }

    const body = {};

    if (nodeReq === 'required') {
      if (!node) { showError(`Akcja „${label}" wymaga wskazania konkretnego węzła.`); markInvalid(nodeSel); return; }
      body.target_node = node;
    } else if (nodeReq === 'optional' && node) {
      body.target_node = node;
    }

    if (userId) {
      const userEl = document.getElementById(userId);
      const user = (userEl.value || '').trim();
      if (!user) { showError(`Akcja „${label}" wymaga podania nazwy użytkownika.`); markInvalid(userEl); return; }
      body.target_user = user;
    }

    if (endpoint === 'bootstrap-ansible') {
      const initialEl = document.getElementById('hd-initial-user');
      const initial = (initialEl.value || '').trim();
      if (initial) body.initial_user = initial;
    }

    btn.disabled = true;
    const orig = btn.textContent;
    btn.textContent = 'Wysyłanie…';

    try {
      const resp = await fetch(`/api/clusters/${cluster}/actions/${endpoint}`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body:    JSON.stringify(body),
      });
      const data = await resp.json().catch(() => ({}));

      if (resp.ok && data.operation_id) {
        pollOperation(data.operation_id, label);
      } else {
        showError(`Błąd (${resp.status}): ${data.detail || resp.statusText}`);
      }
    } catch (e) {
      showError(`Błąd połączenia: ${e.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = orig;
    }
  }

  document.querySelectorAll('.run-btn').forEach(btn => {
    btn.addEventListener('click', () => runAction(btn));
  });

});
