const renderFilteredTasks = refresh;
function filterQuery() {
  const p = new URLSearchParams({status: filter});
  const search = document.querySelector('#searchTasks').value.trim();
  const dateFrom = document.querySelector('#dateFrom').value;
  const dateTo = document.querySelector('#dateTo').value;
  if (search) p.set('search', search);
  if (dateFrom) p.set('date_from', dateFrom);
  if (dateTo) p.set('date_to', dateTo);
  return p.toString();
}
refresh = async function() {
  const query = filterQuery();
  const [tasks, stats] = await Promise.all([request(`/api/tasks?${query}`), request(`/api/stats?${query}`)]);
  $('#activeCount').textContent=stats.active; $('#completedCount').textContent=stats.completed; $('#todayCount').textContent=stats.due_today;
  const activeFilter = document.querySelector('#searchTasks').value || document.querySelector('#dateFrom').value || document.querySelector('#dateTo').value;
  $('#taskSummary').textContent=stats.total ? `${stats.active} tugas belum diselesaikan dari ${stats.total} task yang ditampilkan.` : (activeFilter ? 'Tidak ada task yang cocok dengan filter.' : 'Mulai dengan menambahkan tugas pertama.');
  $('#emptyState').classList.toggle('visible', !tasks.length);
  $('#taskList').innerHTML=tasks.map(t=>`<article class="task ${t.completed?'done':''}"><input class="check" aria-label="Tandai selesai" type="checkbox" ${t.completed?'checked':''} onchange="toggleTask(${t.id},this.checked)"><div><div class="task-title">${esc(t.title)}</div><div class="task-meta"><span><i class="priority ${t.priority}"></i>${t.priority==='high'?'Tinggi':t.priority==='low'?'Rendah':'Sedang'}</span><span>${esc(t.category)}</span>${t.due_date?`<span>${fmtDate(t.due_date)}</span>`:''}</div></div><div class="task-actions"><button onclick="viewTask(${t.id})">View</button><button onclick="editTask(${t.id})">Edit</button><button class="danger" onclick="deleteTask(${t.id})">Delete</button></div></article>`).join('');
};
let searchTimer;
document.querySelector('#searchTasks').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer=setTimeout(refresh, 250); });
document.querySelector('#dateFrom').addEventListener('change', refresh);
document.querySelector('#dateTo').addEventListener('change', refresh);
document.querySelector('#clearFilters').onclick=()=>{document.querySelector('#taskFilters').reset();refresh()};
