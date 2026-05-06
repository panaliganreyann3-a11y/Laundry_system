function goToPage(page) {
  const params = new URLSearchParams(window.location.search);
  params.set('page', page);
  window.location.search = params.toString();
}

document.addEventListener('DOMContentLoaded', () => {
  initLaundryBubbles();
  initRevealMotion();
  initFloatingLabels();
  initWaterAlerts();
  initWaveDividers();
  initContactValidation();

  document.querySelectorAll('.confirm-btn').forEach((button) => {
    button.addEventListener('click', (event) => {
      if (!confirm(button.dataset.msg)) event.preventDefault();
    });
  });
});

function initLaundryBubbles() {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (document.querySelector('.bubble-field')) return;

  const field = document.createElement('div');
  field.className = 'bubble-field';
  const count = Math.min(18, Math.max(10, Math.round(window.innerWidth / 90)));

  for (let i = 0; i < count; i += 1) {
    const bubble = document.createElement('span');
    bubble.style.setProperty('--size', `${18 + Math.random() * 54}px`);
    bubble.style.setProperty('--left', `${Math.random() * 100}%`);
    bubble.style.setProperty('--duration', `${18 + Math.random() * 18}s`);
    bubble.style.setProperty('--delay', `${Math.random() * -28}s`);
    bubble.style.setProperty('--drift', `${-32 + Math.random() * 64}px`);
    field.appendChild(bubble);
  }

  document.body.prepend(field);
}

function initRevealMotion() {
  const targets = document.querySelectorAll('.card, .kpi, .stat, .table-responsive, form.card, .list-group-item');
  targets.forEach((element) => element.classList.add('reveal-on-scroll'));

  if (!('IntersectionObserver' in window)) {
    targets.forEach((element) => element.classList.add('is-visible'));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -32px' });

  targets.forEach((element, index) => {
    element.style.transitionDelay = `${Math.min(index * 24, 180)}ms`;
    observer.observe(element);
  });
}

function initFloatingLabels() {
  document.querySelectorAll('.mb-3, .col-md-2, .col-md-3, .col-md-4, .col-md-6').forEach((group) => {
    if (group.querySelector('.form-label') && group.querySelector('.form-control, .form-select')) {
      group.classList.add('form-floating-lite');
    }
  });
}

function initWaterAlerts() {
  document.querySelectorAll('.alert').forEach((alert) => {
    if (alert.dataset.waterReady) return;
    alert.dataset.waterReady = 'true';
    const drop = document.createElement('i');
    drop.className = 'bi bi-droplet-fill me-2';
    drop.style.color = 'var(--aqua)';
    alert.prepend(drop);
  });
}

function initWaveDividers() {
  const shell = document.querySelector('.page-content');
  if (!shell || shell.querySelector('.laundry-wave-divider')) return;

  [...shell.children].forEach((child, index) => {
    if (index === 0 || index % 3 !== 0 || child.tagName === 'SCRIPT') return;
    const divider = document.createElement('div');
    divider.className = 'laundry-wave-divider';
    divider.setAttribute('aria-hidden', 'true');
    child.before(divider);
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
