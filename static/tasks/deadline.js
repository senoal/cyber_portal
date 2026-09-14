/* Add overdue awareness to the existing Deadline card without changing its
   filters, animation, or task-list workflow. */
(() => {
  const card = document.querySelector('#deadlineCard');
  const count = document.querySelector('#todayCount');
  const label = document.querySelector('#deadlineLabel');
  if (!card || !count || !label) return;

  const update = () => {
    const overdue = Number(card.dataset.overdue || 0);
    const dueToday = Number(card.dataset.dueToday || 0);
    const attention = overdue + dueToday;
    if (Number(count.textContent) !== attention) count.textContent = attention;
    card.classList.toggle('has-warning', attention > 0);
    if (!attention) label.textContent = 'Tidak ada deadline atau task overdue';
    else if (overdue && dueToday) label.textContent = `${overdue} task overdue · ${dueToday} deadline hari ini`;
    else if (overdue) label.textContent = `${overdue} task overdue perlu perhatian`;
    else label.textContent = `${dueToday} task perlu perhatian hari ini`;
  };

  const fetchNative = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const response = await fetchNative(input, init);
    const url = typeof input === 'string' ? input : input.url;
    if (response.ok && url.includes('/api/stats')) {
      response.clone().json().then(stats => {
        card.dataset.overdue = String(stats.overdue || 0);
        card.dataset.dueToday = String(stats.due_today || 0);
        update();
      }).catch(() => {});
    }
    return response;
  };

  new MutationObserver(update).observe(count, {childList: true, characterData: true, subtree: true});
  refresh();
})();
