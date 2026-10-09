// unity: topmost painted surface on a 20×14 grid vs glass.css tier colours; returns shared fg colours too. no args
(() => {
  const P = c => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const probe = document.createElement('i'); probe.style.cssText = 'position:fixed;left:-9px;width:1px;height:1px'; document.body.append(probe);
  const tok = v => { probe.style.backgroundColor = `var(${v})`; return P(getComputedStyle(probe).backgroundColor); };
  const tiers = ['--g-frame', '--g-window', '--g-content', '--g-content-abs', '--g-popover', '--g-card', '--g-fill', '--g-fill-hover',
    '--g-fill-selected', '--g-paper'].map(t => [t, tok(t)]).filter(x => x[1]);
  const fgs = ['--g-fg', '--g-fg-2', '--g-fg-3'].map(t => { probe.style.color = `var(${t})`; return P(getComputedStyle(probe).color); });
  probe.remove();
  const near = (a, b, tc = 8, ta = .05) => Math.abs(a[0]-b[0]) <= tc && Math.abs(a[1]-b[1]) <= tc && Math.abs(a[2]-b[2]) <= tc && Math.abs(a[3]-b[3]) <= ta;
  const W = innerWidth, H = innerHeight, tally = {}, foreign = new Map(); let ok = 0, bad = 0;
  for (let i = 0; i < 20; i++) for (let j = 0; j < 14; j++) {
    for (const e of document.elementsFromPoint((i + .5) * W / 20, (j + .5) * H / 14)) {
      if (e === document.documentElement) break;
      const cs = getComputedStyle(e);
      if (/^(IMG|VIDEO|CANVAS|SVG|PICTURE|IFRAME)$/.test(e.tagName) || (cs.backgroundImage !== 'none' && !cs.backgroundImage.includes('gradient'))) break;
      const c = P(cs.backgroundColor); if (!c || c[3] < .02) continue;
      if ((e.getAttribute('style') || '').includes('background')) break;  // site data colour (event chip, label) — exempt
      const t = tiers.find(([, v]) => near(c, v));
      if (t) { ok++; tally[t[0]] = (tally[t[0]] || 0) + 1; }
      else { bad++; const k = cs.backgroundColor + ' ' + e.tagName.toLowerCase() + (e.getAttribute('role') ? `[role=${e.getAttribute('role')}]` : '')
        + [...e.classList].slice(0, 2).map(x => '.' + x).join(''); foreign.set(k, (foreign.get(k) || 0) + 1); }
      break;
    }
  }
  return JSON.stringify({ surface: ok / Math.max(1, ok + bad), tiers: tally,
    foreign: [...foreign].sort((a, b) => b[1] - a[1]).slice(0, 6), fgs: fgs.map(f => f && f.slice(0, 3)) });
})
