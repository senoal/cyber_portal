function applyDashboardFilter(value) {
  filter = value;
  currentPage = 1;
  document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.dataset.filter === value));
  document.querySelectorAll('[data-dashboard-filter]').forEach(card => card.classList.toggle('selected', card.dataset.dashboardFilter === value));
  refresh();
  document.querySelector('.tasks-section').scrollIntoView({behavior:'smooth', block:'start'});
}
document.querySelectorAll('[data-dashboard-filter]').forEach(card => {
  const activate = () => applyDashboardFilter(card.dataset.dashboardFilter);
  card.addEventListener('click', activate);
  card.addEventListener('keydown', event => { if(event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); } });
});
