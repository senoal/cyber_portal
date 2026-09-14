let taskStates = new Map();
const paginatedRefresh = refresh;
refresh = async function() {
  await paginatedRefresh();
  const result = await request(`/api/tasks?${filterQuery()}`);
  taskStates = new Map(result.items.map(task => [task.id, task]));
  document.querySelectorAll('.task').forEach(card => {
    const view = card.querySelector('button[onclick^="viewTask("]');
    const id = Number(view?.getAttribute('onclick').match(/\d+/)?.[0]);
    const task = taskStates.get(id); if (!task) return;
    if (task.canceled) {
      card.classList.add('canceled');
      const check=card.querySelector('.check'); check.checked=false; check.disabled=true;
      card.querySelector('.task-title').insertAdjacentHTML('beforeend',' <span class="cancelled-badge">BATAL</span>');
    }
    const actions=card.querySelector('.task-actions');
    const button=document.createElement('button'); button.className='cancel-button';
    button.textContent=task.canceled?'Aktifkan':'Batalkan';
    button.onclick=()=>setCanceled(id,!task.canceled); actions.append(button);
  });
};
async function setCanceled(id, canceled) {
  const message=canceled?'Batalkan task ini? Task tetap tersimpan dan dapat diaktifkan kembali.':'Aktifkan kembali task ini?';
  if (!confirm(message)) return;
  await request(`/api/tasks/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({canceled})});
  refresh();
}
refresh();
