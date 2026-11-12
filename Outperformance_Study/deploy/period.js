/* Period test: the whole analysis re-run in the browser for any analysis and testing period.
 *
 * Years are RETURN years: return year Y is paired with parameter year Y - 1. Analysis period: the
 * Statistical analysis (Fama-MacBeth slopes, Newey-West t and p) and each fifth's average
 * excess. Testing period: every fund is placed in a fifth by its parameter, predicted that fifth's analysis
 * average, and compared with what happened. Nothing from the testing period reaches the analysis.
 * Same formulas as stats_analysis.py and stats_prediction.py; panel = window.PANEL (panel.js).
 */
(function (root) {
  var TARGET = 3, EXCESS_MIN = 0.01, MIN_CALLS = 30, Z_CAP = 3, ALPHA = 0.05, UNIQUE_RHO = 0.80, UNIQUE_MIN = 30;
  var MIN_FUNDS_PER_YEAR = 5, MIN_YEARS = 3, QUINTILE_MIN_FUNDS = 10, MAX_FALLBACK = 5, NW_LAGS = 1;
  var ALL = "All funds", OFFSET = 4;
  var TIERS = ["Robust", "Significant (p ≤ 0.05), not Robust", "Strongest by t-statistic, not significant", "none"];
  var STATUS = ["Unique", "Version of", "Moves with"];
  var PREVIOUS = [["Value at Risk", "Value at Risk", 0.62], ["Covariance", "Covariance", 0.47], ["Standard Deviation", "Std Dev (Annualized)", 0.47],
    ["Semi Deviation", "Semi Dev (Annualized)", 0.40], ["Point-to-Point Return", "Return (Cumulative)", -0.44],
    ["Efficiency Ratio", "Efficiency Ratio (arith) (Annualized)", -0.52], ["Down Capture Return", "Down Capture Return", -0.59],
    ["Longest Down-Streak Return", "Longest Down-Streak Return", -0.65], ["Average Drawdown", "Average Drawdown", -0.68]];
  var BASKETS = ["below 0%"]; for (var bk = 0; bk < 10; bk++) BASKETS.push(bk + "-" + (bk + 1) + "%"); BASKETS.push("10% and above");

  function mean(a) { var s = 0; for (var i = 0; i < a.length; i++) s += a[i]; return s / a.length; }
  function basketIndex(v) { return v < 0 ? 0 : v >= 10 ? BASKETS.length - 1 : Math.floor(v) + 1; }
  function family(name) {
    return name.replace(/\((Annualized|arith|geo|non-excess return)\)/g, "").replace(/ Population/g, "").replace(/R-Squared/g, "R2").trim().replace(/\s+/g, " "); }

  // ---- distributions
  function gammaln(x) { var c = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
    var y = x, t = x + 5.5, s = 1.000000000190015; t -= (x + 0.5) * Math.log(t);
    for (var j = 0; j < 6; j++) s += c[j] / ++y;
    return -t + Math.log(2.5066282746310005 * s / x); }
  function betacf(a, b, x) { var qab = a + b, qap = a + 1, qam = a - 1, c = 1, d = 1 - qab * x / qap;
    if (Math.abs(d) < 1e-300) d = 1e-300; d = 1 / d; var h = d;
    for (var m = 1; m <= 300; m++) { var m2 = 2 * m, aa = m * (b - m) * x / ((qam + m2) * (a + m2));
      d = 1 + aa * d; if (Math.abs(d) < 1e-300) d = 1e-300; c = 1 + aa / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; h *= d * c;
      aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
      d = 1 + aa * d; if (Math.abs(d) < 1e-300) d = 1e-300; c = 1 + aa / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d;
      var del = d * c; h *= del; if (Math.abs(del - 1) < 1e-14) break; }
    return h; }
  function ibeta(a, b, x) { if (x <= 0) return 0; if (x >= 1) return 1;
    var bt = Math.exp(gammaln(a + b) - gammaln(a) - gammaln(b) + a * Math.log(x) + b * Math.log(1 - x));
    return x < (a + 1) / (a + b + 2) ? bt * betacf(a, b, x) / a : 1 - bt * betacf(b, a, 1 - x) / b; }
  function tP(t, df) { return ibeta(df / 2, 0.5, df / (df + t * t)); }   // two-sided

  // ---- one year's slope and rank IC
  function ranks(a) { var idx = a.map(function (_, i) { return i; }).sort(function (x, y) { return a[x] - a[y]; }), out = new Array(a.length), i = 0;
    while (i < idx.length) { var j = i; while (j + 1 < idx.length && a[idx[j + 1]] === a[idx[i]]) j++;
      for (var k = i; k <= j; k++) out[idx[k]] = (i + j) / 2 + 1; i = j + 1; }
    return out; }
  function pearson(x, y) { var mx = mean(x), my = mean(y), sxy = 0, sx = 0, sy = 0;
    for (var i = 0; i < x.length; i++) { var a = x[i] - mx, b = y[i] - my; sxy += a * b; sx += a * a; sy += b * b; }
    return sx > 0 && sy > 0 ? sxy / Math.sqrt(sx * sy) : NaN; }
  function distinct(a) { var s = {}, n = 0; a.forEach(function (v) { if (!s[v]) { s[v] = 1; n++; } }); return n; }
  function slopeOf(xs, ys) {
    if (xs.length < MIN_FUNDS_PER_YEAR || distinct(xs) < 3) return null;
    var m = mean(xs), ss = 0; xs.forEach(function (v) { ss += (v - m) * (v - m); });
    var sd = Math.sqrt(ss / (xs.length - 1)); if (!isFinite(sd) || sd === 0) return null;
    var z = xs.map(function (v) { return Math.max(-Z_CAP, Math.min(Z_CAP, (v - m) / sd)); }), mz = mean(z), my = mean(ys), sxy = 0, szz = 0;
    for (var i = 0; i < z.length; i++) { var c = z[i] - mz; sxy += c * (ys[i] - my); szz += c * c; }
    return { slope: sxy / szz, ic: distinct(ys) > 1 ? pearson(ranks(xs), ranks(ys)) : NaN, n: xs.length }; }
  function neweyWest(x) { var n = x.length; if (n < 3) return NaN;
    var m = mean(x), e = x.map(function (v) { return v - m; }), g0 = 0, run = 0, i;
    for (i = 0; i < n; i++) g0 += e[i] * e[i]; g0 /= n; run = g0;
    for (var lag = 1; lag <= Math.min(NW_LAGS, n - 1); lag++) { var w = 1 - lag / (NW_LAGS + 1), s = 0;
      for (i = lag; i < n; i++) s += e[i] * e[i - lag]; run += 2 * w * s / n; }
    return Math.sqrt(Math.max(run, g0 * 0.25) / n); }

  // ---- a year's cross-section: pairs [[value, excess, row], ...] in data order
  function byYear(rows, col, first, last) { var out = {};
    for (var y = first; y <= last; y++) out[y] = [];
    rows.forEach(function (r) { var v = r[col]; if (v !== null && r[3] !== null && out[r[0]]) out[r[0]].push([v, r[3], r]); });
    return out; }
  function stat(hist, first, last) {
    var yrs = [];
    for (var y = first; y <= last; y++) { var s = slopeOf(hist[y].map(function (p) { return p[0]; }), hist[y].map(function (p) { return p[1]; }));
      if (s) { s.year = y; yrs.push(s); } }
    var out = { years: yrs.length, yearly: yrs, status: "insufficient" };
    if (yrs.length < MIN_YEARS) return out;
    var sl = yrs.map(function (s) { return s.slope; }), se = neweyWest(sl), m = mean(sl), t = se > 0 ? m / se : NaN, half = Math.floor(sl.length / 2);
    var ics = yrs.map(function (s) { return s.ic; }).filter(isFinite);
    out.status = "ok"; out.slope = m; out.se = se; out.t = t; out.p = isFinite(t) ? tP(t, sl.length - 1) : NaN;
    out.ic = ics.length ? mean(ics) : NaN; out.sharePos = sl.filter(function (v) { return v > 0; }).length / sl.length;
    out.first = mean(sl.slice(0, half)); out.second = mean(sl.slice(half));
    out.stable = Math.sign(out.first) === Math.sign(out.second) && out.first !== 0;
    return out; }
  function verdict(s) { if (s.status !== "ok") return "Insufficient data";
    if (s.p <= ALPHA && s.stable) return "Robust";
    return s.p <= ALPHA ? "Significant, not robust" : "Not significant"; }

  // ---- fifths: 1..5 by value (ties in data order), as pd.qcut(rank(method="first"), 5)
  function fifths(pairs) { var n = pairs.length;
    if (n < QUINTILE_MIN_FUNDS || distinct(pairs.map(function (p) { return p[0]; })) < 5) return null;
    var idx = pairs.map(function (_, i) { return i; }).sort(function (a, b) { return pairs[a][0] - pairs[b][0] || a - b; }), out = new Array(n);
    idx.forEach(function (i, r) { out[i] = Math.max(1, Math.min(5, Math.ceil(r * 5 / (n - 1) - 1e-9))); });
    return out; }
  function fifthAverages(hist, first, last) {
    var perYear = [];
    for (var y = first; y <= last; y++) { var k = fifths(hist[y]); if (!k) continue;
      var sum = [0, 0, 0, 0, 0], cnt = [0, 0, 0, 0, 0];
      k.forEach(function (q, i) { sum[q - 1] += hist[y][i][1]; cnt[q - 1]++; });
      perYear.push({ year: y, avg: sum.map(function (s, i) { return s / cnt[i]; }) }); }
    if (perYear.length < MIN_YEARS) return null;
    return { years: perYear.length, perYear: perYear, avg: [0, 1, 2, 3, 4].map(function (q) { return mean(perYear.map(function (x) { return x.avg[q]; })); }) }; }

  // ---- the test of one parameter
  function evaluate(rows, col, o, naive, P) {
    var a0 = o.aFrom - 1, a1 = o.aTo - 1, t0 = o.tFrom - 1, t1 = o.tTo - 1, ha = byYear(rows, col, a0, a1), ht = byYear(rows, col, t0, t1), fa = fifthAverages(ha, a0, a1);
    var b = { calls: 0, hits: 0, naive: 0, tol: 0, naiveTol: 0, ge: 0, naiveGe: 0, dev: 0, naiveDev: 0, abs: 0, naiveAbs: 0, called: 0, calledRight: 0, beat: 0, pos: 0, posHit: 0,
      quint: fa ? fa.avg : null, quintYears: fa ? fa.years : 0, perYear: fa ? fa.perYear : [], years: [], detail: [], baskets: BASKETS.map(function () { return [0, 0, 0, 0, 0]; }) };
    if (!fa) return b;
    for (var y = t0; y <= t1; y++) { var k = fifths(ht[y]); if (!k) continue;
      var yr = { year: y + 1, funds: 0, hits: 0, naive: 0, called: 0, beat: 0, tol: 0, ge: 0, pos: 0, posHit: 0 };
      k.forEach(function (q, i) { var p = ht[y][i], pred = fa.avg[q - 1], act = p[1], call = pred >= TARGET, beat = act >= TARGET, nc = naive >= TARGET, d = act - pred, nd = act - naive, bi = basketIndex(pred);
        var right = call === beat, nright = nc === beat;
        b.calls++; b.hits += right; b.naive += nright; b.tol += Math.abs(d) <= o.tol; b.naiveTol += Math.abs(nd) <= o.tol; b.ge += act >= pred; b.naiveGe += act >= naive;
        b.dev += d; b.naiveDev += nd; b.abs += Math.abs(d); b.naiveAbs += Math.abs(nd); b.called += call; b.calledRight += call && beat; b.beat += beat;
        yr.funds++; yr.hits += right; yr.naive += nright; yr.called += call; yr.beat += beat; yr.tol += Math.abs(d) <= o.tol; yr.ge += act >= pred;
        if (pred >= EXCESS_MIN) { b.pos++; yr.pos++; if (act > 0) { b.posHit++; yr.posHit++; } }
        var s = b.baskets[bi]; s[0]++; s[1] += pred; s[2] += act; s[3] += beat; s[4] += Math.abs(d);
        b.detail.push({ year: y + 1, fund: P.funds[p[2][2]], value: p[0], fifth: q, pred: pred, actual: act }); });
      b.years.push(yr); }
    return b; }
  function feasible(b, how, cut) { if (!b || b.calls < MIN_CALLS) return false;
    var r = how === "diff" ? [b.tol, b.naiveTol] : how === "ge" ? [b.ge, b.naiveGe] : [b.hits, b.naive];
    return r[0] / b.calls > cut && r[0] > r[1]; }

  // ---- unique parameters, strongest first: as stats_prediction.select
  function rankColumn(rows, col) { var idx = [], vals = []; rows.forEach(function (r, i) { if (r[col] !== null) { idx.push(i); vals.push(r[col]); } });
    var rk = ranks(vals), out = rows.map(function () { return null; }); idx.forEach(function (i, n) { out[i] = rk[n]; }); return out; }
  function rankCorr(a, b) { var x = [], y = []; for (var i = 0; i < a.length; i++) if (a[i] !== null && b[i] !== null) { x.push(a[i]); y.push(b[i]); }
    return x.length >= UNIQUE_MIN ? Math.abs(pearson(x, y)) : NaN; }
  function pick(cands, rows, P, limit) {
    var best = {}, order = [], status = {};
    cands.forEach(function (c) { var f = family(c.parameter);
      if (best[f]) status[c.parameter] = [1, best[f]]; else { best[f] = c.parameter; order.push(c); } });
    var kept = [], cache = {};
    function rc(c) { return cache[c.parameter] || (cache[c.parameter] = rankColumn(rows, c.col)); }
    order.forEach(function (c) {
      if (limit && kept.length >= limit) { status[c.parameter] = [3, null]; return; }
      var twin = null;
      for (var i = 0; i < kept.length && !twin; i++) { var v = rankCorr(rc(c), rc(kept[i])); if (isFinite(v) && v > UNIQUE_RHO) twin = kept[i].parameter; }
      if (twin) status[c.parameter] = [2, twin]; else { status[c.parameter] = [0, null]; kept.push(c); } });
    return { kept: kept, status: status }; }

  function run(P, o) {
    var catIdx = o.group === ALL ? -1 : P.categories.indexOf(o.group);
    var rows = P.rows.filter(function (r) { return catIdx < 0 || r[1] === catIdx; });
    var a0 = o.aFrom - 1, a1 = o.aTo - 1, ana = rows.filter(function (r) { return r[0] >= a0 && r[0] <= a1; }), test = rows.filter(function (r) { return r[0] >= o.tFrom - 1 && r[0] <= o.tTo - 1; });
    // the group's average excess over the analysis years: the naive prediction for every fund
    var means = {}; ana.forEach(function (r) { if (r[3] !== null) (means[r[0]] = means[r[0]] || []).push(r[3]); });
    var naive = mean(Object.keys(means).map(function (y) { return mean(means[y]); }));
    var stats = P.parameters.map(function (name, i) { var col = OFFSET + i, s = stat(byYear(ana, col, a0, a1), a0, a1); s.parameter = name; s.col = col; return s; });
    stats.forEach(function (s) { s.verdict = verdict(s); });
    // data requirement: the share of each period's years in which a parameter can be used
    var nA = o.aYears || (o.aTo - o.aFrom + 1), nT = o.tYears || (o.tTo - o.tFrom + 1), t0 = o.tFrom - 1, t1 = o.tTo - 1;
    stats.forEach(function (s) { var h = o.tFrom ? byYear(test, s.col, t0, t1) : null, n = 0; if (h) for (var y = t0; y <= t1; y++) if (fifths(h[y])) n++;
      s.testYears = n; s.analysisTotal = nA; s.testTotal = o.tFrom ? nT : 0;
      s.eligible = s.years / nA >= (o.minA || 0) && (!o.tFrom || n / nT >= (o.minT || 0)); });
    function byP(a, b) { return a.p - b.p; }
    var ok = stats.filter(function (s) { return s.eligible && s.status === "ok" && isFinite(s.p); }), cands = ok.filter(function (s) { return s.verdict === "Robust"; }), tier = 0, limit = 0;
    if (!cands.length) { cands = ok.filter(function (s) { return s.p <= ALPHA; }); tier = 1; }
    if (!cands.length) { cands = ok; tier = 2; limit = MAX_FALLBACK; }
    if (!cands.length) tier = 3;
    cands = cands.slice().sort(byP);
    var sel = pick(cands, ana, P, limit);
    var full = rows, tested = sel.kept.map(function (c) { return { name: c.parameter, col: c.col, stat: c, bt: evaluate(full, c.col, o, naive, P) }; });
    var prev = PREVIOUS.map(function (p) { var s = stats.filter(function (x) { return x.parameter === p[1]; })[0];
      return { name: p[0], col: s.col, corr: p[2], column: p[1], stat: s, bt: evaluate(full, s.col, o, naive, P) }; });
    // the hit-ratio table lists every parameter; the shortlist stays the analysis period's own choice
    var every = !o.tFrom ? [] : stats.map(function (s) { var t = tested.filter(function (x) { return x.col === s.col; })[0];
      if (t) { t.shortlisted = true; return t; }
      return { name: s.parameter, col: s.col, stat: s, shortlisted: false, bt: evaluate(full, s.col, o, naive, P) }; });
    return { options: o, naive: naive, all: every, tier: tier, tierName: TIERS[tier], stats: stats, status: sel.status, tested: tested, previous: prev, candidates: cands.length,
      funds: { analysis: distinctFunds(ana), test: distinctFunds(test) }, obs: { analysis: ana.length, test: test.length } }; }
  function distinctFunds(rows) { var s = {}, n = 0; rows.forEach(function (r) { if (!s[r[2]]) { s[r[2]] = 1; n++; } }); return n; }

  // ---- the Excel workbook: every prediction with formulas, summaries built on them
  function sheets(R, P) {
    var o = R.options, F = function (f, v) { return { t: typeof v === "string" ? "s" : "n", v: v, f: f }; }, sets = [["Custom test", R.tested], ["Previous parameter", R.previous]], c = [];
    var head = ["Set", "Parameter", "Return year", "Parameter year", "Fund", "Parameter value", "Fifth", "Predicted excess %", "Actual excess %", "Naive prediction %", "3%+ call right", "Naive 3%+ call right",
      "Within tolerance", "Naive within tolerance", "Actual >= predicted", "Naive: actual >= predicted", "Deviation (actual - predicted)", "Naive deviation", "Miss", "Naive miss", "Basket (predicted excess)", "Excess hit (predicted 0.01%+, actual above 0)"];
    c.push(head);
    var TOL = "Read_Me!$B$9";
    sets.forEach(function (s) { s[1].forEach(function (x) { x.bt.detail.forEach(function (d) { var r = c.length + 1, dv = d.actual - d.pred, nd = d.actual - R.naive;
      c.push([s[0], x.name, d.year, d.year - 1, d.fund, d.value, d.fifth, d.pred, d.actual, R.naive,
        F("IF((H" + r + ">=" + TARGET + ")=(I" + r + ">=" + TARGET + "),1,0)", +((d.pred >= TARGET) === (d.actual >= TARGET))), F("IF((J" + r + ">=" + TARGET + ")=(I" + r + ">=" + TARGET + "),1,0)", +((R.naive >= TARGET) === (d.actual >= TARGET))),
        F("IF(S" + r + "<=" + TOL + ",1,0)", +(Math.abs(dv) <= o.tol)), F("IF(T" + r + "<=" + TOL + ",1,0)", +(Math.abs(nd) <= o.tol)), F("IF(I" + r + ">=H" + r + ",1,0)", +(d.actual >= d.pred)), F("IF(I" + r + ">=J" + r + ",1,0)", +(d.actual >= R.naive)),
        F("I" + r + "-H" + r, dv), F("I" + r + "-J" + r, nd), F("ABS(Q" + r + ")", Math.abs(dv)), F("ABS(R" + r + ")", Math.abs(nd)), BASKETS[basketIndex(d.pred)],
        F("IF(H" + r + ">=" + EXCESS_MIN + ",IF(I" + r + '>0,1,0),"")', d.pred >= EXCESS_MIN ? +(d.actual > 0) : "")]); }); }); });
    var last = c.length, C = function (l) { return "Calls!$" + l + "$2:$" + l + "$" + last; };
    var rh = ["Set", "Parameter", "Verdict in the analysis period", "Slope (pts per 1 SD)", "t", "p", "Predictions", "3%+ call right", "Hit ratio", "Naive right", "Naive hit ratio", "Within tolerance", "Hit ratio", "Naive within", "Naive hit ratio",
      "Actual >= predicted", "Hit ratio", "Naive", "Naive hit ratio", "Average deviation", "Naive average deviation", "Average miss", "Naive average miss", "Feasible (3%+ call)", "Predicted 0.01%+", "Of those, actual above 0", "Excess hit ratio"], res = [rh];
    sets.forEach(function (s) { s[1].forEach(function (x) { var r = res.length + 1, b = x.bt, n = b.calls, k = C("A") + ",$A" + r + "," + C("B") + ",$B" + r;
      function cnt(l, v) { return F("SUMIFS(" + C(l) + "," + k + ")", v); }
      function rat(l, v) { return F("IF($G" + r + ">0," + l + r + "/$G" + r + ',"")', n ? v / n : ""); }
      function avg(l, v) { return F("IF($G" + r + ">0,SUMIFS(" + C(l) + "," + k + ")/$G" + r + ',"")', n ? v / n : ""); }
      res.push([s[0], x.name, x.stat.verdict, cl(x.stat.slope), cl(x.stat.t), cl(x.stat.p), F("COUNTIFS(" + k + ")", n), cnt("K", b.hits), rat("H", b.hits), cnt("L", b.naive), rat("J", b.naive), cnt("M", b.tol), rat("L", b.tol), cnt("N", b.naiveTol), rat("N", b.naiveTol),
        cnt("O", b.ge), rat("P", b.ge), cnt("P", b.naiveGe), rat("R", b.naiveGe), avg("Q", b.dev), avg("R", b.naiveDev), avg("S", b.abs), avg("T", b.naiveAbs),
        F("IF(AND($G" + r + ">=" + MIN_CALLS + ",I" + r + ">Read_Me!$B$10,H" + r + ">J" + r + '),"Yes","no")', x.stat.eligible ? (feasible(b, "call", o.cut) ? "Yes" : "no") : "too little data"),
        F("COUNTIFS(" + k + "," + C("V") + ',">=0")', b.pos), cnt("V", b.posHit), F("IF(Y" + r + ">0,Z" + r + "/Y" + r + ',"")', b.pos ? b.posHit / b.pos : "")]); }); });
    var yr = [["Set", "Parameter", "Return year", "Funds", "Called 3%+", "Actually beat 3%+", "3%+ call right", "Hit ratio", "Naive right", "Within tolerance", "Actual >= predicted", "Predicted 0.01%+", "Of those, actual above 0", "Excess hit ratio"]];
    var fi = [["Set", "Parameter", "Analysis years used", "Q1 (lowest) avg excess %", "Q2", "Q3", "Q4", "Q5 (highest)", "Naive (group average) %"]];
    var bs = [["Set", "Parameter", "Basket (predicted excess)", "Predictions", "Average predicted %", "Average actual %", "Average deviation", "Average miss", "Actually beat 3%+", "Share that beat"]];
    sets.forEach(function (s) { s[1].forEach(function (x) { var b = x.bt;
      b.years.forEach(function (t) { yr.push([s[0], x.name, t.year, t.funds, t.called, t.beat, t.hits, t.funds ? t.hits / t.funds : "", t.naive, t.tol, t.ge, t.pos, t.posHit, t.pos ? t.posHit / t.pos : ""]); });
      fi.push([s[0], x.name, b.quintYears].concat(b.quint || ["", "", "", "", ""]).concat([R.naive]));
      b.baskets.forEach(function (k, i) { if (k[0]) bs.push([s[0], x.name, BASKETS[i], k[0], k[1] / k[0], k[2] / k[0], (k[2] - k[1]) / k[0], k[4] / k[0], k[3], k[3] / k[0]]); }); }); });
    var sh = ["Parameter", "Verdict", "Years", "Slope (pts per 1 SD)", "SE", "t", "p", "Rank IC", "Share of years positive", "First half slope", "Second half slope", "Earlier correlation"];
    function statRow(s, corr) { return [s.parameter, s.verdict, s.years, cl(s.slope), cl(s.se), cl(s.t), cl(s.p), cl(s.ic), cl(s.sharePos), cl(s.first), cl(s.second), corr]; }
    var pst = [sh].concat(R.previous.map(function (x) { return statRow(x.stat, x.corr); }));
    var all = [sh.slice(0, -1).concat(["Status"])].concat(R.stats.slice().sort(function (a, b) { return (isFinite(a.p) ? a.p : 9) - (isFinite(b.p) ? b.p : 9); }).map(function (s) {
      var st = R.status[s.parameter]; return statRow(s, st ? (st[0] === 3 ? "Candidate, past the limit" : STATUS[st[0]] + (st[1] ? " " + st[1] : "")) : ""); }));
    var ah = [["Parameter", "Shortlisted", "Verdict in the analysis period", "t", "p", "Predictions", "Called 3%+", "3%+ call right", "3%+ hit ratio", "Actual >= predicted", "Hit ratio", "Predicted 0.01%+", "Of those, actual above 0", "Excess hit ratio", "Average deviation", "Feasible (3%+ call)", "Analysis years with data", "Testing years with data"]];
    (R.all || []).filter(function (x) { return x.stat.eligible; }).forEach(function (x) { var b = x.bt, n = b.calls; ah.push([x.name, x.shortlisted ? "Yes" : "no", x.stat.verdict, cl(x.stat.t), cl(x.stat.p), n, b.called, b.hits, n ? b.hits / n : "", b.ge, n ? b.ge / n : "", b.pos, b.posHit, b.pos ? b.posHit / b.pos : "", n ? b.dev / n : "", feasible(b, "call", o.cut) ? "Yes" : "no", x.stat.years + " of " + x.stat.analysisTotal, x.stat.testYears + " of " + x.stat.testTotal]); });
    var me = [["Period test: how to read this workbook"], [], ["Group", o.group], ["Analysis (return years)", o.aFrom + "-" + o.aTo], ["Analysis (parameter years)", (o.aFrom - 1) + "-" + (o.aTo - 1)],
      ["Testing (return years)", o.tFrom + "-" + o.tTo], ["Testing (parameter years)", (o.tFrom - 1) + "-" + (o.tTo - 1)], ["Target (beat the Nifty 50 by, points)", TARGET], ["Tolerance (points, change me)", o.tol],
      ["Hit-ratio cut for feasible (change me)", o.cut], ["Naive prediction (group's analysis average, %)", R.naive], ["Parameters tested", R.tierName], ["Data needed", "Analysis: " + Math.round(100 * (o.minA || 0)) + "% of years; testing: " + Math.round(100 * (o.minT || 0)) + "% of years"], [],
      ["Sheets"], ["All_Hit_Ratios", "The hit ratios of all 101 parameters, as values."], ["Results", "The shortlisted and previous parameters: three hit ratios vs naive, deviation and miss. Counts are formulas over Calls."], ["Calls", "Every test prediction of the shortlisted and previous parameters: value, fifth, predicted, actual, and the checks as formulas."],
      ["Yearly", "The same results split by return year."], ["Fifth_Averages", "Each fifth's average next-year excess in the analysis period: these are the predictions."], ["Baskets", "Predictions grouped by predicted excess, with what each basket actually delivered."],
      ["Previous_Stats", "Statistical results of the nine previous parameters in the analysis period."], ["All_Parameters", "Statistical results of all 101 parameters in the analysis period."], [],
      ["Verify by hand"], ["1", "Pick a row in Calls. Find its Set and Parameter in Fifth_Averages, and the fund's Fifth: that column is Predicted excess %."], ["2", "3%+ call right = 1 when predicted >= 3 and actual >= 3 agree (both yes or both no)."],
      ["3", "Filter Calls to one Set and Parameter: Sum of '3%+ call right' / row count = the Results hit ratio."], ["4", "Change the tolerance or cut above: Results recalculates."],
      ["Feasible", "3%+ hit ratio above the cut, more right than naive, and at least " + MIN_CALLS + " predictions."]];
    if (!o.tFrom) return [["Read_Me", [["Analysis only: no testing was run"], [], ["Group", o.group], ["Analysis (return years)", o.aFrom + "-" + o.aTo], ["Analysis (parameter years)", (o.aFrom - 1) + "-" + (o.aTo - 1)],
        ["All_Parameters", "Statistical results of all 101 parameters."], ["Previous_Stats", "Statistical results of the nine previous parameters."], ["Fifth_Averages", "Each fifth's average next-year excess for the shortlisted and previous parameters."]], [44, 90]],
      ["All_Parameters", all, [38, 22, 7, 9, 8, 8, 8, 8, 8, 9, 9, 9, 40]], ["Previous_Stats", pst, [36, 22, 7, 9, 8, 8, 8, 8, 8, 9, 9, 9, 10]], ["Fifth_Averages", fi, [18, 34, 9, 10, 9, 9, 9, 9, 10]]];
    return [["Read_Me", me, [44, 90]], ["All_Hit_Ratios", ah, [40, 9, 22, 7, 7, 9, 8, 8, 8, 9, 8, 9, 9, 8, 9, 10]], ["Results", res, [18, 34, 22, 9, 7, 7, 9, 8, 8, 8, 8, 9, 8, 8, 8, 9, 8, 8, 8, 9, 9, 8, 8, 10]], ["Calls", c, [18, 30, 7, 8, 40, 10, 6, 10, 10, 10, 8, 8, 8, 8, 8, 8, 10, 9, 8, 8, 13]],
      ["Yearly", yr, [18, 34, 8, 8, 8, 8, 8, 8, 8, 8, 8]], ["Fifth_Averages", fi, [18, 34, 9, 10, 9, 9, 9, 9, 10]], ["Baskets", bs, [18, 34, 14, 10, 10, 10, 10, 9, 9, 9]],
      ["Previous_Stats", pst, [36, 22, 7, 9, 8, 8, 8, 8, 8, 9, 9, 9, 10]], ["All_Parameters", all, [38, 22, 7, 9, 8, 8, 8, 8, 8, 9, 9, 9, 40]]]; }
  // ---- indicator tests: each parameter against next-year excess and against beating the Nifty 50 by TARGET+
  function tCrit(df) { var lo = 0, hi = 1000; for (var i = 0; i < 200; i++) { var m = (lo + hi) / 2; if (tP(m, df) > ALPHA) lo = m; else hi = m; } return (lo + hi) / 2; }
  function withCI(s) { if (s.status === "ok" && isFinite(s.se)) { s.df = s.years - 1; s.crit = tCrit(s.df); s.low = s.slope - s.crit * s.se; s.high = s.slope + s.crit * s.se; } return s; }
  function indicators(P, o) {
    var catIdx = o.group === ALL ? -1 : P.categories.indexOf(o.group), a0 = o.from - 1, a1 = o.to - 1;
    var rows = P.rows.filter(function (r) { return (catIdx < 0 || r[1] === catIdx) && r[0] >= a0 && r[0] <= a1; });
    var items = P.parameters.map(function (name, i) { var col = OFFSET + i, he = byYear(rows, col, a0, a1), hb = {};
      for (var y = a0; y <= a1; y++) hb[y] = he[y].map(function (p) { return [p[0], p[1] >= TARGET ? 1 : 0, p[2]]; });
      return { name: name, col: col, excess: withCI(stat(he, a0, a1)), beat: withCI(stat(hb, a0, a1)), fifthExcess: fifthAverages(he, a0, a1), fifthBeat: fifthAverages(hb, a0, a1) }; });
    return { options: o, items: items, rows: rows.length, funds: distinctFunds(rows) }; }
  function indSheets(R, P) { var o = R.options, F = function (f, v) { return { t: "n", v: v, f: f }; };
    var head = ["Indicator"]; [["Excess", "points per 1 SD"], ["Beat 3%+", "probability points per 1 SD"]].forEach(function (t) { head = head.concat([t[0] + ": direction", t[0] + ": effect (" + t[1] + ")", t[0] + ": SE", t[0] + ": years", t[0] + ": t", t[0] + ": p", t[0] + ": 95% CI low", t[0] + ": 95% CI high", t[0] + ": significant", t[0] + ": rank IC"]); });
    var res = [head.concat(["Q5 - Q1 excess (points)", "Q5 - Q1 beat rate (points)"])], letters = "BCDEFGHIJKLMNOPQRSTUVW".split("");
    res = res.concat(R.items.map(function (x, i) { var r = i + 2, line = [x.name];
      [[x.excess, 1, 0], [x.beat, 100, 10]].forEach(function (t) { var s = t[0], k = t[1], L = function (n) { return letters[t[2] + n]; }, ok = s.status === "ok" && isFinite(s.se);
        line = line.concat(ok ? [s.slope > 0 ? "Positive" : "Negative", s.slope * k, s.se * k, s.years, F(L(1) + r + "/" + L(2) + r, s.t), F("TDIST(ABS(" + L(4) + r + ")," + L(3) + r + "-1,2)", s.p), F(L(1) + r + "-TINV(0.05," + L(3) + r + "-1)*" + L(2) + r, s.low * k), F(L(1) + r + "+TINV(0.05," + L(3) + r + "-1)*" + L(2) + r, s.high * k), s.p <= o.cut ? "Yes" : "no", cl(s.ic)] : ["", "", "", s.years, "", "", "", "", "no", ""]); });
      var fe = x.fifthExcess, fb = x.fifthBeat; return line.concat([fe ? fe.avg[4] - fe.avg[0] : "", fb ? 100 * (fb.avg[4] - fb.avg[0]) : ""]); }));
    var yr = [["Indicator", "Return year", "Funds", "Excess slope (points per 1 SD)", "Excess rank IC", "Beat slope (probability points per 1 SD)", "Beat rank IC"]];
    var fi = [["Indicator", "Years", "Q1 (lowest) excess %", "Q2", "Q3", "Q4", "Q5 (highest)", "Q1 (lowest) beat rate %", "Q2", "Q3", "Q4", "Q5 (highest)"]];
    R.items.forEach(function (x) { var by = {}; x.beat.yearly.forEach(function (t) { by[t.year] = t; });
      x.excess.yearly.forEach(function (t) { var b = by[t.year] || {}; yr.push([x.name, t.year + 1, t.n, t.slope, cl(t.ic), b.slope === undefined ? "" : 100 * b.slope, cl(b.ic)]); });
      if (x.fifthExcess) fi.push([x.name, x.fifthExcess.years].concat(x.fifthExcess.avg).concat(x.fifthBeat.avg.map(function (v) { return 100 * v; }))); });
    var me = [["Indicator tests: how to read this workbook"], [], ["Funds", o.group], ["Return years", o.from + "-" + o.to], ["Parameter years", (o.from - 1) + "-" + (o.to - 1)], ["Fund-years", R.rows],
      ["Significant if p <=", o.cut], [],
      ["Effect", "Fama-MacBeth: each year next-year outcome is regressed on the standardised indicator (capped at +/-3 SD); the yearly slopes are averaged."], ["Excess", "Effect = points of next-year excess over the Nifty 50 per 1 SD more of the indicator."], ["Beat 3%+", "Effect = change in the chance of beating the Nifty 50 by 3 points, in probability points, per 1 SD more of the indicator (linear probability)."],
      ["SE", "Newey-West (1 lag) on the yearly slopes."], ["t, p, CI", "t = effect / SE. p and the 95% CI use the t distribution with years - 1 degrees of freedom. These columns are formulas."], [],
      ["Sheets"], ["Results", "One row per indicator."], ["Yearly_Slopes", "The yearly slopes behind each effect."], ["Fifths", "Average excess and beat rate of each fifth."]];
    return [["Read_Me", me, [22, 110]], ["Results", res, [40].concat(head.slice(1).map(function () { return 11; })).concat([11, 11])], ["Yearly_Slopes", yr, [40, 8, 7, 12, 10, 14, 10]], ["Fifths", fi, [40, 7, 10, 9, 9, 9, 9, 10, 9, 9, 9, 9]]]; }

  // ---- linear regression of next-year excess on parameters (OLS, optional year effects)
  function fProb(F, d1, d2) { return ibeta(d2 / 2, d1 / 2, d2 / (d2 + d1 * F)); }
  function invert(A) { var n = A.length, M = A.map(function (row, i) { var r = row.slice(); for (var j = 0; j < n; j++) r.push(i === j ? 1 : 0); return r; });
    for (var c = 0; c < n; c++) { var piv = c; for (var i = c + 1; i < n; i++) if (Math.abs(M[i][c]) > Math.abs(M[piv][c])) piv = i;
      if (Math.abs(M[piv][c]) < 1e-10) return null; var t = M[c]; M[c] = M[piv]; M[piv] = t;
      var d = M[c][c]; for (var j2 = 0; j2 < 2 * n; j2++) M[c][j2] /= d;
      for (var r = 0; r < n; r++) if (r !== c && M[r][c] !== 0) { var f = M[r][c]; for (var j3 = c; j3 < 2 * n; j3++) M[r][j3] -= f * M[c][j3]; } }
    return M.map(function (row) { return row.slice(n); }); }
  function withinYear(col, yrs) { var s = {}, c = {}, i; for (i = 0; i < col.length; i++) { s[yrs[i]] = (s[yrs[i]] || 0) + col[i]; c[yrs[i]] = (c[yrs[i]] || 0) + 1; }
    return col.map(function (v, n) { return v - s[yrs[n]] / c[yrs[n]]; }); }
  // cols = slope columns (raw). Returns coefficients on those columns, plus the intercept when there are no year effects.
  function ols(cols, y, yrs, o) { var N = y.length, G = Object.keys(yrs.reduce(function (m, v) { m[v] = 1; return m; }, {})).length, q = cols.length, sds = cols.map(function (c) { var m = mean(c), s = 0; c.forEach(function (v) { s += (v - m) * (v - m); }); return Math.sqrt(s / (N - 1)); });
    var X = o.fe ? cols.map(function (c) { return withinYear(c, yrs); }) : cols.concat([y.map(function () { return 1; })]), Y = o.fe ? withinYear(y, yrs) : y, k = X.length, K = k + (o.fe ? G : 0);
    if (N <= K + 1) return null;
    var XtX = [], Xty = [], i, j, r; for (i = 0; i < k; i++) { XtX.push(new Array(k)); var s = 0; for (r = 0; r < N; r++) s += X[i][r] * Y[r]; Xty.push(s); }
    for (i = 0; i < k; i++) for (j = i; j < k; j++) { var t = 0; for (r = 0; r < N; r++) t += X[i][r] * X[j][r]; XtX[i][j] = XtX[j][i] = t; }
    var scale = XtX.map(function (row, c) { return Math.sqrt(row[c]) || 1; }), Sc = XtX.map(function (row, a) { return row.map(function (v, b) { return v / (scale[a] * scale[b]); }); }), inv = invert(Sc); if (!inv) return null;
    var Ai = inv.map(function (row, a) { return row.map(function (v, b) { return v / (scale[a] * scale[b]); }); });
    var b = Ai.map(function (row) { var v = 0; for (var c = 0; c < k; c++) v += row[c] * Xty[c]; return v; }), u = new Array(N), rss = 0;
    for (r = 0; r < N; r++) { var fit = 0; for (i = 0; i < k; i++) fit += X[i][r] * b[i]; u[r] = Y[r] - fit; rss += u[r] * u[r]; }
    var my = mean(y), tss = 0; y.forEach(function (v) { tss += (v - my) * (v - my); }); var rss0 = 0, my0 = o.fe ? 0 : my; Y.forEach(function (v) { rss0 += (v - my0) * (v - my0); });
    var V, df;
    if (o.se === "classic") { var s2 = rss / (N - K); V = Ai.map(function (row) { return row.map(function (v) { return v * s2; }); }); df = N - K; }
    else { var score = {}; for (r = 0; r < N; r++) { var g = score[yrs[r]] || (score[yrs[r]] = new Array(k).fill(0)); for (i = 0; i < k; i++) g[i] += X[i][r] * u[r]; }
      var meat = XtX.map(function (row) { return row.map(function () { return 0; }); }); Object.keys(score).forEach(function (kk) { var g = score[kk]; for (i = 0; i < k; i++) for (j = 0; j < k; j++) meat[i][j] += g[i] * g[j]; });
      var c = G / (G - 1) * (N - 1) / (N - K), L = Ai.map(function (row) { return meat.map(function (_, j2) { var v = 0; for (var m2 = 0; m2 < k; m2++) v += row[m2] * meat[m2][j2]; return v; }); });
      V = L.map(function (row) { return Ai.map(function (_, j2) { var v = 0; for (var m2 = 0; m2 < k; m2++) v += row[m2] * Ai[m2][j2]; return v * c; }); }); df = G - 1; }
    var crit = tCrit(df), terms = b.map(function (v, i2) { var se = Math.sqrt(V[i2][i2]), t2 = v / se; return { coef: v, se: se, t: t2, p: tP(t2, df), low: v - crit * se, high: v + crit * se, sd: i2 < q ? sds[i2] : null }; });
    var cen = cols.map(function (c) { if (o.fe) return withinYear(c, yrs); var m = mean(c); return c.map(function (v) { return v - m; }); });
    var Rm = cen.map(function (a2) { return cen.map(function (b2) { return pearson(a2, b2); }); }), Ri = q > 1 ? invert(Rm) : [[1]];
    terms.forEach(function (t3, i3) { if (i3 < q) t3.vif = Ri ? Ri[i3][i3] : Infinity; });
    var dfRes = N - K, F = ((rss0 - rss) / q) / (rss / dfRes), r2 = 1 - rss / tss, n1 = N - 1;
    return { terms: terms, N: N, G: G, K: K, q: q, df: df, dfRes: dfRes, rss: rss, tss: tss, rss0: rss0, r2: r2, adjR2: 1 - (1 - r2) * n1 / dfRes, partialR2: 1 - rss / rss0, rmse: Math.sqrt(rss / dfRes), F: F, pF: fProb(F, q, dfRes), meanY: my, crit: crit }; }
  function sample(rows, cs) { var y = [], yrs = [], use = [], cols = cs.map(function () { return []; });
    rows.forEach(function (r) { if (r[3] === null || cs.some(function (c) { return r[c] === null; })) return; y.push(r[3]); yrs.push(r[0]); use.push(r); cs.forEach(function (c, i) { cols[i].push(r[c]); }); });
    return { y: y, yrs: yrs, cols: cols, rows: use }; }
  function regRows(P, o) { var catIdx = o.group === ALL ? -1 : P.categories.indexOf(o.group); return P.rows.filter(function (r) { return (catIdx < 0 || r[1] === catIdx) && r[0] >= o.from - 1 && r[0] <= o.to - 1; }); }
  function regSimple(P, o) { var rows = regRows(P, o); return P.parameters.map(function (name, i) { var s = sample(rows, [OFFSET + i]), m = s.y.length > 5 && distinct(s.cols[0]) > 2 ? ols(s.cols, s.y, s.yrs, o) : null; return { name: name, fit: m }; }); }
  function regPick(P, o, simple) { var rows = regRows(P, o), order = simple.filter(function (x) { return x.fit && isFinite(x.fit.terms[0].p) && x.fit.N >= Math.max(UNIQUE_MIN, 0.8 * rows.length); }).sort(function (a, b) { return a.fit.terms[0].p - b.fit.terms[0].p; }), kept = [], rk = {};
    function rc(n) { return rk[n] || (rk[n] = rankColumn(rows, OFFSET + P.parameters.indexOf(n))); }
    order.forEach(function (x) { if (kept.length >= 6 || kept.some(function (k) { var v = rankCorr(rc(k), rc(x.name)); return isFinite(v) && v > 0.7; })) return; kept.push(x.name); });
    return kept; }
  function regMulti(P, o, vars) { var rows = regRows(P, o), cs = vars.map(function (v) { return OFFSET + P.parameters.indexOf(v); }), s = sample(rows, cs), m = vars.length ? ols(s.cols, s.y, s.yrs, o) : null;
    return { fit: m, vars: vars, funds: distinctFunds(s.rows), sample: s }; }
  // the 20 parameters with the smallest p in the one-at-a-time regressions, and the rank correlations between them
  function regTop(P, o, simple) { var top = simple.filter(function (x) { return x.fit && isFinite(x.fit.terms[0].p); }).sort(function (a, b) { return a.fit.terms[0].p - b.fit.terms[0].p; }).slice(0, 20), C = corr(P, o), ix = top.map(function (x) { return P.parameters.indexOf(x.name); });
    return { names: top.map(function (x) { return x.name; }), p: top.map(function (x) { return x.fit.terms[0].p; }), r: ix.map(function (a) { return ix.map(function (b) { return C.r[a][b]; }); }), n: ix.map(function (a) { return ix.map(function (b) { return C.n[a][b]; }); }) }; }
  // next-year prediction: the fitted model applied to each fund's latest parameter values
  function regPredict(L, M, o) { var fit = M.fit; if (!fit) return null;
    var q = fit.q, b = fit.terms.slice(0, q).map(function (t) { return t.coef; }), ix = M.vars.map(function (v) { return L.parameters.indexOf(v); }), a, sigma = fit.rmse;
    if (o.fe) { var by = {}, sm = M.sample; sm.y.forEach(function (v, r) { var u = v; b.forEach(function (c, i) { u -= c * sm.cols[i][r]; }); (by[sm.yrs[r]] = by[sm.yrs[r]] || []).push(u); });
      var eff = Object.keys(by).map(function (y) { return mean(by[y]); }); a = mean(eff); var ss = 0; eff.forEach(function (v) { ss += (v - a) * (v - a); }); sigma = Math.sqrt(fit.rmse * fit.rmse + ss / (eff.length - 1)); }
    else a = fit.terms[q].coef;
    var crit = tCrit(fit.dfRes), rows = [], skipped = 0;
    L.funds.forEach(function (fd, i) { if (o.group !== ALL && fd[1] !== o.group) return; var vals = ix.map(function (c) { return L.values[i][c]; });
      if (vals.some(function (v) { return v === null; })) { skipped++; return; }
      var p = a; vals.forEach(function (v, n) { p += b[n] * v; }); rows.push({ name: fd[0], category: fd[1], values: vals, pred: p, low: p - crit * sigma, high: p + crit * sigma, live: fd[2] }); });
    rows.sort(function (x, y) { return y.pred - x.pred; });
    var seen = rows.filter(function (r) { return r.live !== null; }), tell = null;
    if (seen.length > 2) { var called = seen.filter(function (r) { return r.pred >= TARGET; }); tell = { rank: pearson(ranks(seen.map(function (r) { return r.pred; })), ranks(seen.map(function (r) { return r.live; }))), n: seen.length, called: called.length, calledBeat: called.filter(function (r) { return r.live >= TARGET; }).length, beat: seen.filter(function (r) { return r.live >= TARGET; }).length }; }
    return { intercept: a, coefs: b, sigma: sigma, crit: crit, rows: rows, skipped: skipped, tell: tell, vars: M.vars, year: L.year, target: L.target, liveLabel: L.liveLabel, niftyAverage: L.niftyAverage }; }
  function regSheets(M, S, P, o, T) { var fit = M.fit, seName = o.se === "classic" ? "Classic OLS" : "Clustered by year", F = function (f, v) { return { t: "n", v: v, f: f }; };
    var me = [["Linear regression: how to read this workbook"], [], ["Outcome (y)", "Next-year excess return over the Nifty 50, %"], ["Funds", o.group], ["Return years", o.from + "-" + o.to], ["Parameter years", (o.from - 1) + "-" + (o.to - 1)], ["Year effects", o.fe ? "Yes: compares funds within each year" : "No"], ["Standard errors", seName], [],
      ["Multiple_Regression", "One model holding the chosen parameters together. t and p are formulas."], ["Model_Fit", "N, R-squared, F and the other fit statistics."], ["Simple_Regressions", "All 101 parameters, one at a time. Each uses every fund-year where that parameter exists."], ["Data", "The fund-years in the multiple regression. Without year effects, Excel's LINEST on this sheet gives the same coefficients."]];
    var mr = [["Variable", "Coefficient", "Per 1 SD of the parameter", "Standard error", "Degrees of freedom", "t", "p", "95% CI low", "95% CI high", "VIF", "Significant at p <= 0.05"]], fitR = [["Statistic", "Value"]], data = [["Fund", "Return year", "Excess %"].concat(M.vars)];
    if (fit) { fit.terms.forEach(function (t, i) { var r = mr.length + 1; mr.push([i < M.vars.length ? M.vars[i] : "Intercept", t.coef, i < M.vars.length ? t.coef * t.sd : "", t.se, fit.df, F("B" + r + "/D" + r, t.t), F("TDIST(ABS(F" + r + "),E" + r + ",2)", t.p), t.low, t.high, i < M.vars.length ? cl(t.vif) : "", t.p <= ALPHA ? "Yes" : "no"]); });
      [["Fund-years (N)", fit.N], ["Funds", M.funds], ["Years", fit.G], ["Parameters", fit.q], ["R-squared", fit.r2], ["Adjusted R-squared", fit.adjR2], ["R-squared from the parameters only", fit.partialR2], ["F (classic)", fit.F], ["p of F", fit.pF], ["F degrees of freedom", fit.q + ", " + fit.dfRes], ["Residual standard error", fit.rmse], ["Residual sum of squares", fit.rss], ["Total sum of squares", fit.tss], ["Mean excess %", fit.meanY]].forEach(function (x) { fitR.push(x); });
      var sm = M.sample; sm.rows.forEach(function (r, i) { data.push([P.funds[r[2]], r[0] + 1, sm.y[i]].concat(sm.cols.map(function (c) { return c[i]; }))); }); }
    var si = [["Parameter", "Coefficient", "Per 1 SD of the parameter", "Standard error", "Degrees of freedom", "t", "p", "95% CI low", "95% CI high", "R-squared", "Fund-years", "Significant at p <= 0.05"]];
    S.forEach(function (x) { var m = x.fit; if (!m) { si.push([x.name, "", "", "", "", "", "", "", "", "", "", "no data"]); return; } var t = m.terms[0], r = si.length + 1; si.push([x.name, t.coef, t.coef * t.sd, t.se, m.df, F("B" + r + "/D" + r, t.t), F("TDIST(ABS(F" + r + "),E" + r + ",2)", t.p), t.low, t.high, m.r2, m.N, t.p <= ALPHA ? "Yes" : "no"]); });
    var pr = root.REG_PRED, ps = [["Fund", "Category"].concat(pr ? pr.vars.map(function (v) { return v + " (" + pr.year + ")"; }) : []).concat(["Predicted excess %", "95% range low", "95% range high", "Beats the Nifty 50 by 3%+?", "Predicted return % (with average Nifty)", "Actual excess so far %"])];
    if (pr) pr.rows.forEach(function (r) { ps.push([r.name, r.category].concat(r.values).concat([r.pred, r.low, r.high, r.pred >= TARGET ? "Yes" : "No", r.pred + pr.niftyAverage, r.live === null ? "" : r.live])); });
    var tc = [["Rank", "Parameter", "p"].concat(T.names)].concat(T.names.map(function (n, i) { return [i + 1, n, T.p[i]].concat(T.r[i].map(cl)); }));
    me.push(["Prediction", "Each fund's latest parameter values put through the multiple regression."]);
    me.push(["Top20_Correlation", "Rank correlations between the 20 parameters with the smallest p in Simple_Regressions."]);
    return [["Read_Me", me, [24, 100]], ["Multiple_Regression", mr, [40, 11, 11, 10, 9, 8, 8, 10, 10, 8, 11]], ["Model_Fit", fitR, [36, 16]], ["Simple_Regressions", si, [40, 11, 11, 10, 9, 8, 8, 10, 10, 9, 9, 11]], ["Prediction", ps, [40, 16].concat(pr ? pr.vars.map(function () { return 12; }) : []).concat([10, 10, 10, 11, 12, 10])], ["Top20_Correlation", tc, [6, 40, 8].concat(T.names.map(function () { return 10; }))], ["Data", data, [40, 8, 9].concat(M.vars.map(function () { return 12; }))]]; }

  // ---- correlation between parameters: rank correlation of the pooled fund-years (the measure the Unique step uses)
  function corr(P, o) {
    var catIdx = o.group === ALL ? -1 : P.categories.indexOf(o.group);
    var rows = P.rows.filter(function (r) { return (catIdx < 0 || r[1] === catIdx) && r[0] >= o.from - 1 && r[0] <= o.to - 1; });
    var n = P.parameters.length, m = rows.length, cols = P.parameters.map(function (_, i) { return rankColumn(rows, OFFSET + i); });
    var R = [], N = [], pairs = [], i, j, k;
    for (i = 0; i < n; i++) { R.push(new Array(n)); N.push(new Array(n)); }
    for (i = 0; i < n; i++) { var a = cols[i];
      for (j = i; j < n; j++) { var b = cols[j], c = 0, sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
        for (k = 0; k < m; k++) { var x = a[k], y = b[k]; if (x === null || y === null) continue; c++; sx += x; sy += y; sxx += x * x; syy += y * y; sxy += x * y; }
        var dx = sxx - sx * sx / c, dy = syy - sy * sy / c, v = c >= UNIQUE_MIN && dx > 0 && dy > 0 ? (sxy - sx * sy / c) / Math.sqrt(dx * dy) : NaN;
        R[i][j] = R[j][i] = v; N[i][j] = N[j][i] = c;
        if (i !== j && isFinite(v)) pairs.push({ a: i, b: j, r: v, n: c, same: family(P.parameters[i]) === family(P.parameters[j]) }); } }
    pairs.sort(function (p, q) { return Math.abs(q.r) - Math.abs(p.r); });
    return { r: R, n: N, pairs: pairs, rows: m, funds: distinctFunds(rows) }; }
  function corrOrder(C) { // similar parameters next to each other: start from the most connected, then always the closest remaining
    var n = C.r.length, left = [], i, abs = function (a, b) { var v = Math.abs(C.r[a][b]); return isFinite(v) ? v : 0; };
    for (i = 0; i < n; i++) left.push(i);
    function total(a) { var s = 0; for (var b = 0; b < n; b++) if (b !== a) s += abs(a, b); return s; }
    var cur = left.slice().sort(function (a, b) { return total(b) - total(a); })[0], out = [cur]; left.splice(left.indexOf(cur), 1);
    while (left.length) { var best = left[0]; left.forEach(function (c) { if (abs(cur, c) > abs(cur, best)) best = c; }); out.push(best); left.splice(left.indexOf(best), 1); cur = best; }
    return out; }
  function corrSheets(C, P, o) { var names = P.parameters, label = o.group + ", returns " + o.from + "-" + o.to;
    return [["Read_Me", [["Parameter correlation"], [], ["Funds", o.group], ["Return years", o.from + "-" + o.to], ["Parameter years", (o.from - 1) + "-" + (o.to - 1)], ["Fund-years", C.rows],
        ["Measure", "Rank (Spearman-style) correlation of the fund-years in the period. Pairs need at least " + UNIQUE_MIN + " fund-years with both values."], ["Ranking", "Every pair, strongest first, ignoring sign. " + label + "."], ["Matrix", "The full table behind the heatmap."]], [24, 90]],
      ["Ranking", [["Rank", "Parameter A", "Parameter B", "Correlation", "Absolute correlation", "Fund-years", "Versions of one measure"]].concat(C.pairs.map(function (p, i) { return [i + 1, names[p.a], names[p.b], p.r, Math.abs(p.r), p.n, p.same ? "Yes" : "No"]; })), [7, 40, 40, 11, 11, 10, 12]],
      ["Matrix", [["Parameter"].concat(names)].concat(C.r.map(function (row, i) { return [names[i]].concat(row.map(cl)); })), [40].concat(names.map(function () { return 9; }))]]; }
  function cl(v) { return v === undefined || v === null || !isFinite(v) ? "" : v; }

  var api = { regPredict: regPredict, regTop: regTop, regSimple: regSimple, regPick: regPick, regMulti: regMulti, regSheets: regSheets, EXCESS_MIN: EXCESS_MIN, run: run, indicators: indicators, indSheets: indSheets, corr: corr, corrOrder: corrOrder, corrSheets: corrSheets, family: family, feasible: feasible, sheets: sheets, TARGET: TARGET, MIN_CALLS: MIN_CALLS, MIN_YEARS: MIN_YEARS, ALL: ALL, BASKETS: BASKETS, TIERS: TIERS, PREVIOUS: PREVIOUS, FIRST: 2006, LAST: 2025 };
  root.PeriodEngine = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : this);
