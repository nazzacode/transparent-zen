// text runs: APCA per run through its real paint stack over backdrop bounds. args: bounds [[r,g,b]...], tint [r,g,b,a]
((bounds, tint) => {
  const P = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return [0,0,0,0];
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0],p[1],p[2],p.length>3?p[3]:1]; };
  const over = (top, bot) => { const a = top[3]; return [0,1,2].map(i => top[i]*a + bot[i]*(1-a)); };
  const lum = c => { const f = v => (v/=255) <= .03928 ? v/12.92 : ((v+.055)/1.055)**2.4;
    return .2126*f(c[0]) + .7152*f(c[1]) + .0722*f(c[2]); };
  // APCA-W3 0.0.98G (perceptual; weights thin/small text properly) → |Lc|
  const Ys = c => { const f = v => (v/255)**2.4; return .2126729*f(c[0]) + .7151522*f(c[1]) + .072175*f(c[2]); };
  const apca = (t, b) => { const cl = y => y > .022 ? y : y + (.022 - y)**1.414; let T = cl(Ys(t)), B = cl(Ys(b));
    if (Math.abs(B - T) < .0005) return 0;
    const S = B > T ? (B**.56 - T**.57)*1.14 : (B**.65 - T**.62)*1.14;
    return Math.abs(B > T ? (S < .1 ? 0 : S - .027) : (S > -.1 ? 0 : S + .027)) * 100; };
  const cr = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); };
  const sel = e => e.tagName.toLowerCase() + (e.id ? '#'+e.id : '') + [...e.classList].slice(0,2).map(c=>'.'+c).join('')
    + (e.getAttribute('role') ? `[role=${e.getAttribute('role')}]` : '');
  const W = innerWidth, H = innerHeight, seen = new Set(), runs = [];
  // screen-reader-only / clipped / off-screen (sr-only patterns: clip rect, 1px boxes, clip-path inset)
  const hidden = el => { for (let e = el, d = 0; e && e !== document.body && d < 6; e = e.parentElement, d++) {
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    if (s.clip && s.clip !== 'auto') return true;
    if (s.clipPath && s.clipPath.startsWith('inset(50%')) return true;
    if ((r.width <= 2 || r.height <= 2) && s.overflow !== 'visible') return true;
    if (+s.opacity === 0) return true;
    if (r.bottom <= 0 || r.right <= 0 || r.top >= H || r.left >= W) return true; }
    return false; };
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = tw.nextNode()) && runs.length < 600;) {
    const t = n.textContent.trim(); if (t.length < 2) continue;
    const el = n.parentElement; if (!el || seen.has(el)) continue; seen.add(el);
    const cs = getComputedStyle(el); if (cs.visibility !== 'visible' || +cs.opacity === 0) continue;
    if (hidden(el)) continue;
    const r = document.createRange(); r.selectNodeContents(n); const b = r.getClientRects()[0];
    if (!b || b.width < 2 || b.height < 2 || b.right < 0 || b.bottom < 0 || b.left > W || b.top > H) continue;
    const x = Math.min(W-1, Math.max(0, b.left + Math.min(b.width/2, 12))), y = Math.min(H-1, Math.max(0, b.top + b.height/2));
    // strict hit-test: the point must land on the element (or inside it); else it's covered or clipped by a scroller
    const stack = document.elementsFromPoint(x, y); const i = stack.findIndex(s => s === el || el.contains(s));
    if (i < 0) continue;
    let img = false, chip = false; const layers = [];
    for (let k = stack.length - 1; k >= i; k--) { if (stack[k] === document.documentElement) continue; const s = getComputedStyle(stack[k]);
      // image/gradient counts only if nothing opaque paints above it (bottom→top walk: an opaque layer resets it)
      if (s.backgroundImage !== 'none') img = true;
      else if (P(s.backgroundColor)[3] >= .95) img = false;
      const c = P(s.backgroundColor); if (c[3] > 0) layers.push(c);
      // pseudo-element fills paint above their element's own background (pill buttons, cards drawn with ::before)
      for (const pe of ['::before', '::after']) { const ps = getComputedStyle(stack[k], pe);
        // only pseudo fills that cover the element (inset 0 / full size), e.g. pill buttons
        if (ps.content !== 'none' && ps.position === 'absolute' && (ps.inset === '0px' || (ps.top === '0px' && ps.left === '0px'
            && (ps.width === stack[k].getBoundingClientRect().width + 'px' || ps.right === '0px')))) {
          const pc = P(ps.backgroundColor); if (pc[3] > 0) layers.push(pc); } }
      if (c[3] >= .85 && (stack[k].getAttribute('style') || '').includes('background-color')) chip = true;  // site-coloured chip
      if (c[3] >= .85 && Math.max(c[0], c[1], c[2]) - Math.min(c[0], c[1], c[2]) > 60) chip = true; }  // saturated fill = accent control
    // site data colour on the nearest inline-coloured ancestor (chip colour may sit outside the hit-test stack)
    { const anc = el.closest('[style*="background-color"]'); if (anc && P(getComputedStyle(anc).backgroundColor)[3] >= .85) chip = true; }
    const fg = P(cs.color), px = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 600;
    // APCA floors: <16px body Lc75 (short labels ≤20 chars = non-body Lc60), <24px Lc60, larger Lc45; bold eases one step
    // control labels (buttons/tabs/menu items/options) are labels whatever their length
    const label = t.length <= 20 || !!el.closest('button, [role=button], [role=tab], [role=option], [role=menuitem]');
    const tier = (px < 16 ? (label ? 1 : 0) : px < 24 ? 1 : 2) + (bold ? 1 : 0), need = [75, 60, 45, 45][Math.min(tier, 3)];
    const res = bounds.map(bd => { let bg = over(tint, bd); for (const l of layers) bg = over(l, bg); return apca(over(fg, bg), bg); });
    runs.push({ sel: sel(el), t: t.slice(0, 40), x: Math.round(x), y: Math.round(y), n: Math.min(t.length, 200), px: Math.round(px), need, img,
      cr: res.map(v => Math.round(v)), fg: cs.color, chip });
  }
  return JSON.stringify(runs);
})
