document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.usage-edit-btn').forEach((button) => {
    button.addEventListener('click', () => {
      document.getElementById('ruleId').value = button.dataset.ruleId;
      document.getElementById('serviceType').value = button.dataset.serviceType;
      document.getElementById('inventoryItem').value = button.dataset.itemId;
      document.getElementById('quantityPerKg').value = button.dataset.quantityPerKg;
      document.getElementById('fixedQuantity').value = button.dataset.fixedQuantity;
      document.getElementById('isActive').checked = button.dataset.isActive === '1';
      document.getElementById('usageFormTitle').textContent = 'Edit Service Usage';
      document.getElementById('usageSubmitButton').textContent = 'Update Rule';
      document.getElementById('usageForm').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
});
