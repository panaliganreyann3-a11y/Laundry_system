document.addEventListener('DOMContentLoaded', () => {
  document.documentElement.dataset.portal = 'admin';
  tuneCharts();
});

function tuneCharts() {
  if (!window.Chart) return;
  Chart.defaults.color = '#5A7184';
  Chart.defaults.font.family = "'Lato', system-ui, sans-serif";
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.elements.line.borderColor = '#2BAACC';
  Chart.defaults.elements.bar.backgroundColor = 'rgba(26,95,138,.72)';
}
