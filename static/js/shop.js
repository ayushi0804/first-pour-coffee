// Live filtering for the shop page. Everything also works without JS because
// the filters are plain GET params that the server understands.
(function () {
  const filters = document.getElementById('filters');
  const searchForm = document.getElementById('site-search');
  if (!filters || !searchForm) return;

  const qInput = searchForm.elements.q;
  const hiddenQ = filters.querySelector('input[name="q"]');
  const hiddenCat = filters.querySelector('input[name="category"]');
  const minInput = filters.elements.min;
  const maxInput = filters.elements.max;
  const stockBox = filters.elements.in_stock;

  let timer = null;
  let inflight = null;

  function currentParams() {
    const p = new URLSearchParams();
    const q = qInput.value.trim();
    if (q) p.set('q', q);
    if (hiddenCat.value) p.set('category', hiddenCat.value);
    if (minInput.value) p.set('min', minInput.value);
    if (maxInput.value) p.set('max', maxInput.value);
    if (stockBox.checked) p.set('in_stock', '1');
    const sort = filters.elements.sort && filters.elements.sort.value;
    if (sort && sort !== 'featured') p.set('sort', sort);
    return p;
  }

  // keep the form controls in step with a URL (used by chips, category links, back button)
  function applyParams(p) {
    qInput.value = p.get('q') || '';
    hiddenQ.value = qInput.value;
    hiddenCat.value = p.get('category') || '';
    minInput.value = p.get('min') || '';
    maxInput.value = p.get('max') || '';
    stockBox.checked = p.get('in_stock') === '1';
    const sort = document.querySelector('select[name="sort"]');
    if (sort) sort.value = p.get('sort') || 'featured';
    markPresets();
  }

  function markPresets() {
    filters.querySelectorAll('.presets button').forEach(function (b) {
      b.classList.toggle('on', b.dataset.min === minInput.value && b.dataset.max === maxInput.value);
    });
  }

  async function load(params, opts) {
    opts = opts || {};
    const qs = params.toString();
    const url = location.pathname + (qs ? '?' + qs : '');

    if (inflight) inflight.abort();
    inflight = new AbortController();

    const results = document.getElementById('results');
    results.classList.add('loading');

    try {
      const res = await fetch(url, { headers: { 'X-Partial': '1' }, signal: inflight.signal });
      if (!res.ok) throw new Error('bad response ' + res.status);
      const doc = new DOMParser().parseFromString(await res.text(), 'text/html');

      document.getElementById('cats').replaceWith(doc.getElementById('cats'));
      document.getElementById('results').replaceWith(doc.getElementById('results'));

      if (opts.push) history.pushState(null, '', url);
      else history.replaceState(null, '', url);

      if (opts.scroll) {
        document.getElementById('results').scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } catch (err) {
      if (err.name === 'AbortError') return;
      // if anything goes wrong just fall back to a normal page load
      location.href = url;
    }
  }

  function update(delay) {
    clearTimeout(timer);
    hiddenQ.value = qInput.value.trim();
    markPresets();
    timer = setTimeout(function () { load(currentParams()); }, delay || 0);
  }

  qInput.addEventListener('input', function () { update(250); });
  minInput.addEventListener('input', function () { update(400); });
  maxInput.addEventListener('input', function () { update(400); });
  stockBox.addEventListener('change', function () { update(0); });

  // the sort <select> gets swapped out with every response, so listen on the document
  document.addEventListener('change', function (e) {
    if (e.target.matches('select[name="sort"]')) update(0);
  });

  searchForm.addEventListener('submit', function (e) { e.preventDefault(); update(0); });
  filters.addEventListener('submit', function (e) { e.preventDefault(); update(0); });

  filters.querySelectorAll('.presets button').forEach(function (b) {
    b.addEventListener('click', function () {
      const already = b.classList.contains('on');
      minInput.value = already ? '' : b.dataset.min;
      maxInput.value = already ? '' : b.dataset.max;
      update(0);
    });
  });

  // category links, chips, "clear all" and the pager are all ordinary links with data-nav
  document.addEventListener('click', function (e) {
    const link = e.target.closest('a[data-nav]');
    if (!link || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    const params = new URL(link.href).searchParams;
    applyParams(params);
    load(params, { push: true, scroll: link.hasAttribute('data-page') });
  });

  window.addEventListener('popstate', function () {
    const params = new URLSearchParams(location.search);
    applyParams(params);
    load(params);
  });

  markPresets();
})();
