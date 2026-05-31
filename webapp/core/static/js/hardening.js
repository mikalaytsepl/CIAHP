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
  const tabsEl     = document.getElementById('hd-tabs');

  /* ── MULTI-OP STATE ──
   * ops:      opId -> { id, label, endpoint, cluster, node, user, startedAt,
   *                     status, stdout, stderr, returnCode, pollTimer, tabEl }
   * Source of truth for status/logs is the backend; localStorage only stores
   * metadata (id + label + when) so we know which ops to re-attach to on load.
   */
  const STORAGE_KEY = 'ciahp:ops';
  const STORAGE_MAX = 10;
  const STORAGE_TTL_MS = 24 * 60 * 60 * 1000;   // 24h
  const POLL_INTERVAL_MS = 2000;

  const ops = new Map();
  let activeOpId = null;

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

  /* ── LOCAL STORAGE (metadata only) ── */
  function storageRead() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return [];
      const cutoff = Date.now() - STORAGE_TTL_MS;
      return arr.filter(o => o && o.id && (o.startedAt || 0) >= cutoff);
    } catch (e) { return []; }
  }

  function storageWrite() {
    const arr = Array.from(ops.values())
      .sort((a, b) => b.startedAt - a.startedAt)
      .slice(0, STORAGE_MAX)
      .map(o => ({
        id: o.id, label: o.label, endpoint: o.endpoint,
        cluster: o.cluster, node: o.node, user: o.user,
        startedAt: o.startedAt,
      }));
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(arr)); } catch (e) { /* quota */ }
  }

  /* ── TAB / VIEW RENDERING ── */
  function timeLabel(ts) {
    const d = new Date(ts);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function tabLabel(op) {
    const where = op.node || op.user || op.cluster || '';
    const short = where ? ` · ${where}` : '';
    return `${op.label} ${timeLabel(op.startedAt)}${short}`;
  }

  function renderTab(op) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'result-tab';
    btn.dataset.opId = op.id;

    const dot = document.createElement('span');
    dot.className = 'result-tab__dot';
    dot.dataset.status = op.status || 'running';

    const lbl = document.createElement('span');
    lbl.className = 'result-tab__label';
    lbl.textContent = tabLabel(op);

    const close = document.createElement('span');
    close.className = 'result-tab__close';
    close.textContent = '×';
    close.title = 'Zamknij';
    close.addEventListener('click', (e) => { e.stopPropagation(); closeOp(op.id); });

    btn.append(dot, lbl, close);
    btn.addEventListener('click', () => setActive(op.id));
    op.tabEl = btn;
    tabsEl.appendChild(btn);
    tabsEl.hidden = false;
  }

  function updateTab(op) {
    if (!op.tabEl) return;
    const dot = op.tabEl.querySelector('.result-tab__dot');
    if (dot) dot.dataset.status = op.status || 'running';
  }

  function renderActive() {
    tabsEl.querySelectorAll('.result-tab').forEach(t => {
      t.classList.toggle('is-active', t.dataset.opId === activeOpId);
    });

    if (!activeOpId) {
      setStatus(null);
      showInfo('Wybierz klaster i uruchom akcję — postęp i logi pojawią się tutaj.');
      consoleEl.hidden = true;
      return;
    }

    const op = ops.get(activeOpId);
    if (!op) return;

    if (op.status === 'running') {
      setStatus('Running', 'running');
      showInfo(`${op.label} — operacja w toku (ID: ${op.id}).`);
    } else if (op.status === 'success') {
      setStatus('Success', 'success');
      showInfo(`${op.label} — zakończono pomyślnie (rc=${op.returnCode}).`);
    } else if (op.status === 'failed') {
      setStatus('Failed', 'failed');
      showInfo(`${op.label} — zakończono błędem (rc=${op.returnCode}). Sprawdź logi poniżej.`);
    } else {
      setStatus(op.status, 'running');
      showInfo(`${op.label} — status: ${op.status}.`);
    }

    const out = (op.stdout || '').trimEnd();
    const err = (op.stderr || '').trimEnd();
    const text = (out || (op.status === 'running' ? 'Oczekiwanie na pierwsze logi…' : '(brak stdout)'))
               + (err ? `\n\n── STDERR ──\n${err}` : '');
    consoleEl.hidden = false;
    const wasAtBottom = consoleEl.scrollTop + consoleEl.clientHeight >= consoleEl.scrollHeight - 20;
    consoleEl.textContent = text;
    if (wasAtBottom) consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function setActive(opId) {
    activeOpId = opId;
    renderActive();
  }

  function closeOp(opId) {
    const op = ops.get(opId);
    if (!op) return;
    if (op.pollTimer) { clearInterval(op.pollTimer); op.pollTimer = null; }
    if (op.tabEl) op.tabEl.remove();
    ops.delete(opId);
    storageWrite();
    if (!tabsEl.children.length) tabsEl.hidden = true;
    if (activeOpId === opId) {
      const next = Array.from(ops.values()).sort((a, b) => b.startedAt - a.startedAt)[0];
      setActive(next ? next.id : null);
    }
  }

  /* ── OPERATION POLLING ── */
  function applyOpData(op, data) {
    op.stdout = data.stdout || '';
    op.stderr = data.stderr || '';
    op.status = data.status || op.status;
    op.returnCode = (data.return_code !== undefined) ? data.return_code : op.returnCode;
  }

  function startPolling(opId) {
    const op = ops.get(opId);
    if (!op || op.pollTimer) return;

    const tick = async () => {
      try {
        const r = await fetch(`/api/operations/${opId}/`);
        if (!r.ok) return;
        const data = await r.json();
        applyOpData(op, data);
        updateTab(op);
        if (activeOpId === opId) renderActive();

        if (op.status === 'success' || op.status === 'failed') {
          clearInterval(op.pollTimer); op.pollTimer = null;
        }
      } catch (e) { /* transient — keep polling */ }
    };

    tick();
    if (op.status === 'running') {
      op.pollTimer = setInterval(tick, POLL_INTERVAL_MS);
    }
  }

  function registerOp(meta, { activate = true } = {}) {
    if (ops.has(meta.id)) {
      if (activate) setActive(meta.id);
      return ops.get(meta.id);
    }
    const op = {
      id: meta.id,
      label: meta.label || meta.endpoint || 'Operacja',
      endpoint: meta.endpoint || '',
      cluster: meta.cluster || '',
      node: meta.node || '',
      user: meta.user || '',
      startedAt: meta.startedAt || Date.now(),
      status: meta.status || 'running',
      stdout: '', stderr: '', returnCode: null,
      pollTimer: null, tabEl: null,
    };
    ops.set(op.id, op);
    renderTab(op);
    storageWrite();
    if (activate) setActive(op.id);
    startPolling(op.id);
    return op;
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
        registerOp({
          id: data.operation_id,
          label,
          endpoint,
          cluster,
          node: body.target_node || '',
          user: body.target_user || '',
          startedAt: Date.now(),
          status: 'running',
        });
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

  /* ── RESTORE OPERATIONS ON LOAD ──
   * Two sources: localStorage (this browser's history) and the backend
   * (?status=running — picks up ops launched from another tab/session).
   * Merge by id; backend is the source of truth for status.
   */
  async function restoreOperations() {
    const stored = storageRead();
    const remote = await fetch('/api/operations/?status=running')
      .then(r => r.ok ? r.json() : [])
      .catch(() => []);

    const byId = new Map();
    stored.forEach(m => byId.set(m.id, { ...m }));
    remote.forEach(o => {
      const ex = byId.get(o.id) || {};
      byId.set(o.id, {
        id: o.id,
        label: ex.label || o.playbook || 'Operacja',
        endpoint: ex.endpoint || '',
        cluster: ex.cluster || '',
        node: ex.node || '',
        user: ex.user || '',
        startedAt: ex.startedAt || (o.started_at ? Date.parse(o.started_at) : Date.now()),
        status: 'running',
      });
    });

    const metas = Array.from(byId.values()).sort((a, b) => a.startedAt - b.startedAt);
    metas.forEach(m => registerOp(m, { activate: false }));

    const newest = Array.from(ops.values()).sort((a, b) => b.startedAt - a.startedAt)[0];
    if (newest) setActive(newest.id);
  }
  restoreOperations();

  /* ── USER DROPDOWNS (associate / disassociate) ── */
  const USER_MANUAL = '__manual__';

  async function loadUserSelects() {
    const selects = document.querySelectorAll('.ul-user-select');
    if (!selects.length) return;

    let users = [];
    try {
      const r = await fetch('/api/users-list/');
      if (r.ok) users = await r.json();
    } catch (e) { /* offline → manual entry still works */ }

    selects.forEach(sel => {
      const manualOpt = sel.querySelector(`option[value="${USER_MANUAL}"]`);
      users.forEach(u => {
        const o = document.createElement('option');
        o.value = u.name;
        o.textContent = u.name + (u.is_admin ? ' (admin)' : '');
        sel.insertBefore(o, manualOpt);
      });

      const input = document.getElementById(sel.dataset.target);
      sel.addEventListener('change', () => {
        if (sel.value === USER_MANUAL) {
          input.hidden = false;
          input.value = '';
          input.focus();
        } else {
          input.hidden = true;        // preset chosen → feed hidden field that runAction reads
          input.value = sel.value;
        }
      });
    });
  }
  loadUserSelects();

  /* ══════════════════════════════════════════════════════════════════════
     USERS-LIST EDITOR (users-list.txt)
     ══════════════════════════════════════════════════════════════════════ */
  const ulRows   = document.getElementById('ul-rows');
  const ulEmpty  = document.getElementById('ul-empty');
  const ulAdd    = document.getElementById('ul-add');
  const ulSave   = document.getElementById('ul-save');
  const ulStatus = document.getElementById('ul-status');

  function ulSetStatus(text, kind) {
    ulStatus.textContent = text || '';
    if (kind) ulStatus.dataset.kind = kind; else delete ulStatus.dataset.kind;
  }

  function ulRefreshEmpty() {
    ulEmpty.hidden = ulRows.children.length > 0;
  }

  function ulAddRow(user) {
    const u = user || { name: '', key_path: '', is_admin: false };
    const tr = document.createElement('tr');

    const tdName = document.createElement('td');
    const nameInput = document.createElement('input');
    nameInput.className = 'form-input ul-name';
    nameInput.type = 'text';
    nameInput.placeholder = 'np. admin_tester';
    nameInput.value = u.name;
    tdName.appendChild(nameInput);

    const tdKey = document.createElement('td');
    const keyInput = document.createElement('input');
    keyInput.className = 'form-input ul-key';
    keyInput.type = 'text';
    keyInput.placeholder = '~/.ssh/id_ed25519.pub';
    keyInput.value = u.key_path;
    tdKey.appendChild(keyInput);

    const tdAdmin = document.createElement('td');
    tdAdmin.className = 'ul-admin-cell';
    const adminInput = document.createElement('input');
    adminInput.type = 'checkbox';
    adminInput.className = 'ul-admin';
    adminInput.checked = !!u.is_admin;
    tdAdmin.appendChild(adminInput);

    const tdRm = document.createElement('td');
    const rmBtn = document.createElement('button');
    rmBtn.type = 'button';
    rmBtn.className = 'ul-rm';
    rmBtn.title = 'Usuń wiersz';
    rmBtn.textContent = '×';
    rmBtn.addEventListener('click', () => { tr.remove(); ulRefreshEmpty(); });
    tdRm.appendChild(rmBtn);

    tr.append(tdName, tdKey, tdAdmin, tdRm);
    ulRows.appendChild(tr);
    ulRefreshEmpty();
  }

  function ulCollect() {
    const users = [];
    ulRows.querySelectorAll('tr').forEach(tr => {
      const name = tr.querySelector('.ul-name').value.trim();
      const key  = tr.querySelector('.ul-key').value.trim();
      const adm  = tr.querySelector('.ul-admin').checked;
      if (name || key) users.push({ name, key_path: key, is_admin: adm });
    });
    return users;
  }

  async function ulLoad() {
    try {
      const r = await fetch('/api/users-list/');
      if (!r.ok) { ulSetStatus(`Błąd wczytania (${r.status})`, 'err'); return; }
      const users = await r.json();
      ulRows.innerHTML = '';
      users.forEach(ulAddRow);
      ulRefreshEmpty();
      ulSetStatus(users.length ? `Wczytano ${users.length} użytkownik(ów).` : 'Plik pusty lub nie istnieje.', null);
    } catch (e) {
      ulSetStatus(`Błąd połączenia: ${e.message}`, 'err');
    }
  }

  async function ulSaveList() {
    const users = ulCollect();
    // client-side validation mirroring the backend
    const seen = new Set();
    for (const u of users) {
      if (!u.name || !u.key_path) { ulSetStatus('Każdy wiersz musi mieć nazwę i ścieżkę klucza.', 'err'); return; }
      if (u.name.includes(',') || u.key_path.includes(',')) { ulSetStatus('Nazwa/ścieżka nie mogą zawierać przecinka.', 'err'); return; }
      if (seen.has(u.name)) { ulSetStatus(`Zduplikowana nazwa: ${u.name}`, 'err'); return; }
      seen.add(u.name);
    }

    ulSave.disabled = true;
    ulSetStatus('Zapisywanie…', null);
    try {
      const r = await fetch('/api/users-list/', {
        method:  'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body:    JSON.stringify({ users }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok) {
        ulSetStatus(`Zapisano ${Array.isArray(data) ? data.length : users.length} użytkownik(ów).`, 'ok');
      } else {
        ulSetStatus(`Błąd zapisu (${r.status}): ${data.detail || r.statusText}`, 'err');
      }
    } catch (e) {
      ulSetStatus(`Błąd połączenia: ${e.message}`, 'err');
    } finally {
      ulSave.disabled = false;
    }
  }

  if (ulRows) {
    ulAdd.addEventListener('click', () => ulAddRow());
    ulSave.addEventListener('click', ulSaveList);
    ulLoad();
  }

});
