document.addEventListener('DOMContentLoaded', () => {
  initAuthBubbles();
  initContactValidation();
  initPasswordToggles();
  initPasswordStrength();
  initPasswordMatch();

  document.querySelectorAll('.card').forEach((card) => card.classList.add('auth-card'));
  document.querySelectorAll('.alert').forEach((alert) => {
    if (alert.querySelector('.bi-droplet-fill')) return;
    const icon = document.createElement('i');
    icon.className = 'bi bi-droplet-fill me-2';
    icon.style.color = 'var(--aqua)';
    alert.prepend(icon);
  });
});

function initAuthBubbles() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const field = document.createElement('div');
  field.className = 'bubble-field';

  for (let i = 0; i < 14; i += 1) {
    const bubble = document.createElement('span');
    bubble.style.setProperty('--size', `${20 + Math.random() * 48}px`);
    bubble.style.setProperty('--left', `${Math.random() * 100}%`);
    bubble.style.setProperty('--duration', `${18 + Math.random() * 16}s`);
    bubble.style.setProperty('--delay', `${Math.random() * -24}s`);
    bubble.style.setProperty('--drift', `${-30 + Math.random() * 60}px`);
    field.appendChild(bubble);
  }

  document.body.prepend(field);
}

function initContactValidation() {
  document.querySelectorAll('input[name="contact"]').forEach((input) => {
    input.inputMode = 'numeric';
    input.maxLength = 11;
    input.pattern = '\\d{11}';

    input.addEventListener('input', () => {
      input.value = input.value.replace(/\D/g, '').slice(0, 11);
      const valid = /^09\d{9}$/.test(input.value);
      input.setCustomValidity(valid ? '' : 'Contact number must be exactly 11 digits and start with 09.');
    });

    input.form?.addEventListener('submit', (event) => {
      if (/^09\d{9}$/.test(input.value)) return;
      input.setCustomValidity('Contact number must be exactly 11 digits and start with 09.');
      input.reportValidity();
      event.preventDefault();
    });
  });
}

function initPasswordToggles() {
  document.querySelectorAll('.password-toggle').forEach((button) => {
    const input = document.getElementById(button.dataset.target);
    const icon = button.querySelector('i');
    if (!input || !icon) return;

    button.addEventListener('click', () => {
      const shouldShow = input.type === 'password';
      input.type = shouldShow ? 'text' : 'password';
      icon.className = shouldShow ? 'bi bi-eye' : 'bi bi-eye-slash';
      button.setAttribute('aria-label', shouldShow ? 'Hide password' : 'Show password');
    });
  });
}

function initPasswordStrength() {
  const password = document.getElementById('password1');
  const meter = document.getElementById('passwordStrength');
  const fill = meter?.querySelector('.password-meter-fill');
  const label = meter?.querySelector('.password-meter-label');
  const error = document.getElementById('passwordRuleError');
  const form = document.getElementById('customerRegisterForm');
  if (!password || !meter || !fill || !label || !form) return;

  const hasLetter = (value) => /[A-Za-z]/.test(value);
  const hasDigit = (value) => /\d/.test(value);
  const hasLower = (value) => /[a-z]/.test(value);
  const hasUpper = (value) => /[A-Z]/.test(value);
  const hasSpecial = (value) => /[!@#$%^&*]/.test(value);
  const commonPasswords = new Set(['password', 'password1', '123456', '12345678', 'qwerty', 'abc123', 'letmein']);

  function updateMeter() {
    const value = password.value;

    if (!value) {
      meter.classList.add('d-none');
      meter.dataset.strength = '';
      label.textContent = '';
      error?.classList.add('d-none');
      return;
    }

    let score = 0;
    if (value.length >= 8) score += 1;
    if (hasLower(value) && hasUpper(value)) score += 1;
    if (hasDigit(value)) score += 1;
    if (hasSpecial(value)) score += 1;
    if (commonPasswords.has(value.toLowerCase())) score = 0;

    const levels = [
      { key: 'weak', text: 'Weak' },
      { key: 'fair', text: 'Fair' },
      { key: 'strong', text: 'Strong' },
    ];
    const level = score >= 4 ? levels[2] : score >= 2 ? levels[1] : levels[0];

    meter.classList.remove('d-none');
    meter.dataset.strength = level.key;
    label.textContent = level.text;
    error?.classList.toggle('d-none', hasLetter(value) && hasDigit(value) && hasSpecial(value));
  }

  password.addEventListener('input', updateMeter);
  form.addEventListener('submit', (event) => {
    if (password.value.length >= 8 && hasLower(password.value) && hasUpper(password.value) && hasDigit(password.value) && hasSpecial(password.value)) return;
    event.preventDefault();
    error?.classList.remove('d-none');
    password.focus();
  });
}

function initPasswordMatch() {
  const password = document.getElementById('password1');
  const confirm = document.getElementById('password2');
  const error = document.getElementById('passwordMatchError');
  if (!password || !confirm || !error) return;

  function validateMatch() {
    const matches = !confirm.value || confirm.value === password.value;
    error.classList.toggle('d-none', matches);
    confirm.setCustomValidity(matches ? '' : 'Passwords must match.');
  }

  password.addEventListener('input', validateMatch);
  confirm.addEventListener('input', validateMatch);
}