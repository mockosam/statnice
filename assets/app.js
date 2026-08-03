/* ============================================================================
   Státnice — chování stránek
   Bez frameworků a bez fetch(), takže vše funguje i při otevření souboru
   přímo z disku (file://) i na GitHub Pages.

     1. Pomůcky a úložiště      5. Postup (naučeno / k zopakování)
     2. Motiv                   6. Kartičky
     3. Obsah stránky + TOC     7. Glosář — filtr
     4. Hledání                 8. Klávesové zkratky
   ========================================================================== */
(function () {
  'use strict';

  var DATA = window.STATNICE_DATA || { docs: [] };
  var BODY = document.body;
  var UP = BODY.dataset.up || '';
  var SUBJECT = BODY.dataset.subject || '';
  var KIND = BODY.dataset.kind || '';

  /* -------------------------------------------------- 1. Pomůcky a úložiště */

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /** Text bez diakritiky a malými písmeny — pro hledání a filtrování. */
  function fold(s) {
    return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  }

  var store = {
    get: function (key, dflt) {
      try {
        var raw = localStorage.getItem('statnice.' + key);
        return raw ? JSON.parse(raw) : dflt;
      } catch (e) { return dflt; }
    },
    set: function (key, val) {
      try { localStorage.setItem('statnice.' + key, JSON.stringify(val)); } catch (e) {}
    },
    raw: function (key) { try { return localStorage.getItem('statnice.' + key); } catch (e) { return null; } },
    rawSet: function (key, val) { try { localStorage.setItem('statnice.' + key, val); } catch (e) {} }
  };

  /* -------------------------------------------------- 2. Motiv */

  function initTheme() {
    $$('[data-act="theme"]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
        document.documentElement.dataset.theme = next;
        store.rawSet('theme', JSON.stringify(next));
        btn.setAttribute('aria-label', next === 'light' ? 'Přepnout na tmavý režim' : 'Přepnout na světlý režim');
      });
    });
  }

  /* -------------------------------------------------- 3. Obsah stránky (TOC) */

  function initToc() {
    var nav = $('.toc');
    if (!nav) return;
    var heads = $$('.content h2, .content h3').filter(function (h) { return h.id; });
    if (heads.length < 2) { nav.remove(); return; }

    var toggle = el('button', 'toc-toggle');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.appendChild(el('span', null, 'Obsah stránky'));
    toggle.appendChild(el('span', 'toc-n', String(heads.length)));

    var head = el('div', 'toc-head', 'Na této stránce');
    var list = el('ol', 'toc-list');

    heads.forEach(function (h) {
      var li = el('li', h.tagName === 'H3' ? 'lvl3' : 'lvl2');
      var a = el('a', null, (h.textContent || '').trim());
      a.href = '#' + h.id;
      a.dataset.for = h.id;
      li.appendChild(a);
      list.appendChild(li);
    });

    nav.appendChild(toggle);
    nav.appendChild(head);
    nav.appendChild(list);

    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    list.addEventListener('click', function () { nav.classList.remove('open'); });

    // zvýraznění právě čtené sekce
    if (!('IntersectionObserver' in window)) return;
    var links = {};
    $$('a', list).forEach(function (a) { links[a.dataset.for] = a; });
    var visible = [];
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        var i = visible.indexOf(e.target.id);
        if (e.isIntersecting && i < 0) visible.push(e.target.id);
        if (!e.isIntersecting && i >= 0) visible.splice(i, 1);
      });
      var top = null, best = Infinity;
      visible.forEach(function (id) {
        var t = document.getElementById(id).getBoundingClientRect().top;
        if (t < best) { best = t; top = id; }
      });
      $$('a', list).forEach(function (a) { a.classList.toggle('on', a.dataset.for === top); });
    }, { rootMargin: '-15% 0px -70% 0px' });
    heads.forEach(function (h) { obs.observe(h); });
  }

  /* -------------------------------------------------- 4. Hledání */

  var searchOv = null;

  function buildSearchOverlay() {
    var ov = el('div', 'ov');
    ov.id = 'search-ov';
    ov.innerHTML =
      '<div class="ov-panel" role="dialog" aria-modal="true" aria-label="Hledání v materiálu">' +
      '  <div class="ov-head">' +
      '    <input id="sq" type="search" autocomplete="off" spellcheck="false" placeholder="Hledat v otázkách i glosáři…">' +
      '    <button class="ov-close" type="button">Esc</button>' +
      '  </div>' +
      '  <div class="sres" id="sres"></div>' +
      '  <div class="ov-foot"><span><kbd>↑</kbd><kbd>↓</kbd> výběr</span>' +
      '<span><kbd>Enter</kbd> otevřít</span><span><kbd>Esc</kbd> zavřít</span></div>' +
      '</div>';
    document.body.appendChild(ov);

    var input = $('#sq', ov);
    var res = $('#sres', ov);
    var sel = 0;

    function close() { ov.classList.remove('on'); document.documentElement.style.overflow = ''; }
    $('.ov-close', ov).addEventListener('click', close);
    ov.addEventListener('mousedown', function (e) { if (e.target === ov) close(); });

    function render(hits, q) {
      res.innerHTML = '';
      if (!q) {
        res.appendChild(el('p', 'sres-empty', 'Napište, co hledáte — pojem, zákon, jméno autora…'));
        return;
      }
      if (!hits.length) {
        res.appendChild(el('p', 'sres-empty', 'Nic nenalezeno. Zkuste kratší nebo jiný výraz.'));
        return;
      }
      hits.forEach(function (h, i) {
        var a = el('a', 'shit' + (i === sel ? ' sel' : ''));
        a.href = UP + h.doc.u + (h.anchor ? '#' + h.anchor : '');
        var top = el('div', 'shit-top');
        top.appendChild(el('span', null, h.doc.n ? 'Otázka ' + h.doc.n : (DATA.labels && DATA.labels[h.doc.k]) || 'Materiál'));
        top.appendChild(el('span', 'shit-kind', h.where));
        a.appendChild(top);
        a.appendChild(el('span', 'shit-title', h.doc.t));
        var snip = el('span', 'shit-snip');
        snip.innerHTML = h.snippet;
        a.appendChild(snip);
        res.appendChild(a);
      });
    }

    function esc(s) { return s.replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }

    function snippetOf(text, tokens) {
      var folded = fold(text);
      var longest = tokens.slice().sort(function (a, b) { return b.length - a.length; })[0] || '';
      var at = folded.indexOf(longest);
      if (at < 0) at = 0;
      var from = Math.max(0, at - 70);
      var raw = text.slice(from, from + 190);
      if (from > 0) raw = '…' + raw;
      if (from + 190 < text.length) raw += '…';
      var out = esc(raw);
      // zvýraznění: pracujeme na složeném textu, abychom trefili i slova s diakritikou
      tokens.forEach(function (tok) {
        if (tok.length < 2) return;
        var f = fold(out), lo = 0, pieces = [], idx;
        while ((idx = f.indexOf(tok, lo)) >= 0) {
          if (out.slice(0, idx).lastIndexOf('<') > out.slice(0, idx).lastIndexOf('>')) { lo = idx + tok.length; continue; }
          pieces.push(out.slice(lo, idx), '<mark>', out.substr(idx, tok.length), '</mark>');
          lo = idx + tok.length;
        }
        if (pieces.length) { pieces.push(out.slice(lo)); out = pieces.join(''); f = fold(out); }
      });
      return out;
    }

    function search(q) {
      var tokens = fold(q).split(/\s+/).filter(function (t) { return t.length > 1; });
      if (!tokens.length) return [];
      var hits = [];
      DATA.docs.forEach(function (d) {
        if (!d._f) {
          d._f = {
            t: fold(d.t),
            h: fold((d.h || []).join(' • ')),
            c: fold((d.c || []).map(function (p) { return p[0]; }).join(' • ')),
            x: fold(d.x || '')
          };
        }
        var score = 0, ok = true;
        tokens.forEach(function (tok) {
          var s = 0;
          if (d._f.t.indexOf(tok) >= 0) s += 12;
          if (d._f.c.indexOf(tok) >= 0) s += 7;
          if (d._f.h.indexOf(tok) >= 0) s += 5;
          var n = d._f.x.split(tok).length - 1;
          s += Math.min(n, 8);
          if (!s) ok = false;
          score += s;
        });
        if (!ok) return;
        // do jaké části stránky odkaz míří
        var where = 'text', anchor = '';
        var hi = (d.h || []).findIndex(function (h) { return tokens.every(function (t) { return fold(h).indexOf(t) >= 0; }); });
        if (hi >= 0) { where = 'nadpis'; anchor = (d.hid || [])[hi] || ''; score += 6; }
        else if (tokens.every(function (t) { return d._f.c.indexOf(t) >= 0; })) { where = 'klíčový pojem'; score += 4; }
        hits.push({ doc: d, score: score, where: where, anchor: anchor, snippet: snippetOf(d.x || d.t, tokens) });
      });
      return hits.sort(function (a, b) { return b.score - a.score; }).slice(0, 24);
    }

    var timer = null;
    input.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(function () { sel = 0; render(search(input.value), input.value.trim()); }, 90);
    });
    input.addEventListener('keydown', function (e) {
      var items = $$('.shit', res);
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!items.length) return;
        sel = (sel + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
        items.forEach(function (a, i) { a.classList.toggle('sel', i === sel); });
        items[sel].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        if (items[sel]) { e.preventDefault(); items[sel].click(); }
      } else if (e.key === 'Escape') { close(); }
    });

    searchOv = { node: ov, open: function () {
      ov.classList.add('on');
      document.documentElement.style.overflow = 'hidden';
      input.value = ''; sel = 0; render([], '');
      input.focus();
    }, close: close, isOpen: function () { return ov.classList.contains('on'); } };
    render([], '');
  }

  function openSearch() {
    if (!DATA.docs.length) return;
    if (!searchOv) buildSearchOverlay();
    searchOv.open();
  }

  function initSearch() {
    $$('[data-act="search"]').forEach(function (b) {
      if (!DATA.docs.length) { b.remove(); return; }
      b.addEventListener('click', openSearch);
    });
  }

  /* -------------------------------------------------- 5. Postup */

  var STATES = ['none', 'done', 'review'];
  var STATE_LABEL = { none: 'Označit jako naučené', done: 'Naučeno', review: 'K zopakování' };
  var STATE_SHORT = { none: 'neoznačeno', done: 'naučeno', review: 'zopakovat' };

  function progress() { return store.get('progress', {}); }

  function getState(subject, n) {
    var p = progress();
    return (p[subject] && p[subject][n]) || 'none';
  }

  function setState(subject, n, state) {
    var p = progress();
    if (!p[subject]) p[subject] = {};
    if (state === 'none') delete p[subject][n];
    else p[subject][n] = state;
    store.set('progress', p);
  }

  function initProgressChip() {
    var chip = $('[data-act="progress"]');
    if (!chip) return;
    var n = chip.dataset.q;
    function paint() {
      var st = getState(SUBJECT, n);
      chip.textContent = STATE_LABEL[st];
      chip.setAttribute('aria-pressed', st === 'done' ? 'true' : 'false');
      chip.title = 'Stav otázky: ' + STATE_SHORT[st] + ' — klikněte pro změnu (naučeno → k zopakování → neoznačeno)';
      chip.style.borderColor = st === 'review' ? 'var(--c-key)' : '';
      chip.style.color = st === 'review' ? 'var(--c-key)' : '';
    }
    chip.addEventListener('click', function () {
      var st = getState(SUBJECT, n);
      setState(SUBJECT, n, STATES[(STATES.indexOf(st) + 1) % STATES.length]);
      paint();
    });
    paint();
  }

  function initProgressList() {
    var rows = $$('.qrow[data-q]');
    if (!rows.length) return;
    var bar = $('.prog-fill');
    var lbl = $('#prog-label');
    var reset = $('.prog-reset');

    function paint() {
      var done = 0, review = 0;
      rows.forEach(function (row) {
        var st = getState(SUBJECT, row.dataset.q);
        row.dataset.state = st;
        var tag = $('.qrow-state', row);
        if (tag) tag.textContent = STATE_SHORT[st];
        if (st === 'done') done++;
        if (st === 'review') review++;
      });
      if (bar) bar.style.width = (rows.length ? (done / rows.length) * 100 : 0) + '%';
      if (lbl) {
        lbl.innerHTML = '<b>' + done + ' / ' + rows.length + '</b> naučeno' +
          (review ? ' · ' + review + ' k zopakování' : '');
      }
      if (reset) reset.hidden = !(done || review);
    }

    // klik na štítek stavu přepne stav bez opuštění přehledu
    rows.forEach(function (row) {
      var tag = $('.qrow-state', row);
      if (!tag) return;
      tag.setAttribute('role', 'button');
      tag.tabIndex = 0;
      tag.title = 'Přepnout stav této otázky';
      function toggle(e) {
        e.preventDefault(); e.stopPropagation();
        var st = getState(SUBJECT, row.dataset.q);
        setState(SUBJECT, row.dataset.q, STATES[(STATES.indexOf(st) + 1) % STATES.length]);
        paint();
      }
      tag.addEventListener('click', toggle);
      tag.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') toggle(e); });
    });

    if (reset) {
      reset.addEventListener('click', function () {
        if (!confirm('Smazat uložený postup u tohoto předmětu?')) return;
        var p = progress();
        delete p[SUBJECT];
        store.set('progress', p);
        paint();
      });
    }
    paint();
  }

  function initHubProgress() {
    $$('[data-progress-for]').forEach(function (node) {
      var subj = node.dataset.progressFor;
      var total = parseInt(node.dataset.total, 10) || 0;
      var p = progress()[subj] || {};
      var done = Object.keys(p).filter(function (k) { return p[k] === 'done'; }).length;
      node.textContent = done ? done + ' / ' + total + ' naučeno' : total + ' otázek';
    });
  }

  /* -------------------------------------------------- 6. Kartičky */

  var cardOv = null;

  function splitTerm(text) {
    var m = (text || '').match(/^([\s\S]*?)\s[—–]\s([\s\S]+)$/);
    if (!m) return null;
    return [m[1].trim(), m[2].trim()];
  }

  /** Kartičky z právě zobrazené stránky (sekce Klíčové pojmy). */
  function deckFromPage() {
    var out = [];
    $$('.sec-key li, .box.key li, .glist .gitem').forEach(function (li) {
      if (li.classList && li.classList.contains('gitem')) {
        var dt = $('dt', li), dd = $('dd', li);
        if (dt && dd) out.push([dt.textContent.trim(), dd.textContent.trim(), '']);
        return;
      }
      // poznámky „Aktualizace 2026“ do definice na kartičce nepatří
      var clone = li.cloneNode(true);
      $$('details.upd', clone).forEach(function (d) { d.remove(); });
      var pair = splitTerm(clone.textContent.replace(/\s+/g, ' '));
      if (pair) out.push([pair[0], pair[1], '']);
    });
    return out;
  }

  /** Kartičky ze všech stránek podle indexu v data.js; pojmy se neopakují. */
  function deckFromData(filter) {
    var out = [], seen = {};
    // otázky mají přednost před glosářem — dávají pojmu kontext
    var docs = DATA.docs.slice().sort(function (a, b) { return (a.n ? 0 : 1) - (b.n ? 0 : 1); });
    docs.forEach(function (d) {
      if (!d.c || !d.c.length) return;
      if (filter && !filter(d)) return;
      d.c.forEach(function (pair) {
        var key = fold(pair[0]).replace(/\(.*?\)/g, '').replace(/[^a-z0-9× ]/g, '').trim();
        if (seen[key]) return;
        seen[key] = 1;
        out.push([pair[0], pair[1], d.n ? 'Otázka ' + d.n : d.t, UP + d.u]);
      });
    });
    return out;
  }

  function shuffle(a) {
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }

  function buildCardOverlay() {
    var ov = el('div', 'ov');
    ov.id = 'cards-ov';
    ov.innerHTML =
      '<div class="ov-panel card-panel" role="dialog" aria-modal="true" aria-label="Kartičky">' +
      '  <div class="ov-head"><h2>Kartičky</h2><span class="card-count" id="ccount"></span>' +
      '  <button class="ov-close" type="button">Esc</button></div>' +
      '  <div class="card-body" id="cbody"></div>' +
      '</div>';
    document.body.appendChild(ov);

    var body = $('#cbody', ov);
    var count = $('#ccount', ov);
    var queue = [], right = 0, wrong = 0, shown = false;

    function close() { ov.classList.remove('on'); document.documentElement.style.overflow = ''; }
    $('.ov-close', ov).addEventListener('click', close);
    ov.addEventListener('mousedown', function (e) { if (e.target === ov) close(); });

    function finish() {
      count.textContent = '';
      body.innerHTML = '';
      var d = el('div', 'card-done');
      d.appendChild(el('h3', null, 'Hotovo 🎓'));
      d.appendChild(el('p', null, 'Správně napoprvé: ' + right + ' · opakováno: ' + wrong));
      var again = el('button', 'chip', 'Znovu');
      again.type = 'button';
      again.addEventListener('click', function () { start(cardOv.deck); });
      d.appendChild(again);
      body.appendChild(d);
    }

    function draw() {
      if (!queue.length) return finish();
      var card = queue[0];
      shown = false;
      count.textContent = 'zbývá ' + queue.length;
      body.innerHTML = '';

      var face = el('div', 'card-face');
      face.appendChild(el('div', 'card-term', card[0]));
      var def = el('div', 'card-def hidden', card[1]);
      face.appendChild(def);
      var hint = el('div', 'card-hint', 'klepnutím nebo mezerníkem zobrazíte definici');
      face.appendChild(hint);
      if (card[2]) {
        var src = el('div', 'card-src');
        if (card[3]) {
          var a = el('a', null, card[2]);
          a.href = card[3];
          src.appendChild(a);
        } else { src.textContent = card[2]; }
        face.appendChild(src);
      }
      body.appendChild(face);

      var acts = el('div', 'card-acts');
      var no = el('button', 'chip no', 'Neumím');
      var yes = el('button', 'chip yes', 'Umím');
      no.type = yes.type = 'button';
      acts.appendChild(no); acts.appendChild(yes);
      body.appendChild(acts);
      acts.hidden = true;

      function reveal() {
        if (shown) return;
        shown = true;
        def.classList.remove('hidden');
        hint.textContent = 'znáte odpověď?';
        acts.hidden = false;
      }
      face.addEventListener('click', reveal);
      no.addEventListener('click', function () {
        wrong++;
        wrongOnce[card[0]] = true;
        queue.splice(Math.min(queue.length, 4), 0, queue.shift());  // zařadíme ji zpět do balíčku
        draw();
      });
      yes.addEventListener('click', function () {
        if (!wrongOnce[card[0]]) right++;   // „napoprvé“ se počítá jen bez předchozí chyby
        queue.shift();
        draw();
      });
      cardOv._reveal = reveal;
      cardOv._yes = yes;
      cardOv._no = no;
    }

    var wrongOnce = {};
    function start(deck) {
      cardOv.deck = deck;
      queue = shuffle(deck.slice());
      right = 0; wrong = 0; wrongOnce = {};
      draw();
    }

    cardOv = {
      node: ov,
      deck: [],
      start: function (deck) {
        if (!deck.length) return;
        ov.classList.add('on');
        document.documentElement.style.overflow = 'hidden';
        start(deck);
      },
      close: close,
      isOpen: function () { return ov.classList.contains('on'); }
    };
  }

  function openCards(deck) {
    if (!deck || !deck.length) return;
    if (!cardOv) buildCardOverlay();
    cardOv.start(deck);
  }

  /** Rozsah balíčku: "all" | "questions" | "glosar" | "qN" | nic = z této stránky. */
  function deckForScope(scope) {
    if (!scope) return deckFromPage();
    if (scope === 'all') return deckFromData(null);
    if (scope === 'questions') return deckFromData(function (d) { return !!d.n; });
    if (/^q\d+$/.test(scope)) {
      var n = parseInt(scope.slice(1), 10);
      return deckFromData(function (d) { return d.n === n; });
    }
    return deckFromData(function (d) { return d.k === scope; });
  }

  function initCards() {
    $$('[data-act="cards"]').forEach(function (b) {
      b.addEventListener('click', function () { openCards(deckForScope(b.dataset.scope)); });
    });
  }

  /** Doplní počty kartiček tam, kde je HTML označí — aby nemohly zestarat. */
  function initCounts() {
    $$('[data-count-for]').forEach(function (node) {
      var n = deckForScope(node.dataset.countFor).length;
      if (n) node.textContent = String(n);
    });
  }

  /** Na stránce s kartičkami vypíše dostupné balíčky podle indexu. */
  function initDeckList() {
    var host = $('#deck-list');
    if (!host) return;

    function add(scope, label, sub) {
      var deck = deckForScope(scope);
      if (!deck.length) return;
      var b = el('button', 'deck');
      b.type = 'button';
      b.dataset.act = 'cards';
      b.dataset.scope = scope;
      b.appendChild(el('span', 'deck-n', String(deck.length)));
      var t = el('span', 'deck-t');
      t.appendChild(el('span', 'deck-title', label));
      if (sub) t.appendChild(el('span', 'deck-sub', sub));
      b.appendChild(t);
      b.addEventListener('click', function () { openCards(deckForScope(scope)); });
      host.appendChild(b);
    }

    add('all', 'Všechny pojmy', 'klíčové pojmy z otázek i celý glosář, bez duplicit');
    add('questions', 'Klíčové pojmy z otázek', 'jen sekce 🔑 u jednotlivých otázek');
    add('glosar', 'Glosář', 'závěrečný abecední rejstřík');

    var qhost = $('#deck-list-q');
    if (!qhost) return;
    DATA.docs.forEach(function (d) {
      if (!d.n || !d.c || !d.c.length) return;
      var b = el('button', 'deck deck-q');
      b.type = 'button';
      b.appendChild(el('span', 'deck-n', String(d.c.length)));
      var t = el('span', 'deck-t');
      t.appendChild(el('span', 'deck-title', d.n + '. ' + d.t));
      b.appendChild(t);
      b.addEventListener('click', function () { openCards(deckForScope('q' + d.n)); });
      qhost.appendChild(b);
    });
    if (!qhost.children.length) qhost.previousElementSibling.hidden = true;
  }

  /* -------------------------------------------------- 7. Glosář — filtr */

  function clearMarks(root) {
    $$('mark', root).forEach(function (m) {
      var t = document.createTextNode(m.textContent);
      m.parentNode.replaceChild(t, m);
    });
    root.normalize();
  }

  function markText(root, needle) {
    if (!needle) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var nodes = [], n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function (node) {
      var folded = fold(node.nodeValue);
      var at = folded.indexOf(needle);
      if (at < 0) return;
      var mid = node.splitText(at);
      mid.splitText(needle.length);
      var mk = el('mark');
      mk.appendChild(document.createTextNode(mid.nodeValue));
      mid.parentNode.replaceChild(mk, mid);
    });
  }

  function initGlossaryFilter() {
    var input = $('#gq');
    if (!input) return;
    var items = $$('.gitem');
    var countEl = $('#gcount');
    var sections = $$('.content .sec');

    function apply() {
      var q = fold(input.value.trim());
      var shownCount = 0;
      items.forEach(function (it) {
        clearMarks(it);
        var hit = !q || fold(it.textContent).indexOf(q) >= 0;
        it.classList.toggle('hide', !hit);
        if (hit) { shownCount++; if (q) markText(it, q); }
      });
      // schovej i písmenné sekce, které zůstaly prázdné
      sections.forEach(function (sec) {
        var any = $$('.gitem', sec).some(function (i) { return !i.classList.contains('hide'); });
        sec.hidden = !!q && !any && $$('.gitem', sec).length > 0;
      });
      if (countEl) countEl.textContent = q ? shownCount + ' z ' + items.length : items.length + ' pojmů';
    }

    input.addEventListener('input', apply);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { input.value = ''; apply(); }
    });
    apply();
  }

  /* -------------------------------------------------- 8. Drobnosti a zkratky */

  function initMisc() {
    $$('[data-act="print"]').forEach(function (b) {
      b.addEventListener('click', function () { window.print(); });
    });
    $$('[data-act="expand"]').forEach(function (b) {
      b.addEventListener('click', function () {
        var all = $$('details', $('.content'));
        var anyClosed = all.some(function (d) { return !d.open; });
        all.forEach(function (d) { d.open = anyClosed; });
        b.textContent = anyClosed ? 'Sbalit vše' : 'Rozbalit vše';
      });
      if (!$$('details', $('.content') || document).length) b.remove();
    });
  }

  function initKeys() {
    document.addEventListener('keydown', function (e) {
      var tag = (e.target.tagName || '').toLowerCase();
      var typing = tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable;

      if (e.key === 'Escape') {
        if (cardOv && cardOv.isOpen()) return cardOv.close();
        if (searchOv && searchOv.isOpen()) return searchOv.close();
        return;
      }
      if (cardOv && cardOv.isOpen()) {
        if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); if (cardOv._reveal) cardOv._reveal(); }
        else if (e.key === 'ArrowRight' && cardOv._yes && !cardOv._yes.parentNode.hidden) cardOv._yes.click();
        else if (e.key === 'ArrowLeft' && cardOv._no && !cardOv._no.parentNode.hidden) cardOv._no.click();
        return;
      }
      if (typing) return;
      if (e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) {
        e.preventDefault(); openSearch();
      } else if (e.key.toLowerCase() === 'k' && !e.metaKey && !e.ctrlKey && KIND === 'otazka') {
        var deck = deckFromPage();
        if (deck.length) openCards(deck);
      }
    });
  }

  /* -------------------------------------------------- start */

  initTheme();
  initToc();
  initSearch();
  initProgressChip();
  initProgressList();
  initHubProgress();
  initCards();
  initCounts();
  initDeckList();
  initGlossaryFilter();
  initMisc();
  initKeys();
})();
