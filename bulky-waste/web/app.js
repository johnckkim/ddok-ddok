(function () {
  'use strict';
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var I = window.I18N, t = I.t;
  var CAT_ORDER = ['가구류', '가전·전자', '생활용품', '유아용품', '반려동물', '운동·레저', '악기·취미', '사무·기타', '목재', '기타'];
  var state = { muni: '', muniName: '', muniDisp: '', mode: 'place', busy: false, cart: [], cartEl: null, waiting: null };
  var RN = 0;
  var MUNIS = [];

  /* ---------- 공통 ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function toast(msg) {
    var el = $('#toast'); el.textContent = msg; el.classList.add('on');
    clearTimeout(toast.h); toast.h = setTimeout(function () { el.classList.remove('on'); }, 1800);
  }
  function api(path, body) {
    return fetch(path, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined
    }).catch(function () { throw new Error(t('offline')); }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.message || t('tryLater'));
        if (j && j.tk) I.addTags(j.tk);
        return j;
      });
    });
  }
  /* 서버 오류 문구도 고른 언어로 */
  function errMsg(err) {
    return I.tr([err.message]).then(function (a) { return a[0]; });
  }
  /* 지역은 기억하지 않는다: 예전에 저장해 둔 지역도 지운다 */
  try { localStorage.removeItem('bw.muni'); } catch (e) { /* 무시 */ }
  function ko() { return I.lang() === 'ko'; }
  function hasHangul(s) { return /[가-힣]/.test(String(s || '')); }
  function won(n) { return ko() ? n.toLocaleString('ko-KR') + '원' : '₩' + n.toLocaleString('en-US'); }
  function feeNum(fee) { return /^[\d,]+원$/.test(String(fee || '')) ? +String(fee).replace(/[^\d]/g, '') : null; }
  function flat(s) { return String(s || '').replace(/[\s\-–·.,]+/g, '').toLowerCase(); }
  function allNames(s) {
    return String(s || '').split(/[,\n、，;]+/).map(function (x) { return x.trim(); }).filter(Boolean);
  }
  function splitNames(s) { return allNames(s).slice(0, 30); }

  /* ---------- 언어 ---------- */
  function applyStatic() {
    document.documentElement.lang = I.lang();
    document.title = t('title');
    document.querySelectorAll('[data-t]').forEach(function (el) { el.textContent = t(el.dataset.t); });
    document.querySelectorAll('[data-t-aria]').forEach(function (el) { el.setAttribute('aria-label', t(el.dataset.tAria)); });
    $('#langBtn').innerHTML = I.flag(I.lang()) + '<span class="sr">' + esc(t('language')) + '</span>';
    $('#langMenu').innerHTML = I.LANGS.map(function (l) {
      return '<li><button type="button" aria-pressed="' + (l.code === I.lang()) + '" data-lang="' + l.code + '">' +
        I.flag(l.code) + '<span>' + esc(l.name) + '</span></button></li>';
    }).join('');
    setMode(state.mode, true);
  }
  function closeLang() { $('#langMenu').hidden = true; $('#langBtn').setAttribute('aria-expanded', 'false'); }
  $('#langBtn').addEventListener('click', function (e) {
    e.stopPropagation();
    var open = $('#langMenu').hidden;
    $('#langMenu').hidden = !open; $('#langBtn').setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', function (e) { if (!e.target.closest('#langWrap')) closeLang(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !$('#langMenu').hidden) { closeLang(); $('#langBtn').focus(); }
  });
  $('#langMenu').addEventListener('click', function (e) {
    var b = e.target.closest('[data-lang]'); if (!b) return;
    closeLang();
    if (b.dataset.lang === I.lang()) return;
    I.set(b.dataset.lang);
    applyStatic();
    prepareMunis().then(function () {
      if (state.muni) {
        return I.tr([state.muniName]).then(function (a) {
          state.muniDisp = a[0]; $('#muniName').textContent = a[0];
          greetItems();
        });
      }
      askPlace(false);                       // 지역 바로가기(과천시)도 새 언어로 다시
    }).then(function () { return relabelCart(); });
  });

  /* ---------- 대화 ---------- */
  var thread = $('#thread');
  var chat = $('#chat');
  function scrollEnd(instant) {
    var calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    requestAnimationFrame(function () { chat.scrollTo({ top: chat.scrollHeight, behavior: instant || calm ? 'auto' : 'smooth' }); });
  }
  /* 키보드가 올라오면 보이는 높이(visualViewport)에 화면을 맞춰 입력창이 항상 키보드 위에 오게 한다 */
  function fitViewport() {
    var vv = window.visualViewport;
    var h = vv ? vv.height : window.innerHeight;
    var top = vv ? vv.offsetTop : 0;
    document.documentElement.style.setProperty('--app-h', h + 'px');
    document.documentElement.style.setProperty('--app-top', top + 'px');
  }
  fitViewport();
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', function () { fitViewport(); scrollEnd(true); });
    window.visualViewport.addEventListener('scroll', fitViewport);
  }
  window.addEventListener('resize', fitViewport);
  window.addEventListener('orientationchange', function () { setTimeout(fitViewport, 300); });
  function addUser(text) {
    var el = document.createElement('div');
    el.className = 'msg user';
    el.innerHTML = '<div class="bubble">' + esc(text) + '</div>';
    thread.appendChild(el); scrollEnd(); return el;
  }
  function addBot(html, cls) {
    var el = document.createElement('div');
    el.className = 'msg bot' + (cls ? ' ' + cls : '');
    el.innerHTML = '<div class="bubble">' + html + '</div>';
    thread.appendChild(el); scrollEnd(); return el;
  }
  function typing() {
    return addBot('<span class="dots"><i></i><i></i><i></i></span>', 'typing');
  }
  function setMode(mode, keep) {
    state.mode = mode;
    var input = $('#input');
    if (!keep) input.value = '';
    var p = mode === 'place';
    input.placeholder = t(p ? 'phPlace' : 'phItems');
    $('#inputLabel').textContent = t(p ? 'lblPlace' : 'lblItems');
    $('#footnote').textContent = t(p ? 'notePlace' : 'noteItems');
    renderSuggest();
    if (!keep) setTimeout(function () { input.focus(); }, 30);
  }

  /* ---------- 지자체 ---------- */
  /* 한국어가 아니면 지자체 이름도 그 언어로(검색은 한국어·번역 이름 둘 다) */
  function prepareMunis() {
    if (ko() || !MUNIS.length) { MUNIS.forEach(function (m) { m.disp = m.name; }); return Promise.resolve(); }
    return I.tr(MUNIS.map(function (m) { return m.name; })).then(function (a) {
      MUNIS.forEach(function (m, i) { m.disp = a[i] || m.name; });
    });
  }
  function matches(q) {
    var raw = q;
    q = flat(q).replace(/(특별시|광역시|특별자치시|특별자치도)$/, '');
    if (!q) return [];
    var starts = [], has = [];
    MUNIS.forEach(function (m) {
      var parts = m.name.split(' '); var last = flat(parts[parts.length - 1]); var all = flat(m.name);
      var dsp = flat(m.disp || '');
      if (last.indexOf(q) === 0 || last.replace(/(시|군|구)$/, '') === q) starts.push(m);
      else if (all.indexOf(q) >= 0 || (!hasHangul(raw) && q.length >= 3 && dsp.indexOf(q) >= 0)) has.push(m);
    });
    return starts.concat(has).slice(0, 8);
  }
  var DEFAULT_PLACE = 'gwacheon';     // 다른 지자체 답변을 다듬는 동안 첫 화면 바로가기는 과천시
  function askPlace(again) {
    $('#muniPill').hidden = true;
    var d = MUNIS.filter(function (m) { return m.code === DEFAULT_PLACE; })[0];
    addBot(t(again ? 'askPlaceAgain' : 'askPlace') +
      (d ? '<div class="chips"><button type="button" data-place="' + esc(d.code) + '">' + esc(d.disp || d.name) + '</button></div>' : ''));
    setMode('place');
  }
  function greetItems() {
    // 예시 단추는 그 지역에서 금액이 바로 나오는 품목만(서버가 확인)
    return api('/api/examples?m=' + encodeURIComponent(state.muni)).then(function (j) { return j.items || []; }, function () { return []; })
      .then(function (ex) {
        return I.tr(ex).then(function (q) {
          addBot(t('muniSet', { m: esc(state.muniDisp) }) + (ex.length ?
            '<div class="chips">' + ex.map(function (n, i) { return '<button type="button" data-send="' + esc(n) + '" data-shown="' + esc(q[i]) + '">' + esc(q[i]) + '</button>'; }).join('') + '</div>' : ''));
        });
      });
  }
  function setMuni(m, quiet) {
    if (!m) return;
    if (state.cart.length && state.muni && m.code !== state.muni) {   // 수수료는 지역마다 달라서 지역을 바꾸면 비운다
      state.cart = []; renderCart(); toast(t('cartCleared'));
    }
    state.muni = m.code; state.muniName = m.name; state.muniDisp = m.disp || m.name;
    $('#muniName').textContent = state.muniDisp; $('#muniPill').hidden = false;
    $('#muniPill').setAttribute('aria-label', t('regionChange', { m: state.muniDisp }));
    if (!quiet) addUser(state.muniDisp);
    setMode('items');
    var w = state.waiting; state.waiting = null;
    greetItems().then(function () { if (w) sendItems(splitNames(w), w); });   // 지역 고르기 전에 물은 품목은 바로 이어서
  }
  function renderSuggest() {
    var ul = $('#suggest');
    if (state.mode !== 'place') { ul.innerHTML = ''; return; }
    var list = matches($('#input').value);
    ul.innerHTML = list.map(function (m, i) {
      var label = m.disp && m.disp !== m.name ? m.disp + ' · ' + m.name : m.name;
      return '<li><button type="button" role="option" data-code="' + esc(m.code) + '"' + (i === 0 ? ' aria-selected="true"' : '') + '>' + esc(label) + '</button></li>';
    }).join('');
  }
  $('#input').addEventListener('input', renderSuggest);
  $('#input').addEventListener('focus', function () { setTimeout(function () { fitViewport(); scrollEnd(true); }, 250); });
  $('#suggest').addEventListener('click', function (e) {
    var b = e.target.closest('[data-code]'); if (!b) return;
    setMuni(MUNIS.filter(function (m) { return m.code === b.dataset.code; })[0]);
  });
  $('#muniPill').addEventListener('click', function () { askPlace(true); });

  /* ---------- 보내기 ---------- */
  $('#composer').addEventListener('submit', function (e) {
    e.preventDefault();
    var text = $('#input').value.trim();
    if (state.busy) { if (text) toast(t('busy')); return; }
    if (!text) return;
    if (state.mode === 'place') {
      var list = matches(text);
      if (list.length) { setMuni(list[0]); return; }
      if (!MUNIS.length) { start(); return; }       // 지역 목록을 못 불러온 상태: 다시 불러온다
      addUser(text); $('#input').value = ''; renderSuggest();
      /* 지역 이름처럼 보이면 '안내하지 않는 지역', 아니면(품목을 먼저 물으면) 지역부터 묻고 품목은 기억했다가 이어서 답한다 */
      var miss = function (k) {
        var kk = String(k).replace(/\s+/g, '');
        var place = /(특별시|광역시|특별자치|시|군|구|도|읍|면|동)$/.test(kk) && !/(기구|가구|완구|문구|도구|공구|용구|냉동)$/.test(kk);
        if (place) addBot(t('noArea', { n: MUNIS.length }));
        else { state.waiting = text; addBot(t('needPlace', { x: esc(text) })); }
      };
      if (hasHangul(text)) { miss(text); return; }
      I.tr([text], 'ko').then(function (a) {            // 'Gwacheon' → '과천시'
        var l2 = a[0] !== text ? matches(a[0]) : [];
        if (l2.length) setMuni(l2[0], true); else miss(a[0]);
      });
      return;
    }
    var names = allNames(text);
    sendItems(names.slice(0, 30), names.length > 30 ? names.slice(0, 30).join(', ') : text);
    if (names.length > 30) {                   // 30개까지만 보내고 나머지는 입력창에 남긴다
      setTimeout(function () { $('#input').value = names.slice(30).join(', '); }, 0);
      toast(t('tooMany', { n: names.length - 30 }));
    }
  });
  thread.addEventListener('click', function (e) {
    var pl = e.target.closest('[data-place]');
    if (pl && state.mode === 'place') { setMuni(MUNIS.filter(function (m) { return m.code === pl.dataset.place; })[0]); return; }
    var b = e.target.closest('[data-send]');
    if (b && state.mode === 'items' && !state.busy) sendItems([b.dataset.send], b.dataset.shown || b.dataset.send);
  });
  function sendItems(names, shown) {
    if (!names.length) return;
    $('#input').value = '';
    addUser(shown || names.join(', '));
    state.busy = true; $('#send').disabled = true;
    var tp = typing();
    var foreign = names.filter(function (n) { return !hasHangul(n); });
    (foreign.length ? I.tr(names, 'ko') : Promise.resolve(names))       // 다른 언어로 쓴 품목명은 한국어로 바꿔 찾는다
      .then(function (kn) {
        return api('/api/quote', { municipality: state.muni, items: kn.map(function (n) { return { name: n }; }) });
      })
      .then(localize)
      .then(function (j) { tp.remove(); answer(j); })
      .catch(function (err) { errMsg(err).then(function (m) { tp.remove(); addBot(esc(m)); }); })
      .then(function () { state.busy = false; $('#send').disabled = false; $('#input').focus(); });
  }

  /* ---------- 답변 번역: 원문(한국어)은 그대로 두고 화면용 칸(_)을 붙인다 ---------- */
  function feeShown(fee, m) {
    var n = feeNum(fee);
    return n !== null ? won(n) : (m[fee] || fee);
  }
  function localize(j) {
    var texts = [];
    var add = function (s) { if (s && texts.indexOf(s) < 0) texts.push(s); };
    (j.rows || []).forEach(function (r) { add(r['품목']); add(r['규격']); add(r['안내']); if (feeNum(r['수수료']) === null) add(r['수수료']); });
    (j.pending || []).forEach(add);
    (j.needs_confirm || []).forEach(function (c) {
      add(c.item_label); add(c.question); (c.size_options || []).forEach(add);
      (c.options || []).forEach(function (o) { add(o.label); add(o.desc); });
      if (c.product) add(c.product.title);
    });
    CAT_ORDER.forEach(add);
    if (j.message) add(j.message);
    return I.tr(texts).then(function (a) {
      var m = {}; texts.forEach(function (x, i) { m[x] = a[i]; });
      var d = function (s) { return s ? (m[s] || s) : s; };
      (j.rows || []).forEach(function (r) {
        r._item = d(r['품목']); r._spec = d(r['규격']); r._note = d(r['안내']); r._fee = feeShown(r['수수료'], m); r._cat = d(r['분류'] || '기타');
      });
      j._pending = (j.pending || []).map(d);
      (j.needs_confirm || []).forEach(function (c) { localizeCard(c, d); });
      j._message = d(j.message);
      return j;
    });
  }
  function localizeCard(c, d) {
    c._label = d(c.item_label); c._question = d(c.question);
    c._sizes = (c.size_options || []).map(d);
    (c.options || []).forEach(function (o) { o._label = d(o.label); o._desc = d(o.desc); });
    if (c.product) c.product._title = d(c.product.title);
  }
  function itemCell(r) {     // 번역된 이름 아래에 한국어 원래 이름(스티커·주민센터에서 쓰는 이름)
    var sub = r._item && r._item !== r['품목'] ? '<small class="ko" title="' + esc(t('korean')) + '">' + esc(r['품목']) + '</small>' : '';
    return esc(r._item || r['품목']) + sub;
  }

  /* ---------- 답변 ---------- */
  function answer(j) {
    var rows = j.rows || [];
    if (rows.length) addResult(rows);
    if (j.pending && j.pending.length) addPending(j._pending || j.pending, j.ticket);
    (j.needs_confirm || []).forEach(addCard);
    if (!rows.length && !(j.pending || []).length && !(j.needs_confirm || []).length) addBot(t('retryItem'));
  }
  function itemsCount(rows) {
    var s = {}; rows.forEach(function (r) { s[r['품목']] = 1; }); return Object.keys(s).length;
  }
  function sortRows(rows) {
    var order = []; var by = {};
    rows.forEach(function (r) { if (!by[r['품목']]) { by[r['품목']] = []; order.push(r['품목']); } by[r['품목']].push(r); });
    var out = []; order.forEach(function (n) { out = out.concat(by[n]); });
    return out;
  }
  function addResult(rows) {
    rows = sortRows(rows);
    var id = 'r' + (++RN);
    var multi = groups(rows).some(function (g) { return g.idx.length > 1; });
    var el = addBot('<p class="lead">' + esc(t('feeLead')) + '</p>' + (itemsCount(rows) === 1 ? linesHTML(rows, id) : tableHTML(rows, id)) +
      (multi ? '<p class="sub pick-hint">' + esc(t('pickHint')) + '</p>' : '') +
      '<div class="actions"><button type="button" class="pri cart-add" data-act="cart">' + esc(t('addCart')) + '</button></div>', 'result');
    el._rows = rows; el._id = id;
  }
  /* 품목별 묶음: [{name, idx:[행 번호…]}] */
  function groups(rows) {
    var out = [], by = {};
    rows.forEach(function (r, i) {
      var n = r['품목'];
      if (!by[n]) { by[n] = { name: n, shown: r._item || n, idx: [] }; out.push(by[n]); }
      by[n].idx.push(i);
    });
    return out;
  }
  /* 규격이 여러 개인 품목만 고르는 단추를 단다(하나뿐이면 그대로 담는다) */
  function pickBox(rows, i, id) {
    if (!id) return '';
    var gs = groups(rows), g = gs.filter(function (x) { return x.name === rows[i]['품목']; })[0];
    if (g.idx.length < 2) return '';
    return '<input type="radio" class="pk" name="' + id + '_' + gs.indexOf(g) + '" value="' + i + '" aria-label="' +
      esc((rows[i]._item || rows[i]['품목']) + ' ' + (rows[i]._spec || rows[i]['규격'])) + '">';
  }
  function addPending(names, tk) {
    var el = addBot('<p class="lead">' + esc(t('pendLead')) + '</p><ul class="plist">' + names.map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('') + '</ul>' +
      (tk ? '<form class="contact" novalidate><p class="sub">' + esc(t('pendSub')) + '</p>' +
        '<div class="cf"><label>' + esc(t('name')) + '<input name="name" maxlength="20" autocomplete="name" required></label>' +
        '<label>' + esc(t('phone')) + '<input name="phone" type="tel" inputmode="numeric" maxlength="13" autocomplete="tel" placeholder="010-1234-5678" required></label></div>' +
        '<label class="agree"><input type="checkbox" name="agree"> <span>' + esc(t('agree')) + '</span></label>' +
        '<button type="submit" class="pri block">' + esc(t('getSms')) + '</button><p class="err" hidden></p></form>' +
        '<div class="tk">' + esc(t('ticket')) + ' <code>' + esc(tk) + '</code><button type="button" data-ticket="' + esc(tk) + '">' + esc(t('copyLink')) + '</button></div>' : ''), 'pending');
    var f = el.querySelector('form.contact');
    if (!f) return;
    var phone = f.querySelector('[name=phone]');
    phone.addEventListener('input', function () {
      var dd = phone.value.replace(/\D/g, '').slice(0, 11);
      phone.value = dd.length < 4 ? dd : dd.length < 8 ? dd.slice(0, 3) + '-' + dd.slice(3) : dd.slice(0, 3) + '-' + dd.slice(3, dd.length - 4) + '-' + dd.slice(-4);
    });
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      var err = f.querySelector('.err');
      var body = { name: f.name.value.trim(), phone: phone.value, agree: f.agree.checked };
      var bad = !body.name ? t('errName') : !/^01[016789]\d{7,8}$/.test(phone.value.replace(/\D/g, '')) ? t('errPhone') : !body.agree ? t('errAgree') : '';
      if (bad) { err.textContent = bad; err.hidden = false; return; }
      err.hidden = true;
      var btn = f.querySelector('button[type=submit]'); btn.disabled = true;
      api('/api/ticket/' + encodeURIComponent(tk) + '/contact', body).then(function (j) {
        return I.tr([j.message]).then(function (a) {
          f.outerHTML = '<p class="done-msg">' + esc(a[0]) + '</p>';
          scrollEnd();
        });
      }).catch(function (x) { errMsg(x).then(function (m) { btn.disabled = false; err.textContent = m; err.hidden = false; }); });
    });
  }
  function linesHTML(rows, id) {
    return '<ul class="lines">' + rows.map(function (r, i) {
      return '<li data-i="' + i + '">' + pickBox(rows, i, id) + '<span class="nm">' + itemCell(r) + '</span><span class="sp">(' + esc(r._spec || r['규격']) + ')</span>' +
        '<span class="fe">' + esc(r._fee || r['수수료']) + '</span>' + (id ? rowCart(r, i) : '') + ((r._note || r['안내']) ? '<span class="nt">' + esc(r._note || r['안내']) + '</span>' : '') + '</li>';
    }).join('') + '</ul>';
  }
  function tableHTML(rows, id) {
    var hasNote = rows.some(function (r) { return r['안내']; });
    var grouped = itemsCount(rows) >= 10;
    var gs = grouped ? CAT_ORDER.map(function (c) {
      return { c: c, rows: rows.filter(function (r) { return (r['분류'] || '기타') === c; }) };
    }).filter(function (g) { return g.rows.length; }) : [{ c: null, rows: rows }];
    var body = '';
    gs.forEach(function (g) {
      if (g.c) body += '<tr class="cat"><th colspan="3" scope="colgroup">' + esc(g.rows[0]._cat || g.c) + '</th></tr>';
      var prev = null;
      g.rows.forEach(function (r) {
        var same = prev === r['품목']; prev = r['품목'];
        var i = rows.indexOf(r);
        body += '<tr data-i="' + i + '"' + (same ? ' class="same"' : '') + '><td class="item">' + pickBox(rows, i, id) + itemCell(r) +
          ((r._note || r['안내']) ? '<span class="note-inline">' + esc(r._note || r['안내']) + '</span>' : '') + '</td>' +
          '<td>' + esc(r._spec || r['규격']) + '</td><td class="fee">' + esc(r._fee || r['수수료']) + (id ? rowCart(r, i) : '') + '</td></tr>';
      });
    });
    return '<table class="fees' + (hasNote ? ' has-note' : '') + '"><colgroup><col class="c-item"><col class="c-spec"><col class="c-fee"></colgroup>' +
      '<thead><tr><th scope="col">' + esc(t('colItem')) + '</th><th scope="col">' + esc(t('colSpec')) + '</th><th scope="col" class="fee">' + esc(t('colFee')) + '</th></tr></thead><tbody>' + body + '</tbody></table>';
  }

  /* ---------- 장바구니 (원문 한국어 + 화면용 번역을 함께 들고 있다; 엑셀은 한국어 원문) ---------- */
  function addToCart(el) {
    var rows = el._rows || [], gs = groups(rows), pick = [], miss = [];
    gs.forEach(function (g, k) {
      if (g.idx.length === 1) { pick.push(rows[g.idx[0]]); return; }
      var c = el.querySelector('input[name="' + el._id + '_' + k + '"]:checked');
      if (c) pick.push(rows[+c.value]); else miss.push(g.shown);
    });
    if (miss.length) { toast(t('pickFirst', { x: miss.join(', ') })); return; }
    pushCart(pick);
  }
  /* 줄마다 붙은 장바구니 아이콘: 그 규격 한 줄만 바로 담는다 */
  function addRow(btn) {
    var el = btn.closest('.msg'), r = (el._rows || [])[+btn.dataset.addrow];
    if (!r) return;
    pushCart([r]);
    btn.classList.add('done'); setTimeout(function () { btn.classList.remove('done'); }, 1200);
  }
  function pushCart(pick) {
    pick.forEach(function (r) {
      var etc = r['담기'] === '기타';            // 조례에 없는 품목: 장바구니에는 '기타' + 금액, 제품명은 함께 보관
      var hit = state.cart.filter(function (c) { return c.item === r['품목'] && c.spec === r['규격'] && c.fee === r['수수료']; })[0];
      if (hit) hit.qty = Math.min(99, hit.qty + 1);
      else state.cart.push({ item: r['품목'], spec: r['규격'], fee: r['수수료'], note: r['안내'] || '', qty: 1, etc: etc,
        cartItem: r['담기'] || r['품목'],
        dItem: r._item || r['품목'], dSpec: r._spec || r['규격'], dNote: r._note || r['안내'] || '', dFee: r._fee || r['수수료'] });
      bridge(r);
    });
    renderCart();
    toast(t('added', { n: pick.length }));
  }
  /* ---------- 앱 연동 자리: 우리동네플러스 앱에 심으면 실제 장바구니로 넘긴다 ----------
     담을 때마다 아래 4곳으로 같은 내용을 보낸다(있는 것만).
       1) window 이벤트 'bw:add-to-cart' (detail = 아래 item)
       2) window.UdongCart.add(item)            — 앱이 이 함수를 넣어 두면 호출
       3) window.ReactNativeWebView.postMessage — RN 웹뷰
       4) window.parent.postMessage            — iframe 으로 심었을 때
     item = { type, municipality(코드), municipalityName, item(조례 한국어 이름), spec, fee(숫자 또는 null), feeText, note, qty:1 } */
  /* 앱 '기타 > 금액'은 1,000·5,000·10,000원 세 가지를 수량으로 담는다: 7,000원 → 5,000×1 + 1,000×2 */
  function etcPieces(n) {
    var out = [];
    [10000, 5000, 1000].forEach(function (p) { var k = Math.floor(n / p); if (k) { out.push({ price: p, count: k }); n -= p * k; } });
    return out;
  }
  function bridge(r) {
    var etc = r['담기'] === '기타';
    var item = { type: 'bw:add-to-cart', municipality: state.muni, municipalityName: state.muniName,
      item: etc ? '기타' : (r['담기'] || r['품목']),            // 장바구니 품목: 조례 품목명, 조례에 없으면 '기타'
      productName: r['품목'],                                   // 고객이 말한 제품명(조례 보완 자료)
      spec: etc ? '' : r['규격'], sizeHint: r['규격'], fee: feeNum(r['수수료']), feeText: r['수수료'],
      etc: etc, note: r['안내'] || '', qty: 1,
      // 기타일 때 앱 장바구니에 넣을 줄: 카탈로그 '기타 > 금액'(1,000/5,000/10,000원) × 수량
      etcLines: etc && feeNum(r['수수료']) ? etcPieces(feeNum(r['수수료'])).map(function (x) {
        return { category: '기타', item_name: '금액', item_specification: '금액', price: x.price, count: x.count };
      }) : [] };
    try { window.dispatchEvent(new CustomEvent('bw:add-to-cart', { detail: item })); } catch (e) { /* 무시 */ }
    try { if (window.UdongCart && typeof window.UdongCart.add === 'function') window.UdongCart.add(item); } catch (e) { /* 무시 */ }
    try { if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(item)); } catch (e) { /* 무시 */ }
    try { if (window.parent && window.parent !== window) window.parent.postMessage(item, '*'); } catch (e) { /* 무시 */ }
  }
  var CART_SVG = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M3 4h2l2.2 10.2a1.5 1.5 0 0 0 1.5 1.2h8.6a1.5 1.5 0 0 0 1.5-1.1l2.2-6.3H6.2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<circle cx="9.5" cy="19.5" r="1.5" fill="currentColor"/><circle cx="17" cy="19.5" r="1.5" fill="currentColor"/><path class="plus" d="M13 9v4M11 11h4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  function rowCart(r, i) {
    return '<button type="button" class="row-cart" data-addrow="' + i + '" aria-label="' + esc((r._item || r['품목']) + ' ' + (r._spec || r['규격']) + ' — ' + t('addCart')) + '" title="' + esc(t('addCart')) + '">' + CART_SVG + '</button>';
  }
  function relabelCart() {
    if (!state.cart.length) return Promise.resolve();
    var texts = [];
    state.cart.forEach(function (c) { [c.item, c.spec, c.note, feeNum(c.fee) === null ? c.fee : ''].forEach(function (s) { if (s && texts.indexOf(s) < 0) texts.push(s); }); });
    return I.tr(texts).then(function (a) {
      var m = {}; texts.forEach(function (x, i) { m[x] = a[i]; });
      state.cart.forEach(function (c) { c.dItem = m[c.item] || c.item; c.dSpec = m[c.spec] || c.spec; c.dNote = c.note ? (m[c.note] || c.note) : ''; c.dFee = feeShown(c.fee, m); });
      renderCart();
    });
  }
  /* 면적·길이·무게 단위 요금, 기본+추가 요금: 수량은 단위 수이고 합계가 달라질 수 있다 */
  var UNIT_RE = /(\d[\d.,]*\s*(㎡|m2|m²|평|cm|㎝|m|kg|㎏|ℓ|L|리터|톤|인치)\s*(당|마다))|(㎡|평|cm|㎝|m|kg|㎏|ℓ|리터|톤)\s*\)?\s*당|추가|초과\s*시|마다/;   // '개당·장당'은 한 개 값이라 제외
  function isUnit(c) { return UNIT_RE.test(String(c.spec || '')); }
  function cartTotal() {
    var sum = 0, other = 0;
    state.cart.forEach(function (c) { var n = feeNum(c.fee); if (n === null) other++; else sum += n * c.qty; });
    return { sum: sum, other: other };
  }
  function cartHTML() {
    if (!state.cart.length) return '<p class="lead">' + esc(t('cartEmpty')) + '</p><p class="sub">' + esc(t('cartEmptySub')) + '</p>';
    var tt = cartTotal();
    return '<p class="lead">' + esc(t('cartTitle')) + ' · ' + esc(state.muniDisp) + '</p><ul class="cartlist">' + state.cart.map(function (c, k) {
      var n = feeNum(c.fee);
      return '<li><div class="ci"><span class="nm">' + (c.etc ? '<span class="etc-tag">' + esc(t('etc')) + '</span> ' : '') + esc(c.dItem) +
        (c.dItem !== c.item ? ' <small class="ko">' + esc(c.item) + '</small>' : '') + '</span>' +
        '<span class="sp">' + esc(c.dSpec) + '</span>' +
        (c.dNote ? '<span class="nt">' + esc(c.dNote) + '</span>' : '') +
        (isUnit(c) ? '<span class="nt unit">' + esc(t('unitQty')) + '</span>' : '') +
        (c.etc && feeNum(c.fee) ? '<span class="nt">' + esc(t('etcPay')) + ' ' + etcPieces(feeNum(c.fee)).map(function (x) { return won(x.price) + '×' + x.count; }).join(' + ') + '</span>' : '') + '</div>' +
        '<div class="cq"><button type="button" data-cart="dec" data-n="' + k + '" aria-label="' + esc(c.dItem + ' ' + t('minus')) + '">−</button>' +
        '<b>' + c.qty + '</b><button type="button" data-cart="inc" data-n="' + k + '" aria-label="' + esc(c.dItem + ' ' + t('plus')) + '">+</button></div>' +
        '<span class="fe">' + (n === null ? esc(c.dFee) : won(n * c.qty)) + '</span>' +
        '<button type="button" class="del" data-cart="del" data-n="' + k + '" aria-label="' + esc(c.dItem + ' ' + t('remove')) + '">×</button></li>';
    }).join('') + '</ul><div class="total"><span>' + esc(t('total')) + '</span><b>' + won(tt.sum) + '</b></div>' +
      (tt.other ? '<p class="sub">' + esc(t('noFee', { n: tt.other })) + '</p>' : '') +
      (state.cart.some(isUnit) ? '<p class="sub">' + esc(t('unitWarn')) + '</p>' : '') +
      '<div class="actions"><button type="button" data-cart="text">' + esc(t('copy')) + '</button><button type="button" data-cart="xlsx">' + esc(t('excel')) + '</button>' +
      '<button type="button" data-cart="clear">' + esc(t('clear')) + '</button></div>';
  }
  function renderCart() {
    var n = state.cart.reduce(function (a, c) { return a + c.qty; }, 0);
    $('#cartN').textContent = n; $('#cartBtn').hidden = !n;
    $('#cartBtn').setAttribute('aria-label', t('cartCount', { n: n }));
    if (state.cartEl) {
      if (state.cartEl.isConnected) state.cartEl.querySelector('.bubble').innerHTML = cartHTML();
      else state.cartEl = null;
    }
  }
  function openCart() {
    if (state.cartEl) state.cartEl.remove();
    state.cartEl = addBot(cartHTML(), 'result cart');
  }
  function cartRows() {      // 내려받기는 한국어 원문(스티커 구매·신고에 쓰는 이름)
    return state.cart.map(function (c) {
      return c.etc ? { '품목': '기타', '규격': c.spec, '수수료': c.fee, '안내': '제품명: ' + c.item + (c.note ? ' · ' + c.note : ''), '수량': c.qty }
        : { '품목': c.cartItem || c.item, '규격': c.spec, '수수료': c.fee, '안내': c.note, '수량': c.qty };
    });
  }
  function cartText() {
    var tt = cartTotal();
    return [t('cartTextHead', { m: state.muniDisp })].concat(state.cart.map(function (c) {
      var n = feeNum(c.fee);
      return (c.etc ? t('etc') + ' - ' : '') + c.dItem + (c.dItem !== c.item ? ' [' + c.item + ']' : '') + ' (' + c.dSpec + ') ' + (n === null ? c.dFee : won(n)) + ' × ' + c.qty +
        (n === null ? '' : ' = ' + won(n * c.qty)) + (c.dNote ? ' · ' + c.dNote : '');
    })).concat([t('total') + ' ' + won(tt.sum)]).join('\n');
  }
  $('#cartBtn').addEventListener('click', openCart);
  function copy(text, msg) {
    var done = function () { toast(msg || t('copied')); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
    } else { fallbackCopy(text); done(); }
  }
  function fallbackCopy(text) {
    var ta = document.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', '');
    ta.style.position = 'fixed'; ta.style.opacity = '0'; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) { /* 무시 */ }
    document.body.removeChild(ta);
  }
  function download(fmt, rows) {
    fetch('/api/quote/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format: fmt, rows: rows })
    }).then(function (r) { if (!r.ok) throw new Error(t('dlFail')); return r.blob(); })
      .then(function (blob) {
        var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = '대형폐기물_수수료.' + (fmt === 'xlsx' ? 'xlsx' : 'csv');
        document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
      }).catch(function (err) { toast(err.message); });
  }
  thread.addEventListener('click', function (e) {
    var rc = e.target.closest('[data-addrow]');
    if (rc) { addRow(rc); return; }
    var b = e.target.closest('[data-act="cart"]');
    if (b) { addToCart(b.closest('.msg')); return; }
    var c = e.target.closest('[data-cart]');
    if (c) {
      var k = +c.dataset.n, it = state.cart[k], act = c.dataset.cart;
      if (act === 'inc' && it) it.qty = Math.min(99, it.qty + 1);
      else if (act === 'dec' && it) { if (it.qty > 1) it.qty--; else state.cart.splice(k, 1); }
      else if (act === 'del' && it) state.cart.splice(k, 1);
      else if (act === 'clear') state.cart = [];
      else if (act === 'text') { copy(cartText(), t('cartCopied')); return; }
      else if (act === 'xlsx') { download('xlsx', cartRows()); return; }
      renderCart(); return;
    }
    var row = e.target.closest('[data-i]');           // 규격 줄을 누르면 그 규격을 고른다
    if (row && !e.target.closest('input')) {
      var pk = row.querySelector('input.pk'); if (pk) pk.checked = true;
    }
    var tk = e.target.closest('[data-ticket]');
    if (tk) copy(location.origin + '/?t=' + tk.dataset.ticket, t('linkCopied'));
  });

  /* ---------- 확인 질문 ---------- */
  function josa(label) {
    var base = String(label).replace(/\s*\([^()]*\)\s*$/, '').trim();
    var ch = base.charCodeAt(base.length - 1);
    if (ch >= 0xAC00 && ch <= 0xD7A3) return (ch - 0xAC00) % 28 ? '이' : '가';
    return '가';
  }
  function cardHTML(c) {
    var h = '<span class="step">' + esc(t('step', { a: c.step, b: c.max_steps })) + '</span>';
    var label = c._label || c.item_label;
    if (c.kind === 'yesno') {
      h += '<p class="q">' + (c.as_item ? t('asItem', { n: esc(c.name), l: esc(label) })
        : ko() ? '“' + esc(c.name) + '” — 문의하신 품목이 <b>' + esc(label) + '</b>' + josa(label) + ' 맞으신가요?'
          : t('isItem', { n: esc(c.name), l: esc(label) })) + '</p>';
      if (c.product && (c.product.image || c.product.title)) {
        h += '<a class="prod" href="' + esc(c.product.link || '#') + '" target="_blank" rel="noopener noreferrer">' +
          (c.product.image ? '<img src="' + esc(c.product.image) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '') +
          '<span>' + esc(c.product._title || c.product.title) + '</span></a>';
      }
      if (c.size_options) {
        h += '<p class="sub">' + esc(t('chooseSize')) + '</p><div class="seg">' + c.size_options.map(function (s, i) {
          return '<button type="button" data-size="' + i + '" aria-pressed="false">' + esc((c._sizes || [])[i] || s) + '</button>';
        }).join('') + '</div>';
      }
      h += '<div class="row2"><button type="button" class="pri" data-ans="yes">' + esc(t('yes')) + '</button><button type="button" data-ans="no">' + esc(t('no')) + '</button></div>';
    } else if (c.kind === 'choice') {
      h += '<p class="q">“' + esc(c.name) + '” — ' + esc(c._question || c.question) + '</p><div class="opts">' + c.options.map(function (o) {
        return '<button type="button" class="opt" data-choice="' + o.id + '"><b>' + esc(o._label || o.label) + '</b>' +
          ((o._desc || o.desc) ? '<small>' + esc(o._desc || o.desc) + '</small>' : '') + '</button>';
      }).join('') + '</div>' +
        '<div class="other"><input type="text" maxlength="40" placeholder="' + esc(t('other')) + '" aria-label="' + esc(t('other')) + '">' +
        '<button type="button" data-ans="other">' + esc(t('ok')) + '</button></div>';
    } else {
      h += '<p class="q">' + esc(c._question || c.question) + '</p>' +
        '<label class="photo">' + esc(t('photo')) + '<input type="file" accept="image/*" capture="environment"></label>' +
        '<div class="dims"><label>' + esc(t('w')) + '<input type="number" inputmode="decimal" min="0" data-dim="width"></label>' +
        '<label>' + esc(t('d')) + '<input type="number" inputmode="decimal" min="0" data-dim="depth"></label>' +
        '<label>' + esc(t('h')) + '<input type="number" inputmode="decimal" min="0" data-dim="height"></label></div>' +
        '<textarea placeholder="' + esc(t('describe')) + '" maxlength="200" aria-label="' + esc(t('describe')) + '"></textarea>' +
        '<button type="button" class="pri block" data-ans="send">' + esc(t('send')) + '</button>';
    }
    return h + '<p class="err" hidden></p>';
  }
  function addCard(c) {
    var el = addBot(cardHTML(c), 'card');
    wireCard(el, c);
  }
  function wireCard(el, c) {
    var size = null, photo = null;
    el.addEventListener('click', function (e) {
      if (el.classList.contains('done')) return;
      var s = e.target.closest('[data-size]');
      if (s) {
        el.querySelectorAll('[data-size]').forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
        s.setAttribute('aria-pressed', 'true'); size = c.size_options[+s.dataset.size]; return;
      }
      var a = e.target.closest('[data-ans],[data-choice]'); if (!a) return;
      var body = {}, said = '';
      if (a.dataset.choice !== undefined) { body = { answer: 'choice', choice: +a.dataset.choice }; said = a.querySelector('b').textContent; }
      else if (a.dataset.ans === 'yes') { body = { answer: 'yes', size: size }; said = t('yes') + (size ? ', ' + s2(c, size) : ''); }
      else if (a.dataset.ans === 'no') { body = { answer: 'no' }; said = t('no'); }
      else if (a.dataset.ans === 'other') {
        var v = el.querySelector('.other input').value.trim();
        body = { answer: 'other', text: v }; said = v || t('dunno');
      } else if (a.dataset.ans === 'send') {
        var dims = {}; el.querySelectorAll('[data-dim]').forEach(function (i) { if (i.value) dims[i.dataset.dim] = i.value; });
        var text = el.querySelector('textarea').value;
        if (!photo && !Object.keys(dims).length && !text.trim()) { showErr(el, t('needPhoto')); return; }
        body = { answer: 'detail', photo: photo, dims: dims, text: text };
        said = [photo ? t('photoOne') : '', dims.width ? t('w').replace(/\s*\(cm\)|\(cm\)/, '') + ' ' + dims.width + 'cm' : '',
          dims.depth ? t('d').replace(/\s*\(cm\)|\(cm\)/, '') + ' ' + dims.depth + 'cm' : '',
          dims.height ? t('h').replace(/\s*\(cm\)|\(cm\)/, '') + ' ' + dims.height + 'cm' : '', text.trim()].filter(Boolean).join(', ');
      }
      send(el, c, body, said);
    });
    var other = el.querySelector('.other input');
    if (other) other.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); el.querySelector('[data-ans="other"]').click(); } });
    var file = el.querySelector('input[type=file]');
    if (file) file.addEventListener('change', function () {
      var f = file.files && file.files[0]; if (!f) return;
      shrink(f, function (data) {
        photo = data;
        var old = el.querySelector('.photo img'); if (old) old.remove();
        var img = new Image(); img.src = data; img.alt = ''; el.querySelector('.photo').appendChild(img);
      });
    });
  }
  function s2(c, size) { var i = (c.size_options || []).indexOf(size); return (c._sizes || [])[i] || size; }
  function showErr(el, msg) { var p = el.querySelector('.err'); p.textContent = msg; p.hidden = false; }
  function send(el, c, body, said) {
    el.classList.add('done');
    el.querySelectorAll('button, input, textarea').forEach(function (b) { b.disabled = true; });
    addUser(said);
    state.busy = true; $('#send').disabled = true;
    var tp = typing();
    var go = body.answer === 'other' && body.text && !hasHangul(body.text)
      ? I.tr([body.text], 'ko').then(function (a) { body.text = a[0]; }) : Promise.resolve();
    go.then(function () { return api('/api/confirm/' + encodeURIComponent(c.card_id), body); }).then(function (j) {
      if (j.status === 'error') throw new Error(j.message);
      if (j.status === 'card') {
        var tx = [];
        var add = function (s) { if (s && tx.indexOf(s) < 0) tx.push(s); };
        var cd = j.card; add(cd.item_label); add(cd.question); (cd.size_options || []).forEach(add);
        (cd.options || []).forEach(function (o) { add(o.label); add(o.desc); }); if (cd.product) add(cd.product.title);
        return I.tr(tx).then(function (a) {
          var m = {}; tx.forEach(function (x, i) { m[x] = a[i]; });
          localizeCard(cd, function (s) { return s ? (m[s] || s) : s; });
          tp.remove(); addCard(cd);
        });
      }
      return localize(j).then(function (jj) { tp.remove(); answer(jj); });
    }).catch(function (err) { errMsg(err).then(function (m) { tp.remove(); addBot(esc(m)); }); })
      .then(function () { state.busy = false; $('#send').disabled = false; });
  }
  function shrink(file, cb) {
    var r = new FileReader();
    r.onload = function () {
      var img = new Image();
      img.onload = function () {
        var max = 1024, w = img.width, h = img.height, s = Math.min(1, max / Math.max(w, h));
        var cv = document.createElement('canvas'); cv.width = Math.round(w * s); cv.height = Math.round(h * s);
        cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
        cb(cv.toDataURL('image/jpeg', 0.8));
      };
      img.src = r.result;
    };
    r.readAsDataURL(file);
  }

  /* ---------- 접수번호로 다시 보기 ---------- */
  function showTicket(id) {
    api('/api/ticket/' + encodeURIComponent(id)).then(function (j) {
      var extra = (j.pending || []).concat(j.closed || []).concat([j.municipality]);
      return localize({ rows: j.rows || [], pending: extra }).then(function (lj) {
        var m = {}; extra.forEach(function (x, i) { m[x] = lj._pending[i]; });
        var tr = function (a) { return (a || []).map(function (x) { return m[x] || x; }).join(', '); };
        var h = '<p class="lead">' + esc(t('ticketHead', { t: j.ticket, m: m[j.municipality] || j.municipality })) + '</p>';
        if (j.rows && j.rows.length) h += '<p>' + esc(t('feeLead')) + '</p>' + (itemsCount(j.rows) === 1 ? linesHTML(lj.rows) : tableHTML(lj.rows));
        if (j.pending && j.pending.length) h += '<p class="sub">' + esc(t('pendLater', { x: tr(j.pending) })) + '</p>';
        if (j.closed && j.closed.length) h += '<p class="sub">' + esc(t('closed', { x: tr(j.closed) })) + '</p>';
        addBot(h);
      });
    }).catch(function (err) { errMsg(err).then(toast); });
  }

  /* ---------- 시작 ---------- */
  applyStatic();
  var started = false;
  function start() {
  api('/api/municipalities').then(function (j) {
      if (started) return;
      MUNIS = j.items || [];
      if (!MUNIS.length) throw new Error('empty');
      started = true;
      MUNIS.forEach(function (m) { m.disp = m.name; });
      // 첫 질문은 바로 띄우고, 지역 이름 번역은 뒤에서(오래 걸려도 기다리게 하지 않는다)
      var first = ko() ? Promise.resolve() : Promise.race([prepareMunis(), new Promise(function (r) { setTimeout(r, 1500); })]);
      return first.then(function () {
        if (!ko()) prepareMunis().then(function () {
          var chip = document.querySelector('[data-place="gwacheon"]');
          var g = MUNIS.filter(function (m) { return m.code === 'gwacheon'; })[0];
          if (chip && g) chip.textContent = g.disp || g.name;
          if (state.muni) { var m = MUNIS.filter(function (x) { return x.code === state.muni; })[0]; if (m) { state.muniDisp = m.disp; $('#muniName').textContent = m.disp; } }
        });
        var sp = new URLSearchParams(location.search);
        var hit = MUNIS.filter(function (m) { return m.code === sp.get('m'); })[0];
        if (sp.get('t')) showTicket(sp.get('t'));
        askPlace(false);                      // 시작 질문은 항상 지역
        var qq = sp.get('q');
        if (hit && qq) state.waiting = qq;    // 공유 링크(?m=&q=): 인사 다음에 그 품목을 이어서 답한다
        if (hit) setMuni(hit);
      });
    }).catch(function () {
      var el = addBot(esc(t('tryLater')) + '<div class="chips"><button type="button" data-retry="1">' + esc(t('retry')) + '</button></div>');
      el.querySelector('[data-retry]').addEventListener('click', function () { el.remove(); start(); });
    });
  }
  start();
})();
