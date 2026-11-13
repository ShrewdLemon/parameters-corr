/* Period test: the whole analysis re-run in the browser for any analysis and testing period.
 *
 * Years are RETURN years: return year Y is paired with parameter year Y - 1. Analysis period: the
 * Statistical analysis (Fama-MacBeth slopes, Newey-West t and p) and each fifth's average
 * excess. Testing period: every fund is placed in a fifth by its parameter, predicted that fifth's analysis
 * average, and compared with what happened. Nothing from the testing period reaches the analysis.
 * Same formulas as stats_analysis.py and stats_prediction.py; panel = window.PANEL (panel.js).
 */
(function (root) {
  var TARGET = 3, EXCESS_MIN = 0.01, MIN_CALLS = 30, Z_CAP = 3, ALPHA = 0.05, UNIQUE_RHO = 0.80, UNIQUE_MIN = 30, PICK_RHO = 0.90, MIN_COVER = 0.80;
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
  // parameter choice for the multiple regression: significant alone (p <= ALPHA), or the given names, strongest first; thin data
  // (under MIN_COVER of the group's fund-years) is left out; a parameter is dropped if its correlation with one
  // already kept is above PICK_RHO
  function regPick(P, o, simple, names) { var rows = regRows(P, o), order = simple.filter(function (x) { return x.fit && isFinite(x.fit.terms[0].p) && (names ? names.indexOf(x.name) >= 0 : x.fit.terms[0].p <= ALPHA); }).sort(function (a, b) { return a.fit.terms[0].p - b.fit.terms[0].p; }), kept = [], dropped = [], thin = [], rk = {}, ally = rows.filter(function (r) { return r[3] !== null; }).length, allYears = Object.keys(rows.reduce(function (m, r) { m[r[0]] = 1; return m; }, {})).length;
    function rc(n) { return rk[n] || (rk[n] = rankColumn(rows, OFFSET + P.parameters.indexOf(n))); }
    order.forEach(function (x) { if (x.fit.N < MIN_COVER * ally) { thin.push({ name: x.name, n: x.fit.N, years: x.fit.G }); return; }
      var hit = null; kept.forEach(function (k) { var v = rankCorr(rc(k.name), rc(x.name)); if (!hit && isFinite(v) && v > PICK_RHO) hit = { other: k.name, rho: v }; });
      if (hit) dropped.push({ name: x.name, p: x.fit.terms[0].p, other: hit.other, rho: hit.rho }); else kept.push({ name: x.name, p: x.fit.terms[0].p, t: x.fit.terms[0].t, n: x.fit.N }); });
    return { significant: order.length, kept: kept, dropped: dropped, thin: thin, total: ally, allYears: allYears, vars: kept.map(function (k) { return k.name; }) }; }
  function regMulti(P, o, vars) { var rows = regRows(P, o), cs = vars.map(function (v) { return OFFSET + P.parameters.indexOf(v); }), s = sample(rows, cs), m = vars.length ? ols(s.cols, s.y, s.yrs, o) : null;
    return { fit: m, vars: vars, funds: distinctFunds(s.rows), sample: s }; }
  // the 20 parameters with the smallest p in the one-at-a-time regressions, and the rank correlations between them
  function regTop(P, o, simple) { var top = simple.filter(function (x) { return x.fit && isFinite(x.fit.terms[0].p); }).sort(function (a, b) { return a.fit.terms[0].p - b.fit.terms[0].p; }).slice(0, 20), C = corr(P, o), ix = top.map(function (x) { return P.parameters.indexOf(x.name); });
    return { names: top.map(function (x) { return x.name; }), p: top.map(function (x) { return x.fit.terms[0].p; }), r: ix.map(function (a) { return ix.map(function (b) { return C.r[a][b]; }); }), n: ix.map(function (a) { return ix.map(function (b) { return C.n[a][b]; }); }) }; }
  // next-year prediction: the fitted model applied to each fund's latest parameter values
  function regLine(M, o) { var fit = M.fit, q = fit.q, b = fit.terms.slice(0, q).map(function (t) { return t.coef; }), a, sigma = fit.rmse;
    if (o.fe) { var by = {}, sm = M.sample; sm.y.forEach(function (v, r) { var u = v; b.forEach(function (c, i) { u -= c * sm.cols[i][r]; }); (by[sm.yrs[r]] = by[sm.yrs[r]] || []).push(u); });
      var eff = Object.keys(by).map(function (y) { return mean(by[y]); }); a = mean(eff); var ss = 0; eff.forEach(function (v) { ss += (v - a) * (v - a); }); sigma = Math.sqrt(fit.rmse * fit.rmse + ss / (eff.length - 1)); }
    else a = fit.terms[q].coef;
    return { a: a, b: b, sigma: sigma }; }
  function regPredict(L, M, o) { var fit = M.fit; if (!fit) return null;
    var line = regLine(M, o), a = line.a, b = line.b, sigma = line.sigma, ix = M.vars.map(function (v) { return L.parameters.indexOf(v); });
    var crit = tCrit(fit.dfRes), rows = [], skipped = 0;
    L.funds.forEach(function (fd, i) { if (o.group !== ALL && fd[1] !== o.group) return; var vals = ix.map(function (c) { return L.values[i][c]; });
      if (vals.some(function (v) { return v === null; })) { skipped++; return; }
      var p = a; vals.forEach(function (v, n) { p += b[n] * v; }); rows.push({ name: fd[0], category: fd[1], values: vals, pred: p, low: p - crit * sigma, high: p + crit * sigma, live: fd[2] }); });
    rows.sort(function (x, y) { return y.pred - x.pred; });
    var seen = rows.filter(function (r) { return r.live !== null; }), tell = null;
    if (seen.length > 2) { var called = seen.filter(function (r) { return r.pred >= TARGET; }); tell = { rank: pearson(ranks(seen.map(function (r) { return r.pred; })), ranks(seen.map(function (r) { return r.live; }))), n: seen.length, called: called.length, calledBeat: called.filter(function (r) { return r.live >= TARGET; }).length, beat: seen.filter(function (r) { return r.live >= TARGET; }).length }; }
    return { intercept: a, coefs: b, sigma: sigma, crit: crit, rows: rows, skipped: skipped, tell: tell, vars: M.vars, year: L.year, target: L.target, liveLabel: L.liveLabel, niftyAverage: L.niftyAverage }; }
  // the one-parameter regressions in several periods: which parameters are significant in all of them
  function regCompare(P, o, periods) {
    var runs = periods.map(function (w) { var m = { group: o.group, from: w.from, to: w.to, se: o.se, fe: o.fe }; return regSimple(P, m); });
    var rows = P.parameters.map(function (name, i) { var cells = runs.map(function (r) { var f = r[i].fit, t = f && f.terms[0]; return t && isFinite(t.p) ? { t: t.t, p: t.p, n: f.N, sig: t.p <= ALPHA } : null; });
      var on = cells.filter(function (c) { return c && c.sig; }), up = on.filter(function (c) { return c.t > 0; }).length;
      return { name: name, cells: cells, count: on.length, common: on.length === periods.length && periods.length > 0, sameDir: up === 0 || up === on.length, dir: up === on.length ? 1 : up === 0 ? -1 : 0, best: Math.min.apply(null, on.map(function (c) { return c.p; }).concat([9])) }; });
    return { periods: periods.map(function (w, k) { return { from: w.from, to: w.to, sig: rows.filter(function (r) { return r.cells[k] && r.cells[k].sig; }).length }; }), rows: rows,
      common: rows.filter(function (r) { return r.common; }).length, agree: rows.filter(function (r) { return r.common && r.sameDir; }).length }; }
  // how the multiple equation is built from the individual lines (Frisch-Waugh-Lovell): each weight is the slope of
  // excess on the part of that parameter the others can't explain
  function regDerive(M, o, D) { var fit = M.fit, sm = M.sample; if (!fit) return null;
    var yrs = sm.yrs, clean = function (c) { if (o.fe) return withinYear(c, yrs); var m = mean(c); return c.map(function (v) { return v - m; }); }, Y = clean(sm.y), X = sm.cols.map(clean), N = Y.length;
    function dot(a, b) { var s = 0; for (var r = 0; r < N; r++) s += a[r] * b[r]; return s; }
    function level(w, col) { if (!o.fe) return mean(sm.y) - w * mean(col); var by = {}; sm.y.forEach(function (v, r) { (by[yrs[r]] = by[yrs[r]] || []).push(v - w * col[r]); }); return mean(Object.keys(by).map(function (y) { return mean(by[y]); })); }
    var items = M.vars.map(function (name, j) { var x = X[j], ss = dot(x, x), alone = dot(x, Y) / ss, others = X.filter(function (_, i) { return i !== j; }), rest = x.slice();
      if (others.length) { var A = invert(others.map(function (a) { return others.map(function (b) { return dot(a, b) / Math.sqrt(dot(a, a) * dot(b, b)); }); })), sc = others.map(function (a) { return Math.sqrt(dot(a, a)); }), xy = others.map(function (a) { return dot(a, x); }), c = A ? A.map(function (row, i) { var v = 0; row.forEach(function (u, k) { v += u * xy[k] / (sc[i] * sc[k]); }); return v; }) : null;
        if (c) others.forEach(function (a, i) { for (var r = 0; r < N; r++) rest[r] -= c[i] * a[r]; }); }
      var un = dot(rest, rest), ny = dot(rest, Y);
      return { name: name, aloneW: alone, aloneB: level(alone, sm.cols[j]), meanX: mean(sm.cols[j]), uniqueShare: un / ss, sumXY: ny, sumXX: un, weight: ny / un }; });
    return { items: items, meanY: mean(sm.y), intercept: D ? D.intercept : (o.fe ? null : fit.terms[fit.q].coef), N: N }; }
  // regression test: the line built on one period, applied to the fund-years of another
  function regTest(P, o, M) { var line = regLine(M, o), cs = M.vars.map(function (v) { return OFFSET + P.parameters.indexOf(v); }), rows = regRows(P, { group: o.group, from: o.tFrom, to: o.tTo }), s = sample(rows, cs), my = mean(s.y);
    var b = { n: 0, called: 0, beat: 0, hits: 0, pos: 0, posHit: 0, ge: 0, dev: 0, abs: 0, ssRes: 0, ssTot: 0, baskets: BASKETS.map(function () { return [0, 0, 0, 0, 0]; }) }, by = {}, detail = [];
    s.y.forEach(function (act, r) { var pred = line.a, vals = s.cols.map(function (c) { return c[r]; }); vals.forEach(function (v, i) { pred += line.b[i] * v; });
      var y = s.yrs[r] + 1, t = by[y] || (by[y] = { year: y, funds: 0, called: 0, beat: 0, hits: 0, pos: 0, posHit: 0, ge: 0, dev: 0, preds: [], acts: [] }), d = act - pred, call = pred >= TARGET, won = act >= TARGET, k = b.baskets[basketIndex(pred)];
      [b, t].forEach(function (x) { x.called += call; x.beat += won; x.hits += call === won; x.ge += act >= pred; x.dev += d; if (pred >= EXCESS_MIN) { x.pos++; if (act > 0) x.posHit++; } });
      b.n++; t.funds++; t.preds.push(pred); t.acts.push(act); b.abs += Math.abs(d); b.ssRes += d * d; b.ssTot += (act - my) * (act - my); k[0]++; k[1] += pred; k[2] += act; k[3] += won; k[4] += Math.abs(d);
      detail.push({ year: y, fund: P.funds[s.rows[r][2]], values: vals, pred: pred, actual: act }); });
    var years = Object.keys(by).map(function (y) { var t = by[y]; t.ic = t.funds > 2 && distinct(t.preds) > 1 && distinct(t.acts) > 1 ? pearson(ranks(t.preds), ranks(t.acts)) : NaN; delete t.preds; delete t.acts; return t; }).sort(function (x, y) { return x.year - y.year; }), ics = years.map(function (t) { return t.ic; }).filter(isFinite);
    b.ic = ics.length ? mean(ics) : NaN; b.r2 = b.ssTot > 0 ? 1 - b.ssRes / b.ssTot : NaN;
    return { line: line, summary: b, years: years, detail: detail, funds: distinctFunds(s.rows) }; }
  function regTestSheets(R, P) { var o = R.o, M = R.m, fit = M.fit, D = R.der, T = R.test, F = function (f, v) { return { t: typeof v === "string" ? "s" : "n", v: v, f: f }; };
    var me = [["Regression test: how to read this workbook"], [], ["Funds", o.group], ["Line built from (return years)", o.from + "-" + o.to], ["Tested on (return years)", o.tFrom + "-" + o.tTo], ["Parameters", M.vars.join("; ")], ["Year effects", o.fe ? "Yes" : "No"], ["Standard errors", o.se === "classic" ? "Classic OLS" : "Clustered by year"], [],
      ["Parameters", "t, p and 95% CI from the line period."], ["Line_Equation", "Each parameter's individual line and how its weight is built."], ["Test_By_Year", "Results by return year in the test period."], ["Predictions", "Every test prediction: the equation applied to the parameter values, with checks as formulas."]];
    var pr = [["Variable", "Weight", "Standard error", "t in the model", "p in the model", "95% CI low", "95% CI high", "VIF", "t alone, whole line period", "p alone, whole line period", "Significant at p <= 0.05 (p alone)"]]; fit.terms.forEach(function (t, i) { var al = i < M.vars.length ? (R.alone.filter(function (s) { return s.name === M.vars[i]; })[0] || {}).fit : null, c = al ? al.terms[0] : null; pr.push([i < M.vars.length ? M.vars[i] : "Intercept", t.coef, t.se, t.t, t.p, t.low, t.high, i < M.vars.length ? cl(t.vif) : "", c ? c.t : "", c ? c.p : "", c ? (c.p <= ALPHA ? "Yes" : "no") : ""]); });
    var ds = [["Parameter", "Individual line: slope", "Individual line: starting value", "Average value", "Share not explained by the others", "Sum(unique x * excess)", "Sum(unique x squared)", "Weight"]].concat(D.items.map(function (x, i) { var r = i + 2; return [x.name, x.aloneW, x.aloneB, x.meanX, x.uniqueShare, x.sumXY, x.sumXX, F("F" + r + "/G" + r, x.weight)]; })).concat([["Starting value", "", "", "", "", "", "", cl(T.line.a)]]);
    var yr = [["Return year", "Funds", "Called 3%+", "Actually beat 3%+", "Calls right", "3%+ hit ratio", "Predicted 0.01%+", "Of those, actual above 0", "Excess hit ratio", "Actual >= predicted", "Average deviation", "Rank correlation within the year"]].concat(T.years.map(function (t) { return [t.year, t.funds, t.called, t.beat, t.hits, t.hits / t.funds, t.pos, t.posHit, t.pos ? t.posHit / t.pos : "", t.ge, t.dev / t.funds, cl(t.ic)]; }));
    var pd = [["Fund", "Return year"].concat(M.vars).concat(["Predicted excess %", "Actual excess %", "Deviation", "3%+ call right", "Excess hit (predicted 0.01%+, actual above 0)"])], n = M.vars.length, L = function (i) { var a = "", k = i; do { a = String.fromCharCode(65 + k % 26) + a; k = Math.floor(k / 26) - 1; } while (k >= 0); return a; }, pc = L(2 + n), ac = L(3 + n), dc = L(4 + n);
    T.detail.forEach(function (d) { var r = pd.length + 1, fx = String(T.line.a) + M.vars.map(function (_, i) { return "+(" + T.line.b[i] + ")*" + L(2 + i) + r; }).join("");
      pd.push([d.fund, d.year].concat(d.values).concat([F(fx, d.pred), d.actual, F(ac + r + "-" + pc + r, d.actual - d.pred), F("IF((" + pc + r + ">=" + TARGET + ")=(" + ac + r + ">=" + TARGET + "),1,0)", +((d.pred >= TARGET) === (d.actual >= TARGET))), F("IF(" + pc + r + ">=" + EXCESS_MIN + ",IF(" + ac + r + '>0,1,0),"")', d.pred >= EXCESS_MIN ? +(d.actual > 0) : "")])); });
    return [["Read_Me", me, [32, 100]], ["Parameters", pr, [40, 11, 11, 8, 8, 10, 10, 8]], ["Line_Equation", ds, [40, 12, 12, 10, 14, 14, 14, 12]], ["Test_By_Year", yr, [9, 7, 8, 9, 7, 8, 9, 9, 8, 9, 9, 11]], ["Predictions", pd, [40, 8].concat(M.vars.map(function () { return 12; })).concat([10, 10, 10, 8, 12])]]; }
  // rank correlations between the model's own parameters over a chosen period
  function regSquare(P, o, vars, from, to) { var C = corr(P, { group: o.group, from: from, to: to }), ix = vars.map(function (v) { return P.parameters.indexOf(v); });
    return { names: vars, from: from, to: to, rows: C.rows, r: ix.map(function (a) { return ix.map(function (b) { return C.r[a][b]; }); }), n: ix.map(function (a) { return ix.map(function (b) { return C.n[a][b]; }); }) }; }
  // rank correlations of the model's parameters with the nine AR previous parameters
  function regCross(P, o, vars) { var C = corr(P, { group: o.group, from: o.from, to: o.to }), ix = vars.map(function (v) { return P.parameters.indexOf(v); }), jx = PREVIOUS.map(function (p) { return P.parameters.indexOf(p[1]); });
    return { rows: vars, cols: PREVIOUS.map(function (p) { return p[0]; }), r: ix.map(function (a) { return jx.map(function (b) { return C.r[a][b]; }); }), n: ix.map(function (a) { return jx.map(function (b) { return C.n[a][b]; }); }) }; }
  function regSheets(M, S, P, o, T) { var fit = M.fit, seName = o.se === "classic" ? "Classic OLS" : "Clustered by year", F = function (f, v) { return { t: "n", v: v, f: f }; };
    var me = [["Linear regression: how to read this workbook"], [], ["Outcome (y)", "Next-year excess return over the Nifty 50, %"], ["Funds", o.group], ["Return years", o.from + "-" + o.to], ["Parameter years", (o.from - 1) + "-" + (o.to - 1)], ["Year effects", o.fe ? "Yes: compares funds within each year" : "No"], ["Standard errors", seName], [],
      ["Multiple_Regression", "One model holding the chosen parameters together. t and p are formulas."], ["Model_Fit", "N, R-squared, F and the other fit statistics."], ["Simple_Regressions", "All 101 parameters, one at a time. Each uses every fund-year where that parameter exists."], ["Data", "The fund-years in the multiple regression. Without year effects, Excel's LINEST on this sheet gives the same coefficients."]];
    var mr = [["Variable", "Coefficient", "Per 1 SD of the parameter", "Standard error", "Degrees of freedom", "t", "p", "95% CI low", "95% CI high", "VIF", "Significant at p <= 0.05 (p alone)", "t alone, whole period", "p alone, whole period"]], fitR = [["Statistic", "Value"]], data = [["Fund", "Return year", "Excess %"].concat(M.vars)];
    function alone(n) { var x = S.filter(function (s) { return s.name === n; })[0]; return x && x.fit ? x.fit.terms[0] : null; }
    if (fit) { fit.terms.forEach(function (t, i) { var r = mr.length + 1, al = i < M.vars.length ? alone(M.vars[i]) : null; mr.push([i < M.vars.length ? M.vars[i] : "Intercept", t.coef, i < M.vars.length ? t.coef * t.sd : "", t.se, fit.df, F("B" + r + "/D" + r, t.t), F("TDIST(ABS(F" + r + "),E" + r + ",2)", t.p), t.low, t.high, i < M.vars.length ? cl(t.vif) : "", al ? (al.p <= ALPHA ? "Yes" : "no") : "", al ? al.t : "", al ? al.p : ""]); });
      [["Fund-years (N)", fit.N], ["Funds", M.funds], ["Years", fit.G], ["Parameters", fit.q], ["R-squared", fit.r2], ["Adjusted R-squared", fit.adjR2], ["R-squared from the parameters only", fit.partialR2], ["F (classic)", fit.F], ["p of F", fit.pF], ["F degrees of freedom", fit.q + ", " + fit.dfRes], ["Residual standard error", fit.rmse], ["Residual sum of squares", fit.rss], ["Total sum of squares", fit.tss], ["Mean excess %", fit.meanY]].forEach(function (x) { fitR.push(x); });
      var sm = M.sample; sm.rows.forEach(function (r, i) { data.push([P.funds[r[2]], r[0] + 1, sm.y[i]].concat(sm.cols.map(function (c) { return c[i]; }))); }); }
    var si = [["Parameter", "Coefficient", "Per 1 SD of the parameter", "Standard error", "Degrees of freedom", "t", "p", "95% CI low", "95% CI high", "R-squared", "Fund-years", "Significant at p <= 0.05"]];
    S.forEach(function (x) { var m = x.fit; if (!m) { si.push([x.name, "", "", "", "", "", "", "", "", "", "", "no data"]); return; } var t = m.terms[0], r = si.length + 1; si.push([x.name, t.coef, t.coef * t.sd, t.se, m.df, F("B" + r + "/D" + r, t.t), F("TDIST(ABS(F" + r + "),E" + r + ",2)", t.p), t.low, t.high, m.r2, m.N, t.p <= ALPHA ? "Yes" : "no"]); });
    var pr = root.REG_PRED, ps = [["Fund", "Category"].concat(pr ? pr.vars.map(function (v) { return v + " (" + pr.year + ")"; }) : []).concat(["Predicted excess %", "95% range low", "95% range high", "Beats the Nifty 50 by 3%+?", "Predicted return % (with average Nifty)", "Actual excess so far %"])];
    if (pr) pr.rows.forEach(function (r) { ps.push([r.name, r.category].concat(r.values).concat([r.pred, r.low, r.high, r.pred >= TARGET ? "Yes" : "No", r.pred + pr.niftyAverage, r.live === null ? "" : r.live])); });
    var cp = root.REG_CMP, cs = null;
    if (cp && cp.periods.length) { var ch = ["Parameter"]; cp.periods.forEach(function (w) { ch.push(w.from + "-" + w.to + " t", w.from + "-" + w.to + " p"); }); ch.push("Significant in", "Common to all", "Direction");
      cs = [ch].concat(cp.rows.filter(function (r) { return r.count; }).sort(function (a, b) { return b.count - a.count || a.best - b.best; }).map(function (r) { var l = [r.name]; r.cells.forEach(function (c) { l.push(c ? c.t : "", c ? c.p : ""); }); l.push(r.count + " of " + cp.periods.length, r.common ? "Yes" : "no", r.dir > 0 ? "Positive" : r.dir < 0 ? "Negative" : "Flips"); return l; })); }
    var dv = root.REG_DER, ds = null;
    if (dv) ds = [["Parameter", "Individual line: slope", "Individual line: starting value", "Share of the parameter not explained by the others", "Sum(unique x * excess)", "Sum(unique x squared)", "Weight in the multiple equation"]].concat(dv.items.map(function (x, i) { var r = i + 2; return [x.name, x.aloneW, x.aloneB, x.uniqueShare, x.sumXY, x.sumXX, F("E" + r + "/F" + r, x.weight)]; })).concat([["Starting value", "", "", "", "", "", cl(dv.intercept)]]);
    var bk = root.REG_BT, bs = null;
    if (bk) { bs = [["Fund", "Return year"].concat(bk.vars).concat(["Predicted excess %", "Actual excess %", "Deviation", "3%+ call right", "Excess hit (predicted 0.01%+, actual above 0)"])]; bk.test.detail.forEach(function (d) { bs.push([d.fund, d.year].concat(d.values).concat([d.pred, d.actual, d.actual - d.pred, +((d.pred >= TARGET) === (d.actual >= TARGET)), d.pred >= EXCESS_MIN ? +(d.actual > 0) : ""])); }); me.push(["Backtest", "The line equation applied to returns " + bk.from + "-" + bk.to + "."]); }
    var sq = root.REG_SQUARE, qs = null;
    if (sq) { qs = [["Parameter"].concat(sq.names)].concat(sq.names.map(function (n, i) { return [n].concat(sq.r[i].map(cl)); })); me.push(["Shortlist_Correlation", "Rank correlations between the model's parameters in the backtest years, returns " + sq.from + "-" + sq.to + "."]); }
    var xc = root.REG_CROSS, xs = null;
    if (xc) { xs = [["Model parameter"].concat(xc.cols)].concat(xc.rows.map(function (n, i) { return [n].concat(xc.r[i].map(cl)); })); me.push(["Model_vs_AR_Previous", "Rank correlations of the model's parameters with the nine AR previous parameters."]); }
    var tc = [["Rank", "Parameter", "p"].concat(T.names)].concat(T.names.map(function (n, i) { return [i + 1, n, T.p[i]].concat(T.r[i].map(cl)); }));
    me.push(["Prediction", "Each fund's latest parameter values put through the multiple regression."]);
    var pk = root.REG_PICK; if (pk && pk.thin.length) me.push(["Left out for thin data", pk.thin.map(function (x) { return x.name + " (" + x.n + " of " + pk.total + " fund-years, " + x.years + " of " + pk.allYears + " years)"; }).join("; ")]);
    me.push(["Top20_Correlation", "Rank correlations between the 20 parameters with the smallest p in Simple_Regressions."]);
    if (ds) me.push(["Line_Equation", "How the multiple equation is built from each parameter's individual line."]);
    if (cs) me.push(["Period_Comparison", "Parameters significant at p <= 0.05 in the periods you added, one regression per period."]);
    return [["Read_Me", me, [24, 100]]].concat(cs ? [["Period_Comparison", cs, [40].concat(cs[0].slice(1).map(function () { return 11; }))]] : []).concat(ds ? [["Line_Equation", ds, [40, 12, 12, 14, 14, 14, 12]]] : []).concat(qs ? [["Shortlist_Correlation", qs, [40].concat(sq.names.map(function () { return 11; }))]] : []).concat(xs ? [["Model_vs_AR_Previous", xs, [40].concat(xc.cols.map(function () { return 11; }))]] : []).concat(bs ? [["Backtest", bs, [40, 8].concat(bk.vars.map(function () { return 12; })).concat([10, 10, 10, 8, 12])]] : []).concat([["Multiple_Regression", mr, [40, 11, 11, 10, 9, 8, 8, 10, 10, 8, 11]], ["Model_Fit", fitR, [36, 16]], ["Simple_Regressions", si, [40, 11, 11, 10, 9, 8, 8, 10, 10, 9, 9, 11]], ["Prediction", ps, [40, 16].concat(pr ? pr.vars.map(function () { return 12; }) : []).concat([10, 10, 10, 11, 12, 10])], ["Top20_Correlation", tc, [6, 40, 8].concat(T.names.map(function () { return 10; }))], ["Data", data, [40, 8, 9].concat(M.vars.map(function () { return 12; }))]]); }

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

  // ---------------- top quartile: does a line put the right funds in the top quarter of their category?
  // Peer group = one category in one return year (or all funds of that year). In each peer group of PEER_MIN+ funds the
  // top k = round(n / 4) by the line's score are the predicted top quartile, the top k by actual return the real one;
  // a hit is a fund in both. Picking k funds at random would hit k * k / n on average, the baseline.
  var PEER_MIN = 4, TQ_METHODS = [["excess", "Excess return line"], ["absolute", "Absolute return line"], ["rank", "Peer-rank line"], ["seeded", "Seeded top-quartile line"], ["blend", "Blend: peer-rank + seeded"]];
  function peerKey(o, yr, cat) { return o.peer === "all" ? String(yr) : yr + "|" + cat; }
  function topK(n) { return Math.max(1, Math.round(n * 0.25)); }
  function groupsOf(keys) { var g = {}; keys.forEach(function (k, i) { (g[k] = g[k] || []).push(i); }); return g; }
  // percentile of each value inside its peer group, 0-1 (average rank for ties)
  function peerPct(vals, G) { var out = new Array(vals.length); Object.keys(G).forEach(function (k) { var ix = G[k], rk = ranks(ix.map(function (i) { return vals[i]; })), n = ix.length; ix.forEach(function (i, j) { out[i] = (rk[j] - 0.5) / n; }); }); return out; }
  // quartile of each value inside its peer group, 1 = top: the cut-offs round(n/4), round(n/2), round(3n/4), so Q1 = topK
  function quartIdx(vals, G) { var out = vals.map(function () { return null; }); Object.keys(G).forEach(function (k) { var ix = G[k].slice().sort(function (a, b) { return vals[b] - vals[a]; }), n = ix.length, cut = [topK(n), Math.round(n / 2), Math.round(3 * n / 4)];
      ix.forEach(function (i, j) { out[i] = j < cut[0] ? 1 : j < cut[1] ? 2 : j < cut[2] ? 3 : 4; }); }); return out; }
  function topFlags(vals, G) { var out = vals.map(function () { return 0; }); Object.keys(G).forEach(function (k) { var ix = G[k].slice().sort(function (a, b) { return vals[b] - vals[a]; }); ix.slice(0, topK(ix.length)).forEach(function (i) { out[i] = 1; }); }); return out; }
  // fund-years with every chosen parameter and a return, in peer groups big enough to have a quartile
  function tqRows(P, o, from, to, cs) { var rows = regRows(P, { group: o.group, from: from, to: to }).filter(function (r) { return r[3] !== null && cs.every(function (c) { return r[c] !== null; }); }),
      G = groupsOf(rows.map(function (r) { return peerKey(o, r[0], r[1]); })), keep = {}; Object.keys(G).forEach(function (k) { if (G[k].length >= PEER_MIN) G[k].forEach(function (i) { keep[i] = 1; }); });
    rows = rows.filter(function (_, i) { return keep[i]; }); return { rows: rows, G: groupsOf(rows.map(function (r) { return peerKey(o, r[0], r[1]); })) }; }
  // logistic regression by Newton steps; standard errors clustered by year like the lines
  function logit(cols, y, yrs) { var N = y.length, X = cols.concat([y.map(function () { return 1; })]), k = X.length, b = new Array(k).fill(0), p = new Array(N), H, Hi, it, i, j, r;
    for (it = 0; it < 60; it++) { var g = new Array(k).fill(0); H = X.map(function () { return new Array(k).fill(0); });
      for (r = 0; r < N; r++) { var z = 0; for (i = 0; i < k; i++) z += X[i][r] * b[i]; p[r] = 1 / (1 + Math.exp(-z)); var w = p[r] * (1 - p[r]);
        for (i = 0; i < k; i++) { g[i] += X[i][r] * (y[r] - p[r]); for (j = i; j < k; j++) H[i][j] += w * X[i][r] * X[j][r]; } }
      for (i = 0; i < k; i++) for (j = 0; j < i; j++) H[i][j] = H[j][i];
      Hi = invert(H); if (!Hi) return null; var step = Hi.map(function (row) { var v = 0; for (var c = 0; c < k; c++) v += row[c] * g[c]; return v; }), big = 0;
      for (i = 0; i < k; i++) { b[i] += step[i]; big = Math.max(big, Math.abs(step[i])); } if (big < 1e-9) break; }
    var score = {}, ll = 0, p0 = mean(y), ll0 = 0; for (r = 0; r < N; r++) { var s2 = score[yrs[r]] || (score[yrs[r]] = new Array(k).fill(0)); for (i = 0; i < k; i++) s2[i] += X[i][r] * (y[r] - p[r]);
      ll += y[r] ? Math.log(p[r]) : Math.log(1 - p[r]); ll0 += y[r] ? Math.log(p0) : Math.log(1 - p0); }
    var Gn = Object.keys(score).length, meat = X.map(function () { return new Array(k).fill(0); }); Object.keys(score).forEach(function (kk) { var s3 = score[kk]; for (i = 0; i < k; i++) for (j = 0; j < k; j++) meat[i][j] += s3[i] * s3[j]; });
    var L = Hi.map(function (row) { return meat.map(function (_, j2) { var v = 0; for (var m2 = 0; m2 < k; m2++) v += row[m2] * meat[m2][j2]; return v; }); }),
      V = L.map(function (row) { return Hi.map(function (_, j2) { var v = 0; for (var m2 = 0; m2 < k; m2++) v += row[m2] * Hi[m2][j2]; return v * Gn / (Gn - 1); }); }), df = Gn - 1, crit = tCrit(df);
    return { terms: b.map(function (v, i2) { var se = Math.sqrt(V[i2][i2]), t = v / se; return { coef: v, se: se, t: t, p: tP(t, df), low: v - crit * se, high: v + crit * se }; }), N: N, G: Gn, q: cols.length, df: df, pseudoR2: 1 - ll / ll0, base: p0 }; }
  // the line of one method fitted on the training years: o = { group, peer, from, to, se, fe }
  function tqFit(P, o, vars, method) { var cs = vars.map(function (v) { return OFFSET + P.parameters.indexOf(v); }), S = tqRows(P, o, o.from, o.to, cs), rows = S.rows, yrs = rows.map(function (r) { return r[0]; });
    if (rows.length < vars.length + 10) return null;
    var raw = cs.map(function (c) { return rows.map(function (r) { return r[c]; }); }), ex = rows.map(function (r) { return r[3]; }), fit, y, X = raw;
    if (method === "excess" || method === "absolute") { y = method === "excess" ? ex : rows.map(function (r) { return r[3] + P.nifty[r[0] + 1]; }); fit = ols(raw, y, yrs, o); }
    else { X = raw.map(function (c) { return peerPct(c, S.G); });
      if (method === "rank") { y = peerPct(ex, S.G); fit = ols(X, y, yrs, o); } else { y = topFlags(ex, S.G); fit = logit(X, y, yrs); } }
    if (!fit) return null; var q = vars.length, a = method === "seeded" || !o.fe ? fit.terms[q].coef : null;
    if (a === null) { var by = {}; y.forEach(function (v, r) { var u = v; for (var i = 0; i < q; i++) u -= fit.terms[i].coef * X[i][r]; (by[yrs[r]] = by[yrs[r]] || []).push(u); }); a = mean(Object.keys(by).map(function (k) { return mean(by[k]); })); }
    var top = topFlags(ex, S.G); return { method: method, vars: vars, fit: fit, a: a, b: fit.terms.slice(0, q).map(function (t) { return t.coef; }), N: rows.length, G: fit.G, funds: distinctFunds(rows), groups: Object.keys(S.G).length, tops: top.reduce(function (s3, v) { return s3 + v; }, 0) }; }
  // score every fund in a set of peer groups: raw lines use raw values, the others the values' percentiles inside the group
  function tqScore(F, raw, G) { var X = F.method === "excess" || F.method === "absolute" ? raw : raw.map(function (c) { return peerPct(c, G); }), n = raw[0].length, out = new Array(n);
    for (var r = 0; r < n; r++) { var z = F.a; for (var i = 0; i < F.b.length; i++) z += F.b[i] * X[i][r]; out[r] = F.method === "seeded" ? 1 / (1 + Math.exp(-z)) : z; } return out; }
  function tqScores(fits, raw, G) { var sc = {}; fits.forEach(function (F) { sc[F.method] = tqScore(F, raw, G); });
    if (sc.rank && sc.seeded) { var a = peerPct(sc.rank, G), b = peerPct(sc.seeded, G); sc.blend = a.map(function (v, i) { return (v + b[i]) / 2; }); } return sc; }
  // hit ratio of the predicted top quartiles in the test years, for every method
  function tqTest(P, o, fits, vars) { vars = vars || fits[0].vars; var cs = vars.map(function (v) { return OFFSET + P.parameters.indexOf(v); }), S = tqRows(P, o, o.tFrom, o.tTo, cs), rows = S.rows;
    if (!rows.length) return { n: 0, methods: [] };
    var raw = cs.map(function (c) { return rows.map(function (r) { return r[c]; }); }), act = rows.map(function (r) { return r[3]; }), sc = {}, qs = o.quarts || [1], aq = quartIdx(act, S.G), real = aq.map(function (q) { return qs.indexOf(q) >= 0 ? 1 : 0; }), detail = rows.map(function (r, i) { return { year: r[0] + 1, fund: P.funds[r[2]], cat: P.categories[r[1]], values: raw.map(function (c) { return c[i]; }), actual: act[i], top: real[i], q: aq[i], picks: {}, score: {}, pq: {} }; });
    // fits may be one set of lines, or a function giving the lines for each test year (walk-forward)
    var byYear = groupsOf(rows.map(function (r) { return r[0]; })), refits = {};
    Object.keys(byYear).forEach(function (y) { var ix = byYear[y], F = typeof fits === "function" ? fits(+y + 1) : fits, G = {}; if (!F) return; refits[+y + 1] = F;
      Object.keys(S.G).forEach(function (k) { if (rows[S.G[k][0]][0] === +y) G[k] = S.G[k].map(function (i) { return ix.indexOf(i); }); });
      var part = tqScores(F, raw.map(function (c) { return ix.map(function (i) { return c[i]; }); }), G);
      Object.keys(part).forEach(function (m) { sc[m] = sc[m] || rows.map(function () { return null; }); part[m].forEach(function (v, j) { sc[m][ix[j]] = v; }); }); });
    var m0 = Object.keys(sc)[0], keys = Object.keys(S.G).filter(function (k) { return m0 && sc[m0][S.G[k][0]] !== null; }), methods = Object.keys(sc).map(function (m) { var pq = quartIdx(sc[m], S.G), pick = pq.map(function (q) { return qs.indexOf(q) >= 0 ? 1 : 0; }), tot = { calls: 0, hits: 0, base: 0, v: 0, edge: 0 }, years = {}, cats = {};
      keys.forEach(function (k) { var ix = S.G[k], n = ix.length, kk = 0, hits = 0, gm = mean(ix.map(function (i) { return act[i]; })), edge = 0; ix.forEach(function (i) { detail[i].score[m] = sc[m][i]; detail[i].picks[m] = pick[i]; detail[i].pq[m] = pq[i]; if (pick[i]) { kk++; hits += real[i]; edge += act[i] - gm; } });
        var yr = rows[ix[0]][0] + 1, ct = o.peer === "all" ? "All funds" : P.categories[rows[ix[0]][1]], add = function (t) { t.calls += kk; t.hits += hits; t.base += kk * kk / n; t.v += kk * (kk / n) * ((n - kk) / n) * ((n - kk) / Math.max(1, n - 1)); t.edge += edge; t.groups = (t.groups || 0) + 1; };
        add(tot); add(years[yr] = years[yr] || { year: yr, calls: 0, hits: 0, base: 0, v: 0, edge: 0 }); add(cats[ct] = cats[ct] || { cat: ct, calls: 0, hits: 0, base: 0, v: 0, edge: 0 }); });
      var ys = Object.keys(years).map(function (y) { return years[y]; }).sort(function (a, b) { return a.year - b.year; }), d = ys.map(function (t) { return (t.hits - t.base) / t.calls; }), md = mean(d), sd = 0; d.forEach(function (v) { sd += (v - md) * (v - md); }); sd = Math.sqrt(sd / Math.max(1, d.length - 1));
      var z = tot.v > 0 ? (tot.hits - tot.base) / Math.sqrt(tot.v) : NaN, t = d.length > 1 && sd > 0 ? md / (sd / Math.sqrt(d.length)) : NaN;
      return { method: m, calls: tot.calls, hits: tot.hits, base: tot.base, v: tot.v, ratio: tot.hits / tot.calls, baseRatio: tot.base / tot.calls, edge: tot.edge / tot.calls, z: z, pz: isFinite(z) ? 2 * (1 - normCdf(Math.abs(z))) : NaN, t: t, pt: isFinite(t) ? tP(t, d.length - 1) : NaN, beatYears: d.filter(function (v) { return v > 0; }).length,
        years: ys, cats: Object.keys(cats).map(function (c) { return cats[c]; }).sort(function (a, b) { return b.hits / b.calls - a.hits / a.calls; }) }; });
    var used = []; keys.forEach(function (k) { used = used.concat(S.G[k]); }); used.sort(function (a, b) { return a - b; });
    return { n: used.length, funds: distinctFunds(used.map(function (i) { return rows[i]; })), groups: keys.length, methods: methods, detail: used.map(function (i) { return detail[i]; }), vars: vars, refits: refits }; }
  function normCdf(x) { var t = 1 / (1 + 0.2316419 * x), d = 0.3989423 * Math.exp(-x * x / 2); return 1 - d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); }
  // next year's predicted top quartile from the latest parameter values (L = window.LATEST), with the live part-year check
  function tqPredict(L, o, fits, skipCats) { var vars = fits[0].vars, ix = vars.map(function (v) { return L.parameters.indexOf(v); }), use = [];
    L.funds.forEach(function (fd, i) { if ((o.group !== ALL && fd[1] !== o.group) || (skipCats && skipCats.indexOf(fd[1]) >= 0)) return; var vals = ix.map(function (c) { return L.values[i][c]; }); if (vals.every(function (v) { return v !== null; })) use.push({ name: fd[0], cat: fd[1], values: vals, live: fd[2] }); });
    var G = groupsOf(use.map(function (f) { return o.peer === "all" ? "all" : f.cat; })); Object.keys(G).forEach(function (k) { if (G[k].length < PEER_MIN) delete G[k]; });
    var keep = []; Object.keys(G).forEach(function (k) { keep = keep.concat(G[k]); }); keep.sort(function (a, b) { return a - b; }); use = keep.map(function (i) { return use[i]; });
    G = groupsOf(use.map(function (f) { return o.peer === "all" ? "all" : f.cat; }));
    var raw = vars.map(function (_, j) { return use.map(function (f) { return f.values[j]; }); }), sc = tqScores(fits, raw, G), live = {};
    var qs = o.quarts || [1], liveQ = {};
    Object.keys(G).forEach(function (k) { var seen = G[k].filter(function (i) { return use[i].live !== null; }), sub = {}; sub[k] = seen; if (seen.length >= PEER_MIN) { var lq = quartIdx(use.map(function (f) { return f.live; }), sub); seen.forEach(function (i) { liveQ[i] = lq[i]; live[i] = qs.indexOf(lq[i]) >= 0 ? 1 : 0; }); } });
    var pqs = {}; Object.keys(sc).forEach(function (m) { pqs[m] = quartIdx(sc[m], G); });
    use.forEach(function (f, i) { f.score = {}; f.pick = {}; f.pq = {}; Object.keys(sc).forEach(function (m) { f.score[m] = sc[m][i]; f.pq[m] = pqs[m][i]; f.pick[m] = qs.indexOf(pqs[m][i]) >= 0 ? 1 : 0; }); f.liveTop = i in live ? live[i] : null; f.liveQ = i in liveQ ? liveQ[i] : null; });
    var check = Object.keys(sc).map(function (m) { var c = use.filter(function (f) { return f.pick[m] && f.liveTop !== null; }); return { method: m, calls: c.length, hits: c.filter(function (f) { return f.liveTop; }).length }; });
    return { funds: use, groups: Object.keys(G).length, check: check, year: L.year, target: L.target, liveLabel: L.liveLabel, vars: vars }; }
  // parameters for the top quartile: each year, inside each peer group, the rank correlation of the parameter with next-year
  // excess; averaged over the training years with its t; significant (p <= ALPHA), enough data, near-copies dropped
  function tqPick(P, o) { var rows = regRows(P, o).filter(function (r) { return r[3] !== null; }), total = rows.length, out = [];
    P.parameters.forEach(function (name, j) { var c = OFFSET + j, use = rows.filter(function (r) { return r[c] !== null; }), G = groupsOf(use.map(function (r) { return peerKey(o, r[0], r[1]); })), by = {};
      Object.keys(G).forEach(function (k) { var ix = G[k]; if (ix.length < PEER_MIN) return; var x = ix.map(function (i) { return use[i][c]; }), y = ix.map(function (i) { return use[i][3]; }); if (distinct(x) < 2) return;
        var ic = pearson(ranks(x), ranks(y)); if (!isFinite(ic)) return; var yr = use[ix[0]][0], t = by[yr] || (by[yr] = [0, 0]); t[0] += ic * ix.length; t[1] += ix.length; });
      var ics = Object.keys(by).map(function (y) { return by[y][0] / by[y][1]; }); if (ics.length < MIN_YEARS) return;
      var m = mean(ics), sd = 0; ics.forEach(function (v) { sd += (v - m) * (v - m); }); sd = Math.sqrt(sd / (ics.length - 1)); var t2 = sd > 0 ? m / (sd / Math.sqrt(ics.length)) : NaN;
      out.push({ name: name, ic: m, t: t2, p: isFinite(t2) ? tP(t2, ics.length - 1) : NaN, years: ics.length, n: use.length, pos: ics.filter(function (v) { return v > 0; }).length }); });
    out.sort(function (a, b) { return (isFinite(a.p) ? a.p : 9) - (isFinite(b.p) ? b.p : 9); });
    var kept = [], dropped = [], thin = [], rk = {}; function rc(n) { return rk[n] || (rk[n] = rankColumn(rows, OFFSET + P.parameters.indexOf(n))); }
    out.filter(function (x) { return x.p <= ALPHA; }).forEach(function (x) { if (x.n < MIN_COVER * total) { thin.push(x); return; }
      var hit = null; kept.forEach(function (k) { var v = rankCorr(rc(k.name), rc(x.name)); if (!hit && isFinite(v) && v > PICK_RHO) hit = { other: k.name, rho: v }; });
      if (hit) dropped.push({ name: x.name, p: x.p, other: hit.other, rho: hit.rho }); else kept.push(x); });
    return { all: out, kept: kept, dropped: dropped, thin: thin, total: total, vars: kept.map(function (k) { return k.name; }) }; }
  function tqSheets(R, P) { var o = R.o, names = {}, F = function (f, v) { return { t: typeof v === "string" ? "s" : "n", v: v, f: f }; }; TQ_METHODS.forEach(function (m) { names[m[0]] = m[1]; });
    var ms = R.test.methods, me = [["Top quartile prediction: how to read this workbook"], [], ["Funds", o.group], ["Quartiles formed within", o.peer === "all" ? "All funds of a year together" : "Each category in each year"], ["Lines built from (return years)", o.from + "-" + o.to], ["Tested on (return years)", o.tFrom + "-" + o.tTo], ["Parameters", R.vars.join("; ")], ["Year effects", o.fe ? "Yes" : "No"], [],
      ["Top quartile", "In each peer group of " + PEER_MIN + "+ funds, the top round(n/4) funds. Predicted = by the line's score; actual = by the return that year."], ["Hit", "A fund in both the predicted and the actual top quartile. Hit ratio = hits / predicted."], ["Random baseline", "Expected hits if the k funds were picked at random: k*k/n per peer group."],
      ["Excess return line", "OLS of next-year excess over the Nifty 50 on the raw parameters."], ["Absolute return line", "OLS of next-year fund return (excess + Nifty 50 return) on the raw parameters."], ["Peer-rank line", "OLS of the return's percentile in its peer group on the parameters' percentiles in their peer group."], ["Seeded top-quartile line", "Logistic regression of 1 = finished in the top quartile, 0 = not, on the parameters' percentiles in their peer group."], ["Blend", "Average of the peer-rank and seeded scores' percentiles in the peer group."]];
    var sm = [["Method", "Predicted top quartile", "Hits", "Hit ratio", "Random baseline hits", "Baseline ratio", "Lift", "Avg actual excess over peer average (pts)", "Years above baseline", "t (yearly)", "p (yearly)", "z (pooled)", "p (pooled)"]];
    ms.forEach(function (m, i) { var r = i + 2; sm.push([names[m.method], m.calls, m.hits, F("C" + r + "/B" + r, m.ratio), m.base, F("E" + r + "/B" + r, m.baseRatio), F("D" + r + "/F" + r, m.ratio / m.baseRatio), m.edge, m.beatYears + " of " + m.years.length, cl(m.t), cl(m.pt), cl(m.z), cl(m.pz)]); });
    var yr = [["Method", "Return year", "Peer groups", "Predicted", "Hits", "Hit ratio", "Baseline ratio", "Avg actual excess over peer average"]]; ms.forEach(function (m) { m.years.forEach(function (t) { var r = yr.length + 1; yr.push([names[m.method], t.year, t.groups, t.calls, t.hits, F("E" + r + "/D" + r, t.hits / t.calls), t.base / t.calls, t.edge / t.calls]); }); });
    var ct = [["Method", "Category", "Predicted", "Hits", "Hit ratio", "Baseline ratio"]]; ms.forEach(function (m) { m.cats.forEach(function (t) { var r = ct.length + 1; ct.push([names[m.method], t.cat, t.calls, t.hits, F("D" + r + "/C" + r, t.hits / t.calls), t.base / t.calls]); }); });
    var ln = [["Method", "Variable", "Weight", "Standard error", "t", "p", "Fund-years", "Years"]]; R.fits.forEach(function (Fi) { Fi.fit.terms.forEach(function (t, i) { ln.push([names[Fi.method], i < Fi.vars.length ? Fi.vars[i] : "Intercept", t.coef, t.se, t.t, t.p, Fi.N, Fi.G]); }); if (o.fe && Fi.method !== "seeded") ln.push([names[Fi.method], "Starting value (average year effect)", Fi.a, "", "", "", Fi.N, Fi.G]); });
    var dt = [["Return year", "Fund", "Category"].concat(R.vars).concat(["Actual excess", "Actually top quartile"]).concat(ms.map(function (m) { return names[m.method] + " score"; })).concat(ms.map(function (m) { return names[m.method] + " predicted top"; }))];
    R.test.detail.forEach(function (d) { dt.push([d.year, d.fund, d.cat].concat(d.values).concat([d.actual, d.top ? "Yes" : "No"]).concat(ms.map(function (m) { return d.score[m.method]; })).concat(ms.map(function (m) { return d.picks[m.method] ? "Yes" : "No"; }))); });
    var out = [["Read_Me", me, [28, 110]], ["Summary", sm, [26, 12, 8, 10, 12, 10, 8, 14, 12, 10, 10, 10, 10]], ["By_Year", yr, [26, 10, 10, 10, 8, 10, 10, 14]], ["By_Category", ct, [26, 24, 10, 8, 10, 10]], ["Lines", ln, [26, 40, 12, 12, 10, 10, 10, 8]], ["Test_Funds", dt, [10, 40, 22].concat(R.vars.map(function () { return 14; })).concat([12, 10]).concat(ms.map(function () { return 12; })).concat(ms.map(function () { return 10; }))]];
    if (R.pred) { var pr = [["Fund", "Category"].concat(R.vars).concat(ms.map(function (m) { return names[m.method] + " predicted top"; })).concat(["Live return " + R.pred.liveLabel, "Live top quartile"])]; R.pred.funds.forEach(function (f) { pr.push([f.name, f.cat].concat(f.values).concat(ms.map(function (m) { return f.pick[m.method] ? "Yes" : "No"; })).concat([f.live === null ? "" : f.live, f.liveTop === null ? "" : f.liveTop ? "Yes" : "No"])); }); out.push(["Prediction_" + R.pred.target, pr, [40, 22].concat(R.vars.map(function () { return 14; })).concat(ms.map(function () { return 12; })).concat([12, 10])]); }
    if (R.pick) out.push(["Parameter_Pick", [["Parameter", "Avg peer rank correlation", "t", "p", "Years", "Years positive", "Fund-years", "Status"]].concat(R.pick.all.map(function (x) { var st = R.pick.kept.indexOf(x) >= 0 ? "Kept" : R.pick.thin.indexOf(x) >= 0 ? "Too little data" : x.p <= ALPHA ? "Dropped: near-copy" : "Not significant"; return [x.name, x.ic, x.t, x.p, x.years, x.pos, x.n, st]; })), [40, 14, 10, 10, 8, 10, 10, 18]]);
    return out; }

  // ---------------- top quartile, category by category: in each category its own one-parameter regressions, the significant
  // parameters without near-copies (regPick), their multiple regression, and that line's top quartile in each test year
  var ABS = null;
  function absPanel(P) { if (!ABS || ABS.src !== P.rows) ABS = { src: P.rows, P: Object.assign({}, P, { rows: P.rows.map(function (r) { if (r[3] === null) return r; var c = r.slice(); c[3] = r[3] + P.nifty[r[0] + 1]; return c; }) }) }; return ABS.P; }
  function pooled(t) { var z = t.v > 0 ? (t.hits - t.base) / Math.sqrt(t.v) : NaN; return { z: z, p: isFinite(z) ? 2 * (1 - normCdf(Math.abs(z))) : NaN }; }
  // o = { group, target: "excess" | "absolute", from, to, tFrom, tTo, se, fe, vars (optional: fixed parameters, no selection) };
  // L = window.LATEST for the next-year prediction
  function isDropped(DF, name, year) { var v = DF[name]; return v === 1 || (!!v && v[year] === 1); }
  function tqCat(P, o, L, skipCats) { if (o.skip && o.skip.length) { var out0 = o.skip.map(function (c) { return P.categories.indexOf(c); }); P = Object.assign({}, P, { rows: P.rows.filter(function (r) { return out0.indexOf(r[1]) < 0; }) }); skipCats = (skipCats || []).concat(o.skip); }
    // o.dropFunds (the funds of the AMCs ticked on the page) leaves training and testing alone: tqPicks only keeps them out of the live picks
    var Q = o.target === "absolute" ? absPanel(P) : P, seen = {}; P.rows.forEach(function (r) { seen[r[1]] = 1; });
    var cats = o.combined ? [ALL] : o.group === ALL ? P.categories.filter(function (c, i) { return seen[i]; }) : [o.group], tot = { calls: 0, hits: 0, base: 0, v: 0 }, live = { calls: 0, hits: 0 };
    var list = cats.map(function (cat) { var oc = Object.assign({}, o, { group: cat, peer: cat === ALL ? "all" : "cat" }), simple = regSimple(Q, oc), pick = o.vars ? { significant: null, kept: [], dropped: [], thin: [], vars: o.vars.slice() } : regPick(Q, oc, simple), fit = pick.vars.length ? tqFit(P, oc, pick.vars, o.target) : null,
        test = fit ? tqTest(P, oc, [fit]) : null, m = test && test.n ? test.methods[0] : null, pred = fit && L ? tqPredict(L, oc, [fit], skipCats) : null, train = regRows(Q, oc).filter(function (r) { return r[3] !== null; }).length;
      if (m) { tot.calls += m.calls; tot.hits += m.hits; tot.base += m.base; tot.v += m.v; }
      if (pred) { live.calls += pred.check[0].calls; live.hits += pred.check[0].hits; }
      return { cat: cat, o: oc, train: train, simple: simple, pick: pick, fit: fit, test: test, m: m, pred: pred }; });
    var pz = pooled(tot); tot.z = pz.z; tot.p = pz.p;
    return { o: o, list: list, total: tot, live: live }; }
  function quartName(qs) { qs = (qs || [1]).slice().sort(); return qs.length === 4 ? "all quartiles" : qs.join(",") === "1" ? "top quartile" : qs.join(",") === "1,2" ? "top 2 quartiles" : qs.join(",") === "1,2,3" ? "top 3 quartiles" : qs.join(",") === "4" ? "bottom quartile" : qs.length === 1 ? "Q" + qs[0] : "quartiles " + qs.map(function (q) { return "Q" + q; }).join(" + "); }
  function tqCatSheets(R, P) { var qn = quartName(R.o.quarts), o = R.o, F = function (f, v) { return { t: typeof v === "string" ? "s" : "n", v: v, f: f }; }, yname = o.target === "absolute" ? "next-year fund return (excess + Nifty 50 return)" : "next-year excess return over the Nifty 50";
    var me = [["Top quartile prediction by category (" + o.target + " return)"], [], ["Funds", o.combined ? "All funds combined: one model, quartiles across all funds each year" : o.group === ALL ? "Every category, each with its own model" : o.group], ["Quartiles predicted", qn + " (Q1 = top)"], ["y", yname], ["Training (return years)", o.from + "-" + o.to], ["Test (return years)", o.tFrom + "-" + o.tTo], ["Year effects", o.fe ? "Yes" : "No"], ["Standard errors", o.se === "classic" ? "Classic OLS" : "Clustered by year"], [],
      ["Parameters", o.vars ? "Fixed: " + o.vars.join("; ") + " (no selection step)" : "Chosen by steps 1 and 2"], ["Step 1", "Every parameter regressed alone on y inside the category over the training years (sheet Parameters)."], ["Step 2", "Significant = p <= " + ALPHA + ". Left out if under " + Math.round(MIN_COVER * 100) + "% of the category's training fund-years have it; dropped if its rank correlation with a stronger kept parameter is above " + PICK_RHO + "."], ["Step 3", "Multiple regression of y on the kept parameters (sheet Lines)."],
      ["Step 4", "In every test year the funds are split into quartiles by the line's prediction (cut-offs round(n/4), round(n/2), round(3n/4); Q1 = top) and by actual return. Predicted = in the chosen quartiles by prediction; a hit is one also there by actual return. Random baseline = k*k/n, k = funds in the chosen quartiles."]];
    var sm = [["Category", "Training fund-years", "Significant", "In the model", "Predicted, " + qn, "Hits", "Hit ratio", "Random baseline hits", "Baseline ratio", "Lift", "p (pooled)", "Live " + (R.list[0] && R.list[0].pred ? R.list[0].pred.liveLabel : "") + " predicted", "Live hits"]];
    R.list.forEach(function (c) { var m = c.m, r = sm.length + 1, lv = c.pred ? c.pred.check[0] : null; sm.push([c.cat, c.train, c.pick.significant, c.fit ? c.pick.vars.length : 0, m ? m.calls : "", m ? m.hits : "", m ? F("F" + r + "/E" + r, m.ratio) : "", m ? m.base : "", m ? F("H" + r + "/E" + r, m.baseRatio) : "", m ? F("G" + r + "/I" + r, m.ratio / m.baseRatio) : "", m ? cl(m.pz) : "", lv ? lv.calls : "", lv ? lv.hits : ""]); });
    var n = sm.length; sm.push(["All categories", "", "", "", F("SUM(E2:E" + n + ")", R.total.calls), F("SUM(F2:F" + n + ")", R.total.hits), F("F" + (n + 1) + "/E" + (n + 1), R.total.hits / R.total.calls), F("SUM(H2:H" + n + ")", R.total.base), F("H" + (n + 1) + "/E" + (n + 1), R.total.base / R.total.calls), F("G" + (n + 1) + "/I" + (n + 1), R.total.hits / R.total.base), cl(R.total.p), R.live.calls, R.live.hits]);
    var pa = [["Category", "Parameter", "Direction", "t alone", "p alone", "Fund-years", "Share of fund-years", "Status"]];
    R.list.forEach(function (c) { var st = {}; c.pick.kept.forEach(function (k) { st[k.name] = c.fit ? "In the model" : "Kept, no model"; }); c.pick.dropped.forEach(function (d) { st[d.name] = "Dropped: " + d.rho.toFixed(2) + " with " + d.other; }); c.pick.thin.forEach(function (d) { st[d.name] = "Too little data"; });
      c.simple.forEach(function (x) { var t = x.fit ? x.fit.terms[0] : null; pa.push([c.cat, x.name, t ? (t.t > 0 ? "+" : "-") : "", t ? t.t : "", t ? cl(t.p) : "", x.fit ? x.fit.N : 0, x.fit ? x.fit.N / c.train : 0, st[x.name] || (t && t.p <= ALPHA ? "Significant" : t ? "Not significant" : "No result")]); }); });
    var ln = [["Category", "Variable", "Weight", "Standard error", "t", "p", "VIF", "Fund-years", "Years"]];
    R.list.forEach(function (c) { if (!c.fit) return; c.fit.fit.terms.forEach(function (t, i) { ln.push([c.cat, i < c.fit.vars.length ? c.fit.vars[i] : "Intercept", t.coef, t.se, t.t, t.p, i < c.fit.vars.length ? cl(t.vif) : "", c.fit.N, c.fit.G]); }); if (o.fe) ln.push([c.cat, "Starting value (average year effect)", c.fit.a, "", "", "", "", c.fit.N, c.fit.G]); });
    var yr = [["Category", "Return year", "Predicted", "Hits", "Hit ratio", "Baseline ratio"]]; R.list.forEach(function (c) { if (c.m) c.m.years.forEach(function (t) { var r = yr.length + 1; yr.push([c.cat, t.year, t.calls, t.hits, F("D" + r + "/C" + r, t.hits / t.calls), t.base / t.calls]); }); });
    var dt = [["Category", "Return year", "Fund", "Predicted " + o.target + " %", "Actual excess %", "Predicted quartile", "Actual quartile", "Predicted in " + qn, "Actually in " + qn, "Parameters used"]];
    R.list.forEach(function (c) { if (c.m) c.test.detail.forEach(function (d) { dt.push([d.cat, d.year, d.fund, d.score[o.target], d.actual, "Q" + d.pq[o.target], "Q" + d.q, d.picks[o.target] ? "Yes" : "No", d.top ? "Yes" : "No", c.fit.vars.join("; ")]); }); });
    var out = [["Read_Me", me, [24, 110]], ["Summary", sm, [24, 12, 11, 11, 12, 8, 10, 12, 10, 8, 10, 12, 10]], ["Parameters", pa, [22, 44, 9, 9, 9, 10, 10, 40]], ["Lines", ln, [22, 44, 12, 12, 9, 9, 9, 10, 8]], ["By_Year", yr, [22, 10, 10, 8, 10, 10]], ["Test_Funds", dt, [22, 10, 44, 14, 12, 10, 10, 12, 12, 60]]];
    var pr = [["Category", "Fund", "Predicted " + o.target + " %", "Predicted quartile", "Predicted in " + qn, "Live return", "Live quartile", "Live in " + qn]]; R.list.forEach(function (c) { if (c.pred) c.pred.funds.slice().sort(function (a, b) { return b.score[o.target] - a.score[o.target]; }).forEach(function (f) { pr.push([f.cat, f.name, f.score[o.target], "Q" + f.pq[o.target], f.pick[o.target] ? "Yes" : "No", f.live === null ? "" : f.live, f.liveQ === null ? "" : "Q" + f.liveQ, f.liveTop === null ? "" : f.liveTop ? "Yes" : "No"]); }); });
    if (pr.length > 1) out.push(["Prediction_" + (R.list.filter(function (c) { return c.pred; })[0].pred.target), pr, [22, 44, 14, 10, 12, 12, 10, 12]]);
    return out; }

  // ---------------- AR model portfolio: where its funds finished. The portfolio held at the end of March of year Y (the latest
  // rebalance on or before 31 March) is taken as held for all of calendar year Y, like the study's calendar-year returns.
  // Each holding's quartile is its excess return's quartile among its category (or all funds) that year; a hit is a holding
  // in the chosen quartiles. Random = the chosen quartiles' share of the group, k / n.
  function arPortfolio(A, y) { var cut = y + "-03-31", pick = null; A.portfolios.forEach(function (p) { if (p.date <= cut) pick = p; }); return pick; }
  // o = { peer: "cat" | "all", quarts, from, to }; L = window.LATEST for the part-year live row
  function arMp(P, A, o, L, skipCats) { var qs = o.quarts || [1], fi = {}, years = [];
    P.funds.forEach(function (f, i) { fi[f] = i; });
    function score(port, groups, info) { var t = { year: null, date: port.date, held: port.funds.length, funds: [], n: 0, hits: 0, base: 0, v: 0, w: 0, wHits: 0, wBase: 0, quart: [0, 0, 0, 0] };
      port.funds.forEach(function (h) { var x = info(h[0]); if (!x) { t.funds.push({ name: h[0], weight: h[1], q: null }); return; }
        var g = groups[x.key], q = g.q[x.i], k = g.k, pr = k / g.n, hit = qs.indexOf(q) >= 0 ? 1 : 0;
        t.funds.push({ name: h[0], cat: x.cat, weight: h[1], ret: x.ret, rank: g.rank[x.i], size: g.n, q: q, hit: hit });
        t.n++; t.hits += hit; t.base += pr; t.v += pr * (1 - pr); t.w += h[1]; t.wHits += h[1] * hit; t.wBase += h[1] * pr; t.quart[q - 1]++; });
      t.ratio = t.n ? t.hits / t.n : NaN; t.wRatio = t.w ? t.wHits / t.w : NaN; return t; }
    // every fund of one year with its rank and quartile in its group, and the portfolio's weight when it was held
    function everyFund(items, G, port, nameOf) { var held = {}; port.funds.forEach(function (h) { held[h[0]] = h[1]; });
      return items.map(function (it, i) { var g = G[it.key]; if (!g) return null; var name = nameOf(it), q = g.q[i];
        return { name: name, cat: it.cat, ret: it.ret, rank: g.rank[i], size: g.n, q: q, hit: qs.indexOf(q) >= 0 ? 1 : 0, weight: name in held ? held[name] : null }; }).filter(Boolean); }
    // quartiles of one set of funds; key = peer group
    function groupsOf2(items) { var G = {}; items.forEach(function (it, i) { (G[it.key] = G[it.key] || []).push(i); }); var out = {}, vals = items.map(function (it) { return it.ret; }), qi = quartIdx(vals, G);
      Object.keys(G).forEach(function (k) { if (G[k].length < PEER_MIN) return; var ix = G[k], q = {}, rank = {}, sorted = ix.slice().sort(function (a, b) { return vals[b] - vals[a]; });
        ix.forEach(function (i) { q[i] = qi[i]; }); sorted.forEach(function (i, j) { rank[i] = j + 1; }); out[k] = { n: ix.length, q: q, rank: rank, k: ix.filter(function (i) { return qs.indexOf(qi[i]) >= 0; }).length }; });
      return out; }
    for (var y = o.from; y <= o.to; y++) { var port = arPortfolio(A, y); if (!port) continue;
      var rows = P.rows.filter(function (r) { return r[0] === y - 1 && r[3] !== null; }); if (!rows.length) continue;
      var items = rows.map(function (r) { return { key: o.peer === "all" ? "all" : String(r[1]), ret: r[3], fund: r[2], cat: P.categories[r[1]] }; }), G = groupsOf2(items), at = {};
      items.forEach(function (it, i) { at[it.fund] = i; });
      var t = score(port, G, function (name) { var i = at[fi[name]]; if (i === undefined || !G[items[i].key]) return null; return { key: items[i].key, i: i, cat: items[i].cat, ret: items[i].ret }; });
      t.all = everyFund(items, G, port, function (it) { return P.funds[it.fund]; }); t.year = y; years.push(t); }
    var tot = { n: 0, hits: 0, base: 0, v: 0, w: 0, wHits: 0, wBase: 0, quart: [0, 0, 0, 0] };
    years.forEach(function (t) { ["n", "hits", "base", "v", "w", "wHits", "wBase"].forEach(function (k) { tot[k] += t[k]; }); t.quart.forEach(function (c, j) { tot.quart[j] += c; }); });
    var z = tot.v > 0 ? (tot.hits - tot.base) / Math.sqrt(tot.v) : NaN; tot.z = z; tot.p = isFinite(z) ? 2 * (1 - normCdf(Math.abs(z))) : NaN;
    var d = years.filter(function (t) { return t.n; }).map(function (t) { return t.ratio - t.base / t.n; }), md = d.length ? mean(d) : NaN, sd = 0; d.forEach(function (v) { sd += (v - md) * (v - md); }); sd = Math.sqrt(sd / Math.max(1, d.length - 1));
    tot.t = d.length > 1 && sd > 0 ? md / (sd / Math.sqrt(d.length)) : NaN; tot.pt = isFinite(tot.t) ? tP(tot.t, d.length - 1) : NaN; tot.beatYears = d.filter(function (v) { return v > 0; }).length; tot.years = d.length;
    var live = null;
    if (L && arPortfolio(A, L.target)) { var lp = arPortfolio(A, L.target), lit = L.funds.filter(function (f) { return f[2] !== null && !(skipCats && skipCats.indexOf(f[1]) >= 0); }).map(function (f) { return { key: o.peer === "all" ? "all" : f[1], ret: f[2], name: f[0], cat: f[1] }; }), LG = groupsOf2(lit), li = {};
      lit.forEach(function (it, i) { li[it.name] = i; });
      live = score(lp, LG, function (name) { var i = li[name]; if (i === undefined || !LG[lit[i].key]) return null; return { key: lit[i].key, i: i, cat: lit[i].cat, ret: lit[i].ret }; }); live.year = L.target; live.label = L.liveLabel;
      live.all = everyFund(lit, LG, lp, function (it) { return it.name; }); }
    return { o: o, years: years, total: tot, live: live }; }
  function arSheets(R, A) { var o = R.o, qn = quartName(o.quarts), F = function (f, v) { return { t: typeof v === "string" ? "s" : "n", v: v, f: f }; };
    var me = [["AR model portfolio: where its funds finished"], [], ["Source", A.source], ["Rule", "The portfolio held at the end of March of a year (the latest rebalance on or before 31 March) is taken as held for that whole calendar year."], ["Quartiles within", o.peer === "all" ? "All funds of the year" : "The fund's category that year"], ["Chosen quartiles", qn + " (Q1 = top; cut-offs round(n/4), round(n/2), round(3n/4) by calendar-year return)"], ["Hit", "A holding whose return put it in the chosen quartiles."], ["Random", "Expected share if the funds were picked at random: chosen quartiles' funds / all funds of the group."], ["Weighted", "Hits weighted by the portfolio weights."]];
    var yr = [["Return year", "Portfolio date", "Funds held", "With a return", "Q1", "Q2", "Q3", "Q4", "Hits", "Hit ratio", "Random", "Weighted hit ratio"]];
    R.years.concat(R.live ? [R.live] : []).forEach(function (t) { var r = yr.length + 1; yr.push([t.label ? t.year + " (" + t.label + ")" : t.year, t.date, t.held, t.n].concat(t.quart).concat([t.hits, F("I" + r + "/D" + r, t.ratio), t.n ? t.base / t.n : "", t.w ? t.wHits / t.w : ""])); });
    var T = R.total, n = R.years.length + 1; yr.push(["All years", "", F("SUM(C2:C" + n + ")", R.years.reduce(function (s3, t) { return s3 + t.held; }, 0)), F("SUM(D2:D" + n + ")", T.n)].concat(T.quart).concat([F("SUM(I2:I" + n + ")", T.hits), F("I" + (n + 1) + "/D" + (n + 1), T.hits / T.n), T.base / T.n, T.wHits / T.w]));
    var hd = [["Return year", "Portfolio date", "Fund", "Category", "Weight %", "Excess return %", "Rank", "Of", "Quartile", "In " + qn]];
    R.years.concat(R.live ? [R.live] : []).forEach(function (t) { t.funds.forEach(function (f) { hd.push([t.label ? t.year + " (" + t.label + ")" : t.year, t.date, f.name, f.cat || "", f.weight, f.q ? f.ret : "", f.q ? f.rank : "", f.q ? f.size : "", f.q ? "Q" + f.q : "No return", f.q ? (f.hit ? "Yes" : "No") : ""]); }); });
    var af = [["Return year", "Fund", "Category", "Held, weight %", "Excess return %", "Rank", "Of", "Quartile", "In " + qn]];
    R.years.concat(R.live ? [R.live] : []).forEach(function (t) { (t.all || []).forEach(function (f) { af.push([t.label ? t.year + " (" + t.label + ")" : t.year, f.name, f.cat, f.weight === null ? "" : f.weight, f.ret, f.rank, f.size, "Q" + f.q, f.hit ? "Yes" : "No"]); }); });
    return [["Read_Me", me, [18, 110]], ["By_Year", yr, [14, 12, 10, 10, 6, 6, 6, 6, 8, 10, 10, 12]], ["Holdings", hd, [14, 12, 44, 20, 9, 12, 7, 6, 9, 10]], ["All_Funds", af, [14, 44, 20, 12, 12, 7, 6, 9, 8]]]; }

  // ---------------- top picks per category: in every test year each category's best 2 or 3 funds by the line's prediction
  // (3 when the category has o.big+ funds), a hit when the fund finishes in the chosen quartiles of its category; and a
  // basket that takes o.basket[category] funds from each category. R = tqCat result.
  var BASKET = { "Large & Mid Cap": 3, "Focused Fund": 2, "Multi Cap Fund": 2, "Small cap Fund": 2, "Flexi Cap Fund": 2, "Large Cap Fund": 1, "Mid Cap Fund": 1, "Sector Funds": 1 };
  // a fund's score: points for the quartile it finished in, Q1 to Q4
  var SCORE = [100, 65, 35, 0];
  function tqPicks(R, o) { var qs = o.quarts || [1], tg = o.target, big = o.big || 20, basket = o.basket || BASKET, det = [], live = [];
    R.list.forEach(function (x) { if (x.test && x.test.n) det = det.concat(x.test.detail); if (x.pred) live = live.concat(x.pred.funds); });
    // pts = the picks' points, ep = their random score (the average points of their category that year)
    function blank() { return { picks: 0, hits: 0, base: 0, v: 0, pts: 0, ep: 0 }; }
    function add(t, p) { t.picks++; t.hits += p.hit; t.base += p.pr; t.v += p.pr * (1 - p.pr); t.pts += p.pts; t.ep += p.ep; }
    // one year (or the live year): groups by category; score / actual read through the getters
    // the funds of the ticked AMCs (o.dropFunds: 1 = every prediction year, or { year: 1 }) are removed from that test or live
    // year's data: never picked and not counted in the category's quartiles. Training keeps them (tqCat ignores o.dropFunds).
    function kept(yr) { return function (f) { return !o.dropFunds || !isDropped(o.dropFunds, f.fund || f.name, yr); }; }
    function run(items, score, actual, year, blocked) { var G = {}; items.forEach(function (d, i) { if (actual(d) !== null) (G[d.cat] = G[d.cat] || []).push(i); }); var picks = [], bask = [], every = [];
      Object.keys(G).sort().forEach(function (cat) { var ix = G[cat], n = ix.length; if (n < PEER_MIN) return; var sub = {}; sub.g = ix;
        var aq = quartIdx(items.map(actual), sub), k = ix.filter(function (i) { return qs.indexOf(aq[i]) >= 0; }).length, pr = k / n, ep = ix.reduce(function (a, i) { return a + SCORE[aq[i] - 1]; }, 0) / n, order = ix.slice().sort(function (a, b) { return score(items[b]) - score(items[a]); }), aord = ix.slice().sort(function (a, b) { return actual(items[b]) - actual(items[a]); }), N = n >= big ? 3 : 2, B = basket[cat] || 0, np = 0, nb = 0;
        order.forEach(function (i, j) { var d = items[i], row = { year: year, cat: cat, fund: d.fund || d.name, score: score(d), actual: actual(d), q: aq[i], rank: j + 1, actualRank: aord.indexOf(i) + 1, n: n, hit: qs.indexOf(aq[i]) >= 0 ? 1 : 0, pr: pr, pts: SCORE[aq[i] - 1], ep: ep };
          row.blocked = blocked && blocked(d) ? 1 : 0; row.pick = !row.blocked && np < N ? 1 : 0; row.inBasket = !row.blocked && nb < B ? 1 : 0;
          if (row.pick) { np++; picks.push(row); } if (row.inBasket) { nb++; bask.push(row); } every.push(row); }); });
      return { picks: picks, basket: bask, every: every }; }
    var years = {}; det.forEach(function (d) { (years[d.year] = years[d.year] || []).push(d); });
    var out = { years: [], total: blank(), basketTotal: blank(), cats: {}, basketCats: {}, picks: [], basket: [], every: [] };
    Object.keys(years).sort().forEach(function (y) { var r = run(years[y].filter(kept(+y)), function (d) { return d.score[tg]; }, function (d) { return d.actual; }, +y), t = blank(), b = blank();
      r.picks.forEach(function (p) { add(t, p); add(out.total, p); add(out.cats[p.cat] = out.cats[p.cat] || blank(), p); });
      r.basket.forEach(function (p) { add(b, p); add(out.basketTotal, p); add(out.basketCats[p.cat] = out.basketCats[p.cat] || blank(), p); });
      out.picks = out.picks.concat(r.picks); out.basket = out.basket.concat(r.basket); out.every = out.every.concat(r.every); out.years.push({ year: +y, picks: t, basket: b }); });
    [out.total, out.basketTotal].forEach(function (t) { var pz = pooled({ hits: t.hits, base: t.base, v: t.v }); t.z = pz.z; t.p = pz.p; });
    out.live = null;
    var ly = live.length ? R.list.filter(function (x) { return x.pred; })[0].pred.target : null; live = live.filter(kept(ly));
    if (live.length) { var Lr = run(live, function (f) { return f.score[tg]; }, function (f) { return f.live; }, ly), lt = blank(), lb = blank();
      Lr.picks.forEach(function (p) { add(lt, p); }); Lr.basket.forEach(function (p) { add(lb, p); });
      // every fund's next-year pick, including the ones with no live return yet
      var all = run(live, function (f) { return f.score[tg]; }, function () { return 0; }, null);
      out.live = { picks: lt, basket: lb, rows: Lr, next: all, label: R.list.filter(function (x) { return x.pred; })[0].pred.liveLabel, year: R.list.filter(function (x) { return x.pred; })[0].pred.target }; }
    return out; }
  // walk-forward: W = { years: [{ year, R }], live: R or null }, where each R = tqCat trained on o.from to the year before
  // that test year (its parameters chosen afresh) and tested on that year only, and live = tqCat trained up to the last
  // return year with the latest values. The picks of every year merged into one tqPicks-shaped result.
  function tqWalkPicks(W, o) { var z = function () { return { picks: 0, hits: 0, base: 0, v: 0, pts: 0, ep: 0 }; }, F = ["picks", "hits", "base", "v", "pts", "ep"];
    function add(a, b) { F.forEach(function (k) { a[k] += b[k]; }); }
    var out = { years: [], total: z(), basketTotal: z(), cats: {}, basketCats: {}, picks: [], basket: [], every: [], live: null };
    W.years.forEach(function (w) { var K = tqPicks(w.R, o); out.years = out.years.concat(K.years); add(out.total, K.total); add(out.basketTotal, K.basketTotal);
      Object.keys(K.cats).forEach(function (c) { add(out.cats[c] = out.cats[c] || z(), K.cats[c]); }); Object.keys(K.basketCats).forEach(function (c) { add(out.basketCats[c] = out.basketCats[c] || z(), K.basketCats[c]); });
      out.picks = out.picks.concat(K.picks); out.basket = out.basket.concat(K.basket); out.every = out.every.concat(K.every); });
    [out.total, out.basketTotal].forEach(function (t) { var pz = pooled(t); t.z = pz.z; t.p = pz.p; });
    if (W.live) out.live = tqPicks(W.live, o).live;
    return out; }
  function tqPickSheets(K, KA, R, RA, o) { var qn = quartName(o.quarts), F = function (f, v) { return { t: typeof v === "string" ? "s" : "n", v: v, f: f }; }, basket = o.basket || BASKET;
    // scores to one decimal: SF = a formula, SV = a value; pts(c) = the points for the quartile in cell c
    function SF(f, v) { var c = F(f, v); c.z = "0.0"; return c; }
    function SV(v) { return v === "" ? "" : { t: "n", v: v, z: "0.0" }; }
    function avg(t) { return t && t.picks ? t.pts / t.picks : ""; }
    function rnd(t) { return t && t.picks ? t.ep / t.picks : ""; }
    function pts(c) { return "IF(" + c + "=\"Q1\"," + SCORE[0] + ",IF(" + c + "=\"Q2\"," + SCORE[1] + ",IF(" + c + "=\"Q3\"," + SCORE[2] + "," + SCORE[3] + ")))"; }
    var nP = K.picks.length + 1, nB = K.basket.length + 1, PK = function (c) { return "Picks!$" + c + "$2:$" + c + "$" + nP; }, BK = function (c) { return "Basket!$" + c + "$2:$" + c + "$" + nB; };
    var me = [["Top picks per category (" + o.target + " return)"], [], ["Model", o.combined ? "One model on all funds; funds ranked inside their category" : "One model on " + o.group + " funds only, with the parameters chosen in that category"], ["Left out", (o.skip || []).join(", ") + (o.amcOut && o.amcOut.length ? "; these AMCs' funds removed from the test and live years shown (training keeps them): " + o.amcOut.join(", ") : "")], ["Training (return years)", o.from + "-" + o.to], ["Test (return years)", o.tFrom + "-" + o.tTo], ["Picks", "Each test year, each category's best 3 funds by predicted " + o.target + " return when it has " + (o.big || 20) + "+ funds, otherwise the best 2."],
      ["Hit", "A pick that finished in the " + qn + " of its category that year (quartile cut-offs round(n/4), round(n/2), round(3n/4))."], ["Random", "Chance that a randomly picked fund of the category finishes there: funds in the " + qn + " / funds in the category."],
      ["Basket", Object.keys(basket).map(function (c) { return c + " " + basket[c]; }).join(", ") + " (the model portfolio's category counts)."], ["AR previous", "The same picks from a line on the nine AR previous parameters."],
      ["Score", "Points for the quartile a fund finished in: Q1 " + SCORE[0] + ", Q2 " + SCORE[1] + ", Q3 " + SCORE[2] + ", Q4 " + SCORE[3] + " (the Score column on Picks and Basket, a formula on Actual quartile). By_Year and By_Category average it."], ["Random score", "The average score of the fund's category that year: what a random pick from the category would get."]];
    var sy = [["Return year", "Picks", "Hits", "Hit ratio", "Random", "Basket funds", "Basket hits", "Basket hit ratio", "AR previous picks hit ratio", "AR previous basket hit ratio", "Score", "Random score", "Basket score", "AR previous score"]];
    K.years.forEach(function (t) { var r = sy.length + 1, a = KA ? KA.years.filter(function (z) { return z.year === t.year; })[0] : null; sy.push([t.year, t.picks.picks, t.picks.hits, F("C" + r + "/B" + r, t.picks.hits / t.picks.picks), t.picks.base / t.picks.picks, t.basket.picks, t.basket.hits, t.basket.picks ? F("G" + r + "/F" + r, t.basket.hits / t.basket.picks) : "", a ? a.picks.hits / a.picks.picks : "", a && a.basket.picks ? a.basket.hits / a.basket.picks : "",
      SF("IFERROR(AVERAGEIFS(" + PK("K") + "," + PK("A") + ",A" + r + "),\"\")", avg(t.picks)), SF("IFERROR(AVERAGEIFS(" + PK("L") + "," + PK("A") + ",A" + r + "),\"\")", rnd(t.picks)), SF("IFERROR(AVERAGEIFS(" + BK("K") + "," + BK("A") + ",A" + r + "),\"\")", avg(t.basket)), SV(a ? avg(a.picks) : "")]); });
    var n = sy.length; sy.push(["All years", F("SUM(B2:B" + n + ")", K.total.picks), F("SUM(C2:C" + n + ")", K.total.hits), F("C" + (n + 1) + "/B" + (n + 1), K.total.hits / K.total.picks), K.total.base / K.total.picks, F("SUM(F2:F" + n + ")", K.basketTotal.picks), F("SUM(G2:G" + n + ")", K.basketTotal.hits), F("G" + (n + 1) + "/F" + (n + 1), K.basketTotal.hits / K.basketTotal.picks), KA ? KA.total.hits / KA.total.picks : "", KA && KA.basketTotal.picks ? KA.basketTotal.hits / KA.basketTotal.picks : "",
      SF("IFERROR(AVERAGE(" + PK("K") + "),\"\")", avg(K.total)), SF("IFERROR(AVERAGE(" + PK("L") + "),\"\")", rnd(K.total)), SF("IFERROR(AVERAGE(" + BK("K") + "),\"\")", avg(K.basketTotal)), SV(KA ? avg(KA.total) : "")]);
    var sc = [["Category", "Picks", "Hits", "Hit ratio", "Random", "Basket picks", "Basket hits", "AR previous picks hit ratio", "Score", "Random score", "Basket score", "AR previous score"]];
    Object.keys(K.cats).sort().forEach(function (c) { var t = K.cats[c], b = K.basketCats[c], a = KA && KA.cats[c], r = sc.length + 1; sc.push([c, t.picks, t.hits, F("C" + r + "/B" + r, t.hits / t.picks), t.base / t.picks, b ? b.picks : 0, b ? b.hits : 0, a ? a.hits / a.picks : "",
      SF("IFERROR(AVERAGEIFS(" + PK("K") + "," + PK("B") + ",A" + r + "),\"\")", avg(t)), SF("IFERROR(AVERAGEIFS(" + PK("L") + "," + PK("B") + ",A" + r + "),\"\")", rnd(t)), SF("IFERROR(AVERAGEIFS(" + BK("K") + "," + BK("B") + ",A" + r + "),\"\")", avg(b)), SV(a ? avg(a) : "")]); });
    function rows(list, head) { return [head].concat(list.map(function (p, i) { return [p.year, p.cat, p.fund, p.score, p.rank, p.n, p.actual, p.actualRank, "Q" + p.q, p.hit ? "Yes" : "No", F(pts("I" + (i + 2)), p.pts), SV(p.ep)]; })); }
    var head = ["Return year", "Category", "Fund", "Predicted " + o.target + " %", "Predicted rank", "Funds in category", "Actual excess %", "Actual rank", "Actual quartile", "Hit (" + qn + ")", "Score", "Random score"];
    var out = [["Read_Me", me, [22, 110]], ["By_Year", sy, [12, 8, 8, 10, 10, 12, 12, 14, 18, 18, 8, 12, 12, 16]], ["By_Category", sc, [22, 8, 8, 10, 10, 12, 12, 18, 8, 12, 12, 16]], ["Picks", rows(K.picks, head), [12, 20, 44, 14, 12, 12, 12, 10, 12, 12, 8, 12]], ["Basket", rows(K.basket, head), [12, 20, 44, 14, 12, 12, 12, 10, 12, 12, 8, 12]]];
    if (K.live) { var nx = [["Category", "Fund", "Predicted " + o.target + " %", "Rank in category", "Funds", "Top pick", "In basket", "Live return " + K.live.label, "Live quartile", "Live score"]], liveBy = {};
      K.live.rows.picks.concat(K.live.rows.basket).forEach(function (p) { liveBy[p.fund] = p; });
      var bk = {}; K.live.next.basket.forEach(function (p) { bk[p.fund] = 1; });
      K.live.next.picks.concat(K.live.next.basket.filter(function (p) { return !K.live.next.picks.some(function (q) { return q.fund === p.fund; }); })).forEach(function (p) { var l = liveBy[p.fund]; nx.push([p.cat, p.fund, p.score, p.rank, p.n, K.live.next.picks.some(function (q) { return q.fund === p.fund; }) ? "Yes" : "No", bk[p.fund] ? "Yes" : "No", l ? l.actual : "", l ? "Q" + l.q : "", l ? F(pts("I" + (nx.length + 1)), l.pts) : ""]); });
      out.push(["Picks_" + K.live.year, nx, [20, 44, 14, 10, 8, 10, 10, 14, 10, 10]]); }
    tqCatSheets(R, null).forEach(function (sh) { if (sh[0] === "Parameters" || sh[0] === "Lines") out.push(sh); });
    if (RA) tqCatSheets(RA, null).forEach(function (sh) { if (sh[0] === "Lines") out.push(["AR_Prev_Lines", sh[1], sh[2]]); });
    return out; }

  var api = { tqPicks: tqPicks, tqWalkPicks: tqWalkPicks, tqPickSheets: tqPickSheets, BASKET: BASKET, SCORE: SCORE, arMp: arMp, arSheets: arSheets, arPortfolio: arPortfolio, quartName: quartName, tqCat: tqCat, tqCatSheets: tqCatSheets, tqFit: tqFit, tqTest: tqTest, tqPredict: tqPredict, tqPick: tqPick, tqSheets: tqSheets, TQ_METHODS: TQ_METHODS, PEER_MIN: PEER_MIN, regSquare: regSquare, regCross: regCross, regTest: regTest, regTestSheets: regTestSheets, regDerive: regDerive, regCompare: regCompare, regPredict: regPredict, regTop: regTop, regSimple: regSimple, regPick: regPick, regMulti: regMulti, regSheets: regSheets, EXCESS_MIN: EXCESS_MIN, run: run, indicators: indicators, indSheets: indSheets, corr: corr, corrOrder: corrOrder, corrSheets: corrSheets, family: family, feasible: feasible, sheets: sheets, TARGET: TARGET, MIN_CALLS: MIN_CALLS, MIN_YEARS: MIN_YEARS, ALL: ALL, BASKETS: BASKETS, TIERS: TIERS, PREVIOUS: PREVIOUS, FIRST: 2006, LAST: 2025 };
  root.PeriodEngine = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : this);
