function goToPage(page) {
  const params = new URLSearchParams(window.location.search);
  params.set('page', page);
  window.location.search = params.toString();
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.confirm-btn').forEach((button) => {
    button.addEventListener('click', (event) => {
      if (!confirm(button.dataset.msg)) event.preventDefault();
    });
  });
});
