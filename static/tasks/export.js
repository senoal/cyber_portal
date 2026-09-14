document.querySelector('#exportTasks').onclick = async () => {
  const button = document.querySelector('#exportTasks');
  button.disabled = true; button.textContent = 'Menyiapkan...';
  try {
    const params = new URLSearchParams(filterQuery()); params.delete('page');
    const response = await fetch(`/api/tasks/export?${params}`);
    if (!response.ok) { const error = await response.json(); throw new Error(error.error || 'Ekspor gagal.'); }
    const blob = await response.blob(); const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = 'tasks_export.xlsx'; link.click(); URL.revokeObjectURL(url);
  } catch (error) { alert(error.message); }
  finally { button.disabled = false; button.textContent = 'Export Excel'; }
};
