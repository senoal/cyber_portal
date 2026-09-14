async function openSubtaskForm(taskId, subtaskId = null) {
  let s = {name:'', due_date:'', notes:''};
  if (subtaskId) s = await request(`/api/tasks/${taskId}/subtasks/${subtaskId}`);
  const d = document.createElement('div'); d.className = 'modal-backdrop open';
  d.innerHTML = `<form class="modal"><div class="modal-top"><div><p class="eyebrow">${subtaskId?'EDIT STEP':'STEP BARU'}</p><h2>${subtaskId?'Perbarui langkah':'Tambahkan langkah kerja'}</h2></div><button class="close" type="button">×</button></div><label>Nama step<input name="name" required maxlength="120" value="${esc(s.name)}" placeholder="Misalnya, Analysis"></label><label>Due date <span class="optional">opsional</span><input name="due_date" type="date" value="${s.due_date||''}"></label><label>Catatan <span class="optional">opsional</span><textarea name="notes" maxlength="500">${esc(s.notes||'')}</textarea></label><label>Upload file <span class="optional">maks. 50 MB per file</span><input name="files" type="file" multiple></label><div class="form-actions"><button class="cancel" type="button">Batal</button><button class="save" type="submit">Simpan step</button></div></form>`;
  document.body.append(d); const close=()=>d.remove(); d.querySelector('.close').onclick=close; d.querySelector('.cancel').onclick=close;
  d.querySelector('form').onsubmit = async e => { e.preventDefault(); const f=e.target;
    const result=await request(subtaskId?`/api/tasks/${taskId}/subtasks/${subtaskId}`:`/api/tasks/${taskId}/subtasks`, {method:subtaskId?'PATCH':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.name.value,due_date:f.due_date.value,notes:f.notes.value})});
    const stepId=subtaskId||result.id; for(const file of f.files.files){const body=new FormData();body.append('file',file);await request(`/api/tasks/${taskId}/subtasks/${stepId}/attachments`,{method:'POST',body})} close(); viewTask(taskId);
  };
}
async function deleteSubtask(taskId, subtaskId) { if(confirm('Hapus step ini beserta lampirannya?')) { await request(`/api/tasks/${taskId}/subtasks/${subtaskId}`,{method:'DELETE'}); viewTask(taskId); } }
async function viewSubtask(taskId, subtaskId) { const s=await request(`/api/tasks/${taskId}/subtasks/${subtaskId}`); const files=s.attachments.map(a=>`<li><a href="/api/subtask-attachments/${a.id}/download">${esc(a.original_name)}</a><small>${(a.size/1024/1024).toFixed(2)} MB</small></li>`).join('')||'<li class="no-files">Belum ada lampiran.</li>'; const d=document.createElement('div');d.className='modal-backdrop open';d.innerHTML=`<section class="modal"><div class="modal-top"><div><p class="eyebrow">STEP DETAIL</p><h2>${esc(s.name)}</h2></div><button class="close">×</button></div><div class="detail-grid"><div><span>DUE DATE</span><b>${fmtDate(s.due_date)||'Belum ditentukan'}</b></div></div><div class="detail-notes"><span>CATATAN</span><p>${esc(s.notes)||'Tidak ada catatan.'}</p></div><div class="attachments"><span>LAMPIRAN (${s.attachments.length})</span><ul>${files}</ul></div><div class="form-actions"><button class="cancel">Tutup</button><button class="save">Edit step</button></div></section>`;document.body.append(d); const close=()=>d.remove();d.querySelector('.close').onclick=close;d.querySelector('.cancel').onclick=close;d.querySelector('.save').onclick=()=>{close();openSubtaskForm(taskId,subtaskId)}; }
const taskDetail = viewTask;
viewTask = async function(id) { await taskDetail(id); const panel=document.querySelector('.detail-modal'); if(!panel)return; const t=await request(`/api/tasks/${id}`); const steps=(t.subtasks||[]).map(s=>`<li><div><b>${esc(s.name)}</b><small>${fmtDate(s.due_date)||'Tanpa tenggat'}${s.notes?' · Ada catatan':''}</small></div><div class="step-actions"><button onclick="viewSubtask(${id},${s.id})">View</button><button onclick="openSubtaskForm(${id},${s.id})">Edit</button><button class="danger" onclick="deleteSubtask(${id},${s.id})">Delete</button></div></li>`).join('')||'<li class="no-files">Belum ada langkah.</li>'; const box=document.createElement('div');box.className='subtasks';box.innerHTML=`<div class="subtasks-head"><span>STEP / SUBTASK (${t.subtasks.length})</span><button class="mini-add">+ Tambah step</button></div><ul>${steps}</ul>`;panel.querySelector('.attachments').before(box);box.querySelector('.mini-add').onclick=()=>openSubtaskForm(id); };

// Make the feature discoverable directly from each task card as well.
function addStepButtons() {
  document.querySelectorAll('.task-actions').forEach(actions => {
    if (actions.querySelector('.steps-button')) return;
    const view = actions.querySelector('button[onclick^="viewTask("]');
    const match = view && view.getAttribute('onclick').match(/\d+/);
    if (!match) return;
    const button = document.createElement('button');
    button.className = 'steps-button'; button.textContent = 'Steps';
    button.onclick = () => openSubtaskPanel(Number(match[0]));
    actions.prepend(button);
  });
}
async function openSubtaskPanel(taskId) {
  const t = await request(`/api/tasks/${taskId}`);
  const rows = (t.subtasks || []).map(s => `<li><div><b>${esc(s.name)}</b><small>${fmtDate(s.due_date)||'Tanpa tenggat'}</small></div><div class="step-actions"><button onclick="viewSubtask(${taskId},${s.id})">View</button><button onclick="openSubtaskForm(${taskId},${s.id})">Edit</button><button class="danger" onclick="deleteSubtask(${taskId},${s.id})">Delete</button></div></li>`).join('') || '<li class="no-files">Belum ada step. Tambahkan langkah pertama.</li>';
  const d=document.createElement('div'); d.className='modal-backdrop open';
  d.innerHTML=`<section class="modal"><div class="modal-top"><div><p class="eyebrow">STEP / SUBTASK</p><h2>${esc(t.title)}</h2></div><button class="close">×</button></div><div class="subtasks"><div class="subtasks-head"><span>${t.subtasks.length} STEP</span><button class="mini-add">+ Tambah step</button></div><ul>${rows}</ul></div><div class="form-actions"><button class="cancel">Tutup</button></div></section>`;
  document.body.append(d); const close=()=>d.remove(); d.querySelector('.close').onclick=close; d.querySelector('.cancel').onclick=close; d.querySelector('.mini-add').onclick=()=>{close();openSubtaskForm(taskId)};
}
new MutationObserver(addStepButtons).observe(document.querySelector('#taskList'), {childList:true, subtree:true});
addStepButtons();
