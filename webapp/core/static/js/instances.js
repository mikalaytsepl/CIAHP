/* CIAHP — instances.js */

document.addEventListener('DOMContentLoaded', () => {

  /* ── CSRF ── */
  function getCsrf() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    return token ? token.value : '';
  }

  /* ── IP VALIDATION ── */
  const IP_REGEX = /^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$/;

  const ipInput = document.getElementById('inst-ip');
  const ipError = document.getElementById('ip-error');

  function validateIP(value) {
    if (value === '') return null;
    return IP_REGEX.test(value.trim());
  }

  function updateIPState(valid) {
    if (valid === null) {
      ipInput.classList.remove('invalid', 'valid');
      ipError.textContent = '';
      return;
    }
    if (valid) {
      ipInput.classList.replace('invalid', 'valid') || ipInput.classList.add('valid');
      ipError.textContent = '';
    } else {
      ipInput.classList.replace('valid', 'invalid') || ipInput.classList.add('invalid');
      ipError.textContent = 'Nieprawidłowy adres IP (np. 192.168.0.1)';
    }
  }

  let ipDebounce;
  ipInput.addEventListener('input', () => {
    clearTimeout(ipDebounce);
    if (ipInput.value === '') { updateIPState(null); return; }
    ipDebounce = setTimeout(() => updateIPState(validateIP(ipInput.value)), 400);
  });

  ipInput.addEventListener('blur', () => {
    updateIPState(validateIP(ipInput.value));
  });

  /* ── ROLE TOGGLE ── */
  const roleBtns = document.querySelectorAll('.role-btn');
  const roleInput = document.getElementById('role-value');

  roleBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      roleBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      roleInput.value = btn.dataset.role;
    });
  });

  /* ── CLUSTER COLLAPSE ── */
  document.querySelectorAll('.cluster-row').forEach(row => {
    row.addEventListener('click', () => {
      row.closest('.cluster-item').classList.toggle('open');
    });
  });

  /* ── SUB-GROUP COLLAPSE ── */
  document.querySelectorAll('.sub-group-row').forEach(row => {
    row.addEventListener('click', () => {
      row.closest('.sub-group').classList.toggle('open');
    });
  });

  /* ── FORM SUBMIT → API ── */
  const form       = document.getElementById('instance-form');
  const submitBtn  = form.querySelector('.submit-btn');
  const formError  = document.getElementById('form-error');
  const origBtnHTML = submitBtn.innerHTML;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const valid = validateIP(ipInput.value);
    if (!valid) {
      updateIPState(false);
      ipInput.focus();
      return;
    }

    const cluster = document.getElementById('inst-cluster').value;
    if (!cluster) {
      formError.textContent = 'Wybierz klaster.';
      formError.style.display = 'block';
      return;
    }

    formError.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = '[ Dodawanie… ]';

    const body = {
      name: document.getElementById('inst-name').value.trim(),
      ip:   ipInput.value.trim(),
      role: roleInput.value,
    };

    // Optional: one-time bootstrap of `ansible` using an existing admin's creds.
    const bootstrapUser = document.getElementById('inst-user').value.trim();
    if (bootstrapUser) {
      const pass = document.getElementById('inst-pass').value;
      if (!pass) {
        formError.textContent = 'Podaj hasło dla podanego konta startowego.';
        formError.style.display = 'block';
        submitBtn.disabled = false; submitBtn.innerHTML = origBtnHTML;
        return;
      }
      body.bootstrap_user     = bootstrapUser;
      body.bootstrap_password = pass;
    }

    try {
      const resp = await fetch(`/api/clusters/${cluster}/nodes/`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body:    JSON.stringify(body),
      });

      if (resp.ok) {
        window.location.href = '/instances/';
      } else {
        const data = await resp.json().catch(() => ({}));
        formError.textContent = data.detail || `Błąd serwera (${resp.status}).`;
        formError.style.display = 'block';
        submitBtn.disabled = false;
        submitBtn.innerHTML = origBtnHTML;
      }
    } catch (err) {
      formError.textContent = `Błąd połączenia: ${err.message}`;
      formError.style.display = 'block';
      submitBtn.disabled = false;
      submitBtn.innerHTML = origBtnHTML;
    }
  });

  /* ── DELETE NODE ── */
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.delete-node-btn');
    if (!btn) return;

    const cluster = btn.dataset.cluster;
    const node    = btn.dataset.node;
    if (!confirm(`Usunąć węzeł "${node}" z klastra "${cluster}"?\n\nTo uruchomi playbook: węzeł zostanie wyczyszczony (kubeadm reset) i usunięty z klastra. Operacja działa w tle.`)) return;

    btn.disabled = true;

    try {
      const resp = await fetch(`/api/clusters/${cluster}/actions/delete-node`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body:    JSON.stringify({ target_node: node }),
      });

      if (resp.ok) {
        window.location.href = '/instances/';
      } else {
        const data = await resp.json().catch(() => ({}));
        alert(`Błąd usuwania (${resp.status}): ${data.detail || resp.statusText}`);
        btn.disabled = false;
      }
    } catch (err) {
      alert(`Błąd połączenia: ${err.message}`);
      btn.disabled = false;
    }
  });

  /* ── DELETE CLUSTER ── */
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.btn-remove');
    if (!btn) return;

    // stop collapse toggle from firing
    e.stopPropagation();

    const clusterItem = btn.closest('.cluster-item');
    const cluster     = clusterItem.dataset.cluster;
    if (!confirm(`Usunąć klaster "${cluster}" i wszystkie jego węzły?\n\nTo uruchomi playbook: wszystkie maszyny zostaną wyczyszczone (kubeadm reset), a klaster usunięty z inventory i bazy. Operacja działa w tle.`)) return;

    btn.disabled = true;

    try {
      const resp = await fetch(`/api/clusters/${cluster}/actions/delete-cluster`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      });

      if (resp.ok) {
        window.location.href = '/instances/';
      } else {
        const data = await resp.json().catch(() => ({}));
        alert(`Błąd usuwania klastra (${resp.status}): ${data.detail || resp.statusText}`);
        btn.disabled = false;
      }
    } catch (err) {
      alert(`Błąd połączenia: ${err.message}`);
      btn.disabled = false;
    }
  });

});
