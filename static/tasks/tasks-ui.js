/* Single, English-only controller for Tasks.  Replaces overlapping legacy
   scripts so each card has one rendering path and one set of actions. */
(() => {
  const $ = selector => document.querySelector(selector);
  const api = async (url, options) => {
    const response = await fetch(url, options);
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      if (body?.error === 'CSRF token tidak valid atau tidak tersedia.') {
        throw Error('This page session has expired. Refresh the Tasks page, then save again.');
      }
      throw Error(body?.error || `The server could not complete this request (HTTP ${response.status}).`);
    }
    if (response.status === 204) return null;
    const body = await response.json().catch(() => null);
    if (body === null) throw Error('The server returned an invalid response. Please refresh the page and try again.');
    return body;
  };
  const esc = (value='') => { const div=document.createElement('div'); div.textContent=value; return div.innerHTML; };
  const date = value => value ? new Date(`${value}T00:00:00`).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'}) : 'Not set';
  let filter='all', page=1, editingId=null;

  const query = (withPage=true) => { const p=new URLSearchParams({status:filter}); const search=$('#searchTasks').value.trim(); if(search)p.set('search',search); if($('#dateFrom').value)p.set('date_from',$('#dateFrom').value); if($('#dateTo').value)p.set('date_to',$('#dateTo').value); if(withPage)p.set('page',page); return p.toString(); };
  const priority = value => ({high:'High',medium:'Medium',low:'Low'})[value] || 'Medium';
  const localToday = () => {
    const now = new Date();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    return `${now.getFullYear()}-${month}-${day}`;
  };
  const taskStatus = task => {
    if (task.canceled) return 'Canceled';
    if (task.completed) return 'Deployed';
    // Match the dashboard's Deadline state: incomplete tasks due today or earlier
    // require attention and should not be presented as part of the active queue.
    if (task.due_date && task.due_date <= localToday()) return 'Deadline';
    return 'Active queue';
  };
  const statusClass = task => taskStatus(task).toLowerCase().replace(/\s+/g, '-');

  function renderOverview(stats) {
    const attention=(stats.due_today||0)+(stats.overdue||0);
    $('#totalCount').textContent=stats.total; $('#completedCount').textContent=stats.completed; $('#activeCount').textContent=stats.active; $('#canceledCount').textContent=stats.canceled; $('#todayCount').textContent=attention;
    $('#totalLabel').textContent=stats.total ? `${stats.total} tasks match the active filters` : 'No tasks in this workspace';
    $('#completedLabel').textContent=stats.completed ? `${stats.completed} goals successfully completed` : 'No completed tasks yet';
    $('#activeLabel').textContent=stats.active ? `${stats.active} tasks ready to work on` : 'Your active queue is clear';
    $('#canceledLabel').textContent=stats.canceled ? `${stats.canceled} tasks were canceled` : 'No canceled tasks';
    $('#deadlineLabel').textContent=!attention ? 'No deadlines or overdue tasks' : stats.overdue && stats.due_today ? `${stats.overdue} overdue · ${stats.due_today} due today` : stats.overdue ? `${stats.overdue} overdue task${stats.overdue===1?'':'s'} need attention` : `${stats.due_today} task${stats.due_today===1?'':'s'} due today`;
    $('#deadlineCard').classList.toggle('has-warning',attention>0);
  }
  function renderTasks(tasks, total, pages) {
    $('#emptyState').classList.toggle('visible',!tasks.length);
    $('#taskList').innerHTML=tasks.map(t=>`<article class="task ${t.completed?'done':''}${t.canceled?' canceled':''}"><input class="check" aria-label="Mark as complete" type="checkbox" ${t.completed?'checked':''} ${t.canceled?'disabled':''} onchange="taskUI.toggle(${t.id},this.checked)"><div><div class="task-title">${esc(t.title)}</div><div class="task-meta"><span class="task-status ${statusClass(t)}">${taskStatus(t)}</span><span>${esc(t.category)}</span><span>${date(t.due_date)}</span></div></div><div class="task-actions"><button onclick="taskUI.view(${t.id})">View</button><button onclick="taskUI.edit(${t.id})">Edit</button><button class="danger" onclick="taskUI.remove(${t.id})">Delete</button><button class="cancel-button" onclick="taskUI.cancel(${t.id},${!t.canceled})">${t.canceled?'Reactivate':'Cancel'}</button></div></article>`).join('');
    const nav=$('#pagination'); if(!total){nav.innerHTML='';return;}
    nav.innerHTML=`<span class="page-info">Showing ${tasks.length} of ${total} tasks</span><button ${page===1?'disabled':''} onclick="taskUI.goto(${page-1})">←</button>${Array.from({length:pages},(_,i)=>i+1).filter(p=>pages<=7||p===1||p===pages||Math.abs(p-page)<=1).map(p=>`<button class="${p===page?'active':''}" onclick="taskUI.goto(${p})">${p}</button>`).join('')}<button ${page===pages?'disabled':''} onclick="taskUI.goto(${page+1})">→</button>`;
  }
  async function refresh(){ const [result,stats]=await Promise.all([api(`/api/tasks?${query()}`),api(`/api/stats?${query(false)}`)]); page=result.page; renderOverview(stats); renderTasks(result.items,result.total,result.total_pages); $('#taskSummary').textContent=stats.total?`${stats.active} active of ${stats.total} displayed tasks.`:($('#searchTasks').value||$('#dateFrom').value||$('#dateTo').value?'No tasks match the current filters.':'Start by creating your first task.'); }
  function updateNotesCount(){const notes=$('#taskForm [name=description]'),counter=$('#notesCharacterCount');if(!notes||!counter)return;const length=notes.value.length;counter.textContent=`${length.toLocaleString()} / 10,000 characters`;counter.classList.toggle('near-limit',length>=9000&&length<10000);counter.classList.toggle('at-limit',length>=10000);}
  function close(){ $('#modal').classList.remove('open'); $('#taskForm').reset(); updateNotesCount(); editingId=null; $('#taskForm .eyebrow').textContent='NEW TASK'; $('#taskForm h2').textContent='Add a new focus'; $('#taskForm .save').innerHTML='Save task <span>→</span>'; }
  function open(){ $('#modal').classList.add('open'); setTimeout(()=>$('[name=title]').focus(),20); }
  async function upload(taskId, files){for(const file of files){if(file.size>50*1024*1024){alert(`${file.name} exceeds the 50 MB limit.`);continue;}const body=new FormData();body.append('file',file);await api(`/api/tasks/${taskId}/attachments`,{method:'POST',body});}}
  async function edit(id){const task=await api(`/api/tasks/${id}`);const form=$('#taskForm');editingId=id;form.title.value=task.title;form.description.value=task.description||'';updateNotesCount();form.category.value=task.category||'Personal';form.priority.value=task.priority;form.due_date.value=task.due_date||'';form.querySelector('.eyebrow').textContent='EDIT TASK';form.querySelector('h2').textContent='Update task details';form.querySelector('.save').innerHTML='Save changes <span>→</span>';open();}
  function renderEditSteps(task){
    $('#editTaskSteps')?.remove();
    const form=$('#taskForm');
    const steps=(task.subtasks||[]).map(step=>`<li><div><b>${esc(step.name)}</b><small>${date(step.due_date)}${step.notes?' · Notes added':''}</small></div></li>`).join('')||'<li class="no-files">No steps yet.</li>';
    const section=document.createElement('section');section.className='subtasks edit-task-steps';section.id='editTaskSteps';
    section.innerHTML=`<div class="subtasks-head"><span>STEPS (${(task.subtasks||[]).length})</span><button class="mini-add" type="button">+ Add step</button></div><ul>${steps}</ul>`;
    const attachment=form.querySelector('[name=attachments]')?.closest('label');(attachment||form.querySelector('.form-actions')).before(section);
    section.querySelector('.mini-add').onclick=()=>subtaskForm(task.id);
  }
  const baseEdit = edit;
  edit = async id => { await baseEdit(id); renderEditSteps(await api(`/api/tasks/${id}`)); };
  async function remove(id){if(confirm('Delete this task permanently?')){await api(`/api/tasks/${id}`,{method:'DELETE'});refresh();}}
  async function toggle(id,completed){await api(`/api/tasks/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({completed})});refresh();}
  async function cancel(id,canceled){if(confirm(canceled?'Cancel this task? It can be reactivated later.':'Reactivate this task?')){await api(`/api/tasks/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({canceled})});refresh();}}
  const closePanel=panel=>panel.remove();
  async function view(id){const t=await api(`/api/tasks/${id}`);const files=(t.attachments||[]).map(a=>`<li><a href="/api/attachments/${a.id}/download">${esc(a.original_name)}</a><small>${(a.size/1048576).toFixed(2)} MB</small><button onclick="taskUI.deleteAttachment(${a.id},${id})">×</button></li>`).join('')||'<li class="no-files">No attachments yet.</li>';const steps=(t.subtasks||[]).map(s=>`<li><div><b>${esc(s.name)}</b><small>${date(s.due_date)}${s.notes?' · Notes added':''}</small></div><div class="step-actions"><button onclick="taskUI.subtask(${id},${s.id})">View</button><button onclick="taskUI.subtaskForm(${id},${s.id})">Edit</button><button class="danger" onclick="taskUI.deleteSubtask(${id},${s.id})">Delete</button></div></li>`).join('')||'<li class="no-files">No steps yet.</li>';const panel=document.createElement('div');panel.className='modal-backdrop open';panel.innerHTML=`<section class="modal detail-modal"><div class="modal-top"><div><p class="eyebrow">TASK DETAIL / #${t.id}</p><h2>${esc(t.title)}</h2></div><button class="close" type="button">×</button></div><div class="detail-grid"><div><span>STATUS</span><b class="status ${t.completed?'complete':''}">${t.canceled?'CANCELED':t.completed?'COMPLETED':'ACTIVE'}</b></div><div><span>PRIORITY</span><b>${priority(t.priority)}</b></div><div><span>CATEGORY</span><b>${esc(t.category)}</b></div><div><span>DUE DATE</span><b>${date(t.due_date)}</b></div></div><div class="detail-notes"><span>NOTES</span><p>${esc(t.description)||'No notes for this task.'}</p></div><div class="subtasks"><div class="subtasks-head"><span>STEPS (${t.subtasks.length})</span><button class="mini-add">+ Add step</button></div><ul>${steps}</ul></div><div class="attachments"><span>ATTACHMENTS (${t.attachments.length})</span><ul>${files}</ul></div><div class="form-actions"><button class="cancel" type="button">Close</button><button class="save" type="button">Edit task <span>→</span></button></div></section>`;document.body.append(panel);const dismiss=()=>closePanel(panel);panel.onclick=e=>{if(e.target===panel)dismiss();};panel.querySelector('.close').onclick=dismiss;panel.querySelector('.cancel').onclick=dismiss;panel.querySelector('.save').onclick=()=>{dismiss();edit(id);};panel.querySelector('.mini-add').onclick=()=>{dismiss();subtaskForm(id);};}
  async function subtaskForm(taskId,subtaskId){let s={name:'',due_date:'',notes:''};if(subtaskId)s=await api(`/api/tasks/${taskId}/subtasks/${subtaskId}`);const panel=document.createElement('div');panel.className='modal-backdrop open';panel.innerHTML=`<form class="modal"><div class="modal-top"><div><p class="eyebrow">${subtaskId?'EDIT STEP':'NEW STEP'}</p><h2>${subtaskId?'Update step':'Add a work step'}</h2></div><button class="close" type="button">×</button></div><label>Step name<input name="name" required maxlength="120" value="${esc(s.name)}"></label><label>Due date <span class="optional">optional</span><input name="due_date" type="date" value="${s.due_date||''}"></label><label>Notes <span class="optional">optional</span><textarea name="notes" maxlength="500">${esc(s.notes||'')}</textarea></label><label>Upload files <span class="optional">max. 50 MB each</span><input name="files" type="file" multiple></label><div class="form-actions"><button class="cancel" type="button">Cancel</button><button class="save" type="submit">Save step</button></div></form>`;document.body.append(panel);const dismiss=()=>closePanel(panel);panel.querySelector('.close').onclick=dismiss;panel.querySelector('.cancel').onclick=dismiss;panel.querySelector('form').onsubmit=async event=>{event.preventDefault();const f=event.target;const result=await api(subtaskId?`/api/tasks/${taskId}/subtasks/${subtaskId}`:`/api/tasks/${taskId}/subtasks`,{method:subtaskId?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.name.value,due_date:f.due_date.value,notes:f.notes.value})});for(const file of f.files.files){const body=new FormData();body.append('file',file);await api(`/api/tasks/${taskId}/subtasks/${result.id}/attachments`,{method:'POST',body});}dismiss();view(taskId);};}
  // Replace the legacy Step form flow.  A failed attachment upload must not
  // make an already-saved Step look as if it failed to save.
  subtaskForm = async function(taskId,subtaskId){
    let step={name:'',due_date:'',notes:''};
    if(subtaskId)step=await api(`/api/tasks/${taskId}/subtasks/${subtaskId}`);
    const panel=document.createElement('div');panel.className='modal-backdrop open';
    panel.innerHTML=`<form class="modal"><div class="modal-top"><div><p class="eyebrow">${subtaskId?'EDIT STEP':'NEW STEP'}</p><h2>${subtaskId?'Update step':'Add a work step'}</h2></div><button class="close" type="button">×</button></div><label>Step name<input name="name" required maxlength="120" value="${esc(step.name)}"></label><label>Due date <span class="optional">optional</span><input name="due_date" type="date" value="${step.due_date||''}"></label><label>Notes <span class="optional">optional</span><textarea name="notes" maxlength="500">${esc(step.notes||'')}</textarea></label><label>Upload files <span class="optional">max. 50 MB each</span><input name="files" type="file" multiple></label><div class="form-actions"><button class="cancel" type="button">Cancel</button><button class="save" type="submit">Save step</button></div></form>`;
    document.body.append(panel);
    const dismiss=()=>panel.remove();panel.querySelector('.close').onclick=dismiss;panel.querySelector('.cancel').onclick=dismiss;
    panel.querySelector('form').onsubmit=async event=>{
      event.preventDefault();const form=event.target,save=form.querySelector('.save'),files=[...form.files.files];save.disabled=true;
      try{
        const result=await api(subtaskId?`/api/tasks/${taskId}/subtasks/${subtaskId}`:`/api/tasks/${taskId}/subtasks`,{method:subtaskId?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:form.name.value,due_date:form.due_date.value,notes:form.notes.value})});
        dismiss();await refresh();await edit(taskId);
        for(const file of files){
          try{if(file.size>50*1024*1024)throw Error(`${file.name} exceeds the 50 MB limit.`);const body=new FormData();body.append('file',file);await api(`/api/tasks/${taskId}/subtasks/${result.id}/attachments`,{method:'POST',body});}
          catch(error){alert(`Step was saved, but ${file.name} could not be uploaded: ${error.message}`);}
        }
      }catch(error){alert(error.message||'Unable to save the step. Please try again.');}
      finally{save.disabled=false;}
    };
  };
  const stepRequests = new Map();
  async function subtask(taskId,id){
    const key=`${taskId}:${id}`;
    // A double-click used to issue duplicate detail requests. Reuse the
    // in-flight request and render a normal modal instead of blocking the UI
    // with alert(), which browsers can suppress or make appear unresponsive.
    let pending=stepRequests.get(key);
    if(!pending){
      pending=api(`/api/tasks/${taskId}/subtasks/${id}`).finally(()=>stepRequests.delete(key));
      stepRequests.set(key,pending);
    }
    const s=await pending;
    const files=(s.attachments||[]).map(a=>`<li><a href="/api/subtask-attachments/${a.id}/download">${esc(a.original_name)}</a><small>${(a.size/1048576).toFixed(2)} MB</small></li>`).join('')||'<li class="no-files">No attachments yet.</li>';
    const panel=document.createElement('div');panel.className='modal-backdrop open';
    panel.innerHTML=`<section class="modal"><div class="modal-top"><div><p class="eyebrow">STEP DETAIL</p><h2>${esc(s.name)}</h2></div><button class="close" type="button">×</button></div><div class="detail-grid"><div><span>DUE DATE</span><b>${date(s.due_date)}</b></div></div><div class="detail-notes"><span>NOTES</span><p>${esc(s.notes)||'No notes for this step.'}</p></div><div class="attachments"><span>ATTACHMENTS (${s.attachments.length})</span><ul>${files}</ul></div><div class="form-actions"><button class="cancel" type="button">Close</button><button class="save" type="button">Edit step <span>→</span></button></div></section>`;
    document.body.append(panel);const dismiss=()=>panel.remove();panel.onclick=e=>{if(e.target===panel)dismiss();};panel.querySelector('.close').onclick=dismiss;panel.querySelector('.cancel').onclick=dismiss;panel.querySelector('.save').onclick=()=>{dismiss();subtaskForm(taskId,id);};
  }
  async function deleteSubtask(taskId,id){if(confirm('Delete this step and its attachments?')){await api(`/api/tasks/${taskId}/subtasks/${id}`,{method:'DELETE'});view(taskId);}}
  async function deleteAttachment(id,taskId){if(confirm('Delete this attachment?')){await api(`/api/attachments/${id}`,{method:'DELETE'});view(taskId);}}
  async function exportTasks(){const button=$('#exportTasks');button.disabled=true;button.textContent='Preparing…';try{const r=await fetch(`/api/tasks/export?${query(false)}`);if(!r.ok)throw Error((await r.json()).error||'Export failed.');const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='tasks_export.xlsx';a.click();URL.revokeObjectURL(url);}catch(error){alert(error.message);}finally{button.disabled=false;button.innerHTML='<span class="button-icon">↓</span> Export Excel';}}
  window.taskUI={refresh,toggle,edit,remove,cancel,view,steps:view,subtaskForm,subtask,deleteSubtask,deleteAttachment,goto:p=>{page=p;refresh();}};
  $('#openModal').onclick=open; $('#emptyAdd').onclick=open; $('#closeModal').onclick=close; $('#cancelModal').onclick=close; $('#modal').onclick=e=>{if(e.target===$('#modal'))close();};
  $('#taskForm').onsubmit=async e=>{e.preventDefault();const f=e.target,save=f.querySelector('.save'),files=[...f.querySelector('[name=attachments]')?.files||[]],data=Object.fromEntries(new FormData(f));delete data.attachments;save.disabled=true;try{const task=await api(editingId?`/api/tasks/${editingId}`:'/api/tasks',{method:editingId?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const taskId=editingId||task.id;close();await refresh();if(files.length){try{await upload(taskId,files);await refresh();}catch(error){alert(`Task was saved, but the attachment could not be uploaded: ${error.message}`);}}}catch(error){alert(error.message||'Unable to save the task. Please try again.');}finally{save.disabled=false;}};
  const attachment=document.createElement('input');attachment.type='file';attachment.name='attachments';attachment.multiple=true;const attachmentLabel=document.createElement('label');attachmentLabel.innerHTML='Attachments <span class="optional">optional, max. 50 MB each</span>';attachmentLabel.append(attachment);$('#taskForm .form-actions').before(attachmentLabel);
  $('#taskForm [name=description]').addEventListener('input',updateNotesCount);updateNotesCount();
  let timer;$('#searchTasks').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{page=1;refresh();},250);};['#dateFrom','#dateTo'].forEach(id=>$(id).onchange=()=>{page=1;refresh();});$('#clearFilters').onclick=()=>{$('#taskFilters').reset();page=1;refresh();};document.querySelectorAll('[data-dashboard-filter]').forEach(card=>card.onclick=()=>{filter=card.dataset.dashboardFilter;page=1;refresh();$('.tasks-section').scrollIntoView({behavior:'smooth',block:'start'});});$('#exportTasks').onclick=exportTasks;refresh();
})();
