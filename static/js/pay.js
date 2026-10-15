// Pay page: opens Razorpay Checkout (test mode), then sends the result to our server to verify.
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.content : '';
  const errorBox = document.getElementById('pay-error');

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  // countdown for the stock hold
  const countdown = document.getElementById('countdown');
  if (countdown && countdown.dataset.expires) {
    const end = new Date(countdown.dataset.expires).getTime();
    const tick = function () {
      const left = Math.max(0, Math.floor((end - Date.now()) / 1000));
      const m = String(Math.floor(left / 60)).padStart(2, '0');
      const s = String(left % 60).padStart(2, '0');
      countdown.textContent = left > 0 ? 'for ' + m + ':' + s : '(time is up, reload to check)';
      if (left > 0) setTimeout(tick, 1000);
    };
    tick();
  }

  const configEl = document.getElementById('pay-config');
  const button = document.getElementById('pay-button');
  if (!configEl || !button) return;          // local simulator: nothing more to do

  const page = JSON.parse(configEl.textContent);

  function post(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
      body: JSON.stringify(body),
    });
  }

  async function onSuccess(response) {
    button.disabled = true;
    button.textContent = 'Confirming your payment…';
    try {
      const res = await post(page.verify, response);
      const data = await res.json();
      if (data.ok) {
        window.location.href = data.redirect;
        return;
      }
      showError(data.message || 'We could not confirm the payment.');
    } catch (err) {
      showError('Could not reach the store to confirm. If you were charged, your order will update shortly.');
    }
    button.disabled = false;
    button.textContent = 'Try again';
  }

  button.addEventListener('click', function () {
    errorBox.hidden = true;
    const options = {
      key: page.cfg.key,
      amount: page.cfg.amount,
      currency: page.cfg.currency,
      name: 'First Pour Coffee Co.',
      description: 'Order ' + page.number,
      order_id: page.cfg.order_id,
      prefill: { name: page.name, email: page.email, contact: page.phone },
      theme: { color: '#2a44f5' },
      handler: onSuccess,
      modal: { ondismiss: function () { /* closed without paying: the order stays open */ } },
    };
    const rzp = new Razorpay(options);
    rzp.on('payment.failed', function (response) {
      const err = response.error || {};
      post(page.failed, { description: err.description, reason: err.reason, code: err.code });
      showError((err.description || 'The payment failed.') + ' You can try again.');
    });
    rzp.open();
  });
})();
