(function () {
  'use strict';
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var CAT_ORDER = ['가구류', '가전·전자', '생활용품', '유아용품', '반려동물', '운동·레저', '악기·취미', '사무·기타', '목재', '기타'];
  var QUICK = ['소파', '냉장고', '식기세척기', '캣타워', '전동킥보드', '매트리스', '화이트보드', '안마의자'];
  var state = { muni: 'gwacheon', muniName: '', items: [], rows: [], pending: [], tickets: [], cards: [] };

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

  /* ---------- 지자체 ---------- */
  function loadMunis() {
    var sel = $('#muni');
    return api('/api/municipalities').then(function (j) {
      var saved = store('bw.muni');
      sel.innerHTML = j.items.map(function (m) { return '<option value="' + esc(m.code) + '">' + esc(m.name) + '</option>'; }).join('');
      if (saved && j.items.some(function (m) { return m.code === saved; })) sel.value = saved;
      state.muni = sel.value;
      state.muniName = sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : '';
      $('#footnote').textContent = '표시된 금액은 ' + state.muniName + ' 대형폐기물 배출 수수료입니다.';
    });
  }
  $('#muni').addEventListener('change', function (e) {
    state.muni = e.target.value; store('bw.muni', state.muni);
    state.muniName = e.target.options[e.target.selectedIndex].text;
    $('#footnote').textContent = '표시된 금액은 ' + state.muniName + ' 대형폐기물 배출 수수료입니다.';
    resetOut();
  });

  /* ---------- 입력 ---------- */
  function splitNames(s) {
    return String(s || '').split(/[,\n、，]+/).map(function (x) { return x.trim(); }).filter(Boolean);
  }
  function addItems(names) {
    names.forEach(function (n) {
      n = n.slice(0, 40);
      if (state.items.indexOf(n) < 0 && state.items.length < 30) state.items.push(n);
    });
    renderChips();
  }
  function renderChips() {
    $('#chips').innerHTML = state.items.map(function (n, i) {
      return '<li class="chip">' + esc(n) + '<button type="button" data-rm="' + i + '" aria-label="' + esc(n) + ' 빼기">×</button></li>';
    }).join('');
  }
  $('#chips').addEventListener('click', function (e) {
    var b = e.target.closest('[data-rm]'); if (!b) return;
    state.items.splice(+b.dataset.rm, 1); renderChips(); $('#item').focus();
  });
  $('#add').addEventListener('click', function () {
    var v = $('#item').value; if (!v.trim()) { $('#item').focus(); return; }
    addItems(splitNames(v)); $('#item').value = ''; $('#item').focus();
  });
  $('#item').addEventListener('keydown', function (e) {
    if (e.key === ',' ) { e.preventDefault(); $('#add').click(); }
  });
  $('#quick').innerHTML = QUICK.map(function (n) { return '<button type="button" data-q="' + esc(n) + '">' + esc(n) + '</button>'; }).join('');
  $('#quick').addEventListener('click', function (e) {
    var b = e.target.closest('[data-q]'); if (!b) return;
    addItems([b.dataset.q]);
  });

  $('#ask').addEventListener('submit', function (e) {
    e.preventDefault();
    var extra = splitNames($('#item').value);
    if (extra.length) { addItems(extra); $('#item').value = ''; }
    if (!state.items.length) { $('#item').focus(); toast('품목 이름을 입력해 주세요'); return; }
    var go = $('#go'); go.disabled = true; go.innerHTML = '<span class="spin"></span>확인 중';
    api('/api/quote', { municipality: state.muni, items: state.items.map(function (n) { return { name: n }; }) })
      .then(function (j) {
        resetOut();
        merge(j);
        state.items = []; renderChips();
        $('#out').scrollIntoView({ behavior: 'smooth', block: 'start' });
      })
      .catch(function (err) { toast(err.message); })
      .then(function () { go.disabled = false; go.textContent = '수수료 확인'; });
  });

  /* ---------- 결과 ---------- */
  function resetOut() {
    state.rows = []; state.pending = []; state.tickets = []; state.cards = [];
    $('#cards').innerHTML = ''; render();
  }
  function merge(j) {
    (j.rows || []).forEach(function (r) {
      var dup = state.rows.some(function (x) { return x['품목'] === r['품목'] && x['규격'] === r['규격'] && x['수수료'] === r['수수료']; });
      if (!dup) state.rows.push(r);
    });
    (j.pending || []).forEach(function (p) { if (state.pending.indexOf(p) < 0) state.pending.push(p); });
    if (j.ticket) state.tickets.push(j.ticket);
    (j.needs_confirm || []).forEach(function (c) { addCard(c); });
    render();
  }
  function itemsCount(rows) {
    var s = {}; rows.forEach(function (r) { s[r['품목']] = 1; }); return Object.keys(s).length;
  }
  function sortRows(rows) {
    // 같은 품목은 붙여서(처음 나온 순서), 품목 안에서는 서버가 준 순서(작은 규격부터)
    var order = []; var by = {};
    rows.forEach(function (r) { if (!by[r['품목']]) { by[r['품목']] = []; order.push(r['품목']); } by[r['품목']].push(r); });
    var out = []; order.forEach(function (n) { out = out.concat(by[n]); });
    return out;
  }
  function render() {
    var rows = sortRows(state.rows);
    var has = rows.length > 0;
    $('#out').hidden = !(has || state.pending.length || $('#cards').children.length);
    $('#result').hidden = !has;
    if (has) {
      $('#lead').textContent = '문의하신 품목의 수수료입니다.';
      $('#rows').innerHTML = itemsCount(rows) === 1 ? linesHTML(rows) : tableHTML(rows);
    }
    var p = $('#pending');
    p.hidden = !state.pending.length;
    if (state.pending.length) {
      var tk = state.tickets[state.tickets.length - 1];
      p.innerHTML = '<h2>확인 후 안내드리겠습니다.</h2>' +
        '<ul>' + state.pending.map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('') + '</ul>' +
        (tk ? '<div class="tk">접수번호 <code>' + esc(tk) + '</code>' +
          '<button type="button" class="btn small" data-ticket="' + esc(tk) + '">확인 주소 복사</button></div>' +
          '<p class="hint">담당자가 금액을 정하면 이 주소에서 바로 볼 수 있습니다.</p>' : '');
    }
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
    var body = '';
    var groups = grouped ? CAT_ORDER.map(function (c) {
      return { c: c, rows: rows.filter(function (r) { return (r['분류'] || '기타') === c; }) };
    }).filter(function (g) { return g.rows.length; }) : [{ c: null, rows: rows }];
    var cols = hasNote ? 4 : 3;
    groups.forEach(function (g) {
      if (g.c) body += '<tr class="cat"><th colspan="' + cols + '" scope="colgroup">' + esc(g.c) + '</th></tr>';
      var prev = null;
      g.rows.forEach(function (r) {
        var same = prev === r['품목']; prev = r['품목'];
        body += '<tr' + (same ? ' class="same"' : '') + '><td class="item">' + esc(r['품목']) +
          (r['안내'] ? '<span class="note-inline">' + esc(r['안내']) + '</span>' : '') + '</td>' +
          '<td>' + esc(r['규격']) + '</td><td class="fee">' + esc(r['수수료']) + '</td>' +
          (hasNote ? '<td class="note">' + esc(r['안내']) + '</td>' : '') + '</tr>';
      });
    });
    return '<table class="fees' + (hasNote ? ' has-note' : '') + '"><colgroup><col class="c-item"><col class="c-spec"><col class="c-fee">' +
      (hasNote ? '<col class="c-note">' : '') + '</colgroup><thead><tr><th scope="col">품목</th><th scope="col">규격</th>' +
      '<th scope="col" class="fee">수수료</th>' + (hasNote ? '<th scope="col" class="note">안내</th>' : '') +
      '</tr></thead><tbody>' + body + '</tbody></table>';
  }

  /* ---------- 복사·내려받기 ---------- */
  function asText() {
    var rows = sortRows(state.rows);
    return ['문의하신 품목의 수수료입니다.'].concat(rows.map(function (r) {
      return r['품목'] + ' (' + r['규격'] + ') — ' + r['수수료'] + (r['안내'] ? ' · ' + r['안내'] : '');
    })).join('\n');
  }
  function asTable() {
    var rows = sortRows(state.rows);
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
  $('#actions').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    if (b.dataset.copy === 'text') copy(asText());
    if (b.dataset.copy === 'table') copy(asTable(), '표를 복사했습니다. 엑셀·한글에 붙여 넣을 수 있습니다');
    if (b.dataset.dl) download(b.dataset.dl);
  });
  function download(fmt) {
    fetch('/api/quote/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format: fmt, rows: sortRows(state.rows) })
    }).then(function (r) { if (!r.ok) throw new Error('내려받지 못했습니다'); return r.blob(); })
      .then(function (blob) {
        var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = '대형폐기물_수수료.' + (fmt === 'xlsx' ? 'xlsx' : 'csv');
        document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
      }).catch(function (err) { toast(err.message); });
  }
  $('#pending').addEventListener('click', function (e) {
    var b = e.target.closest("[data-ticket]"); if (!b) return;
    copy(location.origin + '/?t=' + b.dataset.ticket, '확인 주소를 복사했습니다');
  });

  /* ---------- 확인 카드 ---------- */
  function addCard(c) {
    var el = document.createElement('div');
    el.className = 'panel card';
    el.dataset.id = c.card_id;
    el.innerHTML = cardHTML(c);
    $('#cards').appendChild(el);
    wireCard(el, c);
  }
  function cardHTML(c) {
    var h = '<span class="step">질문 ' + c.step + '/' + c.max_steps + '</span>' +
      '<p class="about">문의하신 표현: “' + esc(c.name) + '”</p>';
    if (c.kind === 'yesno') {
      h += '<h2>문의하신 품목이 <b>' + esc(c.item_label) + '</b>' + josa(c.item_label) + ' 맞으신가요?</h2>';
      if (c.product && (c.product.image || c.product.title)) {
        h += '<a class="prod" href="' + esc(c.product.link || '#') + '" target="_blank" rel="noopener noreferrer">' +
          (c.product.image ? '<img src="' + esc(c.product.image) + '" alt="" loading="lazy" referrerpolicy="no-referrer">' : '') +
          '<span>' + esc(c.product.title) + '</span></a>';
      }
      if (c.size_options) {
        h += '<div class="sizes"><p>크기를 골라 주세요</p><div class="seg">' + c.size_options.map(function (s, i) {
          return '<button type="button" data-size="' + i + '" aria-pressed="false">' + esc(s) + '</button>';
        }).join('') + '</div></div>';
      }
      h += '<div class="row2"><button type="button" class="btn primary" data-ans="yes">예</button>' +
        '<button type="button" class="btn" data-ans="no">아니요</button></div>';
    } else if (c.kind === 'choice') {
      h += '<h2>' + esc(c.question) + '</h2><div class="opts">' + c.options.map(function (o) {
        return '<button type="button" class="opt" data-choice="' + o.id + '"><b>' + esc(o.label) + '</b>' +
          (o.desc ? '<small>' + esc(o.desc) + '</small>' : '') + '</button>';
      }).join('') + '</div>' +
        '<div class="other"><input type="text" maxlength="40" placeholder="기타(직접 입력)" aria-label="기타 품목 직접 입력">' +
        '<button type="button" class="btn" data-ans="other">확인</button></div>';
    } else {
      h += '<h2>' + esc(c.question) + '</h2>' +
        '<div class="photo"><label>사진<input type="file" accept="image/*" capture="environment"></label></div>' +
        '<div class="dims"><label>가로(cm)<input type="number" inputmode="decimal" min="0" data-dim="width"></label>' +
        '<label>세로(cm)<input type="number" inputmode="decimal" min="0" data-dim="depth"></label>' +
        '<label>높이(cm)<input type="number" inputmode="decimal" min="0" data-dim="height"></label></div>' +
        '<textarea placeholder="어떤 물건인지 한두 마디(선택)" maxlength="200" aria-label="설명"></textarea>' +
        '<button type="button" class="btn primary block" data-ans="send">보내기</button>';
    }
    return h + '<p class="err" hidden></p>';
  }
  function wireCard(el, c) {
    var size = null; var photo = null;
    el.addEventListener('click', function (e) {
      var s = e.target.closest('[data-size]');
      if (s) {
        el.querySelectorAll('[data-size]').forEach(function (b) { b.setAttribute('aria-pressed', 'false'); });
        s.setAttribute('aria-pressed', 'true'); size = c.size_options[+s.dataset.size]; return;
      }
      var a = e.target.closest('[data-ans],[data-choice]'); if (!a) return;
      var body = {};
      if (a.dataset.choice !== undefined) body = { answer: 'choice', choice: +a.dataset.choice };
      else if (a.dataset.ans === 'yes') body = { answer: 'yes', size: size };
      else if (a.dataset.ans === 'no') body = { answer: 'no' };
      else if (a.dataset.ans === 'other') body = { answer: 'other', text: el.querySelector('.other input').value };
      else if (a.dataset.ans === 'send') {
        var dims = {}; el.querySelectorAll('[data-dim]').forEach(function (i) { if (i.value) dims[i.dataset.dim] = i.value; });
        var text = el.querySelector('textarea').value;
        if (!photo && !Object.keys(dims).length && !text.trim()) { showErr(el, '사진이나 크기 중 하나는 알려 주세요.'); return; }
        body = { answer: 'detail', photo: photo, dims: dims, text: text };
      }
      send(el, c, body);
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
  function josa(label) {
    var base = String(label).replace(/\s*\([^()]*\)\s*$/, '').trim();
    var ch = base.charCodeAt(base.length - 1);
    if (ch >= 0xAC00 && ch <= 0xD7A3) return (ch - 0xAC00) % 28 ? '이' : '가';
    return '가';
  }
  function showErr(el, msg) { var p = el.querySelector('.err'); p.textContent = msg; p.hidden = false; }
  function send(el, c, body) {
    el.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
    api('/api/confirm/' + encodeURIComponent(c.card_id), body).then(function (j) {
      if (j.status === 'error') throw new Error(j.message);
      if (j.status === 'card') {
        var nc = j.card; el.dataset.id = nc.card_id; el.innerHTML = cardHTML(nc);
        var fresh = el.cloneNode(true); el.parentNode.replaceChild(fresh, el); wireCard(fresh, nc);
        fresh.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
      el.remove(); merge(j);
      $('#result').hidden || $('#result').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }).catch(function (err) {
      showErr(el, err.message);
      el.querySelectorAll('button').forEach(function (b) { b.disabled = false; });
    });
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
      var v = $('#ticketview'); v.hidden = false;
      var h = '<p class="lead">접수번호 ' + esc(j.ticket) + ' · ' + esc(j.municipality) + '</p>';
      if (j.rows && j.rows.length) h += '<p>문의하신 품목의 수수료입니다.</p>' + (itemsCount(j.rows) === 1 ? linesHTML(j.rows) : tableHTML(j.rows));
      if (j.pending && j.pending.length) h += '<p class="hint">' + esc(j.pending.join(', ')) + ' — 확인 후 안내드리겠습니다.</p>';
      if (j.closed && j.closed.length) h += '<p class="hint">' + esc(j.closed.join(', ')) + ' — 지자체 담당 부서로 문의해 주세요.</p>';
      v.innerHTML = h;
    }).catch(function (err) { toast(err.message); });
  }

  loadMunis().then(function () {
    var t = new URLSearchParams(location.search).get('t');
    if (t) showTicket(t);
  }).catch(function () { toast('잠시 후 다시 시도해 주세요.'); });
})();
