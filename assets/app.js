/* 澳洲總經指標手冊 —— 前端渲染
   資料來源：data/indicators.json（知識層，幾乎不變）
            data/latest.json（數值層，每日由 GitHub Actions 更新）
   本檔不含任何數值，換資料不用改程式。 */

const FACETS = {
  inf: {n:'通膨',    c:'#B3453F'}, lab: {n:'勞動',    c:'#C08A2A'},
  wag: {n:'薪資',    c:'#7FA03A'}, act: {n:'經濟活動', c:'#3F8F5C'},
  con: {n:'信心',    c:'#2E8E93'}, hou: {n:'房市',    c:'#4C6DB8'},
  fis: {n:'財政發債', c:'#8A5FB0'}, fin: {n:'金融條件', c:'#B85586'}
};
const LIGHT = {green:'🟢', yellow:'🟡', gray:'⚪'};
const LIGHT_LABEL = {green:'正常', yellow:'待確認', gray:'未取得'};

// build.py 的 new_since 記的是台北日期，這裡也要用台北日期比，
// 否則跨時區看這頁時 🆕 會早一天消失或晚一天出現。
const TODAY_TPE = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Taipei'}).format(new Date());

let D = [], V = {}, BUILD = '';
const selFacet = new Set();
let selStatus = null, q = '';

const $ = id => document.getElementById(id);

/* ---------------------------------------------------------- 迷你走勢圖 */
function sparkline(history) {
  if (!history || history.length < 4) return '';
  const vals = history.map(h => h.value);
  const min = Math.min(...vals), max = Math.max(...vals);
  const w = 76, h = 24, pad = 2;
  const span = (max - min) || 1;
  const pts = vals.map((v, i) => {
    const x = pad + i * (w - 2 * pad) / (vals.length - 1);
    const y = h - pad - (v - min) / span * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const last = pts[pts.length - 1].split(',');
  const rising = vals[vals.length - 1] >= vals[0];
  const col = rising ? '#ADA595' : '#ADA595';
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <polyline points="${pts.join(' ')}" fill="none" stroke="${col}" stroke-width="1.3"
      stroke-linejoin="round" stroke-linecap="round" opacity=".85"/>
    <circle cx="${last[0]}" cy="${last[1]}" r="2" fill="${rising ? '#D9A441' : '#3FB27F'}"/>
  </svg>`;
}

/* ------------------------------------------------- 相對上期的變動與方向 */
/* 箭頭一律誠實表示「數值」的升降，債市多空由顏色與標籤承載。
   兩者分開才不會誤讀——50 張卡的語義方向並不一致（CPI 升是利空、
   失業率升是利多），把箭頭本身翻過來看到 ▼ 會以為數值下降。
   card.bond_dir：1=值升利空債市、-1=值升利多債市、null=語義不明確不編碼。 */
function changeText(card) {
  const hist = card.history || [];
  if (hist.length < 2 || card.value == null) return '';
  const prev = hist[hist.length - 2].value, cur = card.value;
  const diff = cur - prev;
  if (!isFinite(diff)) return '';
  const arrow = diff > 0 ? '▲' : diff < 0 ? '▼' : '—';
  const dec = Math.abs(diff) >= 100 ? 0 : Math.abs(diff) >= 10 ? 1 : 2;
  const mag = Math.abs(diff).toLocaleString('en-US',
    {minimumFractionDigits: dec, maximumFractionDigits: dec});
  // 百分比類指標的變動是「百分點」，不加註會被誤讀成百分比變化
  const suffix = card.unit === '%' ? ' pp' : (card.unit ? ' ' + card.unit : '');

  // 持平或語義不明確 → 維持中性灰，不給多空判斷
  const sign = diff === 0 ? 0 : (card.bond_dir || 0) * (diff > 0 ? 1 : -1);
  const tone = sign > 0 ? 'bear' : sign < 0 ? 'bull' : 'flat';
  const label = sign > 0 ? '利空債市' : sign < 0 ? '利多債市' : '';

  return `<span class="chg ${tone}">${arrow} ${diff === 0 ? '持平' : mag + suffix}` +
    (label ? `<span class="bondtag">${label}</span>` : '') + `</span>`;
}

/* ------------------------------------------------------------- 篩選列 */
function facetCount(k) { return D.filter(d => d.f.includes(k)).length; }
function statusCount(s) { return D.filter(d => (V[d.id]||{}).status === s).length; }

function renderChips() {
  $('chips').innerHTML =
    `<span class="chip${selFacet.size === 0 ? ' on' : ''}" onclick="clearFacets()">全部<span class="cnt">${D.length}</span></span>` +
    Object.entries(FACETS).map(([k, v]) =>
      `<span class="chip${selFacet.has(k) ? ' on' : ''}" style="${selFacet.has(k) ? 'color:' + v.c : ''}" onclick="toggleFacet('${k}')">` +
      `<span class="dot" style="background:${v.c}"></span>${v.n}<span class="cnt">${facetCount(k)}</span></span>`
    ).join('');
}

function renderStatusBar() {
  $('statusbar').innerHTML = ['green', 'yellow', 'gray'].map(s =>
    `<span class="stat${selStatus === s ? ' on' : ''}" onclick="toggleStatus('${s}')">` +
    `${LIGHT[s]} ${LIGHT_LABEL[s]} ${statusCount(s)}</span>`).join('');
}

function toggleFacet(k) { selFacet.has(k) ? selFacet.delete(k) : selFacet.add(k); renderChips(); renderGrid(); }
function clearFacets() { selFacet.clear(); renderChips(); renderGrid(); }
function toggleStatus(s) { selStatus = selStatus === s ? null : s; renderStatusBar(); renderGrid(); }
function setSearch(s) { $('q').value = s; q = s.toLowerCase(); renderGrid(); window.scrollTo({top: 0}); }

/* --------------------------------------------------------------- 卡片 */
function renderCard(d) {
  const c = V[d.id] || {status: 'gray', notes: ['尚未載入數值'], value_fmt: '—'};
  const col = FACETS[d.f[0]].c;

  const tags = d.f.map(k =>
    `<span class="tag" style="color:${FACETS[k].c};border-color:${FACETS[k].c}">${FACETS[k].n}</span>`).join('');
  const badge = d.mom
    ? `<span class="badge mom">母報告：${d.mom}</span>`
    : (d.p ? `<span class="badge" onclick="setSearch('${d.p}')">📄 出自：${d.p}</span>` : '');

  const hasVal = c.value != null;
  const asof = c.asof_label || c.asof || '期別：—';
  // age_days 算的是「期別結束 → 今天」，不是公布日距今多久（見 scripts/validate.py）。
  // 寫成「N 天前」會被讀成 N 天前才公布，剛出爐的月頻數據看起來像過期。
  const age = c.age_days != null ? `期別結束後 ${c.age_days} 天` : '';
  const isNew = c.new_since && c.new_since === TODAY_TPE;

  // also = 同一指標的其他呈現形式（MoM / 3個月年化 / 總指數 YoY…）
  // extras = 子項與對照序列。兩者都是輔助數字，併排顯示。
  const aux = {...(c.also || {}), ...(c.extras || {})};
  const extras = Object.entries(aux)
    .filter(([, v]) => v != null)
    .map(([k, v]) => {
      const num = typeof v === 'number'
        ? v.toLocaleString('en-US', {maximumFractionDigits: 2}) + (c.unit === '%' && !/指數|利用率/.test(k) ? '%' : '')
        : v;
      return `<span>${k} <b>${num}</b></span>`;
    })
    .join('');

  const warn = (c.notes && c.notes.length && c.status !== 'green')
    ? `<div class="warn">⚠︎ ${c.notes.join('；')}</div>` : '';

  return `<div class="card" style="border-left-color:${col}">
    <div class="namerow">
      <div>
        <div class="name">${d.n}</div>
        <div class="en">${d.e}</div>
      </div>
      <div class="light" title="${(c.notes || []).join('；') || LIGHT_LABEL[c.status]}">${
        isNew ? '<span class="isnew" title="今天期別往前推進，是新公布的數據">🆕</span>' : ''
      }${LIGHT[c.status]}</div>
    </div>
    <div class="tags">${tags}${badge}</div>
    <div class="meta">${d.org} · ${d.t}</div>
    <div class="valrow">
      <div class="valbox">
        <span class="v${hasVal ? '' : ' na'}">${c.value_fmt || '未取得'}</span>
        ${c.value_label ? `<span class="vlabel">${c.value_label}</span>` : ''}
        ${changeText(c)}
      </div>
      ${sparkline(c.history)}
      <div class="asofbox"><span class="asof">${asof}</span><span class="age">${age}</span></div>
    </div>
    ${c.note ? `<div class="note">📌 ${c.note}</div>` : ''}
    ${warn}
    ${extras ? `<div class="extras">${extras}</div>` : ''}
    <details>
      <summary>解讀 · 債市含義 · 關聯 ▾</summary>
      <div class="dl"><span class="k">怎麼解讀</span>${d.read}</div>
      <div class="dl"><span class="k">債市含義</span>${d.bond}</div>
      <div class="dl"><span class="k">關聯指標</span>${d.rel}</div>
      <div class="dl"><span class="k">官方來源</span><a href="${d.src}" target="_blank" rel="noopener">${d.sn}</a>${c.source_label ? ` <span style="color:var(--text3)">（本次取自 ${c.source_label}）</span>` : ''}</div>
    </details>
  </div>`;
}

function renderGrid() {
  let shown = 0;
  $('grid').innerHTML = D.map(d => {
    const st = (V[d.id] || {}).status;
    if (selFacet.size && !d.f.some(k => selFacet.has(k))) return '';
    if (selStatus && st !== selStatus) return '';
    if (q) {
      const hay = `${d.n} ${d.e} ${d.org} ${d.p || ''} ${d.mom || ''}`.toLowerCase();
      if (!hay.includes(q)) return '';
    }
    shown++;
    return renderCard(d);
  }).join('');
  $('count').textContent = `顯示 ${shown} / ${D.length}`;
}

/* --------------------------------------------------------------- 資料載入 */
async function loadData() {
  const [ind, latest] = await Promise.all([
    fetch('data/indicators.json', {cache: 'no-store'}).then(r => r.json()),
    fetch('data/latest.json',     {cache: 'no-store'}).then(r => r.json())
  ]);
  D = ind;
  V = latest.cards || {};
  const changed = BUILD && BUILD !== latest.build_time;
  BUILD = latest.build_time || '';
  $('buildtime').textContent = `上次自動更新：${BUILD}`;
  // 指標張數由資料算，不寫死在 HTML——加卡時忘了改數字比想像中容易發生
  $('cardcount').textContent = D.length;

  const srcs = new Set(Object.values(V).map(c => c.source_label).filter(Boolean));
  $('footer-sources').innerHTML = `<b>本次資料來源</b>　${[...srcs].join('、')}`;
  return changed;
}

function repaint() { renderChips(); renderStatusBar(); renderGrid(); }

/* 重新載入：只重抓 latest.json，不重整頁面，篩選與搜尋條件都保留 */
async function reload(auto = false) {
  const btn = $('reload'), hint = $('reloadhint');
  if (btn) { btn.disabled = true; btn.textContent = '↻ 載入中…'; }
  try {
    const changed = await loadData();
    repaint();
    if (hint) hint.textContent = changed
      ? '✓ 已載入新資料'
      : (auto ? '' : `✓ 已是最新（${BUILD}）`);
  } catch (e) {
    if (hint) hint.textContent = '✗ 載入失敗';
    console.error(e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '↻ 重新載入'; }
    if (hint) setTimeout(() => { hint.textContent = ''; }, 6000);
  }
}

/* --------------------------------------------------------------- 啟動 */
async function init() {
  try {
    await loadData();
  } catch (e) {
    $('buildtime').textContent = '資料載入失敗，請稍後重新整理';
    console.error(e);
    return;
  }
  repaint();
  $('q').addEventListener('input', e => { q = e.target.value.toLowerCase(); renderGrid(); });
  $('reload').addEventListener('click', () => reload());

  // 從 GitHub Actions 分頁按完 Run workflow 切回來時，自動抓一次新資料。
  // 節流 20 秒，避免在分頁間來回切換時狂打。
  let lastAuto = 0;
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    if (Date.now() - lastAuto < 20000) return;
    lastAuto = Date.now();
    reload(true);
  });
}

init();
