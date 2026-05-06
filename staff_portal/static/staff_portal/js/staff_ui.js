document.addEventListener('DOMContentLoaded', () => {
  document.documentElement.dataset.portal = 'staff';
  document.querySelectorAll('[style*="overflow-x:auto"]').forEach((rail) => {
    rail.classList.add('laundry-scroll-rail');
  });
});
