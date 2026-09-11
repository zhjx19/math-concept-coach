/**
 * smoke_test_widgets.mjs — 交互组件冒烟测试（无需浏览器）
 *
 * 用最小 DOM 桩加载 assets/card-widgets.js，把 5 类组件各渲染一次，
 * 检查：① 不抛异常 ② 生成了 canvas/控件/读数 ③ 数值算得对。
 *
 * 用法： node scripts/smoke_test_widgets.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import url from 'node:url';

const here = path.dirname(url.fileURLToPath(import.meta.url));
const JS_PATH = path.join(here, '..', 'assets', 'card-widgets.js');

/* ---------------- 最小 DOM 桩 ---------------- */
function makeCtx(log) {
  const store = {};
  const rec = {
    moveTo: (x, y) => log.push(['moveTo', x, y]),
    lineTo: (x, y) => log.push(['lineTo', x, y]),
    arc: (x, y) => log.push(['arc', x, y]),
    fillRect: (x, y, w, h) => log.push(['fillRect', x, y, w, h]),
    strokeRect: (x, y, w, h) => log.push(['strokeRect', x, y, w, h]),
    fillText: (t, x, y) => log.push(['fillText', x, y])
  };
  return new Proxy(store, {
    get(t, p) { if (p in rec) return rec[p]; if (p in t) return t[p]; return function () { }; },
    set(t, p, v) { t[p] = v; return true; }
  });
}
function makeEl(tag) {
  const el = {
    tagName: tag, className: '', style: {}, children: [],
    _text: '', _html: null, _attrs: {}, _log: [], _ctx: null,
    appendChild(c) { el.children.push(c); return c; },
    addEventListener() { }, removeEventListener() { },
    setAttribute(k, v) { el._attrs[k] = v; },
    getAttribute(k) { return el._attrs[k] != null ? el._attrs[k] : null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    closest() { return null; },
    select() { }
  };
  Object.defineProperty(el, 'textContent', {
    get() { return el._text + el.children.map(c => c.textContent || '').join(''); },
    set(v) { el._text = String(v); el.children.length = 0; }
  });
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._html != null ? el._html : ''; },
    set(v) { el._html = String(v); if (v === '') { el.children.length = 0; el._text = ''; } }
  });
  if (tag === 'canvas') {
    el.clientWidth = 640; el.width = 0; el.height = 0;
    el.getContext = () => (el._ctx || (el._ctx = makeCtx(el._log)));
  }
  return el;
}

/* 统计绘图调用的坐标包围盒 —— 用于判断「曲线是否真的画出来了」 */
function bboxOf(log) {
  var xs = [], ys = [];
  log.forEach(function (c) {
    if (typeof c[1] === 'number') xs.push(c[1]);
    if (typeof c[2] === 'number' && typeof c[1] === 'number') ys.push(c[2]);
    if (c[0] === 'fillRect' || c[0] === 'strokeRect') { xs.push(c[1] + c[3]); ys.push(c[2] + c[4]); }
  });
  if (!xs.length || !ys.length) return null;
  var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
  var y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
  return { x0: x0, x1: x1, y0: y0, y1: y1, w: x1 - x0, h: y1 - y0 };
}

/* ---------------- 待测用例 ---------------- */
const CASES = [
  {
    name: 'plot（ε–δ / 一致连续）',
    expect: { readout: /0\.003/ },
    spec: {
      type: 'plot', expr: 'sin(1/x)', xrange: [0.02, 1], yrange: [-1.35, 1.35],
      sliders: [
        { name: 'x0', label: 'x0', min: 0.03, max: 0.9, step: 0.01, value: 0.6 },
        { name: 'd', label: 'd', min: 0.005, max: 0.25, step: 0.005, value: 0.06 },
        { name: 'eps', label: 'eps', min: 0.1, max: 1.3, step: 0.05, value: 0.6 }
      ],
      overlays: [{ kind: 'hbar', y: 'f(x0)', half: 'eps' }, { kind: 'vband', x: 'x0', half: 'd' }],
      points: [{ x: 'x0', y: 'f(x0)', label: 'A' }, { x: 'x0+d', y: 'f(x0+d)', label: 'B' }],
      segments: [{ x1: 'x0', y1: 'f(x0)', x2: 'x0+d', y2: 'f(x0+d)' }],
      readout: [{ label: 'diff', expr: 'abs(f(x0+d)-f(x0))', digits: 3 }]
    }
  },
  {
    name: 'seq（数列 ε–N）',
    expect: { readout: /N = 10/ },
    spec: {
      type: 'seq', expr: '1/n', nrange: [1, 60], target: 0,
      sliders: [{ name: 'eps', label: 'eps', min: 0.01, max: 0.5, step: 0.01, value: 0.1 }]
    }
  },
  {
    name: 'riemann（定积分）',
    expect: { readout: /0\.2/ },
    spec: {
      type: 'riemann', expr: 'x*x', xrange: [0, 1], yrange: [0, 1.2],
      nslider: { min: 1, max: 60, step: 1, value: 8 }, exact: 1 / 3
    }
  },
  {
    name: 'matrix2（线性变换 / 行列式）',
    expect: { readout: /3\.000/ },
    spec: {
      type: 'matrix2', range: [-3, 3],
      sliders: [
        { name: 'a', label: 'a', min: -2, max: 2, step: 0.05, value: 2 },
        { name: 'b', label: 'b', min: -2, max: 2, step: 0.05, value: 0 },
        { name: 'c', label: 'c', min: -2, max: 2, step: 0.05, value: 0 },
        { name: 'd', label: 'd', min: -2, max: 2, step: 0.05, value: 1.5 }
      ]
    }
  },
  {
    name: 'vectors2（线性相关）',
    expect: { readout: /线性无关/ },
    spec: {
      type: 'vectors2', range: [-3, 3],
      sliders: [
        { name: 'u1', label: 'u1', min: -3, max: 3, step: 0.1, value: 2 },
        { name: 'u2', label: 'u2', min: -3, max: 3, step: 0.1, value: 1 },
        { name: 'v1', label: 'v1', min: -3, max: 3, step: 0.1, value: -1 },
        { name: 'v2', label: 'v2', min: -3, max: 3, step: 0.1, value: 2 }
      ]
    }
  }
];

/* ---------------- 搭桩 + 加载被测代码 ---------------- */
const widgets = CASES.map(c => {
  const box = makeEl('div');
  box.className = 'wb-widget';
  box.setAttribute('data-wb', c.spec.type);
  box.setAttribute('data-spec', Buffer.from(JSON.stringify(c.spec), 'utf8').toString('base64'));
  c.box = box;
  return box;
});

const documentStub = {
  readyState: 'complete',
  createElement: makeEl,
  createTextNode: v => ({ textContent: String(v), children: [] }),
  querySelectorAll: sel => (sel === '.wb-widget' ? widgets : []),
  addEventListener() { },
  body: { appendChild() { }, removeChild() { } }
};
const sandbox = {
  document: documentStub,
  window: { devicePixelRatio: 1, addEventListener() { } },
  atob: s => Buffer.from(s, 'base64').toString('binary'),
  TextDecoder,
  Uint8Array, Math, JSON, isFinite, parseFloat, String, Number, Object, Array,
  console, setTimeout, clearTimeout
};
sandbox.globalThis = sandbox;

let pass = 0, fail = 0;
try {
  vm.runInNewContext(fs.readFileSync(JS_PATH, 'utf8'), sandbox, { filename: 'card-widgets.js' });
} catch (e) {
  console.log(`✗ 加载 card-widgets.js 抛异常：${e.message}`);
  process.exit(1);
}

for (const c of CASES) {
  const box = c.box;
  const err = box.innerHTML && /wb-err/.test(box.innerHTML);
  const canvas = box.children.find(x => x.tagName === 'canvas');
  const ctrls = box.children.find(x => x.className === 'wb-controls');
  const readout = box.children.find(x => x.className === 'wb-readout');
  const rText = readout ? readout.textContent : '';
  const bb = canvas ? bboxOf(canvas._log) : null;
  const problems = [];
  if (err) problems.push('出现错误提示：' + box.innerHTML);
  if (!canvas) problems.push('未生成 canvas');
  if (!ctrls) problems.push('未生成控件');
  if (!readout) problems.push('未生成读数区');
  if (canvas && !bb) problems.push('canvas 上没有任何绘图调用（白板）');
  if (bb && (bb.w < 120 || bb.h < 60)) problems.push(`绘图范围过小（${bb.w.toFixed(0)}×${bb.h.toFixed(0)}），疑似未画出图形`);
  if (c.expect && c.expect.readout && !c.expect.readout.test(rText)) {
    problems.push(`读数不符合预期（期望 ${c.expect.readout}，实际「${rText}」）`);
  }
  if (problems.length) {
    fail++;
    console.log(`✗ ${c.name}`);
    problems.forEach(p => console.log('    - ' + p));
  } else {
    pass++;
    const boxInfo = bb ? `绘图 ${bb.w.toFixed(0)}×${bb.h.toFixed(0)}px / ${canvas._log.length} 次调用` : '';
    console.log(`✓ ${c.name}`);
    console.log(`      读数：${rText}`);
    console.log(`      ${boxInfo}`);
  }
}

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail ? 1 : 0);
