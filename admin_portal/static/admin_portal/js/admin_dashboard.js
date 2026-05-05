document.addEventListener('DOMContentLoaded', () => {
  const config = document.getElementById('adminDashboardData');
  if (config && window.Chart) {
    const data = JSON.parse(config.textContent);
    new Chart(document.getElementById('weekChart'), {
      type: 'bar',
      data: {
        labels: data.weekLabels,
        datasets: [
          { label: 'Revenue (PHP)', data: data.weekRevenue, backgroundColor: 'rgba(32,201,151,.25)', borderColor: '#20c997', borderWidth: 2, yAxisID: 'y', type: 'line', tension: 0.4, fill: true },
          { label: 'Orders', data: data.weekOrders, backgroundColor: 'rgba(13,110,253,.7)', borderRadius: 6, yAxisID: 'y1' },
        ],
      },
      options: {
        plugins: { legend: { display: true, position: 'top' } },
        scales: {
          y: { type: 'linear', position: 'left', title: { display: true, text: 'Revenue (PHP)' } },
          y1: { type: 'linear', position: 'right', title: { display: true, text: 'Orders' }, grid: { drawOnChartArea: false } },
        },
      },
    });
    new Chart(document.getElementById('serviceChart'), {
      type: 'doughnut',
      data: {
        labels: data.serviceLabels,
        datasets: [{ data: data.serviceData, backgroundColor: ['#0d6efd','#20c997','#ffc107','#dc3545','#6610f2','#17a2b8','#fd7e14'] }],
      },
      options: { plugins: { legend: { position: 'right', labels: { font: { size: 11 } } } }, cutout: '60%' },
    });
  }

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
