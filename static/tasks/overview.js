function updateOverviewState() {
  const active = Number(document.querySelector('#activeCount').textContent) || 0;
  const completed = Number(document.querySelector('#completedCount').textContent) || 0;
  const total = Number(document.querySelector('#totalCount').textContent) || 0;
  const canceled = Number(document.querySelector('#canceledCount').textContent) || 0;
  const dueToday = Number(document.querySelector('#todayCount').textContent) || 0;
  document.querySelector('#activeLabel').textContent = active ? `${active} task menunggu untuk dikerjakan` : 'Inbox kerja sedang bersih';
  document.querySelector('#completedLabel').textContent = completed ? `${completed} target berhasil diselesaikan` : 'Belum ada task yang diselesaikan';
  document.querySelector('#totalLabel').textContent = total ? `${total} task sesuai filter aktif` : 'Belum ada task dalam workspace';
  document.querySelector('#canceledLabel').textContent = canceled ? `${canceled} task tidak dilanjutkan` : 'Tidak ada task dibatalkan';
  const deadline = document.querySelector('#deadlineCard');
  deadline.classList.toggle('has-warning', dueToday > 0);
  document.querySelector('#deadlineLabel').textContent = dueToday ? `${dueToday} task perlu perhatian hari ini` : 'Tidak ada deadline hari ini';
}
new MutationObserver(updateOverviewState).observe(document.querySelector('#activeCount'), {childList:true, characterData:true, subtree:true});
new MutationObserver(updateOverviewState).observe(document.querySelector('#completedCount'), {childList:true, characterData:true, subtree:true});
new MutationObserver(updateOverviewState).observe(document.querySelector('#todayCount'), {childList:true, characterData:true, subtree:true});
new MutationObserver(updateOverviewState).observe(document.querySelector('#totalCount'), {childList:true, characterData:true, subtree:true});
new MutationObserver(updateOverviewState).observe(document.querySelector('#canceledCount'), {childList:true, characterData:true, subtree:true});
updateOverviewState();
