let currentPage = 1;
const filteredQuery = filterQuery;
filterQuery = function() { const query = filteredQuery(); return `${query}&page=${currentPage}`; };
const filterForm = document.querySelector('#taskFilters');
filterForm.addEventListener('input', () => { currentPage=1; });
filterForm.addEventListener('change', () => { currentPage=1; });
refresh = async function() {
  const query = filterQuery();
  const [result, stats] = await Promise.all([request(`/api/tasks?${query}`), request(`/api/stats?${query}`)]);
  currentPage = result.page;
  $('#activeCount').textContent=stats.active; $('#completedCount').textContent=stats.completed; $('#todayCount').textContent=stats.due_today;
  $('#totalCount').textContent=stats.total; $('#canceledCount').textContent=stats.canceled;
  const activeFilter = $('#searchTasks').value || $('#dateFrom').value || $('#dateTo').value;
  $('#taskSummary').textContent=stats.total ? `${stats.active} tugas belum diselesaikan dari ${stats.total} task yang ditampilkan.` : (activeFilter ? 'Tidak ada task yang cocok dengan filter.' : 'Mulai dengan menambahkan tugas pertama.');
  $('#emptyState').classList.toggle('visible', !result.items.length);
  $('#taskList').innerHTML=result.items.map(t=>`<article class="task ${t.completed?'done':''}"><input class="check" aria-label="Tandai selesai" type="checkbox" ${t.completed?'checked':''} onchange="toggleTask(${t.id},this.checked)"><div><div class="task-title">${esc(t.title)}</div><div class="task-meta"><span><i class="priority ${t.priority}"></i>${t.priority==='high'?'Tinggi':t.priority==='low'?'Rendah':'Sedang'}</span><span>${esc(t.category)}</span>${t.due_date?`<span>${fmtDate(t.due_date)}</span>`:''}</div></div><div class="task-actions"><button onclick="viewTask(${t.id})">View</button><button onclick="editTask(${t.id})">Edit</button><button class="danger" onclick="deleteTask(${t.id})">Delete</button></div></article>`).join('');
  const pages = result.total_pages; const nav = $('#pagination');
  if (!result.total) { nav.innerHTML=''; return; }
  const buttons = Array.from({length:pages},(_,i)=>i+1).filter(p=>pages<=7 || p===1 || p===pages || Math.abs(p-result.page)<=1).map(p=>`<button class="${p===result.page?'active':''}" onclick="goToPage(${p})">${p}</button>`).join('');
  nav.innerHTML=`<span class="page-info">Menampilkan ${result.items.length} dari ${result.total} task</span><button ${result.page===1?'disabled':''} onclick="goToPage(${result.page-1})">←</button>${buttons}<button ${result.page===pages?'disabled':''} onclick="goToPage(${result.page+1})">→</button>`;
};
function goToPage(page) { currentPage=page; refresh(); document.querySelector('.tasks-section').scrollIntoView({behavior:'smooth',block:'start'}); }
refresh();
