document.addEventListener('DOMContentLoaded', () => {
  const bubbleLayer = document.querySelector('.auth-bubbles');
  if (bubbleLayer) {
    for (let i = 0; i < 18; i += 1) {
      const bubble = document.createElement('span');
      const size = Math.floor(Math.random() * 42) + 18;
      bubble.className = 'auth-bubble';
      bubble.style.width = `${size}px`;
      bubble.style.height = `${size}px`;
      bubble.style.left = `${Math.random() * 100}%`;
      bubble.style.animationDuration = `${Math.random() * 8 + 9}s`;
      bubble.style.animationDelay = `${Math.random() * 6}s`;
      bubble.style.setProperty('--drift', `${Math.random() * 90 - 45}px`);
      bubbleLayer.appendChild(bubble);
    }
  }

  document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;
      input.type = input.type === 'password' ? 'text' : 'password';
      button.querySelector('i')?.classList.toggle('bi-eye');
      button.querySelector('i')?.classList.toggle('bi-eye-slash');
    });
  });
});
