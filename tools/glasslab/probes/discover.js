// discover (run on the NATIVE render): which design tokens actually drive the page's big surfaces and text.
// Causal: a candidate token is set to a sentinel colour inline (!important beats any site rule) on the element and its
// ancestors; it counts only if the element's colour changes. Equal values ≠ driving (Gmail looks GM3 but hard-codes).
// Also: colour-token inventory (role guesses by name) and where tokens are redefined (scope for the site file). no args
(() => {
  const W = innerWidth, H = innerHeight, SENT = 'rgb(1, 2, 3)';
  const P = c => (c && c.match(/[\d.]+/g) || []).map(Number);
  const opaque = c => { const a = P(c); return a.length >= 3 && (a.length < 4 || a[3] >= .85); };
  const norm = (() => { const d = document.createElement('i'); document.body.append(d);
    return v => { d.style.color = ''; d.style.color = v; return d.style.color ? getComputedStyle(d).color : null; }; })();
  const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.getAttribute('role') ? `[role=${e.getAttribute('role')}]` : '')
    + (e.dataset.testid ? `[data-testid=${e.dataset.testid}]` : '') + [...e.classList].slice(0, 2).map(c => '.' + c).join('');
  const scopesOf = el => { const s = [document.documentElement, document.body]; for (let x = el, d = 0; x && d < 14; x = x.parentElement, d++) s.push(x); return [...new Set(s)]; };
  const candidates = (scopes, target) => { const out = new Set();
    for (const sc of scopes) { const cs = getComputedStyle(sc);
      for (const p of cs) if (p.startsWith('--')) { const v = cs.getPropertyValue(p).trim();
        if (v.length < 80 && (target === null || norm(v) === target)) out.add(p); } }
    return [...out]; };
  const drivers = (el, prop, cands) => { const scopes = scopesOf(el), out = [];
    for (const k of cands) { scopes.forEach(s => s.style.setProperty(k, SENT, 'important'));
      if (getComputedStyle(el)[prop] === SENT) out.push(k); scopes.forEach(s => s.style.removeProperty(k)); }
    return out; };
  const rect = e => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)]; };

  // surfaces: topmost opaque background on a 20×14 grid (incl. <html>: some sites paint the page there)
  const hits = new Map();
  for (let i = 0; i < 20; i++) for (let j = 0; j < 14; j++) {
    for (const e of document.elementsFromPoint((i + .5) * W / 20, (j + .5) * H / 14)) {
      const c = getComputedStyle(e).backgroundColor;
      if (opaque(c)) { const h = hits.get(c) || { color: c, n: 0, els: new Set() }; h.n++; h.els.add(e); hits.set(c, h); break; } } }
  const surfaces = [...hits.values()].sort((a, b) => b.n - a.n).slice(0, 10).map(h => {
    const el = [...h.els].sort((a, b) => rect(b)[2] * rect(b)[3] - rect(a)[2] * rect(a)[3])[0];
    const tokens = drivers(el, 'backgroundColor', candidates(scopesOf(el), h.color));
    const page = [...h.els].some(e => e === document.documentElement || e === document.body);
    return { color: h.color, share: +(h.n / 280).toFixed(2), tokens, el: sel(el), rect: rect(el), page,
      els: [...h.els].slice(0, 4).map(sel), hardcoded: !tokens.length };
  });

  // text: colour census by characters, then causal drivers for each colour's biggest element
  const tc = new Map(), tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n, k = 0; (n = tw.nextNode()) && k < 4000; k++) { const t = n.textContent.trim(), el = n.parentElement;
    if (t.length < 2 || !el) continue; const r = el.getBoundingClientRect(); if (r.bottom < 0 || r.top > H || !r.width) continue;
    const c = getComputedStyle(el).color, e = tc.get(c) || { color: c, chars: 0, els: [] }; e.chars += t.length; e.els.push([el, t.length]); tc.set(c, e); }
  const text = [...tc.values()].sort((a, b) => b.chars - a.chars).slice(0, 8).map(e => {
    const el = e.els.sort((a, b) => b[1] - a[1])[0][0];
    const tokens = drivers(el, 'color', candidates(scopesOf(el), e.color));
    return { color: e.color, chars: e.chars, tokens, el: sel(el), hardcoded: !tokens.length,
      els: [...new Set(e.els.map(x => sel(x[0]).replace(/#[^.\[]+/, '')))].slice(0, 5) };
  });

  // inventory: colour tokens on :root/body by role keyword (for mapping beyond what's visible now: menus, hovers…)
  const roles = { bg: /(bg|background|surface|canvas|sidebar|panel|card|elevat|popover|menu|overlay|fill)/i,
    text: /(text|fg|foreground|font-color|on-)/i, line: /(border|outline|divider|separator|stroke)/i,
    accent: /(accent|primary|brand|link|interactive)/i, status: /(error|danger|warning|success|positive|negative)/i };
  const inv = {}; const cs = getComputedStyle(document.body);
  for (const p of cs) if (p.startsWith('--')) { const v = cs.getPropertyValue(p).trim(); if (v.length > 60 || !norm(v)) continue;
    for (const [r, re] of Object.entries(roles)) if (re.test(p)) { (inv[r] = inv[r] || []).push([p, v]); break; } }
  for (const r in inv) inv[r] = inv[r].slice(0, 40);

  // token scopes: elements (besides :root/body) that redefine any driving token → selectors the site file must cover
  const driving = [...new Set([...surfaces, ...text].flatMap(x => x.tokens))], redefined = new Set();
  for (const e of document.querySelectorAll('body *')) { if (redefined.size > 12) break; const p = e.parentElement;
    if (!p) continue; const a = getComputedStyle(e), b = getComputedStyle(p);
    for (const k of driving) if (a.getPropertyValue(k) !== b.getPropertyValue(k)) { redefined.add(sel(e)); break; } }

  return JSON.stringify({ url: location.href, surfaces, text, inventory: inv, redefinedAt: [...redefined] });
})
