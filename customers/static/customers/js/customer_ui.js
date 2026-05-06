document.addEventListener('DOMContentLoaded', () => {
  initCustomerBubbles();
  initCustomerReveal();
  initCustomerWaves();
  initContactValidation();
  document.querySelectorAll('.alert').forEach((alert) => {
    if (alert.querySelector('.bi-droplet-fill')) return;
    const icon = document.createElement('i');
    icon.className = 'bi bi-droplet-fill me-2';
    icon.style.color = 'var(--aqua)';
    alert.prepend(icon);
  });
});

function initCustomerBubbles() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.querySelector('.bubble-field')) return;
  const field = document.createElement('div');
  field.className = 'bubble-field';

  for (let i = 0; i < 16; i += 1) {
    const bubble = document.createElement('span');
    bubble.style.setProperty('--size', `${18 + Math.random() * 52}px`);
    bubble.style.setProperty('--left', `${Math.random() * 100}%`);
    bubble.style.setProperty('--duration', `${18 + Math.random() * 18}s`);
    bubble.style.setProperty('--delay', `${Math.random() * -28}s`);
    bubble.style.setProperty('--drift', `${-34 + Math.random() * 68}px`);
    field.appendChild(bubble);
  }

  document.body.prepend(field);
}

function initCustomerWaves() {
  const shell = document.querySelector('.portal-shell');
  if (!shell || shell.querySelector('.laundry-wave-divider')) return;

  [...shell.children].forEach((child, index) => {
    if (index === 0 || index % 3 !== 0) return;
    const divider = document.createElement('div');
    divider.className = 'laundry-wave-divider';
    divider.setAttribute('aria-hidden', 'true');
    child.before(divider);
  });
}

function initCustomerReveal() {
  const targets = document.querySelectorAll('.card, .stat, .table-responsive, form, .alert');
  targets.forEach((target) => target.classList.add('reveal-on-scroll'));

  if (!('IntersectionObserver' in window)) {
    targets.forEach((target) => target.classList.add('is-visible'));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12 });

  targets.forEach((target, index) => {
    target.style.transitionDelay = `${Math.min(index * 24, 160)}ms`;
    observer.observe(target);
  });
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
