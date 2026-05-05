document.addEventListener('DOMContentLoaded', () => {
  const config = document.getElementById('reportsChartData');
  if (!config || !window.Chart) return;
  const data = JSON.parse(config.textContent);

  new Chart(document.getElementById('revenueChart'), {
    type: 'line',
    data: { labels: data.revenueLabels, datasets: [{ label: 'Revenue (PHP)', data: data.revenueData, borderColor: '#0d6efd', backgroundColor: 'rgba(13,110,253,0.1)', fill: true, tension: 0.4 }] },
    options: { plugins: { legend: { display: false } } },
  });
  new Chart(document.getElementById('ordersChart'), {
    type: 'bar',
    data: { labels: data.revenueLabels, datasets: [{ label: 'Orders', data: data.ordersData, backgroundColor: '#198754' }] },
    options: { plugins: { legend: { display: false } } },
  });
  new Chart(document.getElementById('statusChart'), {
    type: 'doughnut',
    data: { labels: data.statusLabels, datasets: [{ data: data.statusData, backgroundColor: ['#6c757d','#0d6efd','#ffc107','#198754','#212529'] }] },
  });
  new Chart(document.getElementById('serviceChart'), {
    type: 'pie',
    data: { labels: data.serviceLabels, datasets: [{ data: data.serviceData, backgroundColor: ['#0dcaf0','#0d6efd','#6610f2','#d63384'] }] },
  });
});
