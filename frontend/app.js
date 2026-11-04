/* ============================================================
   MAA-PRTS 控制台前端
   ============================================================ */
'use strict';

const S = {
  settings: {}, accounts: [], current: '', detail: null,
  maa: {}, activities: [],
  basket: [], result: null, searching: false, appInfo: null,
  paths: {}, pack: {}, setup: {}, gamedata: {}, onboarded: false,
};

const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
  const r = await fetch(path, opt);
  let j;
  try { j = await r.json(); } catch (e) { throw new Error('服务返回异常（' + r.status + '）'); }
  if (!j.ok) throw new Error(j.error || '未知错误');
  return j.data;
}

/* ------------------------------------------------------------ 提示 */
function toast(msg, type = 'ok', ms = 2600) {
  const el = document.createElement('div');
  el.className = 'toast ' + (type === 'ok' ? '' : type);
  el.innerHTML = '<span class="bar"></span><span>' + esc(msg) + '</span>';
  $('#toast-root').appendChild(el);
  setTimeout(() => {
    el.style.transition = '.25s ease';
    el.style.opacity = '0';
    el.style.transform = 'translateY(6px)';
    setTimeout(() => el.remove(), 260);
  }, ms);
}

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    toast((label || '已复制') + ' ' + text);
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); toast((label || '已复制') + ' ' + text); }
    catch (err) { toast('复制失败，请手动复制：' + text, 'err'); }
    ta.remove();
  }
}

/* ------------------------------------------------------------ 弹窗 */
function modal(html, opts = {}) {
  const mask = document.createElement('div');
  mask.className = 'modal-mask';
  mask.innerHTML = '<div class="modal">' + html + '</div>';
  $('#modal-root').appendChild(mask);
  const close = () => {
    mask.style.transition = '.14s ease';
    mask.style.opacity = '0';
    setTimeout(() => mask.remove(), 140);
  };
  mask.addEventListener('click', e => { if (e.target === mask) close(); });
  mask.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close));
  if (opts.onMount) opts.onMount(mask, close);
  return { el: mask, close };
}

/* ------------------------------------------------------------ 启动 */
function waitPywebview(ms = 2000) {
  return new Promise(resolve => {
    const t0 = Date.now();
    const tick = () => {
      if (window.pywebview && window.pywebview.api) return resolve(window.pywebview.api);
      if (Date.now() - t0 > ms) return resolve(null);
      setTimeout(tick, 60);
    };
    tick();
  });
}

async function boot() {
  try {
    const bridge = await waitPywebview();
    if (bridge) {
      document.documentElement.classList.add('native');
      try { S.appInfo = await bridge.app_info(); } catch (e) { }
    }
    const d = await api('/api/bootstrap');
    S.settings = d.settings;
    S.accounts = d.accounts;
    S.maa = d.maa;
    S.activities = d.activities || [];
    S.paths = d.paths || {};
    S.pack = d.pack || {};
    S.gamedata = d.gamedata || {};
    S.setup = d.setup || {};
    S.current = d.lastAccount || (d.accounts[0] && d.accounts[0].file) || '';
    renderAccounts();
    renderUpdate();
    renderQuick();
    renderMaaState();
    fillBasketProfiles();
    if (S.current) await selectAccount(S.current, true);
    startPing();

    // 首次使用：先让用户填 token 与 MAA 目录，再进主流程
    if (!S.accounts.length || !S.settings.maaDir) {
      openOnboarding();
      return;
    }

    // 支持 ?q=TL-10 直接搜索（做快捷方式用）
    const q0 = new URLSearchParams(location.search).get('q');
    if (q0 && S.current) {
      $('#search-input').value = q0;
      doSearch();
    }
  } catch (e) {
    toast('启动失败：' + e.message, 'err', 6000);
  }
}

function startPing() {
  const ping = () => fetch('/api/ping', { method: 'POST' }).catch(() => {});
  ping();
  setInterval(ping, 20000);
}

/* ------------------------------------------------------------ 账号 */
function renderAccounts() {
  const box = $('#account-list');
  if (!S.accounts.length) {
    box.innerHTML = '<div style="padding:14px 10px;font-size:12px;color:var(--text-3);line-height:1.8">还没有账号<br>点下面的按钮用森空岛 token 添加</div>';
    return;
  }
  box.innerHTML = S.accounts.map(a => {
    const st = a.stats || {};
    const cls = (st.sixStarCount >= 120 ? 'r6' : (st.sixStarCount >= 60 ? 'r5' : ''));
    const ch = (a.nickName || '?').replace(/[#＃].*$/, '').slice(0, 1);
    return `
      <button class="acct ${a.file === S.current ? 'active' : ''}" data-file="${esc(a.file)}">
        <span class="avatar ${cls}">${esc(ch)}</span>
        <span class="acct-main">
          <span class="acct-name">${esc(a.nickName)}</span>
          <span class="acct-sub">${esc(a.channelName || '官服')} · <b>${st.charCount || 0}</b>/${st.charTotal || 440} 干员</span>
        </span>
      </button>`;
  }).join('');
  $$('#account-list .acct').forEach(b => b.addEventListener('click', () => selectAccount(b.dataset.file)));
}

async function selectAccount(file, silent) {
  if (!file) return;
  const changed = S.current && S.current !== file;
  S.current = file;
  renderAccounts();
  if (changed && S.basket.length) {
    S.basket = [];
    renderBasket();
    toast('已切换账号，作业集重新开始', 'warn');
  }
  try {
    const d = await api('/api/account?file=' + encodeURIComponent(file));
    S.detail = d;
    renderHero();
    await api('/api/settings', { lastAccount: file });
    S.settings.lastAccount = file;
    if (!silent) {
      const r = $('#results');
      if (r.dataset.mode) doSearch();
    }
  } catch (e) {
    toast('读取账号失败：' + e.message, 'err');
  }
}

function renderHero() {
  const d = S.detail;
  if (!d) return;
  const a = d.account || {}, st = d.stats || {};
  const name = a.nickName || '未知账号';
  $('#hero-name').textContent = name;
  $('#hero-avatar').textContent = name.replace(/[#＃].*$/, '').slice(0, 1);
  const bits = [a.channelName || '', 'Lv' + (a.level || '?'), 'uid ' + (a.uid || '')];
  const sec = (a.secretary || {}).name;
  if (sec) bits.splice(2, 0, '看板 ' + sec);
  $('#hero-sub').textContent = bits.filter(Boolean).join(' · ');

  const total = st.charTotal || 440;
  const miss = st.missingCount || 0;
  const missing = d.missing || [];
  const missNames = missing.map(m => m.name).join('、');
  $('#hero-stats').innerHTML = `
    <div class="stat"><b>${st.charCount || 0}</b><span>干员 / ${total}</span></div>
    <div class="stat mint"><b>${st.e2Count || 0}</b><span>精二</span></div>
    <div class="stat"><b>${st.sixStarCount || 0}<i style="font-size:11px;color:var(--text-3);font-style:normal">/${st.sixStarTotal || 141}</i></b><span>六星</span></div>
    <button class="stat ${miss > 0 ? 'amber' : 'mint'} clickable" id="stat-missing"
            title="${miss ? '点击查看缺哪 ' + miss + ' 名干员' : '图鉴已满'}">
      <b>${miss}</b><span>缺卡</span>
    </button>
  `;
  const sm = $('#stat-missing');
  if (sm) sm.addEventListener('click', showMissing);
}

/* 缺卡清单：只列名字，按星级分组 */
function showMissing() {
  const d = S.detail || {};
  const list = d.missing || [];
  const name = (d.account || {}).nickName || '';
  if (!list.length) {
    toast('这个账号图鉴已满，没有缺卡', 'ok');
    return;
  }
  const groups = {};
  list.forEach(m => (groups[m.rarity] = groups[m.rarity] || []).push(m));
  const rarities = Object.keys(groups).map(Number).sort((a, b) => b - a);
  const body = rarities.map(r => `
    <div class="miss-group">
      <div class="miss-head"><b>${CN_RARITY[r] || r + '星'}</b>
        <span>${groups[r].length} 名</span></div>
      <div class="miss-names">${groups[r].map(m =>
        `<span class="miss-name r${r}" title="${esc(m.profession || '')}">${esc(m.name)}</span>`).join('')}</div>
    </div>`).join('');
  modal(`
    <h3>缺卡 · ${list.length} 名</h3>
    <div class="sub">${esc(name)} 的图鉴里还没有这些干员（按星级分组，共 ${list.length} 名）。</div>
    <div class="miss-wrap">${body}</div>
    <div class="modal-foot"><button class="btn-solid" data-close>知道了</button></div>
  `);
}

const CN_RARITY = { 6: '六星', 5: '五星', 4: '四星', 3: '三星', 2: '二星', 1: '一星' };

/* ------------------------------------------------------------ MAA 状态 */
function renderMaaState() {
  const el = $('#maa-state');
  const m = S.maa || {};
  const txt = $('.txt', el);
  el.classList.remove('on', 'off', 'warn');
  if (!m.exeExists) {
    el.classList.add('warn');
    txt.textContent = 'MAA 路径无效';
  } else if (m.running) {
    el.classList.add('on');
    txt.textContent = 'MAA 运行中 · ' + (m.current || m.profile || '');
  } else {
    el.classList.add('off');
    txt.textContent = 'MAA 未运行 · ' + (m.profile || '');
  }
  el.title = (m.maaDir || '') + '\n点击刷新状态';
}

async function refreshMaaStatus() {
  try {
    S.maa = await api('/api/maa/status');
    renderMaaState();
    fillBasketProfiles();
  } catch (e) { /* 静默 */ }
}

/* ------------------------------------------------------------ 资源版本 */
const GD_CN = { chars: '干员', stages: '关卡', equips: '模组', skills: '技能', zones: '区域' };

function gdDeltaText(delta) {
  return Object.keys(delta || {})
    .filter(k => GD_CN[k] && delta[k])
    .map(k => (delta[k] > 0 ? '+' : '') + delta[k] + ' ' + GD_CN[k])
    .join(' · ');
}

function newActIds() {
  const p = (S.gamedata || {}).pending;
  return ((p && p.newActs) || []).map(a => a.id);
}

/* 资源包更新提示条：换上新资源后第一次打开就会出现，点「知道了」才消失 */
function renderUpdate() {
  const bar = $('#update-bar');
  if (!bar) return;
  const g = S.gamedata || {};
  const p = g.pending;
  if (!p) { bar.hidden = true; bar.innerHTML = ''; return; }

  const all = p.newActs || [];
  const head = all.slice(0, 4);
  const acts = head
    .map(a => esc(a.name) + (a.prefix ? `<i>${esc(a.prefix)}</i>` : '')).join('、')
    + (all.length > 4 ? ` 等 ${all.length} 个活动` : '');
  const plain = head.map(a => a.name + (a.prefix ? ' ' + a.prefix : '')).join('、')
    + (all.length > 4 ? ` 等 ${all.length} 个活动` : '');
  const delta = gdDeltaText(p.delta);
  const tip = [delta, plain ? '新活动 ' + plain : ''].filter(Boolean).join(' · ');
  bar.hidden = false;
  bar.innerHTML = `
    <span class="ub-ico">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M12 3v12"/><path d="m7.5 8.5 4.5-4.5 4.5 4.5"/><path d="M4 15v3.5A2.5 2.5 0 0 0 6.5 21h11A2.5 2.5 0 0 0 20 18.5V15"/>
      </svg>
    </span>
    <div class="ub-main">
      <b>游戏资源已更新到 ${esc(p.to)}${p.from ? `（原 ${esc(p.from)}）` : ''}</b>
      <span title="${esc(tip)}">${delta ? esc(delta) + ' · ' : ''}${acts ? '新活动 ' + acts : '关卡与干员数据已刷新'}</span>
    </div>
    <button class="ub-btn" id="ub-ack">知道了</button>`;
  const btn = $('#ub-ack', bar);
  if (btn) btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      S.gamedata = await api('/api/gamedata/ack', {});
      renderUpdate();
      renderQuick();
    } catch (e) {
      btn.disabled = false;
      toast('操作失败：' + e.message, 'err');
    }
  });
}

/* ------------------------------------------------------------ 快捷入口 */
function renderQuick() {
  const row = $('#quick-row');
  const news = newActIds();
  const acts = (S.activities || []).slice().sort((a, b) => {
    const na = news.indexOf(a.id) >= 0 ? 1 : 0;
    const nb = news.indexOf(b.id) >= 0 ? 1 : 0;
    if (na !== nb) return nb - na;            // 新活动永远排最前
    return (b.num || 0) - (a.num || 0);       // 其余按新→旧
  });

  let html = '<span class="quick-label">快捷</span>';
  acts.slice(0, 12).forEach(a => {
    const isNew = news.indexOf(a.id) >= 0;
    html += `<button class="chip${isNew ? ' is-new' : ''}" data-q="${esc(a.id)}"
      title="${esc(a.name)}${a.prefix ? ' · ' + esc(a.prefix) : ''}（${a.count} 关）">
      <span class="chip-name">${esc(a.name || a.id)}</span>
      ${a.prefix ? `<em class="chip-code">${esc(a.prefix)}</em>` : ''}
      ${isNew ? '<i class="chip-new">NEW</i>' : ''}
    </button>`;
  });
  row.innerHTML = html;
  $$('#quick-row .chip').forEach(c => c.addEventListener('click', () => {
    $('#search-input').value = c.dataset.q;
    doSearch();
  }));
}

/* ------------------------------------------------------------ 搜索 */
async function doSearch() {
  const q = $('#search-input').value.trim();
  if (!q) { toast('先输入关卡或活动', 'warn'); return; }
  if (!S.current) { toast('先选一个账号', 'warn'); openAddAccount(); return; }
  if (S.searching) return;
  S.searching = true;
  const box = $('#results');
  box.dataset.mode = 'loading';
  box.innerHTML = `<div class="result-head"><div class="result-title">正在检索「${esc(q)}」…<span>比对干员与练度中</span></div></div>
    <div class="loading-row"><span class="spinner"></span>正在从作业站拉取作业，活动关卡多时可能要十几秒</div>
    <div class="ops-grid">${'<div class="skeleton"></div>'.repeat(6)}</div>`;
  try {
    const d = await api('/api/search', { file: S.current, q, pages: 2, limit: 10 });
    S.result = d;
    box.dataset.mode = d.mode;
    renderResult(d);
    box.scrollTop = 0;
  } catch (e) {
    box.dataset.mode = '';
    box.innerHTML = `<div class="empty-state"><h3>没搜到</h3><p>${esc(e.message)}</p></div>`;
    toast(e.message, 'err', 4000);
  } finally {
    S.searching = false;
  }
}

function stars(n) {
  n = Math.max(0, Math.min(10, n || 0));
  if (!n) return '<span class="no-rate">暂无评分</span>';
  const five = Math.round(n / 2);
  return `<b class="score">${n}</b>` + '★'.repeat(five) +
    '<span style="opacity:.18">' + '★'.repeat(5 - five) + '</span>';
}

const MODE_CN = { ready: '可直接抄', borrow: '差一人可借', train: '需补练度', blocked: '打不了' };

function opChips(op, max = 8) {
  const list = (op.opers || []).slice();
  const chips = list.slice(0, max).map(o => {
    let cls = 'own';
    if (!o.owned) cls = 'lack';
    else if (!o.ok) cls = 'train';
    return `<span class="op-chip ${cls}" title="${esc(chipTitle(o))}">${esc(o.name)}</span>`;
  });
  if (list.length > max) chips.push(`<span class="op-chip more">+${list.length - max}</span>`);
  return chips.join('');
}

function chipTitle(o) {
  if (o.group) return '组合：满足任一即可';
  if (!o.owned) return '未拥有';
  const e = ['精零', '精一', '精二'][o.elite] || '';
  const m = (o.mastery || []).map((x, i) => x ? `专${'一二三'[i] || ''}${x}` : '').filter(Boolean).join(' ');
  return `${e} ${o.level} 级${m ? ' · ' + m : ''}`;
}

function opCard(op, opts = {}) {
  const mode = op.mode || 'blocked';
  return `
    <div class="op-card ${opts.best ? 'best' : ''}" data-op="${op.id}" data-mode="${mode}">
      <div class="op-top">
        <span class="stars">${stars(op.rating)}</span>
        <span class="op-id">#${op.id}</span>
      </div>
      <div class="op-title" title="${esc(op.title)}">${esc(op.title)}</div>
      <div class="badges">
        <span class="badge ${mode}">${MODE_CN[mode]}</span>
        <span class="badge plain">${op.total} 人</span>
        ${op.missing && op.missing.length ? `<span class="badge blocked">缺 ${esc(op.missing.join('、'))}</span>` : ''}
        ${op.training && op.training.length ? `<span class="badge train">练度不足 ${esc(op.training.slice(0, 2).join('、'))}</span>` : ''}
      </div>
      <div class="opers">${opChips(op)}</div>
      <div class="op-foot">
        <div class="op-meta">${op.views ? '浏览 ' + op.views : ''}</div>
        <div class="op-btns">
          <button class="mini-btn" data-act="detail">详情</button>
          <button class="mini-btn" data-act="copy">复制代码</button>
          <button class="mini-btn accent" data-act="add" ${opts.inBasket ? 'disabled' : ''}>${opts.inBasket ? '已在作业集' : '加入'}</button>
        </div>
      </div>
    </div>`;
}

function bindOpCards(root, ops) {
  $$('.op-card', root).forEach(card => {
    const id = Number(card.dataset.op);
    const op = ops.find(o => Number(o.id) === id);
    if (!op) return;
    card.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-act]');
      if (!btn) { showOpDetail(op); return; }
      const act = btn.dataset.act;
      if (act === 'copy') copyText(op.maaCode, 'MAA 代码已复制');
      else if (act === 'add') { addToBasket(op); btn.disabled = true; btn.textContent = '已在作业集'; }
      else if (act === 'detail') showOpDetail(op);
    });
  });
}

function renderResult(d) {
  const box = $('#results');
  if (!d.stages || !d.stages.length) {
    box.innerHTML = '<div class="empty-state"><h3>没有结果</h3><p>换个关卡代号试试，例如 TL-10 或 act55side</p></div>';
    return;
  }

  if (d.mode === 'stage' || d.stages.length === 1) {
    const s = d.stages[0];
    const ops = s.ops || [];
    const head = `
      <div class="result-head">
        <div class="result-title">${esc(s.stage.code)} ${esc(s.stage.name)}
          <span>${s.total} 份作业 · 可直接抄 ${s.counts.ready} · 差一人 ${s.counts.borrow} · 需练度 ${s.counts.train}</span>
        </div>
        <div class="result-actions">
          ${s.best ? `<button class="ghost-btn mint" id="add-best">加入推荐作业</button>` : ''}
        </div>
      </div>`;
    if (!ops.length) {
      box.innerHTML = head + '<div class="empty-state"><h3>这个关卡还没有作业</h3><p>作业站上暂时没人上传，换个关卡吧</p></div>';
      return;
    }
    box.innerHTML = head + '<div class="ops-grid">' +
      ops.map((op, i) => opCard(op, {
        best: i === 0 && op.mode !== 'blocked' && op.mode !== 'train',
        inBasket: inBasket(op.id),
      })).join('') + '</div>';
    bindOpCards(box, ops);
    const ab = $('#add-best');
    if (ab && s.best) ab.addEventListener('click', () => addToBasket(s.best));
    return;
  }

  // 活动视图
  const totalOps = d.stages.reduce((n, s) => n + (s.total || 0), 0);
  const readyStages = d.stages.filter(s => s.best && s.best.mode === 'ready').length;
  const head = `
    <div class="result-head">
      <div class="result-title">${esc(d.title)}
        <span>${d.stages.length} 关 · ${totalOps} 份作业 · ${readyStages} 关可直接抄</span>
      </div>
      <div class="result-actions">
        <button class="ghost-btn mint" id="add-all-best">全部加入（每关最佳）</button>
      </div>
    </div>`;
  const rows = d.stages.map(s => {
    const b = s.best;
    const st = s.stage;
    const cls = b ? b.mode : 'blocked';
    const has = (s.ops || []).length;
    return `
      <div class="stage-row" data-stage="${esc(st.stageId)}">
        <div class="stage-main">
          <div class="stage-code">${esc(st.code)}<small>${esc(st.name || '')}</small></div>
          <div class="stage-mid">
            <div class="stage-best">${b ? esc(b.title) : '（暂无可用作业）'}</div>
            <div class="stage-sub">
              ${b ? `<span class="stars">${stars(b.rating)}</span><span>${b.total} 人</span>` : ''}
              <span>共 ${s.total} 份</span>
              ${s.counts.ready ? `<span style="color:var(--mint)">可抄 ${s.counts.ready}</span>` : ''}
              ${s.counts.borrow ? `<span style="color:var(--indigo)">借人 ${s.counts.borrow}</span>` : ''}
              ${s.counts.train ? `<span style="color:var(--amber)">需练度 ${s.counts.train}</span>` : ''}
            </div>
          </div>
          <div class="stage-right">
            <span class="badge ${cls}">${MODE_CN[cls]}</span>
            ${b ? `<button class="mini-btn accent" data-add="${b.id}" data-stage="${esc(st.stageId)}" ${inBasket(b.id) ? 'disabled' : ''}>${inBasket(b.id) ? '已在' : '加入'}</button>` : ''}
          </div>
        </div>
        <div class="stage-ops">
          ${(s.ops || []).slice(0, 6).map(op => `
            <div class="row-op" data-op="${op.id}">
              <span class="stars" style="width:112px">${stars(op.rating)}</span>
              <span class="badge ${op.mode}">${MODE_CN[op.mode]}</span>
              <span class="t" title="${esc(op.title)}">${esc(op.title)}</span>
              <span style="font-size:11px;color:var(--text-3)">${op.total} 人</span>
              <button class="mini-btn" data-copy="${esc(op.maaCode)}">复制</button>
              <button class="mini-btn accent" data-add="${op.id}" data-stage="${esc(st.stageId)}" ${inBasket(op.id) ? 'disabled' : ''}>${inBasket(op.id) ? '已在' : '加入'}</button>
            </div>`).join('') || '<div style="font-size:12px;color:var(--text-3)">没有作业</div>'}
        </div>
      </div>`;
  }).join('');

  box.innerHTML = head + '<div class="stage-list">' + rows + '</div>';

  const allOps = [];
  d.stages.forEach(s => (s.ops || []).forEach(o => allOps.push(o)));

  $$('.stage-row', box).forEach(row => {
    $('.stage-main', row).addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      row.classList.toggle('open');
    });
  });
  $$('[data-add]', box).forEach(b => b.addEventListener('click', (e) => {
    e.stopPropagation();
    const op = allOps.find(o => Number(o.id) === Number(b.dataset.add));
    if (op) { addToBasket(op); b.disabled = true; b.textContent = '已在'; }
  }));
  $$('[data-copy]', box).forEach(b => b.addEventListener('click', (e) => {
    e.stopPropagation();
    copyText(b.dataset.copy, 'MAA 代码已复制');
  }));
  $$('.row-op .t', box).forEach(t => t.addEventListener('click', () => {
    const op = allOps.find(o => Number(o.id) === Number(t.closest('.row-op').dataset.op));
    if (op) showOpDetail(op);
  }));
  const all = $('#add-all-best');
  if (all) all.addEventListener('click', () => {
    let n = 0;
    d.stages.forEach(s => {
      if (s.best && !inBasket(s.best.id)) { S.basket.push(s.best); n++; }
    });
    renderBasket();
    toast(n ? `已加入 ${n} 份作业` : '这些作业都已在作业集里', n ? 'ok' : 'warn');
  });
}

/* ------------------------------------------------------------ 作业详情 */
async function showOpDetail(op) {
  const m = modal(`
    <h3>${esc(op.title)}</h3>
    <div class="sub">作业 #${op.id} · ${esc(op.stageCode || '')} ${esc(op.stageName || '')} · ${op.total} 人 · 评分 ${op.rating}</div>
    <div style="display:flex;gap:8px;margin-bottom:14px">
      <button class="btn-plain" id="copy-code">复制 ${esc(op.maaCode)}</button>
      <button class="btn-solid" id="add-op">加入作业集</button>
    </div>
    <label class="field"><span>干员与要求</span></label>
    <div id="op-detail-body" style="font-size:12px;color:var(--text-2);line-height:1.9">
      <div class="loading-row"><span class="spinner"></span>拉取作业详情…</div>
    </div>
  `, {
    onMount(el, close) {
      $('#copy-code', el).addEventListener('click', () => copyText(op.maaCode, 'MAA 代码已复制'));
      $('#add-op', el).addEventListener('click', () => { addToBasket(op); close(); });
      api('/api/op?id=' + op.id).then(d => {
        const body = d.content || {};
        const rows = (d.opers || []).map(o => {
          const req = o.requirements || {};
          const bits = [];
          if (req.elite != null) bits.push('精' + req.elite);
          if (req.level != null) bits.push(req.level + ' 级');
          if (req.skill_level != null) bits.push(req.skill_level >= 8 ? ('专' + (req.skill_level - 7) + ' 技能' + (req.skill || 1)) : ('技能 ' + req.skill_level));
          if (req.module) bits.push('模组 ' + req.module);
          return `<div style="display:flex;justify-content:space-between;gap:12px;border-bottom:1px dashed rgba(255,255,255,.06);padding:5px 0">
            <span style="color:var(--text)">${esc(o.name)}</span>
            <span style="color:var(--text-3);font-size:11.5px">${esc(bits.join(' · ') || '无特殊要求')}</span>
          </div>`;
        }).join('');
        $('#op-detail-body', el).innerHTML =
          (rows || '<div style="color:var(--text-3)">无干员信息</div>') +
          `<div style="margin-top:12px;font-size:11.5px;color:var(--text-3)">
             动作 ${d.actions} 条 · 关卡 ${esc(d.stageName || '')}
             <br>MAA 代码：<code style="color:var(--mint)">${esc(d.maaCode)}</code>
           </div>`;
      }).catch(e => {
        $('#op-detail-body', el).innerHTML = '<span style="color:var(--rose)">' + esc(e.message) + '</span>';
      });
    }
  });
  return m;
}

/* ------------------------------------------------------------ 作业集 */
function inBasket(id) {
  return S.basket.some(o => Number(o.id) === Number(id));
}

function addToBasket(op) {
  if (inBasket(op.id)) { toast('已经在作业集里了', 'warn'); return; }
  S.basket.push({
    id: op.id, copilotId: op.id, title: op.title, rating: op.rating,
    mode: op.mode, stageCode: op.stageCode || '', stageId: op.stageId || '',
    maaCode: op.maaCode,
  });
  renderBasket();
  toast('已加入作业集');
}

function renderBasket() {
  const list = $('#basket-list');
  $('#basket-count').textContent = S.basket.length;
  $('#btn-apply').disabled = S.basket.length === 0;
  $('#basket-empty').style.display = S.basket.length ? 'none' : 'flex';
  list.innerHTML = S.basket.map((o, i) => `
    <div class="basket-item" draggable="true" data-id="${esc(o.id)}">
      <span class="drag-dots" title="拖动调整顺序">⠿</span>
      <span class="basket-idx">${i + 1}</span>
      <span class="basket-code">${esc(o.stageCode || o.id)}</span>
      <span class="basket-name" title="${esc(o.title)}">${esc(o.title)}</span>
      <button class="icon-btn small" data-del="${i}" title="移除">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>
      </button>
    </div>`).join('');
  $$('[data-del]', list).forEach(b => b.addEventListener('click', () => {
    S.basket.splice(Number(b.dataset.del), 1);
    renderBasket();
  }));
  bindBasketDrag(list);
}

/* 拖动排序：直接挪 DOM，松手后再把 S.basket 按 DOM 顺序重排 */
let _dragEl = null;

function bindBasketDrag(list) {
  $$('.basket-item', list).forEach(el => {
    el.addEventListener('dragstart', e => {
      _dragEl = el;
      el.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      try { e.dataTransfer.setData('text/plain', el.dataset.id); } catch (_) { }
    });
    el.addEventListener('dragend', () => {
      el.classList.remove('dragging');
      _dragEl = null;
      syncBasketOrder();
    });
    el.addEventListener('dragover', e => {
      if (!_dragEl || _dragEl === el) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const r = el.getBoundingClientRect();
      const after = (e.clientY - r.top) > r.height / 2;
      list.insertBefore(_dragEl, after ? el.nextSibling : el);
    });
  });
}

function syncBasketOrder() {
  const ids = $$('#basket-list .basket-item').map(el => String(el.dataset.id));
  if (!ids.length || ids.length !== S.basket.length) return;
  const map = {};
  S.basket.forEach(o => { map[String(o.id)] = o; });
  const next = ids.map(id => map[id]).filter(Boolean);
  if (next.length !== S.basket.length) return;
  const changed = next.some((o, i) => String(o.id) !== String(S.basket[i].id));
  S.basket = next;
  if (changed) setTimeout(renderBasket, 0);   // 重排后刷新序号
}

function fillBasketProfiles() {
  const sel = $('#basket-profile');
  const list = (S.maa && S.maa.profiles) || [];
  const cur = S.settings.profile || (S.maa && S.maa.current) || '';
  sel.innerHTML = list.map(p => `<option value="${esc(p)}" ${p === cur ? 'selected' : ''}>${esc(p)}</option>`).join('')
    || '<option value="">（无配置）</option>';
}

/* ------------------------------------------------------------ 写入 MAA */
async function applyToMaa() {
  if (!S.basket.length) return;
  const btn = $('#btn-apply');
  btn.disabled = true;
  const items = S.basket.map(o => ({ copilotId: o.copilotId, stageCode: o.stageCode, title: o.title }));
  const payload = {
    items,
    profile: $('#basket-profile').value || S.settings.profile,
    mode: $('#basket-mode').value,
    autoStart: $('#basket-autostart').checked,
  };

  const m = modal(`
    <h3>正在写入 MAA</h3>
    <div class="sub">关闭 MAA → 备份配置 → 下载 ${items.length} 份作业 → 写回作业列表${payload.autoStart ? ' → 重启 MAA' : ''}</div>
    <div class="log-box" id="task-log"></div>
    <div class="modal-foot"><button class="btn-plain" data-close>后台执行</button></div>
  `);

  try {
    const { taskId } = await api('/api/maa/apply', payload);
    await pollTask(taskId, m.el);
    S.basket = [];
    renderBasket();
    refreshMaaStatus();
    if (S.result) doSearch();
  } catch (e) {
    toast('写入失败：' + e.message, 'err', 5000);
    btn.disabled = false;
  }
}

function pollTask(tid, root) {
  return new Promise((resolve, reject) => {
    let since = 0;
    let done = false;
    const box = root ? $('#task-log', root) : null;
    const tick = async () => {
      if (done) return;
      try {
        const t = await api('/api/task?id=' + tid + '&since=' + since);
        since = t.logCount || since;
        if (box && t.logs && t.logs.length) {
          t.logs.forEach(line => {
            const div = document.createElement('div');
            const bad = /失败|错误|error|Traceback|✗|退出码/.test(line);
            div.className = bad ? 'err' : '';
            div.textContent = line;
            box.appendChild(div);
          });
          box.scrollTop = box.scrollHeight;
        }
        if (t.status === 'done') {
          done = true;
          if (box) {
            const ok = document.createElement('div');
            ok.className = 'ok';
            ok.textContent = '✓ 完成';
            box.appendChild(ok);
          }
          resolve(t.result);
          return;
        }
        if (t.status === 'error') {
          done = true;
          if (box) {
            const er = document.createElement('div');
            er.className = 'err';
            er.textContent = '✗ ' + (t.error || '失败');
            box.appendChild(er);
          }
          reject(new Error(t.error || '任务失败'));
          return;
        }
        setTimeout(tick, 700);
      } catch (e) {
        done = true;
        reject(e);
      }
    };
    tick();
  });
}

/* ------------------------------------------------------------ 添加账号 */
const TOKEN_GUIDE = `
  <b>三步拿到 token</b>
  <ol>
    <li>浏览器打开<button class="link-btn" data-url="https://www.skland.com/">森空岛社区</button>并登录自己的账号</li>
    <li>按 <code>F12</code> 打开开发者工具，切到 <b>Network</b> 后刷新页面</li>
    <li>点开任意一个发往 <code>zonai.skland.com</code> 的请求，请求头里找 <code>token</code>，整段复制</li>
  </ol>
  <span>token 就是账号凭证，只写在本机 <code>skland/tokens.txt</code>，不会上传。失效了重新取一次即可。</span>`;

function openAddAccount() {
  const m = modal(`
    <h3>添加账号</h3>
    <div class="sub">粘贴森空岛 token（鹰角通行证），会自动拉取该账号的干员与练度并生成本地配置。</div>
    <label class="field"><span>森空岛 Token</span>
      <textarea id="token-input" placeholder="粘贴你自己的森空岛 token，一长串字符，不要带引号和空格"></textarea>
    </label>
    <div class="token-help-row">
      <button class="link-btn" id="add-guide-toggle">怎么拿 token？</button>
      <button class="link-btn" data-url="https://www.skland.com/">打开森空岛</button>
    </div>
    <div class="onb-hint token-guide" id="add-guide" hidden>${TOKEN_GUIDE}</div>
    <label class="field"><span>备注（可选，用于在列表里区分）</span>
      <input type="text" id="alias-input" placeholder="例如：杂鱼">
    </label>
    <div class="log-box" id="add-log" style="display:none"></div>
    <div class="modal-foot">
      <button class="btn-plain" data-close>取消</button>
      <button class="btn-solid" id="btn-do-add">开始同步</button>
    </div>
  `, {
    onMount(el, close) {
      const guide = $('#add-guide', el);
      $('#add-guide-toggle', el).addEventListener('click', () => {
        guide.hidden = !guide.hidden;
      });
      $$('[data-url]', el).forEach(b => b.addEventListener('click', () => openUrl(b.dataset.url)));
      const btn = $('#btn-do-add', el);
      btn.addEventListener('click', async () => {
        const token = $('#token-input', el).value.trim();
        if (!token) { toast('先粘贴 token', 'warn'); return; }
        btn.disabled = true;
        btn.textContent = '同步中…';
        const logBox = $('#add-log', el);
        logBox.style.display = 'block';
        try {
          const alias = $('#alias-input', el).value.trim();
          const { taskId } = await api('/api/account/refresh', { token, alias });
          const result = await pollTask(taskId, el);
          const d = await api('/api/accounts');
          S.accounts = d.accounts;
          renderAccounts();
          close();
          toast('账号已同步');
          const target = (result && result.newest) || (S.accounts[0] && S.accounts[0].file);
          if (target) await selectAccount(target, true);
        } catch (e) {
          toast('同步失败：' + e.message, 'err', 6000);
          btn.disabled = false;
          btn.textContent = '重试';
        }
      });
    }
  });
  setTimeout(() => { const t = $('#token-input', m.el); if (t) t.focus(); }, 60);
}

/* ------------------------------------------------------------ 首次启动引导 */
function openOnboarding() {
  if (S.onboarded) return;
  S.onboarded = true;
  const p = S.paths || {};
  const m = document.createElement('div');
  m.className = 'onboard';
  m.innerHTML = `
    <div class="onb-card">
      <div class="onb-head">
        <div class="brand-mark">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
            <path d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5z"/><path d="M8.5 13.5 12 16l3.5-2.5"/>
          </svg>
        </div>
        <div>
          <h2>两步就能开始</h2>
          <p>先填森空岛 token 读取练度，再指一下 MAA 目录。数据都保存在本机项目里。</p>
        </div>
      </div>

      <div class="onb-step">
        <div class="onb-idx">1</div>
        <div class="onb-body">
          <h3>森空岛 Token</h3>
          <p>用于拉取干员、等级、专精、模组，生成本地账号配置。</p>
          <textarea id="onb-token" rows="3" spellcheck="false"
            placeholder="把你自己账号的森空岛 token 粘贴到这里"></textarea>
          <div class="path-row">
            <input type="text" id="onb-alias" placeholder="备注（可选，例如：大号）">
            <button class="btn-plain mini" id="onb-token-help">怎么拿 token</button>
          </div>
          <div class="onb-hint token-guide" id="onb-token-guide" hidden>${TOKEN_GUIDE}</div>
          <div class="onb-hint">token 会写进 <code>skland/tokens.txt</code>，下次打开可以一键同步全部账号。</div>
        </div>
      </div>

      <div class="onb-step">
        <div class="onb-idx">2</div>
        <div class="onb-body">
          <h3>MAA 根目录</h3>
          <p>包含 <code>MAA.exe</code> 的那个文件夹，用来写入多个作业并重启 MAA。</p>
          <div class="path-row">
            <input type="text" id="onb-maa" placeholder="例如 D:\\MAA\\MAA-v6.20.1-win-x64">
            <button class="btn-plain mini" id="onb-pick">浏览</button>
            <button class="btn-plain mini" id="onb-probe">检测</button>
          </div>
          <div class="onb-hint" id="onb-maa-state">还没检测。</div>
        </div>
      </div>

      <div class="log-box" id="task-log" style="display:none"></div>

      <div class="onb-foot">
        <span class="onb-note">数据目录 <code>${esc(p.skland || 'skland/')}</code></span>
        <div class="onb-btns">
          <button class="btn-plain" id="onb-skip">稍后设置</button>
          <button class="btn-solid" id="onb-go">保存并同步账号</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(m);

  const close = () => {
    m.style.transition = '.18s ease';
    m.style.opacity = '0';
    setTimeout(() => m.remove(), 180);
  };
  const state = $('#onb-maa-state', m);
  $('#onb-token-help', m).addEventListener('click', () => {
    const g = $('#onb-token-guide', m);
    g.hidden = !g.hidden;
    if (!g.hidden) $('#onb-token', m).focus();
  });
  $$('[data-url]', m).forEach(b => b.addEventListener('click', () => openUrl(b.dataset.url)));
  const probe = async () => {
    const dir = $('#onb-maa', m).value.trim();
    if (!dir) { state.className = 'onb-hint'; state.textContent = '先填一个目录再检测。'; return null; }
    try {
      const r = await api('/api/maa/probe?dir=' + encodeURIComponent(dir));
      if (r.exeExists && r.configExists) {
        state.className = 'onb-hint ok';
        state.innerHTML = `✓ 找到 MAA.exe，配置 ${r.profiles.length} 个：<code>${esc(r.profiles.slice(0, 4).join(' / '))}</code>`;
      } else if (r.exeExists) {
        state.className = 'onb-hint bad';
        state.textContent = '! 找到 MAA.exe，但还没有 config/gui.new.json（先启动一次 MAA 就好）';
      } else {
        state.className = 'onb-hint bad';
        state.textContent = '✗ 这个目录里没有 MAA.exe，请选包含 MAA.exe 的文件夹';
      }
      return r;
    } catch (e) {
      state.className = 'onb-hint bad';
      state.textContent = '检测失败：' + e.message;
      return null;
    }
  };

  $('#onb-pick', m).addEventListener('click', async () => {
    const input = $('#onb-maa', m);
    await pickFolder(input);
    if (input.value.trim()) probe();
  });
  $('#onb-probe', m).addEventListener('click', probe);
  $('#onb-skip', m).addEventListener('click', () => {
    close();
    if (!S.accounts.length) setTimeout(openAddAccount, 200);
  });

  $('#onb-go', m).addEventListener('click', async () => {
    const token = $('#onb-token', m).value.trim();
    const alias = $('#onb-alias', m).value.trim();
    const maaDir = $('#onb-maa', m).value.trim();
    if (!token) { toast('先把森空岛 token 粘进来', 'warn'); $('#onb-token', m).focus(); return; }
    if (!maaDir) { toast('把 MAA 根目录填上，或者点「稍后设置」', 'warn'); $('#onb-maa', m).focus(); return; }
    const ok = await probe();
    if (!ok || !ok.exeExists) { toast('MAA 目录没通过检测，改一下再试', 'err'); return; }

    const btn = $('#onb-go', m);
    btn.disabled = true;
    btn.textContent = '同步中…';
    const logBox = $('#task-log', m);
    logBox.style.display = 'block';
    logBox.innerHTML = '';
    try {
      S.settings = (await api('/api/settings', { maaDir })).settings;
      S.maa = (await api('/api/maa/status'));
      fillBasketProfiles();
      const { taskId } = await api('/api/account/refresh', { token, alias });
      const result = await pollTask(taskId, m);
      const acc = await api('/api/accounts');
      S.accounts = acc.accounts;
      renderAccounts();
      renderMaaState();
      close();
      toast('账号已就绪');
      const target = (result && result.newest) || (S.accounts[0] && S.accounts[0].file);
      if (target) await selectAccount(target, true);
    } catch (e) {
      toast('同步失败：' + e.message, 'err', 6000);
      btn.disabled = false;
      btn.textContent = '重试';
    }
  });

  setTimeout(() => { const t = $('#onb-token', m); if (t) t.focus(); }, 80);
}

/* ------------------------------------------------------------ 设置 */
function nativeApi() { return (window.pywebview && window.pywebview.api) || null; }

async function openUrl(url) {
  const n = nativeApi();
  if (n && n.open_url) {
    try {
      const r = await n.open_url(url);
      if (r && r.ok === false) toast(r.error || '打开失败', 'err');
      return;
    } catch (e) { /* 落到 window.open */ }
  }
  window.open(url, '_blank');
}

async function pickFolder(inputEl) {
  const n = nativeApi();
  if (!n || !n.choose_folder) {
    toast('当前不是桌面窗口，请手动粘贴路径', 'err');
    return;
  }
  const r = await n.choose_folder('选择文件夹', inputEl.value.trim());
  if (r && r.path) inputEl.value = r.path;
  else if (r && r.error) toast('选择失败：' + r.error, 'err');
}

function openSettings() {
  const s = S.settings;
  const p = S.paths || {};
  const pk = S.pack || {};
  const gd = S.gamedata || {};
  const counts = pk.counts || {};
  const n = nativeApi();
  const openBtn = (which, label) => n
    ? `<button class="btn-plain mini" data-open="${which}">${label}</button>` : '';
  modal(`
    <h3>设置</h3>
    <div class="sub">改动立即生效。账号数据与配置都保存在本机项目目录里，不会上传。</div>
    <label class="field"><span>MAA 根目录（包含 MAA.exe）</span>
      <div class="path-row">
        <input type="text" id="set-maa" value="${esc(s.maaDir || '')}">
        <button class="btn-plain mini" data-pick="set-maa">浏览</button>
        <button class="btn-plain mini" id="set-probe">检测</button>
      </div></label>
    <div class="onb-hint" id="set-maa-state">${
      S.maa && S.maa.exeExists ? '✓ MAA.exe 已找到' : '✗ 尚未检测到 MAA.exe'}</div>
    <label class="field"><span>默认配置名</span>
      <input type="text" id="set-profile" value="${esc(s.profile || '')}" placeholder="moren"></label>
    <label class="check-row" style="margin-bottom:14px">
      <input type="checkbox" id="set-autostart" ${s.autoStartMaa ? 'checked' : ''}>
      <span>写完作业后自动启动 MAA</span>
    </label>

    <div class="path-list">
      <div class="path-item"><span>账号数据</span><code>${esc(p.skland || '')}</code>${openBtn('skland', '打开')}</div>
      <div class="path-item"><span>配置与日志</span><code>${esc(p.config || '')}</code>${openBtn('config', '打开')}</div>
      <div class="path-item"><span>游戏资源</span><code>v${esc(gd.version || pk.version || '?')} · ${counts.chars || 0} 干员 · ${counts.stages || 0} 关卡</code></div>
      <div class="path-item"><span>程序版本</span><code>MAA-PRTS ${esc(gd.app || (S.appInfo && S.appInfo.version) || '')}</code></div>
    </div>

    <div class="modal-foot">
      <button class="btn-plain" data-close>取消</button>
      <button class="btn-solid" id="btn-save-set">保存</button>
    </div>
  `, {
    onMount(el, close) {
      $$('[data-pick]', el).forEach(b => b.addEventListener('click', async () => {
        const input = $('#' + b.dataset.pick, el);
        await pickFolder(input);
      }));
      $$('[data-open]', el).forEach(b => b.addEventListener('click', async () => {
        const api2 = nativeApi();
        if (api2 && api2.open_folder) {
          const r = await api2.open_folder(b.dataset.open);
          if (r && r.ok === false) toast(r.error || '打开失败', 'err');
        }
      }));
      $('#set-probe', el).addEventListener('click', async () => {
        const box = $('#set-maa-state', el);
        const dir = $('#set-maa', el).value.trim();
        if (!dir) { box.className = 'onb-hint bad'; box.textContent = '先填目录'; return; }
        try {
          const r = await api('/api/maa/probe?dir=' + encodeURIComponent(dir));
          box.className = 'onb-hint ' + (r.exeExists && r.configExists ? 'ok' : 'bad');
          box.textContent = r.exeExists
            ? (r.configExists ? `✓ 找到 MAA.exe，配置 ${r.profiles.length} 个` : '✗ 缺 config/gui.new.json')
            : '✗ 这个目录里没有 MAA.exe';
        } catch (e) {
          box.className = 'onb-hint bad';
          box.textContent = '检测失败：' + e.message;
        }
      });
      $('#btn-save-set', el).addEventListener('click', async () => {
        try {
          const d = await api('/api/settings', {
            maaDir: $('#set-maa', el).value.trim(),
            profile: $('#set-profile', el).value.trim(),
            autoStartMaa: $('#set-autostart', el).checked,
          });
          S.settings = d.settings;
          S.maa = d.maa;
          renderMaaState();
          fillBasketProfiles();
          close();
          toast('设置已保存');
        } catch (e) { toast('保存失败：' + e.message, 'err'); }
      });
    }
  });
}

/* ------------------------------------------------------------ 事件绑定 */
function bindGlobal() {
  $('#btn-search').addEventListener('click', doSearch);
  $('#search-input').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
  $('#btn-add-account').addEventListener('click', openAddAccount);
  $('#btn-settings').addEventListener('click', openSettings);
  $('#maa-state').addEventListener('click', async () => {
    await refreshMaaStatus();
    toast(S.maa.running ? 'MAA 正在运行' : 'MAA 未运行');
  });
  $('#btn-apply').addEventListener('click', applyToMaa);
  $('#btn-clear-basket').addEventListener('click', () => { S.basket = []; renderBasket(); });
  $('#btn-refresh-all').addEventListener('click', async () => {
    const m = modal(`<h3>同步全部账号</h3>
      <div class="sub">按 tokens.txt 逐个刷新，可能耗时 1~3 分钟。</div>
      <div class="log-box" id="task-log"></div>
      <div class="modal-foot"><button class="btn-plain" data-close>后台执行</button></div>`);
    try {
      const { taskId } = await api('/api/account/refresh', {});
      await pollTask(taskId, m.el);
      const d = await api('/api/accounts');
      S.accounts = d.accounts;
      renderAccounts();
      toast('全部账号已同步');
      if (S.current) selectAccount(S.current, true);
    } catch (e) { toast('同步失败：' + e.message, 'err', 5000); }
  });
  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault();
      $('#search-input').focus();
    }
  });
  setInterval(refreshMaaStatus, 30000);
}

document.addEventListener('DOMContentLoaded', () => {
  bindGlobal();
  renderBasket();
  boot();
});
