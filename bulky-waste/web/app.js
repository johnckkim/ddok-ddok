(function () {
  'use strict';
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var CAT_ORDER = ['가구류', '가전·전자', '생활용품', '유아용품', '반려동물', '운동·레저', '악기·취미', '사무·기타', '목재', '기타'];
  var QUICK = ['소파', '냉장고', '식기세척기', '캣타워', '전동킥보드', '매트리스'];
  var state = { muni: '', muniName: '', mode: 'place', busy: false };
  var MUNIS = [];

  /* ---------- 공통 ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function toast(msg) {
    var t = $('#toast'); t.textContent = msg; t.classList.add('on');
    clearTimeout(toast.h); toast.h = setTimeout(function () { t.classList.remove('on'); }, 1800);
  }
  function api(path, body) {
    return fetch(path, {
      method: body ? 'POST' : 'GET',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.message || '잠시 후 다시 시도해 주세요.');
        return j;
      });
    });
  }
  function store(key, val) {
    try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch (e) { return null; }
  }
  function flat(s) { return String(s || '').replace(/\s+/g, ''); }
  function splitNames(s) {
    return String(s || '').split(/[,\n、，]+/).map(function (x) { return x.trim(); }).filter(Boolean).slice(0, 30);
  }

  /* ---------- 대화 ---------- */
  var thread = $('#thread');
  function scrollEnd() {
    requestAnimationFrame(function () { window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }); });
  }
  function addUser(text) {
    var el = document.createElement('div');
    el.className = 'msg user';
    el.innerHTML = '<div class="bubble">' + esc(text) + '</div>';
    thread.appendChild(el); scrollEnd(); return el;
  }
  function addBot(html, cls) {
    var el = document.createElement('div');
    el.className = 'msg bot' + (cls ? ' ' + cls : '');
    el.innerHTML = '<img class="avatar" src="/static/icon.svg" alt="" width="30" height="30"><div class="bubble">' + html + '</div>';
    thread.appendChild(el); scrollEnd(); return el;
  }
  function typing() {
    return addBot('<span class="dots" aria-label="답변 작성 중"><i></i><i></i><i></i></span>', 'typing');
  }
  function setMode(mode) {
    state.mode = mode;
    var input = $('#input');
    input.value = '';
    if (mode === 'place') {
      input.placeholder = '거주하고 계신 지자체명 (예: 과천시)';
      $('#inputLabel').textContent = '지자체명';
      $('#footnote').textContent = '시·군·구 이름 일부만 입력해도 됩니다.';
    } else {
      input.placeholder = '버릴 품목을 입력하세요 (예: 식기세척기, 캣타워)';
      $('#inputLabel').textContent = '품목';
      $('#footnote').textContent = '여러 품목은 쉼표(,)로 구분해 주세요.';
    }
    renderSuggest();
    setTimeout(function () { input.focus(); }, 30);
  }

  /* ---------- 지자체 ---------- */
  function matches(q) {
    q = flat(q).replace(/(특별시|광역시|특별자치시|특별자치도)$/, '');
    if (!q) return [];
    var starts = [], has = [];
    MUNIS.forEach(function (m) {
      var parts = m.name.split(' '); var last = flat(parts[parts.length - 1]); var all = flat(m.name);
      if (last.indexOf(q) === 0 || last.replace(/(시|군|구)$/, '') === q) starts.push(m);
      else if (all.indexOf(q) >= 0) has.push(m);
    });
    return starts.concat(has).slice(0, 8);
  }
  function askPlace(again) {
    $('#muniPill').hidden = true;
    addBot(again ? '지자체를 바꿀게요. <b>거주하고 계신 지자체명</b>을 입력해 주세요.'
      : '안녕하세요! 대형폐기물 수수료를 알려드릴게요.<br>먼저 <b>거주하고 계신 지자체명</b>을 입력해 주세요.');
    setMode('place');
  }
  function setMuni(m, quiet) {
    state.muni = m.code; state.muniName = m.name; store('bw.muni', m.code);
    $('#muniName').textContent = m.name; $('#muniPill').hidden = false;
    if (!quiet) addUser(m.name);
    addBot('<b>' + esc(m.name) + '</b> 기준으로 안내해 드릴게요.<br>버릴 품목을 입력해 주세요. 여러 개는 쉼표(,)로 구분하면 됩니다.' +
      '<div class="chips">' + QUICK.map(function (n) { return '<button type="button" data-send="' + esc(n) + '">' + esc(n) + '</button>'; }).join('') + '</div>');
    setMode('items');
  }
  function renderSuggest() {
    var ul = $('#suggest');
    if (state.mode !== 'place') { ul.innerHTML = ''; return; }
    var list = matches($('#input').value);
    ul.innerHTML = list.map(function (m, i) {
      return '<li><button type="button" role="option" data-code="' + esc(m.code) + '"' + (i === 0 ? ' aria-selected="true"' : '') + '>' + esc(m.name) + '</button></li>';
    }).join('');
  }
  $('#input').addEventListener('input', renderSuggest);
  $('#suggest').addEventListener('click', function (e) {
    var b = e.target.closest('[data-code]'); if (!b) return;
    setMuni(MUNIS.filter(function (m) { return m.code === b.dataset.code; })[0]);
  });
  $('#muniPill').addEventListener('click', function () { askPlace(true); });

  /* ---------- 보내기 ---------- */
  $('#composer').addEventListener('submit', function (e) {
    e.preventDefault();
    var text = $('#input').value.trim();
    if (!text || state.busy) return;
    if (state.mode === 'place') {
      var list = matches(text);
      if (list.length) { setMuni(list[0]); return; }
      addUser(text); $('#input').value = ''; renderSuggest();
      addBot('아직 안내하지 않는 지역이에요. 시·군·구 이름을 다시 확인해 주세요. (현재 ' + MUNIS.length + '곳 안내)');
      return;
    }
    sendItems(splitNames(text), text);
  });
  thread.addEventListener('click', function (e) {
    var b = e.target.closest('[data-send]');
    if (b && state.mode === 'items' && !state.busy) sendItems([b.dataset.send], b.dataset.send);
  });
  function sendItems(names, shown) {
    if (!names.length) return;
    $('#input').value = '';
    addUser(shown || names.join(', '));
    state.busy = true; $('#send').disabled = true;
    var t = typing();
    api('/api/quote', { municipality: state.muni, items: names.map(function (n) { return { name: n }; }) })
      .then(function (j) { t.remove(); answer(j); })
      .catch(function (err) { t.remove(); addBot(esc(err.message)); })
      .then(function () { state.busy = false; $('#send').disabled = false; $('#input').focus(); });
  }

  /* ---------- 답변 ---------- */
  function answer(j) {
    var rows = j.rows || [];
    if (rows.length) addResult(rows);
    if (j.pending && j.pending.length) addPending(j.pending, j.ticket);
    (j.needs_confirm || []).forEach(addCard);
    if (!rows.length && !(j.pending || []).length && !(j.needs_confirm || []).length) addBot('품목 이름을 다시 입력해 주세요.');
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
    var el = addBot('<p class="lead">문의하신 품목의 수수료입니다.</p>' + (itemsCount(rows) === 1 ? linesHTML(rows) : tableHTML(rows)) +
      '<div class="actions"><button type="button" data-act="text">복사</button><button type="button" data-act="table">표 복사</button>' +
      '<button type="button" data-act="csv">CSV</button><button type="button" data-act="xlsx">엑셀</button></div>', 'result');
    el._rows = rows;
  }
  function addPending(names, tk) {
    addBot('<p class="lead">확인 후 안내드리겠습니다.</p><ul class="plist">' + names.map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('') + '</ul>' +
      (tk ? '<div class="tk">접수번호 <code>' + esc(tk) + '</code><button type="button" data-ticket="' + esc(tk) + '">확인 주소 복사</button></div>' +
        '<p class="sub">담당자가 금액을 정하면 이 주소에서 바로 볼 수 있습니다.</p>' : ''), 'pending');
  }
  function linesHTML(rows) {
    return '<ul class="lines">' + rows.map(function (r) {
      return '<li><span class="nm">' + esc(r['품목']) + '</span><span class="sp">(' + esc(r['규격']) + ')</span>' +
        '<span class="fe">' + esc(r['수수료']) + '</span>' + (r['안내'] ? '<span class="nt">' + esc(r['안내']) + '</span>' : '') + '</li>';
    }).join('') + '</ul>';
  }
  function tableHTML(rows) {
    var hasNote = rows.some(function (r) { return r['안내']; });
    var grouped = itemsCount(rows) >= 10;
    var groups = grouped ? CAT_ORDER.map(function (c) {
      return { c: c, rows: rows.filter(function (r) { return (r['분류'] || '기타') === c; }) };
    }).filter(function (g) { return g.rows.length; }) : [{ c: null, rows: rows }];
    var body = '';
    groups.forEach(function (g) {
      if (g.c) body += '<tr class="cat"><th colspan="3" scope="colgroup">' + esc(g.c) + '</th></tr>';
      var prev = null;
      g.rows.forEach(function (r) {
        var same = prev === r['품목']; prev = r['품목'];
        body += '<tr' + (same ? ' class="same"' : '') + '><td class="item">' + esc(r['품목']) +
          (r['안내'] ? '<span class="note-inline">' + esc(r['안내']) + '</span>' : '') + '</td>' +
          '<td>' + esc(r['규격']) + '</td><td class="fee">' + esc(r['수수료']) + '</td></tr>';
      });
    });
    return '<table class="fees' + (hasNote ? ' has-note' : '') + '"><colgroup><col class="c-item"><col class="c-spec"><col class="c-fee"></colgroup>' +
      '<thead><tr><th scope="col">품목</th><th scope="col">규격</th><th scope="col" class="fee">수수료</th></tr></thead><tbody>' + body + '</tbody></table>';
  }

  /* ---------- 복사·내려받기 ---------- */
  function asText(rows) {
    return ['문의하신 품목의 수수료입니다.'].concat(rows.map(function (r) {
      return r['품목'] + ' (' + r['규격'] + ') — ' + r['수수료'] + (r['안내'] ? ' · ' + r['안내'] : '');
    })).join('\n');
  }
  function asTable(rows) {
    var hasNote = rows.some(function (r) { return r['안내']; });
    var head = ['품목', '규격', '수수료'].concat(hasNote ? ['안내'] : []);
    return [head.join('\t')].concat(rows.map(function (r) {
      return [r['품목'], r['규격'], r['수수료']].concat(hasNote ? [r['안내']] : []).join('\t');
    })).join('\n');
  }
  function copy(text, msg) {
    var done = function () { toast(msg || '복사했습니다'); };
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
    }).then(function (r) { if (!r.ok) throw new Error('내려받지 못했습니다'); return r.blob(); })
      .then(function (blob) {
        var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = '대형폐기물_수수료.' + (fmt === 'xlsx' ? 'xlsx' : 'csv');
        document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
      }).catch(function (err) { toast(err.message); });
  }
  thread.addEventListener('click', function (e) {
    var b = e.target.closest('[data-act]');
    if (b) {
      var rows = b.closest('.msg')._rows || [];
      if (b.dataset.act === 'text') copy(asText(rows));
      else if (b.dataset.act === 'table') copy(asTable(rows), '표를 복사했습니다. 엑셀·한글에 붙여 넣을 수 있습니다');
      else download(b.dataset.act, rows);
      return;
    }
    var t = e.target.closest('[data-ticket]');
    if (t) copy(location.origin + '/?t=' + t.dataset.ticket, '확인 주소를 복사했습니다');
  });

  /* ---------- 확인 질문 ---------- */
  function josa(label) {
    var base = String(label).replace(/\s*\([^()]*\)\s*$/, '').trim();
    var ch = base.charCodeAt(base.length - 1);
    if (ch >= 0xAC00 && ch <= 0xD7A3) return (ch - 0xAC00) % 28 ? '이' : '가';
    return '가';
  }
  function cardHTML(c) {
    var h = '<span class="step">질문 ' + c.step + '/' + c.max_steps + '</span>';
    if (c.kind === 'yesno') {
      h += '<p class="q">“' + esc(c.name) + '” — 문의하신 품목이 <b>' + esc(c.item_label) + '</b>' + josa(c.item_label) + ' 맞으신가요?</p>';
      if (c.product && (c.product.image || c.product.title)) {
        h += '<a class="prod" href="' + esc(c.product.link || '#') + '" target="_blank" rel="noopener noreferrer">' +
          (c.product.image ? '<img src="' + esc(c.product.image) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '') +
          '<span>' + esc(c.product.title) + '</span></a>';
      }
      if (c.size_options) {
        h += '<p class="sub">크기를 골라 주세요</p><div class="seg">' + c.size_options.map(function (s, i) {
          return '<button type="button" data-size="' + i + '" aria-pressed="false">' + esc(s) + '</button>';
        }).join('') + '</div>';
      }
      h += '<div class="row2"><button type="button" class="pri" data-ans="yes">예</button><button type="button" data-ans="no">아니요</button></div>';
    } else if (c.kind === 'choice') {
      h += '<p class="q">“' + esc(c.name) + '” — ' + esc(c.question) + '</p><div class="opts">' + c.options.map(function (o) {
        return '<button type="button" class="opt" data-choice="' + o.id + '"><b>' + esc(o.label) + '</b>' +
          (o.desc ? '<small>' + esc(o.desc) + '</small>' : '') + '</button>';
      }).join('') + '</div>' +
        '<div class="other"><input type="text" maxlength="40" placeholder="기타(직접 입력)" aria-label="기타 품목 직접 입력">' +
        '<button type="button" data-ans="other">확인</button></div>';
    } else {
      h += '<p class="q">' + esc(c.question) + '</p>' +
        '<label class="photo">사진<input type="file" accept="image/*" capture="environment"></label>' +
        '<div class="dims"><label>가로(cm)<input type="number" inputmode="decimal" min="0" data-dim="width"></label>' +
        '<label>세로(cm)<input type="number" inputmode="decimal" min="0" data-dim="depth"></label>' +
        '<label>높이(cm)<input type="number" inputmode="decimal" min="0" data-dim="height"></label></div>' +
        '<textarea placeholder="어떤 물건인지 한두 마디(선택)" maxlength="200" aria-label="설명"></textarea>' +
        '<button type="button" class="pri block" data-ans="send">보내기</button>';
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
      else if (a.dataset.ans === 'yes') { body = { answer: 'yes', size: size }; said = '예' + (size ? ', ' + size : ''); }
      else if (a.dataset.ans === 'no') { body = { answer: 'no' }; said = '아니요'; }
      else if (a.dataset.ans === 'other') {
        var v = el.querySelector('.other input').value.trim();
        body = { answer: 'other', text: v }; said = v || '잘 모르겠어요';
      } else if (a.dataset.ans === 'send') {
        var dims = {}; el.querySelectorAll('[data-dim]').forEach(function (i) { if (i.value) dims[i.dataset.dim] = i.value; });
        var text = el.querySelector('textarea').value;
        if (!photo && !Object.keys(dims).length && !text.trim()) { showErr(el, '사진이나 크기 중 하나는 알려 주세요.'); return; }
        body = { answer: 'detail', photo: photo, dims: dims, text: text };
        said = [photo ? '사진 1장' : '', dims.width ? '가로 ' + dims.width + 'cm' : '', dims.depth ? '세로 ' + dims.depth + 'cm' : '',
          dims.height ? '높이 ' + dims.height + 'cm' : '', text.trim()].filter(Boolean).join(', ');
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
        var img = new Image(); img.src = data; img.alt = '올린 사진'; el.querySelector('.photo').appendChild(img);
      });
    });
  }
  function showErr(el, msg) { var p = el.querySelector('.err'); p.textContent = msg; p.hidden = false; }
  function send(el, c, body, said) {
    el.classList.add('done');
    el.querySelectorAll('button, input, textarea').forEach(function (b) { b.disabled = true; });
    addUser(said);
    var t = typing();
    api('/api/confirm/' + encodeURIComponent(c.card_id), body).then(function (j) {
      t.remove();
      if (j.status === 'error') throw new Error(j.message);
      if (j.status === 'card') { addCard(j.card); return; }
      answer(j);
    }).catch(function (err) { t.remove(); addBot(esc(err.message)); });
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
      var h = '<p class="lead">접수번호 ' + esc(j.ticket) + ' · ' + esc(j.municipality) + '</p>';
      if (j.rows && j.rows.length) h += '<p>문의하신 품목의 수수료입니다.</p>' + (itemsCount(j.rows) === 1 ? linesHTML(j.rows) : tableHTML(j.rows));
      if (j.pending && j.pending.length) h += '<p class="sub">' + esc(j.pending.join(', ')) + ' — 확인 후 안내드리겠습니다.</p>';
      if (j.closed && j.closed.length) h += '<p class="sub">' + esc(j.closed.join(', ')) + ' — 지자체 담당 부서로 문의해 주세요.</p>';
      addBot(h);
    }).catch(function (err) { toast(err.message); });
  }

  /* ---------- 시작 ---------- */
  api('/api/municipalities').then(function (j) {
    MUNIS = j.items;
    var sp = new URLSearchParams(location.search);
    var want = sp.get('m') || store('bw.muni');
    var hit = MUNIS.filter(function (m) { return m.code === want; })[0];
    if (sp.get('t')) showTicket(sp.get('t'));
    if (hit) setMuni(hit, true); else askPlace(false);
    var qq = sp.get('q');
    if (qq && hit) sendItems(splitNames(qq), qq);
  }).catch(function () { addBot('잠시 후 다시 시도해 주세요.'); });
})();
