function displayInventoryQuantity(value, unit) {
  return unit === 'ml' ? Math.round((value / 1000) * 10000) / 10000 : value;
}

function updateRestockPreview() {
  const current = parseFloat(document.getElementById('inventoryStockData')?.dataset.currentStock || '0');
  const inputUnit = document.getElementById('inventoryStockData')?.dataset.inputUnit || '';
  const displayUnit = document.getElementById('inventoryStockData')?.dataset.displayUnit || inputUnit;
  const qty = parseFloat(document.getElementById('restockQty')?.value) || 0;
  const newStock = Math.round((current + qty) * 10000) / 10000;
  const preview = document.getElementById('restockPreview');
  if (preview) preview.textContent = displayInventoryQuantity(newStock, inputUnit) + ' ' + displayUnit;
}

function updateDeductPreview() {
  const current = parseFloat(document.getElementById('inventoryStockData')?.dataset.currentStock || '0');
  const inputUnit = document.getElementById('inventoryStockData')?.dataset.inputUnit || '';
  const displayUnit = document.getElementById('inventoryStockData')?.dataset.displayUnit || inputUnit;
  const qty = parseFloat(document.getElementById('deductQty')?.value) || 0;
  const remaining = Math.max(0, Math.round((current - qty) * 10000) / 10000);
  const preview = document.getElementById('deductPreview');
  if (preview) preview.textContent = displayInventoryQuantity(remaining, inputUnit) + ' ' + displayUnit;
  document.getElementById('overStockWarning')?.classList.toggle('d-none', qty <= current);
}

function toggleNewCat() {
  const select = document.getElementById('categorySelect');
  const newCategory = document.getElementById('newCatDiv');
  if (!select || !newCategory) return;
  newCategory.style.display = select.value === '__new__' ? 'block' : 'none';
  if (select.value === '__new__') select.value = '';
}
