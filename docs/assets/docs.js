// Shared behaviour for generated docs pages (docs/xs_game/CARDS.html, docs/xs_game/KNOBS.html): click a
// header to sort, type in the search box to filter. One file, linked, so a page never carries its
// own copy — the same reasoning engine/termcade/web moved its scripts out of Python strings for.

window.sortable = function sortable(table) {
  const headers = table.querySelectorAll('th');
  headers.forEach((th, i) => {
    th.addEventListener('click', () => {
      const desc = th.classList.contains('sorted') && !th.classList.contains('desc');
      headers.forEach((h) => h.classList.remove('sorted', 'desc'));
      th.classList.add('sorted');
      if (desc) th.classList.add('desc');
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {
        const av = a.children[i].dataset.sort ?? a.children[i].textContent.trim();
        const bv = b.children[i].dataset.sort ?? b.children[i].textContent.trim();
        const an = parseFloat(av);
        const bn = parseFloat(bv);
        const cmp = !isNaN(an) && !isNaN(bn) ? an - bn : av.localeCompare(bv);
        return desc ? -cmp : cmp;
      });
      rows.forEach((r) => tbody.appendChild(r));
    });
  });
};

window.filterable = function filterable(input, table, countEl) {
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase();
    let shown = 0;
    table.querySelectorAll('tbody tr').forEach((tr) => {
      const hit = tr.textContent.toLowerCase().includes(q);
      tr.style.display = hit ? '' : 'none';
      if (hit) shown++;
    });
    if (countEl) countEl.textContent = `${shown} shown`;
  });
};

// A <select data-filter-column="N" data-filter-target="tableId" data-count="countId">
// filters that table's rows by an exact match on column N's text (case-insensitive), same
// independent-toggle behaviour as `filterable` above — the two don't combine, whichever fires
// last wins, matching how the search box and a column filter always behaved on this page.
window.columnFilterable = function columnFilterable(select) {
  const table = document.getElementById(select.dataset.filterTarget);
  const countEl = document.getElementById(select.dataset.count);
  const col = parseInt(select.dataset.filterColumn, 10);
  select.addEventListener('change', () => {
    const v = select.value.toLowerCase();
    let shown = 0;
    table.querySelectorAll('tbody tr').forEach((tr) => {
      const cell = tr.children[col].textContent.trim().toLowerCase();
      const hit = !v || cell === v;
      tr.style.display = hit ? '' : 'none';
      if (hit) shown++;
    });
    if (countEl) countEl.textContent = `${shown} shown`;
  });
};

// Click-to-explain for a `.mech` cell, wired from the page's own #mechanic-rules JSON blob
// (embedded by docs_html.py's mechanic_rules_script()) — one shared popup element, reused and
// repositioned under whichever cell was clicked, so the rule stays a click away without ever
// duplicating game text by hand onto the page.
window.mechanicPopups = function mechanicPopups() {
  const dataEl = document.getElementById('mechanic-rules');
  if (!dataEl) return;
  const rules = JSON.parse(dataEl.textContent);

  const popup = document.createElement('div');
  popup.className = 'mech-popup';
  popup.hidden = true;
  document.body.appendChild(popup);
  popup.addEventListener('click', (event) => event.stopPropagation());

  function showFor(cell, mechanic) {
    popup.textContent = '';
    const text = document.createElement('p');
    text.textContent = rules[mechanic];
    popup.append(text);
    const r = cell.getBoundingClientRect();
    const left = Math.min(r.left + window.scrollX, document.documentElement.clientWidth - 320);
    popup.style.left = `${Math.max(0, left)}px`;
    popup.style.top = `${r.bottom + window.scrollY + 4}px`;
    popup.hidden = false;
  }

  document.querySelectorAll('td.mech').forEach((cell) => {
    const mechanic = cell.textContent.trim();
    if (!rules[mechanic]) return;
    cell.classList.add('mech-clickable');
    cell.addEventListener('click', (event) => {
      event.stopPropagation();
      const wasShowingThis = !popup.hidden && popup.dataset.mechanic === mechanic;
      popup.hidden = true;
      if (!wasShowingThis) {
        popup.dataset.mechanic = mechanic;
        showFor(cell, mechanic);
      }
    });
  });

  document.addEventListener('click', () => {
    popup.hidden = true;
  });
};

// Wires every generated page from data attributes alone — no page ever needs its own inline
// <script>, so nothing can call `sortable`/`filterable` before this file has defined them.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('table[data-sortable]').forEach(window.sortable);
  document.querySelectorAll('input[data-filter]').forEach((input) => {
    window.filterable(
      input,
      document.getElementById(input.dataset.filter),
      document.getElementById(input.dataset.count),
    );
  });
  document.querySelectorAll('select[data-filter-column]').forEach(window.columnFilterable);
  window.mechanicPopups();
});
