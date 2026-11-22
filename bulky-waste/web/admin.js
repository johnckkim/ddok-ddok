(function () {
  'use strict';
  var $ = function (s, el) { return (el || document).querySelector(s); };
  var $$ = function (s, el) { return Array.prototype.slice.call((el || document).querySelectorAll(s)); };
  var CATS = ['가구류', '가전·전자', '생활용품', '유아용품', '반려동물', '운동·레저', '악기·취미', '사무·기타', '목재', '기타'];
  var METHODS = ['무상수거', '종량제봉투 배출', '대상 아님(건설폐기물)'];
  var S = { muni: 'gwacheon', tab: 'review', overview: null, status: 'open', targets: '서울 전체, 경기 전체' };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function fmt(n) { return n == null || n === '' ? '' : Number(n).toLocaleString('ko-KR'); }
  function when(t) { if (!t) return ''; var d = new Date(t * 1000); return d.toLocaleString('ko-KR', { year: '2-digit', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  function toast(m) { var t = $('#toast'); t.textContent = m; t.classList.add('on'); clearTimeout(toast.h); toast.h = setTimeout(function () { t.classList.remove('on'); }, 2200); }
  function api(path, opt) {
    opt = opt || {};
    var init = { method: opt.method || (opt.body || opt.form ? 'POST' : 'GET'), credentials: 'same-origin', headers: {} };
    if (opt.body) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(opt.body); }
    if (opt.form) init.body = opt.form;
    return fetch(path, init).then(function (r) {
      if (r.status === 401 && path.indexOf('/login') < 0) { showLogin(); throw new Error('로그인이 필요합니다'); }
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.message || ('오류 ' + r.status)); return j; });
    });
  }
  function q(p) { return p + (p.indexOf('?') < 0 ? '?' : '&') + 'muni=' + encodeURIComponent(S.muni); }

  /* ---------- 로그인 ---------- */
  function showLogin() { $('#login').hidden = false; $('#app').hidden = true; $('#who').hidden = true; }
  $('#loginf').addEventListener('submit', function (e) {
    e.preventDefault();
    var f = e.target;
    api('/api/admin/login', { body: { id: f.id.value, pw: f.pw.value } }).then(function () { f.pw.value = ''; boot(); })
      .catch(function (err) { var p = $('#loginerr'); p.textContent = err.message; p.hidden = false; });
  });
  $('#logout').addEventListener('click', function () { api('/api/admin/logout', { body: {} }).then(showLogin); });

  function boot() {
    api('/api/admin/me').then(function (u) {
      $('#uname').textContent = u.name + ' 님'; $('#login').hidden = true; $('#app').hidden = false; $('#who').hidden = false;
      return refreshOverview();
    }).then(function () { go(S.tab); }).catch(function () { showLogin(); });
  }
  function refreshOverview() {
    return api(q('/api/admin/overview')).then(function (o) {
      S.overview = o;
      var sel = $('#muni');
      sel.innerHTML = o.municipalities.map(function (m) { return '<option value="' + esc(m.code) + '">' + esc(m.name) + '</option>'; }).join('');
      sel.value = S.muni;
      var st = o.stats;
      $('#kpis').innerHTML = [
        ['검토 대기', o.open_reviews], ['조례 행', st.rows], ['확정표 행', st.confirmed], ['지역 보정 k', st.k],
        ['전국 통계', (o.nat_updated || '-')], ['공개 정책', o.policy === 'hold' ? '확정 전 대기' : '바로 보여주기'],
        ['쇼핑몰 연동', o.shopping.filter(function (p) { return p.available; }).map(function (p) { return p.name; }).join(', ') || '없음(대체 후보)'],
        ['저장소 동기화', o.sync.enabled ? (o.sync.error ? '오류' : '사용') : '로컬']
      ].map(function (k) { return '<div class="kpi"><b>' + esc(k[1]) + '</b><span>' + esc(k[0]) + '</span></div>'; }).join('');
      $('#b-review').textContent = o.open_reviews || '';
      $('#b-syn').textContent = o.new_expressions || '';
    });
  }
  $('#muni').addEventListener('change', function (e) { S.muni = e.target.value; refreshOverview().then(function () { go(S.tab); }); });
  $('#tabs').addEventListener('click', function (e) { var b = e.target.closest('[data-tab]'); if (b) go(b.dataset.tab); });
  function go(tab) {
    S.tab = tab;
    $$('#tabs [data-tab]').forEach(function (b) { b.setAttribute('aria-selected', b.dataset.tab === tab ? 'true' : 'false'); });
    $('#view').onclick = null;
    $('#view').innerHTML = '<p class="muted">불러오는 중…</p>';
    ({ review: vReview, confirmed: vConfirmed, ordinance: vOrdinance, synonyms: vSynonyms, national: vNational, history: vHistory, settings: vSettings })[tab]();
  }

  /* ---------- 검토 대기열 ---------- */
  function vReview() {
    api(q('/api/admin/review?status=' + S.status)).then(function (j) {
      var h = '<div class="bar"><b class="grow">검토 대기열</b><label class="muted">상태 <select id="rvst">' +
        [['open', '대기'], ['confirmed', '확정'], ['rejected', '반려']].map(function (o) { return '<option value="' + o[0] + '"' + (S.status === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('') +
        '</select></label></div>';
      if (!j.items.length) h += '<p class="muted">항목이 없습니다.</p>';
      h += j.items.map(rvHTML).join('');
      $('#view').innerHTML = h;
      $('#rvst').addEventListener('change', function (e) { S.status = e.target.value; vReview(); });
      $$('.rv').forEach(function (el) { wireRv(el, j.items.filter(function (x) { return String(x.id) === el.dataset.id; })[0]); });
    }).catch(err);
  }
  function rvHTML(r) {
    var d = r.detail || {};
    var rows = (r.status === 'open' ? r.proposal : r.result) || [];
    if (!rows.length) rows = [{ spec: '모든규격', fee: '' }];
    var grade = d['등급'] || '';
    var kv = [['등급', grade], ['신뢰도', d['신뢰도']], ['엔진 금액', d['수수료'] ? fmt(d['수수료']) + '원' : ''], ['경로', d['경로']], ['유사품목', d['유사']],
      ['유사구간', (d['유사구간'] || []).map(fmt).join(' / ')], ['통계추정', d['통계추정'] && d['통계추정'] !== '-' ? fmt(d['통계추정']) : d['통계추정']],
      ['전국', d['전국']], ['구간', d['구간'] ? JSON.stringify(d['구간']) : ''], ['조치', d['조치']],
      ['확정표', d['확정'] ? JSON.stringify(d['확정']) : '']].filter(function (x) { return x[1] !== undefined && x[1] !== null && x[1] !== ''; });
    var editable = r.status === 'open';
    return '<article class="rv" data-id="' + r.id + '">' +
      '<h3>' + esc(r.query) + (r.label && r.label !== r.query ? ' <span class="muted">→ ' + esc(r.label) + '</span>' : '') +
      ' <span class="tag' + (/L2\*|L3|L4|L\?/.test(grade) ? ' warn' : '') + '">' + esc(grade || '확인') + '</span>' +
      ' <span class="muted">문의 ' + r.asks + '회 · ' + when(r.updated_at) + '</span></h3>' +
      '<div class="grid"><div><dl class="kv">' + kv.map(function (x) { return '<dt>' + esc(x[0]) + '</dt><dd>' + esc(x[1]) + '</dd>'; }).join('') + '</dl>' +
      (r.dims ? '<p class="muted">치수: ' + esc(Object.keys(r.dims).map(function (k) { return ({ width: '가로', depth: '세로', height: '높이' })[k] + ' ' + r.dims[k] + 'cm'; }).join(', ')) + '</p>' : '') +
      (r.memo ? '<p class="muted">메모: ' + esc(r.memo) + '</p>' : '') +
      (r.has_photo ? '<div class="photo"><img src="/api/admin/review/' + r.id + '/photo" alt="문의 사진" loading="lazy"></div>' : '') +
      '</div><div>' +
      '<div class="form-inline"><label>품목명(확정표에 들어갈 이름)<input data-f="item" value="' + esc(r.query) + '"' + (editable ? '' : ' disabled') + '></label>' +
      '<label>분류<select data-f="cat"' + (editable ? '' : ' disabled') + '>' + CATS.map(function (c) { return '<option' + (c === r.category ? ' selected' : '') + '>' + c + '</option>'; }).join('') + '</select></label></div>' +
      '<table class="tbl" style="margin-top:8px"><thead><tr><th>규격</th><th class="num">수수료(원) 또는 배출 방법</th>' + (editable ? '<th></th>' : '') + '</tr></thead><tbody>' +
      rows.map(function (x) { return rowEdit(x, editable); }).join('') + '</tbody></table>' +
      (editable ? '<div class="acts"><button class="btn small" data-act="addrow">+ 규격 줄</button>' +
        '<button class="btn primary small" data-act="confirm">확정</button>' +
        '<button class="btn small" data-act="edit">금액 수정 후 확정</button>' +
        '<button class="btn small danger" data-act="reject">반려</button></div>'
        : '<p class="muted">' + esc(r.resolved_by || '') + ' · ' + when(r.resolved_at) + '</p>') +
      '</div></div></article>';
  }
  function rowEdit(x, editable) {
    var spec = x.spec || x['규격'] || '모든규격';
    var fee = x.method || x.fee || x['수수료'] || '';
    if (!editable) return '<tr><td>' + esc(spec) + '</td><td class="num">' + esc(typeof fee === 'number' ? fmt(fee) : fee) + '</td></tr>';
    return '<tr><td><input data-c="spec" value="' + esc(spec) + '"></td><td><input data-c="fee" list="methods" value="' + esc(fee) + '"></td>' +
      '<td><button class="btn small" data-act="delrow" aria-label="줄 삭제">−</button></td></tr>';
  }
  function wireRv(el, r) {
    el.addEventListener('click', function (e) {
      var b = e.target.closest('[data-act]'); if (!b) return;
      var a = b.dataset.act;
      if (a === 'addrow') { $('tbody', el).insertAdjacentHTML('beforeend', rowEdit({ spec: '', fee: '' }, true)); return; }
      if (a === 'delrow') { b.closest('tr').remove(); return; }
      var body = { action: a === 'reject' ? 'reject' : a };
      if (a === 'reject') { if (!confirm('“' + r.query + '” 문의를 반려할까요? 고객에게는 담당 부서 문의 안내가 나갑니다.')) return; }
      else {
        body.item = $('[data-f=item]', el).value.trim(); body.category = $('[data-f=cat]', el).value;
        body.rows = $$('tbody tr', el).map(function (tr) {
          var fee = $('[data-c=fee]', tr).value.trim();
          return METHODS.indexOf(fee) >= 0 ? { spec: $('[data-c=spec]', tr).value.trim(), method: fee } : { spec: $('[data-c=spec]', tr).value.trim(), fee: fee };
        }).filter(function (x) { return x.spec || x.fee || x.method; });
      }
      api('/api/admin/review/' + r.id, { body: body }).then(function () {
        toast(a === 'reject' ? '반려했습니다' : '확정했습니다. 같은 품목은 이제 확정 금액으로 안내됩니다');
        refreshOverview(); vReview();
      }).catch(err);
    });
  }

  /* ---------- 확정표 ---------- */
  function vConfirmed() {
    api(q('/api/admin/confirmed')).then(function (j) {
      var h = '<div class="bar"><b>확정표</b><span class="muted">' + j.items.length + '행</span><span class="grow"></span>' +
        '<input id="cf" placeholder="품목 찾기" style="max-width:200px">' +
        '<a class="btn small" href="' + q('/api/admin/confirmed/export.xlsx') + '">엑셀 내보내기</a></div>' +
        '<details class="report"><summary><b>엑셀·CSV 가져오기</b> <span class="muted">(3행 머리행 분류|품목|규격|수수료(원), 4행부터 데이터)</span></summary>' +
        '<form id="imp" class="form-inline" style="margin-top:8px"><input type="file" name="file" accept=".xlsx,.csv" required>' +
        '<label>방식<select name="mode"><option value="merge">추가·수정만</option><option value="replace">전체 바꾸기</option></select></label>' +
        '<button class="btn small" type="submit">미리 보기</button></form><div id="impr"></div></details>' +
        '<form id="addf" class="form-inline report"><b style="width:100%">새 확정 금액</b>' +
        '<label>품목<input name="item" required placeholder="예: 킥보드(어린이용)"></label><label>규격<input name="spec" value="모든규격"></label>' +
        '<label>수수료(원) 또는 배출 방법<input name="fee" list="methods" required></label>' +
        '<label>분류<select name="category"><option value="">자동</option>' + CATS.map(function (c) { return '<option>' + c + '</option>'; }).join('') + '</select></label>' +
        '<button class="btn primary small" type="submit">추가</button></form>' +
        '<div class="scroll"><table class="tbl"><thead><tr><th>분류</th><th>품목</th><th>규격</th><th class="num">수수료</th><th>수정</th><th></th></tr></thead><tbody id="ctb">' +
        j.items.map(function (r) {
          return '<tr data-id="' + r.id + '" data-s="' + esc((r.item + ' ' + r.spec).toLowerCase()) + '"><td><select data-c="category">' + CATS.map(function (c) { return '<option' + (c === r.category ? ' selected' : '') + '>' + c + '</option>'; }).join('') + '</select></td>' +
            '<td><input data-c="item" value="' + esc(r.item) + '"></td><td><input data-c="spec" value="' + esc(r.spec) + '"></td>' +
            '<td><input data-c="fee" list="methods" value="' + esc(r.method || r.fee) + '" style="text-align:right"></td>' +
            '<td class="muted" style="white-space:nowrap">' + esc(r.updated_by || '') + '<br>' + when(r.updated_at) + '</td>' +
            '<td style="white-space:nowrap"><button class="btn small" data-act="save">저장</button> <button class="btn small danger" data-act="del">삭제</button></td></tr>';
        }).join('') + '</tbody></table></div>' + methodsList();
      $('#view').innerHTML = h;
      $('#cf').addEventListener('input', function (e) { var v = e.target.value.trim().toLowerCase(); $$('#ctb tr').forEach(function (tr) { tr.hidden = v && tr.dataset.s.indexOf(v) < 0; }); });
      $('#ctb').addEventListener('click', function (e) {
        var b = e.target.closest('[data-act]'); if (!b) return; var tr = b.closest('tr'); var id = tr.dataset.id;
        if (b.dataset.act === 'del') {
          if (!confirm('이 행을 삭제할까요?')) return;
          return api('/api/admin/confirmed/' + id, { method: 'DELETE' }).then(function () { toast('삭제했습니다'); vConfirmed(); refreshOverview(); }).catch(err);
        }
        var fee = $('[data-c=fee]', tr).value.trim();
        var body = { item: $('[data-c=item]', tr).value, spec: $('[data-c=spec]', tr).value, category: $('[data-c=category]', tr).value };
        if (METHODS.indexOf(fee) >= 0) { body.method = fee; body.fee = null; } else { body.fee = fee; body.method = null; }
        api('/api/admin/confirmed/' + id, { method: 'PUT', body: body }).then(function () { toast('저장했습니다'); }).catch(err);
      });
      $('#addf').addEventListener('submit', function (e) {
        e.preventDefault(); var f = e.target; var fee = f.fee.value.trim();
        var body = { item: f.item.value, spec: f.spec.value, category: f.category.value };
        if (METHODS.indexOf(fee) >= 0) body.method = fee; else body.fee = fee;
        api(q('/api/admin/confirmed'), { body: body }).then(function () { toast('추가했습니다'); vConfirmed(); refreshOverview(); }).catch(err);
      });
      $('#imp').addEventListener('submit', function (e) { e.preventDefault(); doImport(e.target, '1'); });
    }).catch(err);
  }
  function methodsList() { return '<datalist id="methods">' + METHODS.map(function (m) { return '<option value="' + m + '">'; }).join('') + '</datalist>'; }
  function doImport(f, dry) {
    var fd = new FormData(f); fd.append('muni', S.muni); fd.append('dry', dry);
    api('/api/admin/confirmed/import', { form: fd }).then(function (r) {
      var bad = r.errors.length || r.duplicates.length || r.bad_spec.length;
      var h = '<div class="report"><p>읽은 행 <b>' + r.rows + '</b> · 추가 <b>' + r.add + '</b> · 변경 <b>' + r.change + '</b>' + (r.mode === 'replace' ? ' · 삭제 <b>' + r.remove + '</b>' : '') + '</p>' +
        list('오류', r.errors) + list('중복(품목+규격)', r.duplicates) + list("규격에 '이하·초과'(미만/이상으로 고쳐 주세요)", r.bad_spec) +
        list('추가 예시', r.sample_add) + list('변경 예시', r.sample_change) +
        (r.applied ? '<p class="ok">적용했습니다.</p>' : (bad ? '<p class="bad">문제를 고친 뒤 다시 올려 주세요.</p>' : '<button class="btn primary small" id="impgo">이대로 적용</button>')) + '</div>';
      $('#impr').innerHTML = h;
      var g = $('#impgo'); if (g) g.addEventListener('click', function () { doImport(f, '0'); });
      if (r.applied) { refreshOverview(); setTimeout(vConfirmed, 900); }
    }).catch(err);
  }
  function list(t, a) { return a && a.length ? '<p><b>' + esc(t) + '</b></p><ul>' + a.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul>' : ''; }

  /* ---------- 조례 ---------- */
  function vOrdinance() {
    api(q('/api/admin/ordinance')).then(function (j) {
      var st = j.stats;
      var bs = j.basis;
      var h = '<form id="pubf" class="report"><b>공공데이터에서 지자체 수수료표 가져오기</b> <span class="muted">(전국대형폐기물수거수수료정보표준데이터, 각 지자체 등록 기준일자 표시)</span>' +
        '<textarea name="targets" rows="3" style="width:100%;margin-top:6px" placeholder="예: 서울 전체, 경기 전체, 부산 사하구">' + esc(S.targets || '') + '</textarea>' +
        '<div class="form-inline"><label><input type="checkbox" name="force"> 직접 올린 조례도 덮어쓰기</label>' +
        '<button class="btn small" type="submit" data-dry="1">미리 보기</button><button class="btn primary small" type="button" id="pubgo">가져오기</button></div><div id="pubr"></div></form>' +
        '<div class="grid2"><div class="report"><b>현재 조례</b>' + (bs ? ' <span class="muted">출처: ' + esc(bs.source) + ' · 기준일자 ' + esc(bs.date || '-') + ' · ' + esc(bs.institution) + '</span>' : '') +
        '<dl class="kv" style="margin-top:6px"><dt>행 수</dt><dd>' + st.rows + '</dd>' +
        '<dt>금액 격자</dt><dd><div class="chipsline">' + st.grid.map(function (g) { return '<span>' + fmt(g) + '</span>'; }).join('') + '</div></dd>' +
        '<dt>2회 이상 금액</dt><dd><div class="chipsline">' + st.grid2.map(function (g) { return '<span>' + fmt(g) + '</span>'; }).join('') + '</div></dd>' +
        '<dt>보정계수 k</dt><dd>' + st.k + ' (보정쌍 ' + st.k_pairs + ', MAD ' + st.mad + ')</dd></dl>' +
        '<p><a class="btn small" href="' + q('/api/admin/ordinance/export.csv') + '">CSV 내보내기</a></p></div>' +
        '<form id="ordf" class="report"><b>조례 가격표 올리기</b><p class="muted">CSV 또는 엑셀, 머리행 <code>품목,규격,수수료</code> (선택: 표시품목,표시규격). 묶음 품목은 하위품목으로 풀어 주세요.</p>' +
        '<div class="form-inline"><label>지자체 코드<input name="muni" value="' + esc(S.muni) + '" required pattern="[a-z0-9_-]+"></label>' +
        '<label>지자체 이름(새로 추가할 때)<input name="name" placeholder="예: 의왕시"></label>' +
        '<input type="file" name="file" accept=".csv,.xlsx" required><button class="btn small" type="submit">미리 보기</button></div><div id="ordr"></div></form></div>' +
        '<div class="scroll" style="margin-top:12px"><table class="tbl"><thead><tr><th>품목</th><th>규격(원문)</th><th>화면 표시</th><th class="num">수수료</th></tr></thead><tbody>' +
        j.items.map(function (r) {
          return '<tr><td>' + esc(r.item) + '</td><td>' + esc(r.spec) + '</td><td class="muted">' + esc([r.disp_item, r.disp_spec].filter(Boolean).join(' / ')) + '</td><td class="num">' + fmt(r.fee) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
      $('#view').innerHTML = h;
      $('#ordf').addEventListener('submit', function (e) { e.preventDefault(); ordUpload(e.target, '1'); });
      var pub = function (dry) {
        var f = $('#pubf'); S.targets = f.targets.value;
        $('#pubr').innerHTML = '<p class="muted">공공데이터포털에서 받는 중… (1분 안팎)</p>';
        api('/api/admin/import-public', { body: { targets: f.targets.value, force: f.force.checked, dry: dry } }).then(function (r) {
          $('#pubr').innerHTML = '<div class="report"><p>' + (dry ? '미리 보기' : '<span class="ok">가져왔습니다</span>') + ' — ' + r.imported.length + '곳 · 규격 칸 ' + esc(r.spec_column || '없음') + ' · 기준일자 칸 ' + esc(r.date_column || '없음') + '</p>' +
            list('가져올 지자체', r.imported.map(function (i) { return i.name + ' (' + i.rows + '행' + (i.free ? ', 무상 ' + i.free : '') + ', 기준 ' + (i.date || '-') + ')'; })) +
            list('건너뜀', r.skipped.map(function (i) { return i.name + ': ' + i.reason; })) + list('공공데이터에 없음', r.missing) + '</div>';
          if (!dry) refreshOverview();
        }).catch(err);
      };
      $('#pubf').addEventListener('submit', function (e) { e.preventDefault(); pub(true); });
      $('#pubgo').addEventListener('click', function () { if (confirm('가져올까요? 공공데이터로 들어온 지자체 조례는 최신 값으로 바뀝니다.')) pub(false); });
    }).catch(err);
  }
  function ordUpload(f, dry) {
    var fd = new FormData(f); fd.append('dry', dry);
    api('/api/admin/ordinance', { form: fd }).then(function (r) {
      var h = '<div class="report"><p>' + (r.new_municipality ? '<b class="ok">새 지자체</b> · ' : '') + '데이터 줄 <b>' + r.data_lines + '</b> · 금액 칸 <b>' + r.fee_cells + '</b> · 읽은 행 <b>' + r.rows + '</b> ' +
        (r.match ? '<span class="ok">일치</span>' : '<span class="bad">불일치 — 버린 줄을 확인하세요</span>') + '</p>' +
        '<p>금액 격자: ' + r.grid.map(fmt).join(' · ') + '<br>보정계수 k = <b>' + r.k + '</b> (보정쌍 ' + r.k_pairs + ', MAD ' + r.mad + ')</p>' +
        list('버린 줄', r.dropped.map(function (d) { return d.line + '행: ' + JSON.stringify(d.row); })) +
        list('추가', r.added) + list('삭제', r.removed) + list('금액 변경', r.changed) +
        (r.applied ? '<p class="ok">적용했습니다.</p>' : '<button type="button" class="btn primary small" id="ordgo">이대로 적용</button>') + '</div>';
      $('#ordr').innerHTML = h;
      var g = $('#ordgo'); if (g) g.addEventListener('click', function () { ordUpload(f, '0'); });
      if (r.applied) { S.muni = f.muni.value; refreshOverview().then(function () { setTimeout(vOrdinance, 900); }); }
    }).catch(err);
  }

  /* ---------- 표현 사전 ---------- */
  function vSynonyms() {
    api(q('/api/admin/synonyms')).then(function (j) {
      var h = '<p class="muted">확인 질문으로 밝혀진 “고객 표현 → 일반 명칭” 기록입니다. 한 품목으로만 정해지는 표현은 SYN(바로 그 품목으로 안내)으로, 여러 품목에 걸치면 AMBIG(항상 확인 질문)로 등록하세요.</p>' +
        '<div class="scroll"><table class="tbl"><thead><tr><th>고객 표현</th><th>일반 명칭</th><th class="num">횟수</th><th>상태</th><th></th></tr></thead><tbody>' +
        (j.log.length ? '' : '<tr><td colspan="5" class="muted">아직 기록이 없습니다.</td></tr>') +
        j.log.map(function (r) {
          return '<tr data-id="' + r.id + '"><td>' + esc(r.expr) + '</td><td>' + esc(r.generals.join(' / ')) + (r.single ? '' : ' <span class="tag warn">여러 품목</span>') + '</td><td class="num">' + r.count + '</td>' +
            '<td>' + ({ new: '새 기록', approved: '등록됨', rejected: '보류' })[r.status] + '</td><td style="white-space:nowrap">' +
            (r.status === 'new' ? (r.single ? '<button class="btn small" data-act="syn" data-expr="' + esc(r.expr) + '" data-target="' + esc(r.query || r.general) + '">SYN 등록</button> ' : '') +
              '<button class="btn small" data-act="ambig" data-expr="' + esc(r.expr) + '">AMBIG</button> <button class="btn small danger" data-act="rej">보류</button>' : '') + '</td></tr>';
        }).join('') + '</tbody></table></div>' +
        '<form id="synf" class="form-inline report"><b style="width:100%">직접 등록</b><label>종류<select name="kind"><option value="SYN">SYN — 표현을 품목으로 바꿈</option><option value="AMBIG">AMBIG — 들어 있으면 확인 질문</option><option value="VAGUE">VAGUE — 이 말만 오면 확인 질문</option><option value="HINT">HINT — 확인 후보 목록</option></select></label>' +
        '<label>표현<input name="expr" required placeholder="예: 스탠바이미"></label><label>대상 품목(SYN·HINT)<input name="target" placeholder="예: 이동식티비 / HINT는 후보를 쉼표로"></label><button class="btn primary small">등록</button></form>' +
        '<h3>등록된 사전</h3><div class="scroll"><table class="tbl"><thead><tr><th>종류</th><th>표현</th><th>대상</th><th>등록</th><th></th></tr></thead><tbody>' +
        j.dictionary.map(function (r) { return '<tr><td>' + r.kind + '</td><td>' + esc(r.expr) + '</td><td>' + esc(r.target) + '</td><td class="muted">' + esc(r.by) + ' ' + when(r.at) + '</td><td><button class="btn small danger" data-del="' + r.id + '">삭제</button></td></tr>'; }).join('') +
        (j.dictionary.length ? '' : '<tr><td colspan="5" class="muted">없음</td></tr>') + '</tbody></table></div>' +
        '<details class="report"><summary>엔진 기본 사전 보기</summary><p><b>SYN</b></p><div class="chipsline">' + j.builtin.SYN.map(function (x) { return '<span>' + esc(x) + '</span>'; }).join('') + '</div>' +
        '<p><b>AMBIG</b></p><div class="chipsline">' + j.builtin.AMBIG.map(function (x) { return '<span>' + esc(x) + '</span>'; }).join('') + '</div>' +
        '<p><b>VAGUE</b></p><div class="chipsline">' + j.builtin.VAGUE.map(function (x) { return '<span>' + esc(x) + '</span>'; }).join('') + '</div></details>';
      $('#view').innerHTML = h;
      $('#view').onclick = function (e) {
        var b = e.target.closest('[data-act],[data-del]'); if (!b) return;
        if (b.dataset.del) return api('/api/admin/synonyms/' + b.dataset.del, { method: 'DELETE' }).then(function () { toast('삭제했습니다'); vSynonyms(); }).catch(err);
        var id = b.closest('tr').dataset.id;
        if (b.dataset.act === 'rej') return api('/api/admin/synonyms/log/' + id, { body: { action: 'reject' } }).then(function () { vSynonyms(); refreshOverview(); }).catch(err);
        var body = b.dataset.act === 'syn' ? { kind: 'SYN', expr: b.dataset.expr, target: b.dataset.target, log_id: +id } : { kind: 'AMBIG', expr: b.dataset.expr, log_id: +id };
        if (!confirm(body.kind + ' 로 등록할까요?\n' + body.expr + (body.target ? ' → ' + body.target : ''))) return;
        api('/api/admin/synonyms', { body: body }).then(function () { toast('등록했습니다'); vSynonyms(); refreshOverview(); }).catch(err);
      };
      $('#synf').addEventListener('submit', function (e) {
        e.preventDefault(); var f = e.target;
        api('/api/admin/synonyms', { body: { kind: f.kind.value, expr: f.expr.value, target: f.target.value } }).then(function () { toast('등록했습니다'); vSynonyms(); }).catch(err);
      });
    }).catch(err);
  }

  /* ---------- 전국 통계 ---------- */
  function vNational() {
    api('/api/admin/national').then(function (j) {
      var h = '<div class="grid2"><div class="report"><b>전국 대형폐기물 수수료 통계</b><dl class="kv" style="margin-top:6px"><dt>마지막 갱신</dt><dd>' + esc(j.updated) + '</dd><dt>출처</dt><dd>' + esc(j.source) + '</dd><dt>품목 수</dt><dd>' + j.items + '</dd></dl>' +
        '<p><button class="btn primary small" id="natgo">지금 갱신(공공데이터포털)</button></p><p class="muted">분기마다 자동 갱신(1·4·7·10월 1일). 실패하면 아래에서 파일로 올릴 수 있습니다.</p></div>' +
        '<form id="natf" class="report"><b>파일로 갱신</b><p class="muted">공공데이터포털 원본 JSON(<code>{"rows":[…]}</code>) 또는 요약 TSV(품목·기관수·중앙값·p25·p75)</p><div class="form-inline"><input type="file" name="file" required accept=".json,.tsv,.txt"><button class="btn small">올리기</button></div></form></div>' +
        '<div class="scroll" style="margin-top:12px"><table class="tbl"><thead><tr><th>품목(정규화)</th><th class="num">기관 수</th><th class="num">중앙값</th><th class="num">p25</th><th class="num">p75</th></tr></thead><tbody>' +
        j.top.map(function (r) { return '<tr><td>' + esc(r['품목']) + '</td><td class="num">' + r['기관수'] + '</td><td class="num">' + fmt(r['중앙값']) + '</td><td class="num">' + fmt(r.p25) + '</td><td class="num">' + fmt(r.p75) + '</td></tr>'; }).join('') + '</tbody></table></div>';
      $('#view').innerHTML = h;
      $('#natgo').addEventListener('click', function (e) {
        var b = e.target; b.disabled = true; b.textContent = '받는 중…';
        api('/api/admin/national/refresh', { body: {} }).then(function (r) { toast('갱신했습니다: ' + r.items + '품목'); refreshOverview(); vNational(); })
          .catch(function (x) { err(x); b.disabled = false; b.textContent = '지금 갱신(공공데이터포털)'; });
      });
      $('#natf').addEventListener('submit', function (e) {
        e.preventDefault(); var fd = new FormData(e.target);
        api('/api/admin/national/upload', { form: fd }).then(function (r) { toast('갱신했습니다: ' + r.items + '품목'); refreshOverview(); vNational(); }).catch(err);
      });
    }).catch(err);
  }

  /* ---------- 이력 ---------- */
  function vHistory() {
    api('/api/admin/history').then(function (j) {
      $('#view').innerHTML = '<div class="scroll"><table class="tbl"><thead><tr><th>언제</th><th>누가</th><th>무엇을</th><th>대상</th><th>이전 값</th><th>바뀐 값</th></tr></thead><tbody>' +
        j.items.map(function (r) {
          return '<tr><td style="white-space:nowrap">' + when(r.at) + '</td><td>' + esc(r.user) + '</td><td>' + esc(r.action) + '</td><td>' + esc(r.target) + '</td>' +
            '<td class="muted">' + esc(r.before ? JSON.stringify(r.before) : '') + '</td><td>' + esc(r.after ? JSON.stringify(r.after) : '') + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }).catch(err);
  }

  /* ---------- 설정·시험 ---------- */
  function vSettings() {
    var o = S.overview;
    var h = '<div class="grid2"><form id="polf" class="report"><b>확정 안 된 금액의 고객 안내</b>' +
      '<p><label><input type="radio" name="p" value="hold"' + (o.policy === 'hold' ? ' checked' : '') + '> 확정 전 대기 — “확인 후 안내드리겠습니다”(기본)</label><br>' +
      '<label><input type="radio" name="p" value="show"' + (o.policy === 'show' ? ' checked' : '') + '> 바로 보여주기 — 엔진 금액을 바로 안내하고 대기열에도 넣음</label></p>' +
      '<button class="btn primary small">저장</button></form>' +
      '<form id="tryf" class="report"><b>품목 시험</b> <span class="muted">(근거 포함, 운영자만)</span><div class="form-inline" style="margin-top:6px"><input name="q" required placeholder="예: 목검"><button class="btn small">계산</button></div><div id="tryr"></div></form></div>';
    $('#view').innerHTML = h;
    $('#polf').addEventListener('submit', function (e) {
      e.preventDefault(); var v = e.target.querySelector('input[name=p]:checked').value;
      api('/api/admin/settings', { body: { muni: S.muni, policy: v } }).then(function () { toast('저장했습니다'); refreshOverview(); }).catch(err);
    });
    $('#tryf').addEventListener('submit', function (e) {
      e.preventDefault();
      api(q('/api/admin/try?q=' + encodeURIComponent(e.target.q.value))).then(function (r) {
        $('#tryr').innerHTML = '<table class="tbl" style="margin:8px 0"><thead><tr><th>품목</th><th>규격</th><th class="num">수수료</th><th>안내</th></tr></thead><tbody>' +
          r.rows.map(function (x) { return '<tr><td>' + esc(x['품목']) + '</td><td>' + esc(x['규격']) + '</td><td class="num">' + esc(x['수수료']) + '</td><td>' + esc(x['안내']) + '</td></tr>'; }).join('') +
          '</tbody></table><p>' + (r.ambiguous ? '<span class="bad">확인 질문 대상</span>' : r.review ? '<span class="bad">확정 필요(검토 대상)</span>' : '<span class="ok">바로 안내</span>') + '</p><pre class="json">' + esc(JSON.stringify(r.result, null, 2)) + '</pre>';
      }).catch(err);
    });
  }

  function err(e) { toast(e.message || String(e)); }
  boot();
})();
