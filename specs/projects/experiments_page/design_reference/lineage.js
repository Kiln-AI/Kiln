// Lineage page — reference implementation (vanilla JS, no framework).
// Sections: 1) dimension + color tokens  2) node encoding (the "halve, then quarter" tile)
// 3) sample data generator (replace with real data)  4) tree layout  5) render + state.

// ---------- 1. Dimensions ----------
// Fixed order matters: segments are always filled in this order.
const DIMS = [
  { k: 'P', name: 'Prompt',          c: '#415CF5' },              // Kiln primary
  { k: 'T', name: 'Tools',           c: 'oklch(0.6 0.17 290)' },  // ≈ #7a5af0
  { k: 'S', name: 'Skills',          c: 'oklch(0.72 0.12 230)' }, // ≈ #4fa6d8
  { k: 'M', name: 'Model',           c: 'oklch(0.68 0.17 45)' },  // ≈ #e8743a
  { k: 'H', name: 'Hyperparameters', c: 'oklch(0.82 0.15 85)' }   // ≈ #eebf45
];
const COPY_FILL = '#d1d5db'; // no changes (copy / re-run)
const ROOT_FILL = '#131517'; // starting point
const BEST_RING = '#33B79D'; // success

// ---------- 2. Node encoding ----------
// Unit-square rects per change count. [x, y, w, h, isOverlay]
const QUAD = [[0, 0, .5, .5], [.5, 0, .5, .5], [0, .5, .5, .5], [.5, .5, .5, .5]];
const SHAPES = [
  [[0, 0, 1, 1]],                                    // 1: solid
  [[0, 0, .5, 1], [.5, 0, .5, 1]],                   // 2: halves (left | right)
  [[0, 0, .5, 1], [.5, 0, .5, .5], [.5, .5, .5, .5]],// 3: left half + two right quarters
  QUAD,                                              // 4: quadrants (TL, TR, BL, BR)
  [...QUAD, [.3, .3, .4, .4, 1]]                     // 5: quadrants + center square (5th = center)
];
// changes: string of dim keys, e.g. "PM". size: px. gap: px between segments.
function nodeRects(changes, size, gap) {
  const cols = DIMS.filter(d => changes.includes(d.k)).map(d => d.c);
  if (!cols.length) return [];
  return SHAPES[cols.length - 1].map(([x, y, w, h, ov], i) => {
    let x1 = x * size, x2 = (x + w) * size, y1 = y * size, y2 = (y + h) * size;
    if (!ov) { // inset only internal edges by half the gap
      if (x > .001) x1 += gap / 2; if (x + w < .999) x2 -= gap / 2;
      if (y > .001) y1 += gap / 2; if (y + h < .999) y2 -= gap / 2;
    }
    return { l: x1, t: y1, w: x2 - x1, h: y2 - y1, bg: cols[i], overlay: !!ov };
  });
}
function nodeHTML(n, size, gap, extraStyle = '') {
  const bg = n.id === 0 ? ROOT_FILL : !n.ch ? COPY_FILL : '#fff';
  const inner = nodeRects(n.ch, size, gap).map(r =>
    `<div style="position:absolute;left:${r.l}px;top:${r.t}px;width:${r.w}px;height:${r.h}px;background:${r.bg};${r.overlay ? `box-shadow:0 0 0 ${gap}px #fff;` : ''}"></div>`).join('');
  return `<div style="position:relative;width:${size}px;height:${size}px;border-radius:${size >= 32 ? 4 : 2}px;overflow:hidden;background:${bg};${extraStyle}">${inner}</div>`;
}

// ---------- 3. Sample data (replace with API data) ----------
// Each node: { id, parent, ch: "PTSMH" subset, cfg: {prompt, tools[], skills[], model, temp, max}, score, depth, kids[] }
const MODELS = [
  ['gpt-4o-mini', 'openai'], ['gpt-4o', 'openai'], ['gpt-4.1', 'openai'], ['gpt-4.1-mini', 'openai'], ['o4-mini', 'openai'],
  ['claude-3.5-haiku', 'anthropic'], ['claude-3.7-sonnet', 'anthropic'], ['claude-sonnet-4', 'anthropic'],
  ['gemini-2.0-flash', 'gemini'], ['gemini-2.5-flash', 'gemini'], ['gemini-2.5-pro', 'gemini'],
  ['llama-3.3-70b', 'groq'], ['llama-4-maverick', 'together_ai'], ['qwen-3-32b', 'fireworks'],
  ['deepseek-v3', 'fireworks'], ['mistral-small-3', 'openrouter'], ['gemma-3-27b', 'ollama']
];
const TOOLS = ['web_search', 'lookup_order', 'sql_query', 'retrieve_docs'];
const SKILLS = ['tone_guide', 'escalation_policy', 'refund_rules'];
const TEMPS = [0, 0.2, 0.3, 0.5, 0.7, 1], MAXT = [512, 1024, 2048];

function rng(seed) {
  return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
function generate(total = 182) {
  const R = rng(11), pick = a => a[Math.floor(R() * a.length)], nodes = [];
  let promptV = 1;
  const add = (parent, ch) => {
    const cfg = parent ? JSON.parse(JSON.stringify(parent.cfg)) : { prompt: 1, tools: [], skills: [], model: 0, temp: 0.7, max: 1024 };
    for (const k of ch) {
      if (k === 'P') cfg.prompt = ++promptV;
      if (k === 'T') { const t = pick(TOOLS); cfg.tools = cfg.tools.includes(t) ? cfg.tools.filter(x => x !== t) : [...cfg.tools, t]; }
      if (k === 'S') { const s = pick(SKILLS); cfg.skills = cfg.skills.includes(s) ? cfg.skills.filter(x => x !== s) : [...cfg.skills, s]; }
      if (k === 'M') { let m; do { m = Math.floor(R() * MODELS.length); } while (m === cfg.model); cfg.model = m; }
      if (k === 'H') { if (R() < .65) { let t; do { t = pick(TEMPS); } while (t === cfg.temp); cfg.temp = t; } else { let m; do { m = pick(MAXT); } while (m === cfg.max); cfg.max = m; } }
    }
    const base = parent ? parent.score : 0.58;
    const score = parent ? Math.min(0.93, Math.max(0.36, base + (ch ? (R() - 0.43) * 0.09 : (R() - 0.5) * 0.02))) : base;
    const n = { id: nodes.length, parent, ch, cfg, score, depth: parent ? parent.depth + 1 : 0, kids: [] };
    if (parent) parent.kids.push(n);
    nodes.push(n); return n;
  };
  const dims = () => {
    if (R() < 0.2) return '';
    const r = R(), cnt = r < .6 ? 1 : r < .85 ? 2 : r < .95 ? 3 : r < .99 ? 4 : 5;
    const w = { P: .3, T: .12, S: .1, M: .25, H: .23 }, chosen = new Set();
    while (chosen.size < cnt) {
      let x = R() * Object.values(w).reduce((a, b) => a + b, 0);
      for (const [k, v] of Object.entries(w)) { if (chosen.has(k)) continue; x -= v; if (x <= 0) { chosen.add(k); break; } }
      if (x > 0) for (const k of 'PTSMH') if (!chosen.has(k)) { chosen.add(k); break; }
    }
    return 'PTSMH'.split('').filter(k => chosen.has(k)).join('');
  };
  let focus = add(null, '');
  while (nodes.length < total) {
    const rem = total - nodes.length;
    if (R() < 0.07 && rem > 8 && focus.depth > 1) {
      const k = Math.min(rem, 6 + Math.floor(R() * 16)), sweep = [];
      for (let i = 0; i < k; i++) sweep.push(add(focus, R() < .1 ? '' : R() < .75 ? 'M' : 'MH'));
      focus = sweep.reduce((a, b) => (b.score > a.score ? b : a)); continue;
    }
    const c = add(focus, dims());
    if (c.ch && c.score > focus.score && R() < 0.6) focus = c;
    else if (R() < 0.1) focus = pick(nodes);
    if (focus.depth >= 16) focus = pick(nodes.filter(n => n.depth < 8));
  }
  return nodes;
}

// ---------- 4. Layout (tidy tree: leaves left→right, parents centered over children) ----------
function layout(nodes, ns) {
  const gap = Math.max(3, Math.round(ns * 0.3)), rowH = ns * 2, pad = 4; let cur = 0;
  const place = n => {
    n.y = pad + n.depth * rowH;
    if (!n.kids.length) { n.x = pad + cur; cur += ns + gap; }
    else { n.kids.forEach(place); n.x = (n.kids[0].x + n.kids[n.kids.length - 1].x) / 2; }
  };
  place(nodes[0]);
  // Elbow edges: down from parent, across at mid-row, down into child
  const edge = c => { const p = c.parent, m = p.y + ns + (rowH - ns) / 2; return `M${p.x + ns / 2} ${p.y + ns}V${m}H${c.x + ns / 2}V${c.y}`; };
  return { w: cur - gap + pad * 2, h: Math.max(...nodes.map(n => n.y)) + ns + pad * 2, edge, edgeD: nodes.slice(1).map(edge).join(' ') };
}

// ---------- 5. Render ----------
const fmt = {
  P: c => `Prompt v${c.prompt}`,
  T: c => c.tools.length ? c.tools.join(', ') : 'None',
  S: c => c.skills.length ? c.skills.join(', ') : 'None',
  M: c => MODELS[c.model][0],
  H: c => `temperature ${c.temp} · max ${c.max} tokens`
};
const NS = 14; // node size px
const nodes = generate();
const best = nodes.reduce((a, b) => (b.score > a.score ? b : a));
const lay = layout(nodes, NS);
const state = { sel: best.id, hover: null, filter: [], zoom: 1 };
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const matches = n => !state.filter.length || state.filter.some(k => (k === 'C' ? n.id > 0 && !n.ch : n.ch.includes(k)));

function renderStats() {
  $('stat-total').textContent = nodes.length;
  $('stat-models').textContent = new Set(nodes.map(n => n.cfg.model)).size;
  $('stat-best').textContent = best.score.toFixed(2);
}
function renderChips() {
  const chips = [...DIMS.map(d => ({ k: d.k, name: d.name, sw: d.c })), { k: 'C', name: 'Copy or re-run', sw: COPY_FILL }];
  $('chips').innerHTML = chips.map(c => {
    const on = state.filter.includes(c.k);
    const count = c.k === 'C' ? nodes.filter(n => n.id > 0 && !n.ch).length : nodes.filter(n => n.ch.includes(c.k)).length;
    return `<button class="chip${on ? ' on' : ''}" data-k="${c.k}"><span class="sw" style="background:${c.sw}"></span><span>${c.name}</span><span class="count">${count}</span></button>`;
  }).join('') + (state.filter.length ? `<button class="clear" data-clear>Clear</button>` : '');
}
function renderGraph() {
  const z = state.zoom;
  $('zoom-pct').textContent = `${Math.round(z * 100)}%`;
  const sized = $('graph-sized'); sized.style.width = lay.w * z + 'px'; sized.style.height = lay.h * z + 'px';
  const layer = $('graph-layer'); layer.style.width = lay.w + 'px'; layer.style.height = lay.h + 'px'; layer.style.transform = `scale(${z})`;
  const path = new Set(); for (let n = state.sel != null ? nodes[state.sel] : null; n; n = n.parent) path.add(n.id);
  const pathD = nodes.filter(n => n.parent && path.has(n.id)).map(lay.edge).join(' ');
  $('graph-svg').setAttribute('width', lay.w); $('graph-svg').setAttribute('height', lay.h);
  $('edges').setAttribute('d', lay.edgeD); $('lineage-path').setAttribute('d', pathD);
  $('graph-nodes').innerHTML = nodes.map(n => {
    const isSel = n.id === state.sel, ring = isSel ? 'box-shadow:0 0 0 2px #fff,0 0 0 3.5px #161616;' : n === best ? `box-shadow:0 0 0 1.5px #fff,0 0 0 3px ${BEST_RING};` : '';
    const op = matches(n) || isSel ? 1 : 0.15;
    return `<div class="node" data-id="${n.id}" style="left:${n.x}px;top:${n.y}px;opacity:${op}">${nodeHTML(n, NS, 1, ring)}</div>`;
  }).join('');
}
function renderTip() {
  const tip = $('tip'), h = state.hover != null ? nodes[state.hover] : null;
  if (!h) { tip.hidden = true; return; }
  tip.hidden = false;
  tip.style.left = (h.x + NS) * state.zoom + 8 + 'px'; tip.style.top = h.y * state.zoom - 8 + 'px';
  const changes = h.id === 0 ? fmt.M(h.cfg) : h.ch ? DIMS.filter(d => h.ch.includes(d.k)).map(d => d.name).join(', ') : 'Copy or re-run, no changes';
  tip.innerHTML = `<span class="t">${h.id === 0 ? 'Starting point' : `Configuration #${h.id}`}</span><span>${esc(changes)}</span><span>${esc(fmt.M(h.cfg))} · score ${h.score.toFixed(2)}</span>`;
}
function renderPanel() {
  const panel = $('panel');
  if (state.sel == null) { panel.hidden = true; return; }
  panel.hidden = false;
  const s = nodes[state.sel], p = s.parent, d = p ? s.score - p.score : 0;
  $('panel-tile').innerHTML = nodeHTML(s, 40, 2);
  $('panel-title').textContent = s.id === 0 ? 'Starting point' : `Configuration #${s.id}`;
  $('panel-best').hidden = s !== best;
  const kids = s.kids.length === 1 ? '1 child' : `${s.kids.length} children`;
  $('panel-sub').innerHTML = p ? `Child of <a href="#" data-goto="${p.id}">${p.id === 0 ? 'starting point' : '#' + p.id}</a> · ${kids}` : `Starting point · ${kids}`;
  $('panel-score').textContent = s.score.toFixed(2);
  const delta = $('panel-delta');
  delta.textContent = p ? `${d >= 0 ? '+' : '−'}${Math.abs(d).toFixed(2)} vs parent` : '';
  delta.style.color = d >= 0 ? '#1f8a74' : '#c2391f';
  $('panel-summary').textContent = s.id === 0 ? 'Configuration' : s.ch.length ? `${s.ch.length} of 5 changed from parent` : 'Same settings as parent';
  $('panel-rows').innerHTML = DIMS.map(dm => {
    const ch = s.ch.includes(dm.k);
    const icon = dm.k === 'M' ? `<img src="assets/providers/${MODELS[s.cfg.model][1]}.svg" width="14" height="14" alt="">` : '';
    return `<div class="row"><span class="sw" style="${ch ? `background:${dm.c}` : 'background:#fff;border:1px solid #d1d5db'}"></span><span class="lbl">${dm.name}</span>
      <div class="val"><div class="cur" style="font-weight:${ch ? 500 : 400}">${icon}<span>${esc(fmt[dm.k](s.cfg))}</span></div>${ch && p ? `<span class="from">${esc(fmt[dm.k](p.cfg))}</span>` : ''}</div></div>`;
  }).join('');
  $('btn-compare').disabled = s.id === 0;
}
function render() { renderChips(); renderGraph(); renderTip(); renderPanel(); }

// ---------- Events ----------
$('chips').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  if (b.dataset.clear != null) state.filter = [];
  else { const k = b.dataset.k; state.filter = state.filter.includes(k) ? state.filter.filter(x => x !== k) : [...state.filter, k]; }
  render();
});
$('graph-nodes').addEventListener('click', e => { const n = e.target.closest('.node'); if (n) { state.sel = +n.dataset.id; render(); } });
$('graph-nodes').addEventListener('mouseover', e => { const n = e.target.closest('.node'); if (n && state.hover !== +n.dataset.id) { state.hover = +n.dataset.id; renderTip(); } });
$('graph-nodes').addEventListener('mouseleave', () => { state.hover = null; renderTip(); });
$('zoom-in').onclick = () => { state.zoom = Math.min(2, state.zoom + 0.25); render(); };
$('zoom-out').onclick = () => { state.zoom = Math.max(0.5, state.zoom - 0.25); render(); };
$('panel-close').onclick = () => { state.sel = null; render(); };
$('panel-sub').addEventListener('click', e => { const a = e.target.closest('[data-goto]'); if (a) { e.preventDefault(); state.sel = +a.dataset.goto; render(); } });

renderStats(); render();
// Initial scroll: center the best configuration
const sc = $('graph-scroll');
sc.scrollLeft = Math.max(0, best.x - sc.clientWidth / 2);
sc.scrollTop = Math.max(0, best.y - sc.clientHeight / 2);
