// ---- Persistent visitor ID ----
(function () {
  const KEY = 'ryaninsky_visitor_id';
  let vid = localStorage.getItem(KEY);
  if (!vid || !/^[a-f0-9\-]{36}$/.test(vid)) {
    vid = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
            const r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
          });
    localStorage.setItem(KEY, vid);
  }
  window._visitorId = vid;
})();

function apiFetch(url, options = {}) {
  options.headers = Object.assign({}, options.headers, {
    'X-Visitor-Id': window._visitorId,
  });
  return fetch(url, options);
}

// ---- Burger menu ----
const burger = document.getElementById('burger');
const mobileNav = document.getElementById('mobileNav');
if (burger && mobileNav) {
  burger.addEventListener('click', () => mobileNav.classList.toggle('open'));
}

// ---- Heart buttons on card rows ----
document.querySelectorAll('.heart-btn').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const workId = btn.dataset.workId;
    const resp = await apiFetch('/api/heart/' + workId, { method: 'POST' });
    const data = await resp.json();
    document.querySelectorAll('.heart-btn[data-work-id="' + workId + '"]').forEach(b => {
      b.classList.toggle('hearted', data.hearted);
      b.textContent = data.hearted ? '❤️' : '🤍';
    });
    document.querySelectorAll('.hearts-val[data-work-id="' + workId + '"]').forEach(el => {
      el.textContent = data.count;
    });
  });
});

// ---- Heart button on detail page ----
const workHeartBtn = document.getElementById('workHeartBtn');
if (workHeartBtn) {
  workHeartBtn.addEventListener('click', async () => {
    const workId = workHeartBtn.dataset.workId;
    const resp = await apiFetch('/api/heart/' + workId, { method: 'POST' });
    const data = await resp.json();
    workHeartBtn.classList.toggle('hearted', data.hearted);
    workHeartBtn.textContent = data.hearted ? '❤️' : '🤍';
    const countEl = document.getElementById('workHeartsCount');
    if (countEl) countEl.textContent = data.count;
  });
}

// ---- Suggest form ----
const suggestForm = document.getElementById('suggestForm');
if (suggestForm) {
  suggestForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = {
      title: suggestForm.title_field.value.trim(),
      category: suggestForm.category_field.value,
      note: suggestForm.note_field.value.trim(),
    };
    if (!formData.title) return;
    const resp = await apiFetch('/api/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    });
    const data = await resp.json();
    if (data.id) {
      suggestForm.reset();
      prependSuggestion(data);
    }
  });
}

function prependSuggestion(s) {
  const list = document.getElementById('suggestionsList');
  if (!list) return;
  const div = document.createElement('div');
  div.className = 'suggestion-item';
  div.innerHTML = '<div>'
    + '<div class="suggestion-title">' + esc(s.title) + '</div>'
    + (s.category ? '<div class="suggestion-cat">' + esc(s.category) + '</div>' : '')
    + (s.note ? '<div class="suggestion-note">' + esc(s.note) + '</div>' : '')
    + '<div class="suggestion-date">' + esc(s.created_at) + '</div>'
    + '</div>'
    + '<span class="suggestion-status status-considering">Рассматривается</span>';
  list.prepend(div);
}

function esc(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ---- Admin: suggestion status ----
document.querySelectorAll('.status-select').forEach(sel => {
  sel.addEventListener('change', async () => {
    const sid = sel.dataset.sid;
    await apiFetch('/admin/suggestion/' + sid + '/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: sel.value }),
    });
  });
});

// ---- Admin: highlight rows ----
const addHighlightBtn = document.getElementById('addHighlight');
if (addHighlightBtn) {
  addHighlightBtn.addEventListener('click', () => {
    const group = document.getElementById('highlightsGroup');
    const row = document.createElement('div');
    row.className = 'highlight-row';
    row.innerHTML = '<input type="text" name="highlight_ep[]" placeholder="Серия / трек / глава" style="max-width:160px">'
      + '<input type="text" name="highlight_title[]" placeholder="Название" style="flex:2">'
      + '<input type="text" name="highlight_note[]" placeholder="Заметка">'
      + '<button type="button" class="rm-highlight" onclick="this.closest(\'.highlight-row\').remove()">✕</button>';
    group.appendChild(row);
  });
}
