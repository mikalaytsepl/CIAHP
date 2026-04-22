/* CIAHP — instances.js */

document.addEventListener('DOMContentLoaded', () => {

  /* ── IP VALIDATION ── */
  const IP_REGEX = /^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)$/;

  const ipInput = document.getElementById('inst-ip');
  const ipError = document.getElementById('ip-error');

  function validateIP(value) {
    if (value === '') return null;           // empty field — skip validation
    return IP_REGEX.test(value.trim());     // true = valid, false = invalid
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

  // Real-time: validate on each keystroke with a short debounce
  let ipDebounce;
  ipInput.addEventListener('input', () => {
    clearTimeout(ipDebounce);
    // clear state immediately if field is empty
    if (ipInput.value === '') { updateIPState(null); return; }
    ipDebounce = setTimeout(() => updateIPState(validateIP(ipInput.value)), 400);
  });

  // Also validate on blur
  ipInput.addEventListener('blur', () => {
    updateIPState(validateIP(ipInput.value));
  });

  // Block form submission if IP is invalid
  document.getElementById('instance-form').addEventListener('submit', e => {
    const valid = validateIP(ipInput.value);
    if (valid === null || valid === false) {
      e.preventDefault();
      updateIPState(false);
      ipInput.focus();
    }
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

  /* ── AUTH METHOD ── */
  const authCards = document.querySelectorAll('.auth-card');
  const authInput = document.getElementById('auth-method-value');

  authCards.forEach(card => {
    card.addEventListener('click', () => {
      authCards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');

      const method = card.dataset.method;
      authInput.value = method;

      document.querySelectorAll('.auth-fields').forEach(f => f.classList.remove('visible'));
      document.getElementById('auth-' + method).classList.add('visible');
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

});
