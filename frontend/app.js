/* ============================================================
   MAA-PRTS 控制台前端
   ============================================================ */
'use strict';

const S = {
  settings: {}, accounts: [], current: '', detail: null,
  maa: {}, activities: [],
  basket: [], result: null, searching: false, appInfo: null,
  paths: {}, pack: {}, setup: {}, gamedata: {}, onboarded: false,
  paradoxPending: [],
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
    $('#basket-autostart').checked = S.settings.autoStartMaa !== false;   // 设置里的默认开关真正生效
    renderAccounts();
    renderUpdate();
    renderQuick();
    renderMaaState();
    fillBasketProfiles();
    if (S.current) await selectAccount(S.current, true);
    startPing();

    // 首次使用：先让用户填 token 与 MAA 目录，再进主流程
    // （needsMaa 按上次账号绑定的 MAA 判断——账号各自配了 MAA 就不再拦）
    if ((S.setup && (S.setup.needsToken || S.setup.needsMaa)) || !S.accounts.length) {
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
    updateParadoxChip();
    await api('/api/settings', { lastAccount: file });
    S.settings.lastAccount = file;
    refreshMaaStatus();          // 状态卡与配置下拉切到这个账号绑定的 MAA
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
  const importBtn = $('#btn-import-maa');
  if (importBtn) importBtn.hidden = !d;   // 有选中账号才给「从 MAA 导入干员信息」入口
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

/* ------------------------------------------------------------ 从 MAA 导入干员信息
   用当前账号绑定的 MAA 目录里的干员识别结果（data/OperBoxData.json）
   更新练度：不需要森空岛 token，后端同步处理直接返回结果（不走任务轮询）。
   注意本地识别不含技能/专精/模组，导入后这类要求按未练处理，须明示。 */
async function importFromMaa() {
  if (!S.current) { toast('先在左侧选择一个账号', 'warn'); return; }
  // 与后端 _maa_dir_for 同语义：账号绑定的目录优先，没绑定回退全局默认
  const dir = String((((S.detail || {}).maa || {}).dir) || S.settings.maaDir || '').trim();
  if (!dir) { toast('该账号没有绑定 MAA 目录，也没有设置全局默认', 'err'); return; }
  let pr;
  try {
    pr = await api('/api/maa/probe?dir=' + encodeURIComponent(dir));
  } catch (e) { toast('检测 MAA 目录失败：' + e.message, 'err'); return; }
  if (!pr.exeExists) { toast('这个 MAA 目录里没有 MAA.exe：' + dir, 'err'); return; }
  if (!pr.operbox) { toast('MAA 目录下没有 data/OperBoxData.json（先在 MAA 小工具里跑一次干员识别）', 'err', 4200); return; }
  const fmtTime = t => (t ? String(t).replace('T', ' ').slice(0, 16) : '—');
  const operboxFile = dir.replace(/[\\/]+$/, '') + '\\data\\OperBoxData.json';
  const who = (((S.detail || {}).account || {}).nickName) || S.current;
  modal(`
    <h3>从 MAA 导入干员信息</h3>
    <div class="sub">用这个 MAA 的干员识别结果更新「${esc(who)}」的练度，不需要森空岛 token。</div>
    <div class="path-list">
      <div class="path-item"><span>MAA 目录</span><code>${esc(dir)}</code></div>
      <div class="path-item"><span>识别文件</span><code>${esc(operboxFile)}</code></div>
      <div class="path-item"><span>识别结果</span><code>${
        pr.operboxCount != null ? pr.operboxCount + ' 名干员' : '内容待导入时解析'
      }${pr.operboxSyncTime ? ' · ' + esc(fmtTime(pr.operboxSyncTime)) + ' 识别' : ''}</code></div>
    </div>
    <div class="onb-hint bad">! 本地识别不含技能、专精、模组数据，导入后这类要求会按未练处理。</div>
    <div class="modal-foot">
      <button class="btn-plain" data-close>取消</button>
      <button class="btn-solid" id="btn-import-go">开始导入</button>
    </div>
  `, {
    onMount(el, close) {
      $('#btn-import-go', el).addEventListener('click', async () => {
        const btn = $('#btn-import-go', el);
        btn.disabled = true;
        btn.textContent = '导入中…';
        try {
          const r = await api('/api/account/import-maa', { file: S.current });
          const st = r.stats || {};
          const warns = (r.warnings || []).map(w => `<div class="onb-hint bad">! ${esc(w)}</div>`).join('');
          close();
          modal(`
            <h3>导入完成</h3>
            <div class="sub">已用 MAA 的干员识别结果更新 ${esc(r.file || S.current)}。</div>
            <div class="path-list">
              <div class="path-item"><span>导入干员</span><code>${r.imported || 0} 名${r.skipped ? '（跳过 ' + r.skipped + ' 名）' : ''}</code></div>
              <div class="path-item"><span>数据来源</span><code>${r.source === 'yituliu' ? '一图流' : 'MAA 本地识别'}</code></div>
              <div class="path-item"><span>识别时间</span><code>${esc(fmtTime(r.syncTime))}</code></div>
              <div class="path-item"><span>练度概况</span><code>${st.charCount || 0} 干员 · 精二 ${st.e2Count || 0} · 六星 ${st.sixStarCount || 0} · 缺卡 ${st.missingCount || 0}</code></div>
            </div>
            ${warns}
            <div class="modal-foot"><button class="btn-solid" data-close>知道了</button></div>
          `);
          toast('已从 MAA 导入 ' + (r.imported || 0) + ' 名干员');
          const acc = await api('/api/accounts');
          S.accounts = acc.accounts;
          renderAccounts();
          await selectAccount(S.current, true);
        } catch (e) {
          toast('导入失败：' + e.message, 'err', 6000);
          btn.disabled = false;
          btn.textContent = '重试';
        }
      });
    }
  });
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
    txt.textContent = 'MAA 运行中 · ' + (m.current || '');
  } else {
    el.classList.add('off');
    txt.textContent = 'MAA 未运行 · ' + (m.current || '');
  }
  el.title = (m.maaDir || '') + '\n点击刷新状态';
}

async function refreshMaaStatus() {
  try {
    // 带上当前账号：返回的是它绑定的 MAA 的状态（没绑定就是全局默认）
    const q = S.current ? '?file=' + encodeURIComponent(S.current) : '';
    S.maa = await api('/api/maa/status' + q);
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
  // 顺序由后端给：进行中的活动在最前，其次按开始时间倒序。
  // 这里不再按编号重排，否则一堆 NEW 会把当前活动挤到滚动区外面去。
  const acts = (S.activities || []);

  let html = '<span class="quick-label">快捷</span>' + paradoxChip();
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
  $$('#quick-row .chip[data-q]').forEach(c => c.addEventListener('click', () => {
    $('#search-input').value = c.dataset.q;
    doSearch();
  }));
  const px = $('#chip-paradox');
  if (px) px.addEventListener('click', openParadox);
}

/* ------------------------------------------------------------ 悖论模拟
   入口沿用「快捷」这一行：它本来就是「按活动直接搜」，悖论是同一类入口，
   放这里不用新增侧栏/顶栏元素，界面不会有异物感。
   数字角标 = 练度够开打、且没导入过的数量。 */
function paradoxChip() {
  const st = (S.detail && S.detail.paradox) || null;
  const todo = st ? (st.todo || 0) : 0;
  const tip = st
    ? `可开打 ${st.ready} 个，其中 ${todo} 个还没导入过 —— 点开按练度推算的清单`
    : '按当前账号练度推算哪些悖论模拟能开打，一键加进作业集';
  return `<button class="chip paradox" id="chip-paradox" title="${esc(tip)}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3v3M12 18v3M3 12h3M18 12h3"/><circle cx="12" cy="12" r="5"/>
      </svg>
      <span class="chip-name">悖论模拟</span>
      ${todo ? `<i class="px-badge">${todo}</i>` : ''}
    </button>`;
}

function updateParadoxChip() {
  const cur = $('#chip-paradox');
  if (!cur) { renderQuick(); return; }
  const wrap = document.createElement('div');
  wrap.innerHTML = paradoxChip();
  cur.replaceWith(wrap.firstElementChild);
  $('#chip-paradox').addEventListener('click', openParadox);
}

function pxEliteText(need) {
  return { 0: '无需精英化', 1: '精一', 2: '精二' }[need] || ('精英化 ' + need);
}

async function openParadox() {
  if (!S.current) { toast('先选一个账号', 'warn'); openAddAccount(); return; }
  const m = modal(`
    <h3>悖论模拟</h3>
    <div class="sub">按你的练度算出哪些悖论能开打，勾选想打的（默认不勾），加入后自动去作业站取作业。
      解锁条件只看对应干员的精英化，关卡内是官方固定阵容。</div>
    <div id="px-body"><div class="loading-row"><span class="spinner"></span>正在按练度推算…</div></div>`);
  m.el.querySelector('.modal').classList.add('modal-wide');
  try {
    const d = await api('/api/paradox/plan', { file: S.current });
    renderParadoxPanel(m.el, d, m.close);
  } catch (e) {
    $('#px-body', m.el).innerHTML = `<div class="empty-state"><h3>读取失败</h3><p>${esc(e.message)}</p></div>`;
  }
}

function renderParadoxPanel(root, d, close) {
  const items = d.items || [], st = d.stats || {};
  const body = $('#px-body', root);
  if (!items.length) {
    body.innerHTML = '<div class="empty-state"><h3>这个账号还没有可开打的悖论</h3>'
      + '<p>悖论模拟需要先把干员精英化：三星精一、四星以上精二。</p></div>';
    return;
  }

  const ver = (d.table && d.table.gameVersion) ? String(d.table.gameVersion).slice(0, 8) : '';
  body.innerHTML = `
    <div class="px-stats">
      <span><b>${st.ready}</b> 可开打</span>
      <span><b class="mint">${st.todo}</b> 未导入</span>
      <span><b>${st.locked}</b> 练度不够</span>
      <span><b>${st.notOwned}</b> 未拥有</span>
      ${ver ? `<em class="px-ver">数据 ${esc(ver)}</em>` : ''}
    </div>
    <div class="px-tools">
      <input type="text" id="px-q" placeholder="搜干员名 / 悖论名 / mem 代号">
      <label class="px-check"><input type="checkbox" id="px-only-todo" checked><span>只看未导入</span></label>
      <button class="btn-plain mini" id="px-all">全选</button>
      <button class="btn-plain mini" id="px-none">清空</button>
    </div>
    <div class="px-list" id="px-list"></div>
    <div class="modal-foot">
      <span class="px-sel" id="px-sel">已选 0 个</span>
      <button class="btn-plain" data-close>取消</button>
      <button class="btn-solid" id="px-add">加入作业集</button>
    </div>`;

  const list = $('#px-list', root);
  const sel = $('#px-sel', root);
  const addBtn = $('#px-add', root);

  // 底栏是弹窗创建之后才注入的，modal() 当时绑不到这里的 data-close，这里补上
  $$('.modal-foot [data-close]', root).forEach(b => b.addEventListener('click', close));

  // 用「选择集」记住用户勾选的项：默认一个都不选，由用户自己挑没打过的；
  // 搜索/切换筛选重绘时勾选状态不会丢。导入过的行默认灰着（想重跑可手动勾）。
  const on = new Set();

  const visible = () => {
    const q = ($('#px-q', root).value || '').trim().toLowerCase();
    const onlyTodo = $('#px-only-todo', root).checked;
    let rows = items;
    if (onlyTodo) rows = rows.filter(r => r.ready && !r.imported);
    if (q) rows = rows.filter(r => (r.name + ' ' + r.pname + ' ' + r.stage).toLowerCase().indexOf(q) >= 0);
    return rows;
  };

  const paint = () => {
    const rows = visible();
    if (!rows.length) {
      list.innerHTML = '<div class="px-empty">没有符合条件的条目</div>';
    } else {
      list.innerHTML = rows.map(r => {
        const tag = r.ready
          ? (r.imported ? `<i class="px-tag done" title="${esc(r.importedAt)} 导入过">已导入</i>` : '<i class="px-tag">未导入</i>')
          : `<i class="px-tag lock">${esc(pxEliteText(r.needElite))}${r.needLevel > 1 ? ' Lv' + r.needLevel : ''} 可开</i>`;
        const checked = r.ready && on.has(r.stage);
        return `<label class="px-row${r.ready ? '' : ' is-locked'}">
          <input type="checkbox" data-stage="${esc(r.stage)}" ${checked ? 'checked' : ''} ${r.ready ? '' : 'disabled'}>
          <span class="px-r r${r.rarity}">${r.rarity}★</span>
          <span class="px-name">${esc(r.name)}</span>
          <span class="px-pname">${esc(r.pname)}</span>
          <span class="px-code">${esc(r.stage)}</span>
          ${tag}
        </label>`;
      }).join('');
    }
    syncSel();
  };

  const selected = () => items.filter(r => r.ready && on.has(r.stage)).map(r => r.stage);

  function syncSel() {
    const n = selected().length;
    sel.textContent = `已选 ${n} 个`;
    addBtn.disabled = n === 0;
    addBtn.textContent = n ? `加入作业集（${n}）` : '加入作业集';
  }

  list.addEventListener('change', e => {
    const box = e.target;
    if (!box || box.type !== 'checkbox' || !box.dataset.stage) return;
    if (box.checked) on.add(box.dataset.stage);
    else on.delete(box.dataset.stage);
    syncSel();
  });
  $('#px-q', root).addEventListener('input', paint);
  $('#px-only-todo', root).addEventListener('change', paint);
  // 全选/清空只作用在当前筛选可见的条目上，避免误改看不见的那一堆
  $('#px-all', root).addEventListener('click', () => {
    visible().forEach(r => { if (r.ready) on.add(r.stage); });
    paint();
  });
  $('#px-none', root).addEventListener('click', () => {
    visible().forEach(r => { if (r.ready) on.delete(r.stage); });
    paint();
  });

  addBtn.addEventListener('click', async () => {
    const stages = selected();
    if (!stages.length) return;
    addBtn.disabled = true;
    addBtn.textContent = '正在取作业…';
    try {
      const r = await api('/api/paradox/pick', { file: S.current, stages });
      const ops = [];
      (r.ok || []).forEach(x => {
        const meta = items.find(i => i.stage === x.stage) || {};
        ops.push({
          id: x.copilotId, title: `${meta.name || ''} · ${meta.pname || ''}`.trim(),
          rating: x.rating, mode: 'ready',
          stageCode: x.stage, stageId: x.stage,
          // MAA 靠 TaskList 的 Name 导航到悖论关卡，这里必须只是干员名；
          // 界面里显示的是 title / stageCode，不受影响。
          name: meta.name || '',
          difficulty: x.difficulty, difficultyText: x.difficultyText,
          maaCode: 'maa://' + x.copilotId,
        });
      });
      const added = addManyToBasket(ops);
      S.paradoxPending = (S.paradoxPending || []).concat((r.ok || []).map(x => x.stage));
      const failed = r.failed || [];
      close();
      if (added) toast(`已加入 ${added} 个悖论作业` + (failed.length ? `，${failed.length} 个没有作业` : ''));
      else toast('都没能加入，看看下面的原因', 'warn', 4000);
      if (failed.length) {
        modal(`<h3>这 ${failed.length} 个没加进去</h3>
          <div class="sub">作业站没有对应关卡的作业，只能等有人上传，或者手动打一次。</div>
          <div class="px-list">${failed.map(f => {
            const meta = items.find(i => i.stage === f.stage) || {};
            return `<div class="px-row"><span class="px-r r${meta.rarity || 0}">${meta.rarity || ''}★</span>
              <span class="px-name">${esc(meta.name || f.stage)}</span>
              <span class="px-pname">${esc(f.reason || '')}</span></div>`;
          }).join('')}</div>
          <div class="modal-foot"><button class="btn-plain" data-close>知道了</button></div>`);
      }
    } catch (e) {
      toast(e.message, 'err', 4000);
      addBtn.disabled = false;
      syncSel();
    }
  });

  paint();
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

/* 难度：1 普通、2 突袭、3 普通+突袭兼容（作业里 difficulty 位标志，冗余 0/缺失 视为普通）。
   EX 关才谈得上突袭，其它关卡即使标了普通也不显眼地摆个徽标。 */
function difficultyTag(op, code) {
  const f = Number(op.difficulty) || 1;
  const c = String(code || op.stageCode || '');
  if (f === 1 && !/-EX-|_ex\d|EX-\d/i.test(c)) return '';
  const cls = f === 2 ? 'raid' : (f === 3 ? 'both' : 'normal');
  const txt = op.difficultyText || (f === 2 ? '突袭' : (f === 3 ? '通用' : '普通'));
  const tip = f === 3 ? '这份作业普通与突袭都能用' : (f === 2 ? '只适用于突袭' : '只适用于普通难度');
  return `<span class="badge diff ${cls}" title="${tip}">${esc(txt)}</span>`;
}

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
  const e = ['精零', '精一', '精二'][o.elite] || '';
  const m = (o.mastery || []).map((x, i) => x ? `专${'一二三'[i] || ''}${x}` : '').filter(Boolean).join(' ');
  // 练度要求（v1 老作业没写的会补默认值，带 implied 标记）
  const req = o.req || {};
  const need = [];
  if (req.elite != null) need.push('精' + req.elite);
  if (req.level != null) need.push(req.level + '级');
  if (req.implied) need.push('默认');
  const needTxt = need.length ? ` · 要求 ${need.join(' ')}` : '';
  if (!o.owned) return '未拥有' + needTxt;
  return `${e} ${o.level} 级${m ? ' · ' + m : ''}${needTxt}`;
}

/* 浏览量展示：过万缩写成 x.x万 */
function fmtViews(n) {
  n = Number(n) || 0;
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\.0$/, '') + '万';
  return n ? String(n) : '';
}

/* 作业简介取第一行有信息量的文字：跳过作者署名、群号、任何带链接的推广行 */
function briefOf(op) {
  const lines = (op.details || '').split('\n').map(s => s.trim()).filter(Boolean);
  const line = lines.find(s => s.length >= 4 && !/http|qm\.qq\.com/.test(s)
    && !/^(原作者|json作者|作者|作业交流群|MAA|maa|【)/.test(s)) || '';
  return line.slice(0, 60);
}

function opCard(op, opts = {}) {
  const mode = op.mode || 'blocked';
  return `
    <div class="op-card ${opts.best ? 'best' : ''}" data-op="${op.id}" data-mode="${mode}">
      <div class="op-top">
        <span class="stars">${stars(op.rating)}</span>
        <span class="op-id">#${op.id}</span>
        <span class="op-up" title="作者：${esc(op.uploader || '佚名')}">@${esc(op.uploader || '佚名')}</span>
      </div>
      <div class="op-title" title="${esc(op.title)}">${esc(op.title)}</div>
      <div class="badges">
        <span class="badge ${mode}">${MODE_CN[mode]}</span>
        ${difficultyTag(op, op.stageCode)}
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

function bindOpCards(root, ops, variant) {
  $$('.op-card', root).forEach(card => {
    const id = Number(card.dataset.op);
    const op = ops.find(o => Number(o.id) === id);
    if (!op) return;
    card.addEventListener('click', async (e) => {
      const btn = e.target.closest('[data-act]');
      if (!btn) { showOpDetail(op); return; }
      const act = btn.dataset.act;
      if (act === 'copy') copyText(op.maaCode, 'MAA 代码已复制');
      else if (act === 'add') { addToBasket(op, variant); btn.disabled = true; btn.textContent = '已在作业集'; }
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

  if (d.stages.length === 1) {
    const s = d.stages[0];
    const ops = s.ops || [];
    const head = `
      <div class="result-head">
        <div class="result-title">${esc(s.stage.code)} ${esc(s.stage.name)}
          ${s.stage.activity ? `<em class="result-act">${esc(s.stage.activity)}</em>` : ''}
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
        inBasket: inBasket(op.id, s.stage.variant),
      })).join('') + '</div>';
    bindOpCards(box, ops, s.stage.variant);
    const ab = $('#add-best');
    if (ab && s.best) ab.addEventListener('click', () => addToBasket(s.best, s.stage.variant));
    return;
  }

  // 活动视图（有突袭版的关卡会拆成「普通」「突袭」两行，通用作业两边都在）
  const codes = [...new Set(d.stages.map(s => s.stage.code))];
  const opIds = new Set();
  d.stages.forEach(s => (s.ops || []).forEach(o => opIds.add(o.id)));
  const totalOps = opIds.size;
  const readyStages = codes.filter(code => d.stages.some(s =>
    s.stage.code === code && s.best && s.best.mode === 'ready')).length;
  const raidRows = d.stages.filter(s => s.stage.variant === 'raid').length;
  const head = `
    <div class="result-head">
      <div class="result-title">${esc(d.title)}
        <span>${codes.length} 关 · ${totalOps} 份作业 · ${readyStages} 关可直接抄${raidRows ? ` · ${raidRows} 个突袭关` : ''}</span>
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
    const isRaid = st.variant === 'raid';
    const variant = st.variant
      ? `<em class="badge diff ${isRaid ? 'raid' : 'normal'}">${isRaid ? '突袭' : '普通'}</em>`
      : '';
    return `
      <div class="stage-row${isRaid ? ' is-raid' : ''}" data-stage="${esc(st.stageId)}" data-variant="${esc(st.variant || '')}">
        <div class="stage-main">
          <div class="stage-code">${esc(st.code)}<small class="sc-sub">${esc(st.name || '')}${variant}</small></div>
          <div class="stage-mid">
            <div class="stage-best-line">
              <div class="stage-best">${b ? esc(b.title) : '（暂无可用作业）'}</div>
              ${b ? `<div class="best-meta"><b>@${esc(b.uploader || '佚名')}</b>${briefOf(b) ? ' · ' + esc(briefOf(b)) : ''}</div>` : ''}
            </div>
            <div class="stage-sub">
              ${b ? `<span class="stars">${stars(b.rating)}</span><span>${b.total} 人</span><span>浏览 ${fmtViews(b.views) || 0}</span>` : ''}
              <span>共 ${s.total} 份</span>
              ${s.counts.ready ? `<span style="color:var(--mint)">可抄 ${s.counts.ready}</span>` : ''}
              ${s.counts.borrow ? `<span style="color:var(--indigo)">借人 ${s.counts.borrow}</span>` : ''}
              ${s.counts.train ? `<span style="color:var(--amber)">需练度 ${s.counts.train}</span>` : ''}
            </div>
          </div>
          <div class="stage-right">
            <span class="badge ${cls}">${MODE_CN[cls]}</span>
            ${b ? `<button class="mini-btn accent" data-add="${b.id}" data-variant="${esc(st.variant || '')}" data-stage="${esc(st.stageId)}" ${inBasket(b.id, st.variant) ? 'disabled' : ''}>${inBasket(b.id, st.variant) ? '已在' : '加入'}</button>` : ''}
          </div>
        </div>
        <div class="stage-ops">
          ${(s.ops || []).slice(0, 6).map(op => `
            <div class="row-op" data-op="${op.id}">
              <span class="stars" style="width:112px">${stars(op.rating)}</span>
              <span class="badge ${op.mode}">${MODE_CN[op.mode]}</span>
              ${difficultyTag(op, st.code)}
              <span class="t" title="${esc(op.title)}">${esc(op.title)}</span>
              <span class="up" title="作者：${esc(op.uploader || '佚名')}">@${esc(op.uploader || '佚名')}</span>
              <span class="vw">浏览 ${fmtViews(op.views) || 0}</span>
              <span style="font-size:11px;color:var(--text-3)">${op.total} 人</span>
              <button class="mini-btn" data-copy="${esc(op.maaCode)}">复制</button>
              <button class="mini-btn accent" data-add="${op.id}" data-variant="${esc(st.variant || '')}" data-stage="${esc(st.stageId)}" ${inBasket(op.id, st.variant) ? 'disabled' : ''}>${inBasket(op.id, st.variant) ? '已在' : '加入'}</button>
            </div>`).join('') || `<div style="font-size:12px;color:var(--text-3)">没有${isRaid ? '突袭' : ''}作业</div>`}
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
    if (!op) return;
    const v = b.dataset.variant || '';
    addToBasket(op, v);
    // 同一份作业在普通/突袭两行各有一组按钮，只置灰对应那一组
    $$(`[data-add="${op.id}"]`, box).forEach(x => {
      if ((x.dataset.variant || '') === v) { x.disabled = true; x.textContent = '已在'; }
    });
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
    const seen = new Set();
    d.stages.forEach(s => {
      if (!s.best) return;
      // 按「关卡 + 难度行」去重：有突袭版的关卡普通、突袭各加一份，
      // 这样 MAA 里两档都有作业可跑
      const key = s.stage.stageId + '|' + (s.stage.variant || '');
      if (seen.has(key) || inBasket(s.best.id, s.stage.variant || undefined)) return;
      seen.add(key);
      S.basket.push({
        id: s.best.id, copilotId: s.best.id, title: s.best.title, rating: s.best.rating,
        mode: s.best.mode, stageCode: s.best.stageCode || '', stageId: s.best.stageId || '',
        maaCode: s.best.maaCode,
        difficulty: Number(s.best.difficulty) || 1,
        difficultyText: s.best.difficultyText || '普通',
        variant: s.stage.variant || '',
      });
      n++;
    });
    renderBasket();
    toast(n ? `已加入 ${n} 份作业` : '这些作业都已在作业集里', n ? 'ok' : 'warn');
  });
}

/* ------------------------------------------------------------ 作业详情 */
async function showOpDetail(op) {
  const m = modal(`
    <h3>${esc(op.title)}</h3>
    <div class="sub">作业 #${op.id} · ${esc(op.stageCode || '')} ${esc(op.stageName || '')} · ${esc(op.difficultyText || '普通')} · ${op.total} 人 · 评分 ${op.rating}</div>
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
          if (req.implied) bits.push('老作业未标注，按星级默认');
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
/* variant：'normal' / 'raid' 表示从哪一行加的（只写对应那条）；不传表示不区分 */
function inBasket(id, variant) {
  return S.basket.some(o => Number(o.id) === Number(id)
    && (variant === undefined || (o.variant || '') === (variant || '')));
}

function addToBasket(op, variant, quiet) {
  const v = variant || op.variant || '';
  if (inBasket(op.id, v || undefined)) {
    if (!quiet) toast(v === 'raid' ? '这份作业已经在作业集的突袭里了' : (v === 'normal' ? '这份作业已经在作业集的普通里了' : '已经在作业集里了'), 'warn');
    return false;
  }
  S.basket.push({
    id: op.id, copilotId: op.id, title: op.title, rating: op.rating,
    mode: op.mode, stageCode: op.stageCode || '', stageId: op.stageId || '',
    name: op.name || '',
    maaCode: op.maaCode,
    difficulty: Number(op.difficulty) || 1,
    difficultyText: op.difficultyText || '普通',
    variant: v,
  });
  if (quiet) return true;
  renderBasket();
  const fab = $('#basket-fab');
  if (fab) { fab.classList.remove('pulse'); void fab.offsetWidth; fab.classList.add('pulse'); }
  toast(v === 'raid' ? '已加入作业集（突袭）' : '已加入作业集');
  return true;
}

/* 批量加入（悖论模拟一次可能几十上百条）：不逐条弹提示，也不逐条重绘 */
function addManyToBasket(ops) {
  let n = 0;
  (ops || []).forEach(op => { if (addToBasket(op, op.variant || '', true)) n++; });
  if (!n) return 0;
  renderBasket();
  const fab = $('#basket-fab');
  if (fab) { fab.classList.remove('pulse'); void fab.offsetWidth; fab.classList.add('pulse'); }
  return n;
}

function basketDiffTag(o) {
  if (o.variant === 'raid') return '<i class="diff-pill raid">突袭</i>';
  if (o.variant === 'normal') return '<i class="diff-pill normal">普通</i>';
  const f = Number(o.difficulty) || 1;
  if (!(f & 2)) return '';
  const txt = f & 1 ? '普通+突袭' : '突袭';
  return `<i class="diff-pill ${f & 1 ? 'both' : 'raid'}">${txt}</i>`;
}

/* 实际写进 MAA 的条数：带 variant 的只写一条，其余按难度标志展开 */
function basketEntryCount(o) {
  if (o.variant === 'raid' || o.variant === 'normal') return 1;
  const f = Number(o.difficulty) || 1;
  return [1, 2].filter(b => f & b).length;
}

function renderBasket() {
  const list = $('#basket-list');
  $('#basket-count').textContent = S.basket.length;
  const entries = S.basket.reduce((n, o) => n + basketEntryCount(o), 0);
  const applyBtn = $('#btn-apply');
  applyBtn.disabled = S.basket.length === 0;
  applyBtn.textContent = entries ? `写入 MAA（${entries} 条）` : '写入 MAA 并重启';
  $('#basket-empty').style.display = S.basket.length ? 'none' : 'flex';
  const fab = $('#fab-count');
  if (fab) {
    fab.textContent = S.basket.length;
    fab.hidden = S.basket.length === 0;
  }
  list.innerHTML = S.basket.map((o, i) => `
    <div class="basket-item" draggable="true" data-idx="${i}">
      <span class="drag-dots" title="拖动调整顺序">⠿</span>
      <span class="basket-idx">${i + 1}</span>
      <span class="basket-code">${esc(o.stageCode || o.id)}${basketDiffTag(o)}</span>
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
      try { e.dataTransfer.setData('text/plain', el.dataset.idx); } catch (_) { }
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
  // 用 DOM 里各块的原始序号还原新顺序：同一份作业可能加两次（普通/突袭），不能用 id
  const order = $$('#basket-list .basket-item').map(el => Number(el.dataset.idx));
  if (!order.length || order.length !== S.basket.length) return;
  const next = order.map(i => S.basket[i]).filter(Boolean);
  if (next.length !== S.basket.length) return;
  const changed = next.some((o, i) => o !== S.basket[i]);
  S.basket = next;
  if (changed) setTimeout(renderBasket, 0);   // 重排后刷新序号
}

function fillBasketProfiles() {
  const sel = $('#basket-profile');
  const list = (S.maa && S.maa.profiles) || [];
  // 不做预选：档案列表来自当前账号绑定的 MAA，默认选第一个
  sel.innerHTML = list.map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join('')
    || '<option value="">（无配置）</option>';
}

/* ------------------------------------------------------------ 写入 MAA */
async function applyToMaa() {
  if (!S.basket.length) return;
  const btn = $('#btn-apply');
  btn.disabled = true;
  const items = S.basket.map(o => ({
    copilotId: o.copilotId, stageCode: o.stageCode, title: o.title,
    name: o.name || '', variant: o.variant || '',
  }));
  const payload = {
    items,
    file: S.current || '',
    profile: $('#basket-profile').value,
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
    const px = S.paradoxPending || [];
    S.basket = [];
    renderBasket();
    toggleBasket(false);          // 窄屏写完顺手收起抽屉
    refreshMaaStatus();
    if (S.result) doSearch();
    // 悖论：写完才记「已导入」，下次打开面板默认不勾
    if (px.length) {
      S.paradoxPending = [];
      api('/api/paradox/mark', { file: S.current, stages: px })
        .then(() => api('/api/paradox/plan', { file: S.current }))
        .then(p => { if (S.detail) S.detail.paradox = p.stats; updateParadoxChip(); })
        .catch(() => { });
    }
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
  <span>token 就是账号凭证，加密保存在本机的账号文件里（Windows DPAPI，仅本机可解），不会上传。失效了重新取一次即可。</span>`;

/* ------------------------------------------------------------ 添加账号（两页向导）
   第 1 页给这个账号挑 MAA（与首次引导同序：先 MAA 后 token）：
   已存过的 / 新探测到的（排除已存过）/ 手动填写。第 2 页森空岛 token，
   支持一行一个批量导入：逐个同步，失败的单独重试，不拖累其他行。
   MAA 不去重——多个账号可以共用一个，也可以各配各的。 */
function openAddAccount() {
  const p = S.paths || {};
  const saved = (S.settings.maaDirs || []).filter(d => d && typeof d === 'string');
  const savedKeys = new Set(saved.map(d => d.replace(/[\\/]+$/, '').toLowerCase()));
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
          <h2>添加账号</h2>
          <p>先给这个账号指定用哪个 MAA，再拿森空岛 token 读取账号信息。</p>
        </div>
      </div>

      <div class="onb-page" data-page="1">
        <div class="onb-step">
          <div class="onb-idx">1</div>
          <div class="onb-body">
            <h3>这个账号用哪个 MAA</h3>
            <p>多个账号可以共用同一个 MAA；要分开养号就给这个账号单独配一个。</p>
            <div class="onb-box">
              <div class="onb-box-head"><span>已保存的 MAA</span></div>
              <div id="aa-saved">${
                saved.length ? '' : '<span class="onb-hint">还没有保存过的 MAA 路径。</span>'
              }</div>
            </div>
            <div class="onb-box">
              <div class="onb-box-head">
                <span>正在运行的 MAA（新发现）</span>
                <button class="btn-plain mini" id="aa-procs-refresh">刷新</button>
              </div>
              <div id="aa-procs"><span class="onb-hint">检测中…</span></div>
            </div>
            <div class="onb-manual">
              <h4>自行选择 MAA 路径</h4>
              <div class="path-row">
                <input type="text" id="aa-maa" placeholder="例如 D:\\MAA\\MAA-v6.20.1-win-x64">
                <button class="btn-plain mini" id="aa-pick">浏览</button>
                <button class="btn-plain mini" id="aa-probe">检测</button>
              </div>
              <div class="onb-hint" id="aa-maa-state">从上面列表选一个，或手动填写后点「检测」；通过后才能进下一步。</div>
            </div>
          </div>
        </div>
      </div>

      <div class="onb-page" data-page="2" hidden>
        <div class="onb-step">
          <div class="onb-idx">2</div>
          <div class="onb-body">
            <h3>森空岛 Token</h3>
            <p>和首次添加一样：优先用内置窗口登录自动抓取，抓不到再手动粘贴。一次加多个账号，就在下面一行粘一个 token，回车换行。</p>
            <div class="onb-login">
              <div class="onb-login-main">
                <div>
                  <b>在内置窗口登录（推荐）</b>
                  <span>打开森空岛官网的登录页，登录成功后自动抓取 token 填进下方，不用自己翻 F12。</span>
                </div>
                <button class="btn-solid mini" id="onb-login-btn">打开登录窗口</button>
              </div>
              <div class="onb-hint" id="onb-login-state">小窗会要求重新登录一次森空岛——token 只在登录的瞬间出现，抓到就自动验证并填到下方。</div>
            </div>
            <div class="onb-manual">
              <h4>自行输入森空岛 token</h4>
              <textarea id="onb-token" rows="3" spellcheck="false"
                placeholder="一行一个 token（回车换行），可一次粘贴多个账号"></textarea>
              <div class="path-row">
                <input type="text" id="onb-alias" placeholder="备注（可选，例如：大号）">
                <button class="btn-plain mini" id="onb-token-help">怎么拿 token</button>
              </div>
              <div class="onb-hint token-guide" id="onb-token-guide" hidden>${TOKEN_GUIDE}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="log-box" id="task-log" style="display:none"></div>

      <div class="onb-foot">
        <span class="onb-note">数据目录 <code>${esc(p.accounts || 'config/')}</code></span>
        <div class="onb-btns">
          <button class="btn-plain" id="aa-cancel">取消</button>
          <button class="btn-plain" id="aa-back" hidden>上一步</button>
          <button class="btn-solid" id="aa-next">下一步</button>
          <button class="btn-solid" id="aa-go" hidden>保存并同步账号</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(m);

  const stopLoginPoll = wireSklandLogin(m, '✓ token 已验证并填好，点「保存并同步账号」。');

  const close = () => {
    stopLoginPoll();
    api('/api/skland/login/cancel', {}).catch(() => { });
    m.style.transition = '.18s ease';
    m.style.opacity = '0';
    setTimeout(() => m.remove(), 180);
  };
  const showPage = n => {
    $$('[data-page]', m).forEach(el => { el.hidden = +el.dataset.page !== n; });
    $('#aa-next', m).hidden = n !== 1;
    $('#aa-go', m).hidden = n !== 2;
    $('#aa-back', m).hidden = n !== 2;
  };
  const state = $('#aa-maa-state', m);
  const input = $('#aa-maa', m);

  const probe = async () => {
    const dir = input.value.trim();
    if (!dir) { state.className = 'onb-hint'; state.textContent = '先填一个目录再检测，或从上面列表选一个。'; return null; }
    try {
      const r = await api('/api/maa/probe?dir=' + encodeURIComponent(dir));
      if (r.exeExists && r.configExists) {
        state.className = 'onb-hint ok';
        state.innerHTML = `✓ 找到 MAA.exe，配置 ${r.profiles.length} 个：<code>${esc(r.profiles.slice(0, 4).join(' / '))}</code>`
          + (r.operbox
            ? `<br>该 MAA 有练度数据（${r.operboxCount != null ? r.operboxCount + ' 名' : ''}${r.operboxSyncTime ? '，' + esc(String(r.operboxSyncTime).slice(0, 10)) + ' 识别' : ''}），账号添加后可「从 MAA 导入干员信息」`
            : '');
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
  const pickRow = (dir, extra = '') => {
    const lab = document.createElement('label');
    lab.className = 'onb-proc';
    lab.innerHTML = `<input type="radio" name="aa-dir">
      <code title="${esc(dir)}">${esc(dir)}</code>${extra}`;
    lab.querySelector('input').addEventListener('change', () => {
      input.value = dir;
      probe();
    });
    return lab;
  };

  // 已保存列表（历史 maaDirs）
  const savedBox = $('#aa-saved', m);
  if (saved.length) {
    saved.forEach(d => savedBox.appendChild(pickRow(d)));
    input.value = saved[0];
  }

  // 新发现的正在运行 MAA（排除已保存的）
  const loadProcs = async () => {
    const box = $('#aa-procs', m);
    box.innerHTML = '<span class="onb-hint">检测中…</span>';
    try {
      const r = await api('/api/maa/running');
      const rows = (r.list || []).filter(
        row => !savedKeys.has(row.dir.replace(/[\\/]+$/, '').toLowerCase()));
      if (!rows.length) {
        box.innerHTML = '<span class="onb-hint">没有新发现——正在运行的 MAA 都已在上面列表里，或没有 MAA 在跑。</span>';
        return;
      }
      box.innerHTML = '';
      rows.forEach(row => {
        box.appendChild(pickRow(row.dir, `<span class="onb-proc-pid">PID ${row.pids.join(' / ')}</span>`));
      });
      if (!input.value.trim()) { input.value = rows[0].dir; probe(); }
    } catch (e) {
      box.innerHTML = `<span class="onb-hint bad">检测失败：${esc(e.message)}</span>`;
    }
  };

  $('#onb-token-help', m).addEventListener('click', () => {
    const g = $('#onb-token-guide', m);
    g.hidden = !g.hidden;
    if (!g.hidden) $('#onb-token', m).focus();
  });
  input.addEventListener('input', () => {
    $$('input[name="aa-dir"]', m).forEach(r => { r.checked = false; });
  });
  $('#aa-procs-refresh', m).addEventListener('click', loadProcs);
  $('#aa-pick', m).addEventListener('click', async () => {
    await pickFolder(input);
    if (input.value.trim()) { $$('input[name="aa-dir"]', m).forEach(r => { r.checked = false; }); probe(); }
  });
  $('#aa-probe', m).addEventListener('click', probe);
  loadProcs();

  $('#aa-cancel', m).addEventListener('click', close);
  $('#aa-back', m).addEventListener('click', () => showPage(1));
  $('#aa-next', m).addEventListener('click', async () => {
    const dir = input.value.trim();
    if (!dir) { toast('先给这个账号选一个 MAA 根目录', 'warn'); input.focus(); return; }
    const ok = await probe();
    if (!ok || !ok.exeExists) { toast('MAA 目录没通过检测，改一下再试', 'err'); return; }
    showPage(2);
    setTimeout(() => { const t = $('#onb-token', m); if (t && !t.value.trim()) t.focus(); }, 80);
  });

  // 一行一个 token：按行拆开去重后逐个同步，失败的不拖累后面的行
  let pendingRetry = [];
  $('#aa-go', m).addEventListener('click', async () => {
    const btn = $('#aa-go', m);
    const tokens = pendingRetry.length ? pendingRetry
      : [...new Set($('#onb-token', m).value.split(/\r?\n/).map(s => s.trim()).filter(Boolean))];
    const alias = $('#onb-alias', m).value.trim();
    const dir = input.value.trim();
    if (!tokens.length) { toast('先把森空岛 token 粘进来', 'warn'); showPage(2); $('#onb-token', m).focus(); return; }
    if (!pendingRetry.length && dir) {
      const ok = await probe();
      if (!ok || !ok.exeExists) { toast('MAA 目录没通过检测，改一下再试', 'err'); showPage(1); return; }
    }
    pendingRetry = [];
    btn.disabled = true;
    const logBox = $('#task-log', m);
    logBox.style.display = 'block';
    logBox.innerHTML = '';
    const many = tokens.length > 1;
    if (many && alias) {
      const div = document.createElement('div');
      div.textContent = '一次添加多个账号时「备注」不生效（各账号用森空岛昵称区分），已忽略。';
      logBox.appendChild(div);
    }
    const added = [];
    const failed = [];
    for (let i = 0; i < tokens.length; i++) {
      btn.textContent = many ? `同步中…（${i + 1}/${tokens.length}）` : '同步中…';
      try {
        const { taskId } = await api('/api/account/refresh', { token: tokens[i], alias: many ? '' : alias });
        const result = await pollTask(taskId, m);
        added.push((result && result.newest) || '');
      } catch (e) {
        failed.push({ token: tokens[i], error: e.message });
      }
    }
    if (added.length) {
      // 给新加的账号们绑定选定的 MAA；留空就不绑定（回退全局默认）
      if (dir) {
        for (const file of added) {
          if (file) await api('/api/account/maa', { file, patch: { dir } }).catch(() => { });
        }
      }
      const acc = await api('/api/accounts');
      S.accounts = acc.accounts;
      renderAccounts();
      const st = await api('/api/settings', {});
      S.settings = st.settings;
    }
    if (failed.length) {
      toast(`成功 ${added.length} 个，失败 ${failed.length} 个，详见日志`, 'err', 6000);
      failed.forEach(f => {
        const div = document.createElement('div');
        div.className = 'err';
        div.textContent = `✗ token ${f.token.slice(0, 6)}…：${f.error}`;
        logBox.appendChild(div);
      });
      pendingRetry = failed.map(f => f.token);
      btn.disabled = false;
      btn.textContent = `重试失败的 ${failed.length} 个`;
      return;
    }
    close();
    toast(many ? `${added.length} 个账号已添加` : '账号已添加');
    const target = added[added.length - 1];
    if (target) await selectAccount(target, true);
  });

  showPage(1);
  setTimeout(() => { const t = $('#aa-maa', m); if (t) t.focus(); }, 80);
}

/* ------------------------------------------------------------ 内置森空岛登录
   首次引导 / 添加账号两个向导共用：打开登录小窗，轮询状态，
   成功就把验证过的 token 回填到向导里的 #onb-token。返回停止轮询函数。 */
function wireSklandLogin(m, doneHtml) {
  let timer = null;
  const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
  const loginState = $('#onb-login-state', m);
  const setLoginState = (cls, html) => {
    loginState.className = 'onb-hint' + (cls ? ' ' + cls : '');
    loginState.innerHTML = html;
  };
  $('#onb-login-btn', m).addEventListener('click', async () => {
    const btn = $('#onb-login-btn', m);
    btn.disabled = true;
    btn.textContent = '登录窗口已打开…';
    try {
      await api('/api/skland/login', {});
    } catch (e) {
      btn.disabled = false;
      btn.textContent = '打开登录窗口';
      setLoginState('bad', '✗ ' + esc(e.message));
      return;
    }
    setLoginState('', '在弹出的森空岛小窗里登录，成功后会自动验证 token、关掉小窗并填到下方。');
    stop();
    timer = setInterval(async () => {
      let st;
      try { st = await api('/api/skland/login/status'); } catch (e) { return; }
      if (st.phase === 'verifying') {
        setLoginState('', '已捕获请求，正在验证 token…');
      } else if (st.phase === 'done' && st.token) {
        stop();
        $('#onb-token', m).value = st.token;
        btn.disabled = false;
        btn.textContent = '再抓一次';
        setLoginState('ok', doneHtml || '✓ token 已验证并填好，继续操作即可。');
        toast('森空岛 token 已自动获取');
      } else if (st.phase === 'failed') {
        stop();
        btn.disabled = false;
        btn.textContent = '打开登录窗口';
        setLoginState('bad', '✗ ' + esc(st.error || '内置登录出错') + '，也可以在下面手动粘贴 token。');
      } else if (st.phase === 'closed') {
        stop();
        btn.disabled = false;
        btn.textContent = '打开登录窗口';
        setLoginState('', '登录窗口已关闭。没抓到的话重新打开，或在下面手动粘贴。');
      }
    }, 900);
  });
  return stop;
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
          <p>先指一下 MAA 目录，再拿森空岛 token 读取练度。数据都保存在本机项目里。</p>
        </div>
      </div>

      <div class="onb-page" data-page="1">
        <div class="onb-step">
          <div class="onb-idx">1</div>
          <div class="onb-body">
            <h3>MAA 根目录</h3>
            <p>包含 <code>MAA.exe</code> 的那个文件夹，用来写入多个作业并重启 MAA。</p>
            <div class="onb-box">
              <div class="onb-box-head">
                <span>正在运行的 MAA</span>
                <button class="btn-plain mini" id="onb-procs-refresh">刷新</button>
              </div>
              <div id="onb-procs"><span class="onb-hint">检测中…</span></div>
            </div>
            <div class="onb-manual">
              <h4>自行选择 MAA 路径</h4>
              <div class="path-row">
                <input type="text" id="onb-maa" placeholder="例如 D:\\MAA\\MAA-v6.20.1-win-x64">
                <button class="btn-plain mini" id="onb-pick">浏览</button>
                <button class="btn-plain mini" id="onb-probe">检测</button>
              </div>
              <div class="onb-hint" id="onb-maa-state">还没检测。</div>
            </div>
          </div>
        </div>
      </div>

      <div class="onb-page" data-page="2" hidden>
        <div class="onb-step">
          <div class="onb-idx">2</div>
          <div class="onb-body">
            <h3>森空岛 Token</h3>
            <p>用于拉取干员、等级、专精、模组，生成本地账号配置。</p>
            <div class="onb-login">
              <div class="onb-login-main">
                <div>
                  <b>在内置窗口登录（推荐）</b>
                  <span>打开森空岛官网的登录页，登录成功后自动抓取 token 填进下方，不用自己翻 F12。</span>
                </div>
                <button class="btn-solid mini" id="onb-login-btn">打开登录窗口</button>
              </div>
              <div class="onb-hint" id="onb-login-state">小窗会要求重新登录一次森空岛——token 只在登录的瞬间出现，抓到就自动验证并填到下方。</div>
            </div>
            <div class="onb-manual">
              <h4>自行输入森空岛 token</h4>
              <textarea id="onb-token" rows="3" spellcheck="false"
                placeholder="把你自己账号的森空岛 token 粘贴到这里"></textarea>
              <div class="path-row">
                <input type="text" id="onb-alias" placeholder="备注（可选，例如：大号）">
                <button class="btn-plain mini" id="onb-token-help">怎么拿 token</button>
              </div>
              <div class="onb-hint token-guide" id="onb-token-guide" hidden>${TOKEN_GUIDE}</div>
              <div class="onb-hint">token 会加密写进本机账号文件，下次打开可以一键同步全部账号。</div>
            </div>
          </div>
        </div>
      </div>

      <div class="log-box" id="task-log" style="display:none"></div>

      <div class="onb-foot">
        <span class="onb-note">数据目录 <code>${esc(p.accounts || 'config/')}</code></span>
        <div class="onb-btns">
          <button class="btn-plain" id="onb-skip">稍后设置</button>
          <button class="btn-plain" id="onb-back" hidden>上一步</button>
          <button class="btn-solid" id="onb-next">下一步</button>
          <button class="btn-solid" id="onb-go" hidden>保存并同步账号</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(m);

  // 内置登录：小窗里登录成功 → 后端嗅探并验证 token → 自动回填
  const stopLoginPoll = wireSklandLogin(m, '✓ token 已验证并填好，直接点「保存并同步账号」。');

  const close = () => {
    stopLoginPoll();
    api('/api/skland/login/cancel', {}).catch(() => { });   // 顺手关掉可能还开着的登录小窗
    m.style.transition = '.18s ease';
    m.style.opacity = '0';
    setTimeout(() => m.remove(), 180);
  };
  const showPage = n => {
    $$('[data-page]', m).forEach(el => { el.hidden = +el.dataset.page !== n; });
    $('#onb-next', m).hidden = n !== 1;
    $('#onb-go', m).hidden = n !== 2;
    $('#onb-back', m).hidden = n !== 2;
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

  // 从正在运行的 MAA.exe 反查安装目录，勾选即填入并检测
  const loadProcs = async () => {
    const box = $('#onb-procs', m);
    box.innerHTML = '<span class="onb-hint">检测中…</span>';
    try {
      const r = await api('/api/maa/running');
      const rows = r.list || [];
      if (!rows.length) {
        box.innerHTML = '<span class="onb-hint">未找到正在运行的 MAA——先启动 MAA 再点「刷新」，或在下面自行选择路径。</span>';
        return;
      }
      box.innerHTML = '';
      rows.forEach((row, i) => {
        const lab = document.createElement('label');
        lab.className = 'onb-proc';
        lab.innerHTML = `<input type="radio" name="onb-proc"${i === 0 ? ' checked' : ''}>
          <code title="${esc(row.path)}">${esc(row.dir)}</code>
          <span class="onb-proc-pid">PID ${row.pids.join(' / ')}</span>`;
        lab.querySelector('input').addEventListener('change', () => {
          $('#onb-maa', m).value = row.dir;
          probe();
        });
        box.appendChild(lab);
      });
      $('#onb-maa', m).value = rows[0].dir;
      probe();
    } catch (e) {
      box.innerHTML = `<span class="onb-hint bad">检测失败：${esc(e.message)}</span>`;
    }
  };
  loadProcs();
  $('#onb-procs-refresh', m).addEventListener('click', loadProcs);

  $('#onb-pick', m).addEventListener('click', async () => {
    const input = $('#onb-maa', m);
    await pickFolder(input);
    if (input.value.trim()) probe();
  });
  $('#onb-probe', m).addEventListener('click', probe);
  $('#onb-next', m).addEventListener('click', async () => {
    const dir = $('#onb-maa', m).value.trim();
    if (!dir) { toast('先选好 MAA 根目录，或点「稍后设置」', 'warn'); $('#onb-maa', m).focus(); return; }
    const ok = await probe();
    if (!ok || !ok.exeExists) { toast('MAA 目录没通过检测，改一下再试', 'err'); return; }
    showPage(2);
    setTimeout(() => { const t = $('#onb-token', m); if (t && !t.value.trim()) t.focus(); }, 80);
  });
  $('#onb-back', m).addEventListener('click', () => showPage(1));
  $('#onb-skip', m).addEventListener('click', () => {
    close();
    if (!S.accounts.length) setTimeout(openAddAccount, 200);
  });

  $('#onb-go', m).addEventListener('click', async () => {
    const token = $('#onb-token', m).value.trim();
    const alias = $('#onb-alias', m).value.trim();
    const maaDir = $('#onb-maa', m).value.trim();
    if (!token) { toast('先把森空岛 token 粘进来，或用上方内置登录自动抓取', 'warn'); $('#onb-token', m).focus(); return; }
    if (!maaDir) { toast('把 MAA 根目录填上，或者点「稍后设置」', 'warn'); showPage(1); return; }
    const ok = await probe();
    if (!ok || !ok.exeExists) { toast('MAA 目录没通过检测，改一下再试', 'err'); showPage(1); return; }

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
      // 首个账号也记下自己用的 MAA，与后续添加的账号同规则
      if (target && maaDir) await api('/api/account/maa', { file: target, patch: { dir: maaDir } }).catch(() => { });
      if (target) await selectAccount(target, true);
    } catch (e) {
      toast('同步失败：' + e.message, 'err', 6000);
      btn.disabled = false;
      btn.textContent = '重试';
    }
  });

  showPage(1);
  setTimeout(() => { $('#onb-maa', m).focus(); }, 80);
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
    <label class="field"><span>默认 MAA 根目录（包含 MAA.exe；账号没单独指定就用它）</span>
      <div class="path-row">
        <input type="text" id="set-maa" value="${esc(s.maaDir || '')}">
        <button class="btn-plain mini" data-pick="set-maa">浏览</button>
        <button class="btn-plain mini" id="set-probe">检测</button>
      </div></label>
    <div class="onb-hint" id="set-maa-state">${
      S.maa && S.maa.exeExists ? '✓ MAA.exe 已找到' : '✗ 尚未检测到 MAA.exe'}</div>
    <label class="check-row" style="margin-bottom:14px">
      <input type="checkbox" id="set-autostart" ${s.autoStartMaa ? 'checked' : ''}>
      <span>写完作业后自动启动 MAA</span>
    </label>

    <div class="path-list">
      <div class="path-item"><span>账号数据</span><code>${esc(p.accounts || '')}</code>${openBtn('accounts', '打开')}</div>
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
  $('#btn-import-maa').addEventListener('click', importFromMaa);
  $('#btn-settings').addEventListener('click', openSettings);
  $('#maa-state').addEventListener('click', async () => {
    await refreshMaaStatus();
    toast(S.maa.running ? 'MAA 正在运行' : 'MAA 未运行');
  });
  $('#btn-apply').addEventListener('click', applyToMaa);
  $('#btn-clear-basket').addEventListener('click', () => { S.basket = []; renderBasket(); });
  $('#btn-refresh-all').addEventListener('click', async () => {
    const m = modal(`<h3>同步全部账号</h3>
      <div class="sub">按 tokens.json 逐个刷新，可能耗时 1~3 分钟。</div>
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
    if (e.key === 'Escape') { toggleBasket(false); return; }
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault();
      $('#search-input').focus();
    }
  });
  // 窄屏抽屉：浮动按钮开关，点遮罩关闭，窗口拖宽后自动收起
  $('#basket-fab').addEventListener('click', () => toggleBasket());
  $('#basket-mask').addEventListener('click', () => toggleBasket(false));
  window.addEventListener('resize', () => {
    if (window.innerWidth > 1180) toggleBasket(false);
  });
  setInterval(refreshMaaStatus, 30000);
}

/* 窄屏抽屉开关：不传参数就切换 */
function toggleBasket(open) {
  const box = $('#basket');
  const mask = $('#basket-mask');
  if (!box) return;
  const on = open === undefined ? !box.classList.contains('show') : !!open;
  box.classList.toggle('show', on);
  if (mask) mask.classList.toggle('show', on);
  document.body.classList.toggle('drawer-open', on);
}

document.addEventListener('DOMContentLoaded', () => {
  bindGlobal();
  renderBasket();
  boot();
});
