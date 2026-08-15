// 一次性轉換：indicator_data.js（47卡知識層）→ data/indicators.json
// 只換格式，不改任何內容。額外為每卡產生穩定 id 供 mapping.json 對應。
const fs = require('fs');
const path = require('path');

const SRC = process.argv[2];
const OUT = process.argv[3];

const js = fs.readFileSync(SRC, 'utf8');
const D = eval(js + '; D');   // 檔案本身是 const D=[...]

const slug = (e) => e
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '_')
  .replace(/^_+|_+$/g, '')
  .slice(0, 40);

const seen = new Map();
const out = D.map((card, i) => {
  let id = slug(card.e);
  if (seen.has(id)) { const n = seen.get(id) + 1; seen.set(id, n); id = `${id}_${n}`; }
  else seen.set(id, 1);
  return { id, order: i, ...card };
});

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify(out, null, 1), 'utf8');

// 統計
const byFacet = {};
out.forEach(c => c.f.forEach(f => byFacet[f] = (byFacet[f] || 0) + 1));
console.log(`總卡數: ${out.length}`);
console.log('面向分布(含跨面向重複計):', JSON.stringify(byFacet));
console.log('機構分布:', JSON.stringify(
  out.reduce((a, c) => (a[c.org] = (a[c.org] || 0) + 1, a), {}), null, 0));
