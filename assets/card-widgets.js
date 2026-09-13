/* ============================================================
   card-widgets.js — 概念卡自绘交互组件（零依赖 / 离线可用）
   由 md2card.py 自动注入。扫描 .wb-widget[data-wb][data-spec] 并渲染。
   data-spec = base64(UTF-8 JSON)
   ============================================================ */
(function () {
  'use strict';

  /* ---------------- 表达式编译 ---------------- */
  var FN = {
    sin: 'Math.sin', cos: 'Math.cos', tan: 'Math.tan',
    asin: 'Math.asin', acos: 'Math.acos', atan: 'Math.atan',
    sinh: 'Math.sinh', cosh: 'Math.cosh', tanh: 'Math.tanh',
    exp: 'Math.exp', log: 'Math.log', ln: 'Math.log', sqrt: 'Math.sqrt',
    abs: 'Math.abs', floor: 'Math.floor', ceil: 'Math.ceil', sign: 'Math.sign',
    min: 'Math.min', max: 'Math.max', pow: 'Math.pow',
    pi: 'Math.PI', PI: 'Math.PI', e: 'Math.E', E: 'Math.E'
  };

  // 把一个数学表达式编译为 fn(V, f)；V 含变量值，f 为主函数（供叠加层使用）
  function makeFn(expr, vars, funcs) {
    vars = vars || []; funcs = funcs || [];
    var body = String(expr).replace(/[A-Za-z_][A-Za-z_0-9]*/g, function (t) {
      if (funcs.indexOf(t) >= 0) return t;
      if (FN[t]) return FN[t];
      return 'V.' + t;
    }).replace(/\^/g, '**');
    var raw;
    try { raw = new Function('V', 'f', 'return (' + body + ');'); }
    catch (err) { throw new Error('表达式无法解析：' + expr); }
    return function (V, f) {
      var r;
      try { r = raw(V, f); } catch (e2) { return NaN; }
      return (typeof r === 'number' && isFinite(r)) ? r : NaN;
    };
  }

  /* ---------------- 小工具 ---------------- */
  function el(tag, cls, txt) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }
  function fmtNum(v) {
    if (!isFinite(v)) return '—';
    if (v === 0) return '0';
    var a = Math.abs(v);
    if (a >= 1e5 || a < 1e-4) return v.toExponential(2);
    return String(Math.round(v * 1e4) / 1e4);
  }
  function niceTicks(a, b, count) {
    var span = b - a;
    if (!(span > 0)) return [a];
    var step = Math.pow(10, Math.floor(Math.log10(span / count)));
    var err = span / count / step;
    if (err >= 7.5) step *= 10; else if (err >= 3.5) step *= 5; else if (err >= 1.5) step *= 2;
    var out = [], v = Math.ceil(a / step) * step, guard = 0;
    while (v <= b + step * 1e-6 && guard++ < 200) {
      out.push(Math.abs(v) < step * 1e-6 ? 0 : v);
      v += step;
    }
    return out;
  }
  function b64utf8(s) {
    var bin = atob(s);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder('utf-8').decode(bytes);
  }
  function frame(cv, ratio) {
    var dpr = window.devicePixelRatio || 1;
    var w = cv.clientWidth || 640;
    if (w < 220) w = 640;
    var h = Math.round(w * (ratio || 0.52));
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    cv.style.height = h + 'px';
    var ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx: ctx, W: w, H: h };
  }

  /* ---------------- 坐标系 ---------------- */
  function makeAxes(ctx, W, H, xr, yr, opts) {
    opts = opts || {};
    var pad = opts.square ? { l: 18, r: 18, t: 18, b: 18 } : { l: 50, r: 18, t: 16, b: 34 };
    var iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    function X(x) { return pad.l + (x - xr[0]) / (xr[1] - xr[0]) * iw; }
    function Y(y) { return pad.t + (yr[1] - y) / (yr[1] - yr[0]) * ih; }
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
    if (!opts.square) {
      ctx.strokeStyle = '#eef2f6'; ctx.lineWidth = 1;
      niceTicks(xr[0], xr[1], 6).forEach(function (v) {
        ctx.beginPath(); ctx.moveTo(X(v), pad.t); ctx.lineTo(X(v), pad.t + ih); ctx.stroke();
      });
      niceTicks(yr[0], yr[1], 5).forEach(function (v) {
        ctx.beginPath(); ctx.moveTo(pad.l, Y(v)); ctx.lineTo(pad.l + iw, Y(v)); ctx.stroke();
      });
    }
    // 坐标轴
    ctx.strokeStyle = opts.axisColor || '#9aa6b2'; ctx.lineWidth = 1.4;
    var y0 = Math.max(pad.t, Math.min(pad.t + ih, Y(0)));
    var x0 = Math.max(pad.l, Math.min(pad.l + iw, X(0)));
    ctx.beginPath(); ctx.moveTo(pad.l, y0); ctx.lineTo(pad.l + iw, y0); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x0, pad.t); ctx.lineTo(x0, pad.t + ih); ctx.stroke();
    if (!opts.square) {
      ctx.fillStyle = '#5b6570'; ctx.font = '11px system-ui,-apple-system,sans-serif';
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      niceTicks(xr[0], xr[1], 6).forEach(function (v) { ctx.fillText(fmtNum(v), X(v), pad.t + ih + 6); });
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      niceTicks(yr[0], yr[1], 5).forEach(function (v) { ctx.fillText(fmtNum(v), pad.l - 6, Y(v)); });
    }
    return { X: X, Y: Y, pad: pad, iw: iw, ih: ih, xr: xr, yr: yr, ctx: ctx };
  }

  function drawCurve(A, fn, V, main, color, width, dash) {
    var ctx = A.ctx, xr = A.xr, yr = A.yr;
    var span = yr[1] - yr[0];
    ctx.save();
    ctx.strokeStyle = color; ctx.lineWidth = width || 2.4;
    if (dash) ctx.setLineDash(dash);
    ctx.beginPath();
    var started = false, N = Math.max(A.iw, 2);
    for (var i = 0; i <= N; i++) {
      var x = xr[0] + (xr[1] - xr[0]) * i / N;
      V.x = x;
      var y = fn(V, main);
      if (!isFinite(y) || y < yr[0] - span * 3 || y > yr[1] + span * 3) { started = false; continue; }
      var px = A.X(x), py = A.Y(y);
      if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
    }
    ctx.stroke(); ctx.restore();
  }

  function dot(A, x, y, color, r, label) {
    var ctx = A.ctx;
    ctx.fillStyle = color; ctx.beginPath();
    ctx.arc(A.X(x), A.Y(y), r || 4, 0, Math.PI * 2); ctx.fill();
    if (label) {
      ctx.fillStyle = color; ctx.font = '600 12px system-ui,-apple-system,sans-serif';
      ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
      ctx.fillText(label, A.X(x) + 6, A.Y(y) - 4);
    }
  }

  /* ---------------- 控件 ---------------- */
  function buildControls(box, sliders, onChange) {
    var V = {};
    var wrap = el('div', 'wb-controls');
    (sliders || []).forEach(function (s) {
      V[s.name] = (s.value != null) ? s.value : (s.min + s.max) / 2;
      var lab = el('label', 'wb-ctl');
      lab.appendChild(el('span', 'wb-ctl-name', s.label || s.name));
      var inp = document.createElement('input');
      inp.type = 'range';
      inp.min = s.min; inp.max = s.max; inp.step = s.step || 0.01; inp.value = V[s.name];
      var out = el('span', 'wb-ctl-out', fmtNum(V[s.name]));
      inp.addEventListener('input', function () {
        V[s.name] = parseFloat(inp.value);
        out.textContent = fmtNum(V[s.name]);
        onChange();
      });
      lab.appendChild(inp); lab.appendChild(out);
      wrap.appendChild(lab);
    });
    box.appendChild(wrap);
    return V;
  }

  function buildReadout(box, rows) {
    if (!rows || !rows.length) return null;
    var d = el('div', 'wb-readout');
    d.innerHTML = '';
    box.appendChild(d);
    return {
      el: d,
      update: function (vals) {
        d.innerHTML = '';
        rows.forEach(function (r) {
          var s = el('span', 'wb-ro');
          s.appendChild(el('b', null, r.label + ' = '));
          s.appendChild(document.createTextNode(vals[r.label] != null ? vals[r.label] : '—'));
          d.appendChild(s);
        });
      }
    };
  }

  /* ---------------- 组件：plot ---------------- */
  function renderPlot(box, spec) {
    var cv = el('canvas', 'wb-canvas'); cv.style.display = 'block';
    box.appendChild(cv);
    var varNames = (spec.sliders || []).map(function (s) { return s.name; }).concat(['x']);
    var main = makeFn(spec.expr, varNames, ['f']);
    var xr = spec.xrange, yr = spec.yrange;
    var A, ro;
    // f(t)：把 t 作为自变量求主函数值（不能在叠加层里直接复用 V.x）
    function fOf(t) {
      var tmp = {}; for (var k in V) tmp[k] = V[k];
      tmp.x = t;
      return main(tmp, main);
    }
    function ev(expr) { return makeFn(expr, varNames, ['f'])(V, fOf); }
    function draw() {
      var f = frame(cv, spec.ratio || 0.52);
      A = makeAxes(f.ctx, f.W, f.H, xr, yr);
      var ctx = A.ctx;
      // 叠加层（带 / 条）先画，压在曲线下
      (spec.overlays || []).forEach(function (o) {
        var col = o.color || '#f0a53a';
        if (o.kind === 'hbar') {
          var yc = ev(o.y);
          var h = Math.abs(ev(o.half));
          if (isFinite(yc) && isFinite(h)) {
            ctx.fillStyle = col; ctx.globalAlpha = 0.18;
            ctx.fillRect(A.pad.l, A.Y(yc + h), A.iw, A.Y(yc - h) - A.Y(yc + h));
            ctx.globalAlpha = 1; ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.setLineDash([5, 4]);
            ctx.beginPath(); ctx.moveTo(A.pad.l, A.Y(yc + h)); ctx.lineTo(A.pad.l + A.iw, A.Y(yc + h));
            ctx.moveTo(A.pad.l, A.Y(yc - h)); ctx.lineTo(A.pad.l + A.iw, A.Y(yc - h)); ctx.stroke();
            ctx.setLineDash([]);
            if (o.label) { ctx.fillStyle = col; ctx.font = '12px system-ui,sans-serif'; ctx.textAlign = 'right'; ctx.textBaseline = 'bottom'; ctx.fillText(o.label, A.pad.l + A.iw - 4, A.Y(yc + h) - 3); }
          }
        } else if (o.kind === 'vband') {
          var xc = ev(o.x);
          var hw = Math.abs(ev(o.half));
          if (isFinite(xc) && isFinite(hw)) {
            ctx.fillStyle = col; ctx.globalAlpha = 0.18;
            ctx.fillRect(A.X(xc - hw), A.pad.t, A.X(xc + hw) - A.X(xc - hw), A.ih);
            ctx.globalAlpha = 1; ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.setLineDash([5, 4]);
            ctx.beginPath(); ctx.moveTo(A.X(xc - hw), A.pad.t); ctx.lineTo(A.X(xc - hw), A.pad.t + A.ih);
            ctx.moveTo(A.X(xc + hw), A.pad.t); ctx.lineTo(A.X(xc + hw), A.pad.t + A.ih); ctx.stroke();
            ctx.setLineDash([]);
          }
        }
      });
      drawCurve(A, main, V, main, '#2f6fb3', 2.6);
      // 线段（割线等）
      (spec.segments || []).forEach(function (sg) {
        var x1 = ev(sg.x1), y1 = ev(sg.y1), x2 = ev(sg.x2), y2 = ev(sg.y2);
        if (!isFinite(x1) || !isFinite(x2)) return;
        ctx.strokeStyle = sg.color || '#c2582a'; ctx.lineWidth = 2; ctx.setLineDash(sg.dash || []);
        ctx.beginPath(); ctx.moveTo(A.X(x1), A.Y(y1)); ctx.lineTo(A.X(x2), A.Y(y2)); ctx.stroke();
        ctx.setLineDash([]);
      });
      // 点
      (spec.points || []).forEach(function (p) {
        var x = ev(p.x), y = ev(p.y);
        if (isFinite(x) && isFinite(y)) dot(A, x, y, p.color || '#c2582a', p.r || 4.5, p.label);
      });
      // 数值读出
      if (ro) {
        var vals = {};
        (spec.readout || []).forEach(function (r) {
          var v = ev(r.expr);
          vals[r.label] = (r.digits != null) ? (isFinite(v) ? v.toFixed(r.digits) : '—') : fmtNum(v);
        });
        ro.update(vals);
      }
    }
    var V = buildControls(box, spec.sliders, function () { draw(); });
    ro = buildReadout(box, spec.readout);
    if (spec.hint) box.appendChild(el('p', 'wb-hint', '👉 ' + spec.hint));
    draw();
    return function () { draw(); };
  }

  /* ---------------- 组件：seq（数列 ε-N） ---------------- */
  function renderSeq(box, spec) {
    var cv = el('canvas', 'wb-canvas'); cv.style.display = 'block';
    box.appendChild(cv);
    var varNames = (spec.sliders || []).map(function (s) { return s.name; }).concat(['n']);
    var an = makeFn(spec.expr, varNames, []);
    var n1 = spec.nrange[0], n2 = spec.nrange[1], target = spec.target;
    var A, ro;
    function draw() {
      var V2 = {}; for (var k in V) V2[k] = V[k];
      V2.x = undefined;
      var vals = [];
      for (var n = n1; n <= n2; n++) { V2.n = n; vals.push([n, an(V2, null)]); }
      var lo = Math.min.apply(null, vals.map(function (p) { return isFinite(p[1]) ? p[1] : 0; }).concat([target]));
      var hi = Math.max.apply(null, vals.map(function (p) { return isFinite(p[1]) ? p[1] : 0; }).concat([target]));
      var pad = (hi - lo) * 0.25 || 1;
      var yr = [lo - pad, hi + pad];
      var f = frame(cv, 0.5);
      A = makeAxes(f.ctx, f.W, f.H, [n1 - 1, n2 + 1], yr);
      var ctx = A.ctx, eps = V.eps;
      // ε 带
      ctx.fillStyle = '#f0a53a'; ctx.globalAlpha = 0.18;
      ctx.fillRect(A.pad.l, A.Y(target + eps), A.iw, A.Y(target - eps) - A.Y(target + eps));
      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#f0a53a'; ctx.setLineDash([5, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(A.pad.l, A.Y(target + eps)); ctx.lineTo(A.pad.l + A.iw, A.Y(target + eps));
      ctx.moveTo(A.pad.l, A.Y(target - eps)); ctx.lineTo(A.pad.l + A.iw, A.Y(target - eps)); ctx.stroke();
      ctx.setLineDash([]);
      // 极限线
      ctx.strokeStyle = '#1f8a63'; ctx.lineWidth = 1.6; ctx.setLineDash([6, 4]);
      ctx.beginPath(); ctx.moveTo(A.pad.l, A.Y(target)); ctx.lineTo(A.pad.l + A.iw, A.Y(target)); ctx.stroke();
      ctx.setLineDash([]);
      // 找 N：所有 n>N 都落在带内
      var N = null;
      for (var i = vals.length - 1; i >= 0; i--) {
        var ok = (Math.abs(vals[i][1] - target) < eps);
        if (!ok) { N = vals[i][0]; break; }
      }
      if (N == null) N = n1 - 1;
      var xN = A.X(N + 0.5);
      ctx.strokeStyle = '#c2582a'; ctx.lineWidth = 1.8;
      ctx.beginPath(); ctx.moveTo(xN, A.pad.t); ctx.lineTo(xN, A.pad.t + A.ih); ctx.stroke();
      ctx.fillStyle = '#c2582a'; ctx.font = '600 12px system-ui,sans-serif';
      ctx.textAlign = 'left'; ctx.textBaseline = 'top';
      ctx.fillText('N = ' + N + '（此后全部落入 ε 带）', xN + 4, A.pad.t + 2);
      // 点
      vals.forEach(function (p) {
        if (!isFinite(p[1])) return;
        var inside = Math.abs(p[1] - target) < eps;
        ctx.fillStyle = inside ? '#1f8a63' : '#c2582a';
        ctx.beginPath(); ctx.arc(A.X(p[0]), A.Y(p[1]), 3.2, 0, Math.PI * 2); ctx.fill();
      });
      if (ro) ro.update({ 'N': String(N), '第 N+1 项': fmtNum(vals[Math.max(0, N + 1 - n1)] ? vals[Math.max(0, N + 1 - n1)][1] : NaN) });
    }
    var V = buildControls(box, spec.sliders, function () { draw(); });
    ro = buildReadout(box, [{ label: 'N' }, { label: '第 N+1 项' }]);
    if (spec.hint) box.appendChild(el('p', 'wb-hint', '👉 ' + spec.hint));
    draw();
    return function () { draw(); };
  }

  /* ---------------- 组件：riemann ---------------- */
  function renderRiemann(box, spec) {
    var cv = el('canvas', 'wb-canvas'); cv.style.display = 'block';
    box.appendChild(cv);
    var main = makeFn(spec.expr, ['x'], []);
    var V = { x: 0 };
    var a = spec.xrange[0], b = spec.xrange[1];
    var A, ro;
    function draw() {
      var f = frame(cv, 0.5);
      A = makeAxes(f.ctx, f.W, f.H, spec.xrange, spec.yrange);
      var ctx = A.ctx, n = V.n, dx = (b - a) / n, S = 0;
      ctx.fillStyle = '#6aa3d5'; ctx.globalAlpha = 0.35; ctx.strokeStyle = '#2f6fb3'; ctx.lineWidth = 1;
      for (var i = 0; i < n; i++) {
        var xl = a + i * dx; V.x = xl;
        var y = main(V, null); if (!isFinite(y)) continue;
        S += y * dx;
        var px = A.X(xl), pw = A.X(xl + dx) - A.X(xl), py = A.Y(y), ph = A.Y(0) - A.Y(y);
        ctx.fillRect(px, py, pw, ph);
        if (n <= 40) ctx.strokeRect(px, py, pw, ph);
      }
      ctx.globalAlpha = 1;
      drawCurve(A, main, V, null, '#c2582a', 2.6);
      if (ro) {
        var ex = spec.exact;
        ro.update({
          'n': String(n),
          'S_n': S.toFixed(5),
          '精确值': (ex != null) ? ex.toFixed(5) : '—',
          '误差': (ex != null) ? Math.abs(S - ex).toFixed(5) : '—'
        });
      }
    }
    var V2 = buildControls(box, [{
      name: 'n', label: spec.nslider.label || 'n（分割份数）',
      min: spec.nslider.min, max: spec.nslider.max, step: spec.nslider.step || 1, value: spec.nslider.value
    }], function () { V.n = V2.n; draw(); });
    V.n = V2.n;
    ro = buildReadout(box, [{ label: 'n' }, { label: 'S_n' }, { label: '精确值' }, { label: '误差' }]);
    if (spec.hint) box.appendChild(el('p', 'wb-hint', '👉 ' + spec.hint));
    draw();
    return function () { draw(); };
  }

  /* ---------------- 组件：matrix2（线性变换） ---------------- */
  function renderMatrix2(box, spec) {
    var cv = el('canvas', 'wb-canvas'); cv.style.display = 'block';
    box.appendChild(cv);
    var rng = spec.range || [-3, 3], A, ro;
    function draw() {
      var f = frame(cv, 0.72);
      A = makeAxes(f.ctx, f.W, f.H, rng, rng, { square: true });
      var ctx = A.ctx;
      var a = V.a, b = V.b, c = V.c, d = V.d;
      function T(x, y) { return [a * x + b * y, c * x + d * y]; }
      var R = Math.max(Math.abs(rng[0]), Math.abs(rng[1])) * 2.2, S = 0.25;
      // 原网格
      ctx.strokeStyle = '#e6ebf0'; ctx.lineWidth = 1;
      for (var k = -3; k <= 3; k += 1) {
        ctx.beginPath(); ctx.moveTo(A.X(k), A.Y(rng[0])); ctx.lineTo(A.X(k), A.Y(rng[1])); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(A.X(rng[0]), A.Y(k)); ctx.lineTo(A.X(rng[1]), A.Y(k)); ctx.stroke();
      }
      // 变换后的网格
      ctx.strokeStyle = '#6aa3d5'; ctx.lineWidth = 1.2;
      for (var k2 = -3; k2 <= 3; k2 += 1) {
        var p1 = T(k2, -R), p2 = T(k2, R);
        ctx.beginPath(); ctx.moveTo(A.X(p1[0]), A.Y(p1[1])); ctx.lineTo(A.X(p2[0]), A.Y(p2[1])); ctx.stroke();
        var q1 = T(-R, k2), q2 = T(R, k2);
        ctx.beginPath(); ctx.moveTo(A.X(q1[0]), A.Y(q1[1])); ctx.lineTo(A.X(q2[0]), A.Y(q2[1])); ctx.stroke();
      }
      // 单位正方形 → 像
      var O = T(0, 0), U = T(1, 0), W2 = T(1, 1), Z = T(0, 1);
      ctx.fillStyle = '#c2582a'; ctx.globalAlpha = 0.22;
      ctx.beginPath(); ctx.moveTo(A.X(O[0]), A.Y(O[1])); ctx.lineTo(A.X(U[0]), A.Y(U[1]));
      ctx.lineTo(A.X(W2[0]), A.Y(W2[1])); ctx.lineTo(A.X(Z[0]), A.Y(Z[1])); ctx.closePath(); ctx.fill();
      ctx.globalAlpha = 1; ctx.strokeStyle = '#c2582a'; ctx.lineWidth = 2; ctx.stroke();
      // 列向量
      vec(A, O, U, '#1f8a63', '列1');
      vec(A, O, Z, '#7a4fb3', '列2');
      if (ro) {
        var det = a * d - b * c;
        var rank = Math.abs(det) > 1e-9 ? 2 : (Math.abs(a) + Math.abs(b) + Math.abs(c) + Math.abs(d) > 1e-9 ? 1 : 0);
        ro.update({
          'det': det.toFixed(3),
          '秩': String(rank),
          '像': rank === 2 ? '整个平面（可逆）' : (rank === 1 ? '塌成一条直线' : '塌成一个点')
        });
      }
    }
    var V = buildControls(box, spec.sliders, function () { draw(); });
    ro = buildReadout(box, [{ label: 'det' }, { label: '秩' }, { label: '像' }]);
    if (spec.hint) box.appendChild(el('p', 'wb-hint', '👉 ' + spec.hint));
    draw();
    return function () { draw(); };
  }

  function vec(A, from, to, color, label) {
    var ctx = A.ctx;
    ctx.strokeStyle = color; ctx.lineWidth = 2.6;
    ctx.beginPath(); ctx.moveTo(A.X(from[0]), A.Y(from[1])); ctx.lineTo(A.X(to[0]), A.Y(to[1])); ctx.stroke();
    var ang = Math.atan2(-(to[1] - from[1]), to[0] - from[0]);
    var px = A.X(to[0]), py = A.Y(to[1]), s = 9;
    ctx.fillStyle = color; ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.lineTo(px - s * Math.cos(ang - 0.4), py - s * Math.sin(ang - 0.4));
    ctx.lineTo(px - s * Math.cos(ang + 0.4), py - s * Math.sin(ang + 0.4));
    ctx.closePath(); ctx.fill();
    if (label) {
      ctx.font = '600 12px system-ui,sans-serif'; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
      ctx.fillText(label, px + 6, py - 4);
    }
  }

  /* ---------------- 组件：vectors2（线性相关） ---------------- */
  function renderVectors2(box, spec) {
    var cv = el('canvas', 'wb-canvas'); cv.style.display = 'block';
    box.appendChild(cv);
    var rng = spec.range || [-3, 3], A, ro;
    function draw() {
      var f = frame(cv, 0.68);
      A = makeAxes(f.ctx, f.W, f.H, rng, rng, { square: true });
      var ctx = A.ctx, O = [0, 0];
      var u = [V.u1, V.u2], v = [V.v1, V.v2];
      var det = u[0] * v[1] - u[1] * v[0];
      var dep = Math.abs(det) < 1e-6;
      ctx.strokeStyle = '#e6ebf0'; ctx.lineWidth = 1;
      for (var k = -3; k <= 3; k += 1) {
        ctx.beginPath(); ctx.moveTo(A.X(k), A.Y(rng[0])); ctx.lineTo(A.X(k), A.Y(rng[1])); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(A.X(rng[0]), A.Y(k)); ctx.lineTo(A.X(rng[1]), A.Y(k)); ctx.stroke();
      }
      if (!dep) {
        // 张成整个平面：淡色铺底
        ctx.fillStyle = '#6aa3d5'; ctx.globalAlpha = 0.08;
        ctx.fillRect(A.pad.l, A.pad.t, A.iw, A.ih); ctx.globalAlpha = 1;
      } else {
        // 共线：高亮这条直线
        var L = 6, n0 = Math.hypot(u[0], u[1]) || 1;
        var dx = u[0] / n0, dy = u[1] / n0;
        ctx.strokeStyle = '#c2582a'; ctx.lineWidth = 8; ctx.globalAlpha = 0.18;
        ctx.beginPath(); ctx.moveTo(A.X(-dx * L), A.Y(-dy * L)); ctx.lineTo(A.X(dx * L), A.Y(dy * L)); ctx.stroke();
        ctx.globalAlpha = 1;
      }
      // 平行四边形（行列式的几何意义）
      if (!dep) {
        var S = [u[0] + v[0], u[1] + v[1]];
        ctx.fillStyle = '#c2582a'; ctx.globalAlpha = 0.16;
        ctx.beginPath(); ctx.moveTo(A.X(0), A.Y(0)); ctx.lineTo(A.X(u[0]), A.Y(u[1]));
        ctx.lineTo(A.X(S[0]), A.Y(S[1])); ctx.lineTo(A.X(v[0]), A.Y(v[1])); ctx.closePath(); ctx.fill();
        ctx.globalAlpha = 1;
      }
      vec(A, O, u, '#1f8a63', 'u');
      vec(A, O, v, '#7a4fb3', 'v');
      if (ro) {
        ro.update({
          'det(u,v)': det.toFixed(3),
          '判定': dep ? '线性相关（共线）' : '线性无关',
          '张成空间': dep ? (Math.hypot(u[0], u[1]) + Math.hypot(v[0], v[1]) < 1e-9 ? '零空间 {0}' : '一条直线（1 维）') : '整个平面（2 维）'
        });
      }
    }
    var V = buildControls(box, spec.sliders, function () { draw(); });
    ro = buildReadout(box, [{ label: 'det(u,v)' }, { label: '判定' }, { label: '张成空间' }]);
    if (spec.hint) box.appendChild(el('p', 'wb-hint', '👉 ' + spec.hint));
    draw();
    return function () { draw(); };
  }

  /* ---------------- 复制到剪贴板（GeoGebra 指令块 / 模拟代码块共用） ---------------- */
  function copyToClipboard(txt, done) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(done, function () { fallbackCopy(txt, done); });
    } else fallbackCopy(txt, done);
  }
  function fallbackCopy(txt, done) {
    var ta = document.createElement('textarea');
    ta.value = txt; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); done(); } catch (e) { }
    document.body.removeChild(ta);
  }

  function bindCopy() {
    document.querySelectorAll('.gb-copy').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var blk = btn.closest('.gb-block');
        var code = blk ? blk.querySelector('code') : null;
        if (!code) return;
        copyToClipboard(code.textContent, function () {
          btn.textContent = '已复制 ✓'; setTimeout(function () { btn.textContent = '复制指令'; }, 1600);
        });
      });
    });
  }

  /* ---------------- 模拟代码选项卡（sim 块：默认 Python，可切换 R） ---------------- */
  function bindSimTabs() {
    document.querySelectorAll('.sim-block').forEach(function (blk) {
      var tabs = blk.querySelectorAll('.sim-tab');
      tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
          var lang = tab.getAttribute('data-lang');
          tabs.forEach(function (t) { t.classList.toggle('is-active', t === tab); });
          blk.querySelectorAll('.sim-pane').forEach(function (p) {
            p.classList.toggle('is-active', p.getAttribute('data-lang') === lang);
          });
          var c = blk.querySelector('.sim-copy');
          if (c) c.textContent = '复制代码';
        });
      });
    });
    document.querySelectorAll('.sim-copy').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var blk = btn.closest('.sim-block');
        var code = blk ? blk.querySelector('.sim-pane.is-active code') : null;
        if (!code) return;
        copyToClipboard(code.textContent, function () {
          btn.textContent = '已复制 ✓'; setTimeout(function () { btn.textContent = '复制代码'; }, 1600);
        });
      });
    });
  }

  /* ---------------- 折叠面（渐进揭示） ---------------- */
  function bindFacets(redrawAll) {
    var all = document.querySelectorAll('details.facet');
    if (!all.length) return;
    document.querySelectorAll('.facet-toggle').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var isOpen = btn.getAttribute('data-open') === '1';
        all.forEach(function (d) { d.open = !isOpen; });
        btn.setAttribute('data-open', isOpen ? '0' : '1');
        btn.textContent = isOpen ? '展开全部' : '收起全部';
        if (redrawAll) setTimeout(redrawAll, 40);
      });
    });
    // 折叠时 canvas 宽度为 0，展开后需重绘
    all.forEach(function (d) {
      d.addEventListener('toggle', function () { if (d.open && redrawAll) setTimeout(redrawAll, 40); });
    });
    // 打印前把所有折叠面打开，保证纸质版内容完整
    window.addEventListener('beforeprint', function () {
      document.querySelectorAll('details').forEach(function (d) { d.open = true; });
      if (redrawAll) redrawAll();
    });
  }

  /* ---------------- 初始化 ---------------- */
  var RENDER = {
    plot: renderPlot, seq: renderSeq, riemann: renderRiemann,
    matrix2: renderMatrix2, vectors2: renderVectors2
  };

  function init() {
    var widgets = [];
    document.querySelectorAll('.wb-widget').forEach(function (box) {
      var kind = box.getAttribute('data-wb');
      var specStr = box.getAttribute('data-spec') || '';
      var spec;
      try { spec = JSON.parse(b64utf8(specStr)); }
      catch (e) { box.innerHTML = '<p class="wb-err">组件参数解析失败：' + e.message + '</p>'; return; }
      var fn = RENDER[kind];
      if (!fn) { box.innerHTML = '<p class="wb-err">未知组件类型：' + kind + '</p>'; return; }
      var redraw;
      try { redraw = fn(box, spec); }
      catch (e2) { box.innerHTML = '<p class="wb-err">组件渲染失败：' + e2.message + '</p>'; return; }
      widgets.push(redraw);
    });
    if (widgets.length) {
      var t = null;
      window.addEventListener('resize', function () {
        clearTimeout(t); t = setTimeout(function () { widgets.forEach(function (f) { try { f(); } catch (e) { } }); }, 160);
      });
    }
    bindCopy();
    bindSimTabs();
    bindFacets(function () {
      widgets.forEach(function (f) { try { f(); } catch (e) { } });
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
