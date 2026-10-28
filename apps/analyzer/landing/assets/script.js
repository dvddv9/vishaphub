// Vishap landing: example tabs and the mobile menu. No dependencies.
(function () {
  'use strict';

  // ---- Example tabs (WAI-ARIA tabs pattern: arrow keys, Home, End) ----
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.sheet [role="tab"]'));

  function select(tab, focus) {
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      var panel = document.getElementById(t.getAttribute('aria-controls'));
      if (!panel) return;
      if (on) {
        // Re-adding the class restarts the one animation on the flagged line.
        panel.classList.remove('is-active');
        void panel.offsetWidth;
        panel.classList.add('is-active');
      } else {
        panel.classList.remove('is-active');
      }
    });
    if (focus) tab.focus();
  }

  tabs.forEach(function (tab, i) {
    tab.addEventListener('click', function () { select(tab, false); });
    tab.addEventListener('keydown', function (e) {
      var next = null;
      if (e.key === 'ArrowRight') next = tabs[(i + 1) % tabs.length];
      else if (e.key === 'ArrowLeft') next = tabs[(i - 1 + tabs.length) % tabs.length];
      else if (e.key === 'Home') next = tabs[0];
      else if (e.key === 'End') next = tabs[tabs.length - 1];
      if (next) { e.preventDefault(); select(next, true); }
    });
  });

  // ---- Mobile menu ----
  var toggle = document.getElementById('menu-toggle');
  var menu = document.getElementById('mobile-menu');

  function setMenu(open) {
    if (!toggle || !menu) return;
    menu.hidden = !open;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
  }

  if (toggle && menu) {
    toggle.addEventListener('click', function () { setMenu(menu.hidden); });
    menu.addEventListener('click', function (e) {
      if (e.target.closest('a')) setMenu(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !menu.hidden) { setMenu(false); toggle.focus(); }
    });
  }

  // ---- Reviews: real reviews only, loaded from assets/reviews.json ----
  // Each item: { "name": "...", "role": "...", "date": "2026-11-01", "text": "...", "url": "https://..." }.
  // No fetch, no file, or an empty list: the "No reviews yet" text stays. Text is set with textContent only.
  var list = document.getElementById('reviews-list');
  var empty = document.getElementById('reviews-empty');

  function renderReviews(items) {
    var shown = 0;
    items.slice(0, 12).forEach(function (r) {
      if (!r || typeof r.text !== 'string' || typeof r.name !== 'string') return;
      var text = r.text.trim().slice(0, 600);
      var name = r.name.trim().slice(0, 80);
      if (!text || !name) return;

      var li = document.createElement('li');
      li.className = 'review';

      var quote = document.createElement('blockquote');
      var p = document.createElement('p');
      p.textContent = text;
      quote.appendChild(p);
      li.appendChild(quote);

      var by = document.createElement('p');
      by.className = 'review-by';
      var strong = document.createElement('strong');
      strong.textContent = name;
      by.appendChild(strong);
      var extra = [];
      if (typeof r.role === 'string' && r.role.trim()) extra.push(r.role.trim().slice(0, 80));
      if (typeof r.date === 'string' && r.date.trim()) extra.push(r.date.trim().slice(0, 20));
      if (extra.length) by.appendChild(document.createTextNode(', ' + extra.join(', ')));
      if (typeof r.url === 'string' && /^https:\/\//.test(r.url)) {
        var a = document.createElement('a');
        a.href = r.url;
        a.rel = 'noopener';
        a.textContent = 'source';
        by.appendChild(document.createTextNode(' \u00b7 '));
        by.appendChild(a);
      }
      li.appendChild(by);
      list.appendChild(li);
      shown += 1;
    });
    if (shown) { list.hidden = false; empty.hidden = true; }
  }

  if (list && empty && window.fetch) {
    fetch('assets/reviews.json', { cache: 'no-cache' })
      .then(function (res) { return res.ok ? res.json() : []; })
      .then(function (items) { if (Array.isArray(items)) renderReviews(items); })
      .catch(function () { /* keep the empty state */ });
  }
})();
