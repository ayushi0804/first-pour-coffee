// Small helpers for the cart. Every form here still works without JavaScript.
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.content : '';
  const badge = document.querySelector('.cart-count');
  const toastBox = document.getElementById('toast');
  let toastTimer;

  function setCount(n) {
    if (!badge) return;
    badge.textContent = n;
    badge.hidden = !n;
  }

  function toast(message, ok) {
    if (!toastBox) return;
    toastBox.textContent = message;
    toastBox.className = 'toast ' + (ok ? 'toast-ok' : 'toast-error');
    toastBox.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastBox.hidden = true; }, 3200);
  }

  // "Add to cart" buttons: post in the background so the shopper keeps their place
  document.addEventListener('submit', async function (e) {
    const form = e.target.closest('form[data-add]');
    if (!form) return;
    e.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const res = await fetch(form.action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'fetch', 'X-CSRF-Token': token },
      });
      const data = await res.json();
      setCount(data.count);
      toast(data.message, data.ok);
    } catch (err) {
      form.submit();          // anything odd: do a normal form post instead
    } finally {
      button.disabled = false;
    }
  });

  // + / - buttons on the cart page
  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-step]');
    if (!btn) return;
    const form = btn.closest('form');
    const input = form.elements.qty;
    const next = (parseInt(input.value, 10) || 0) + parseInt(btn.dataset.step, 10);
    const max = parseInt(input.max, 10) || 99;
    input.value = Math.min(Math.max(next, 0), max);
    form.requestSubmit();
  });

  // typing a quantity and leaving the box saves it too
  document.addEventListener('change', function (e) {
    if (e.target.matches('.qty-form input[name="qty"]')) e.target.form.requestSubmit();
  });

  // stop double clicks on "Place order" from sending the form twice
  const checkout = document.getElementById('checkout-form');
  if (checkout) {
    checkout.addEventListener('submit', function () {
      const btn = checkout.querySelector('button[type="submit"]');
      btn.disabled = true;
      btn.textContent = 'Placing your order…';
    });
  }
})();
