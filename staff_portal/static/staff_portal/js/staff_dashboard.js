document.addEventListener('DOMContentLoaded', () => {
  const selectAll = document.getElementById('selAll');
  const bulkBar = document.getElementById('bulkBar');
  const selectedCount = document.getElementById('selCount');
  function updateBulk() {
    const count = document.querySelectorAll('.order-cb:checked').length;
    if (bulkBar) bulkBar.classList.toggle('d-none', count === 0);
    if (selectedCount) selectedCount.textContent = count + ' selected';
  }
  if (selectAll) {
    selectAll.addEventListener('change', function() {
      document.querySelectorAll('.order-cb').forEach((checkbox) => { checkbox.checked = this.checked; });
      updateBulk();
    });
  }
  document.querySelectorAll('.order-cb').forEach((checkbox) => checkbox.addEventListener('change', updateBulk));
});
