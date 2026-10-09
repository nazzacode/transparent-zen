#!/usr/bin/env python3
"""glasslab: readability + look test matrix for site glass styles (headless Zen, live cookies, never touches focus).

  glasslab.py XPI OUTDIR [SCREEN-FILTER]      (run in nix-shell -p "python3.withPackages(p:[p.websockets p.pillow])")

Per screen × glass mode (dark/light) × slider alpha (ALPHAS):
  - captures the page over pure black and pure white → exact per-pixel colour + alpha (CSP-proof; no page backdrop needed)
  - probes every visible text run: composites its real paint stack (elementsFromPoint) over the worst realistic backdrops
    (BOUNDS = blurred-wallpaper luminance extremes, behind Zen's web-app window tint) → APCA Lc vs size-based floors
Offline: composites the captures onto blurred wallpapers (WALLS) → contact sheets; report.json + report.md with
per-combo pass rates and worst offenders. Exit code ≠ 0 if any default-alpha combo falls under PASS_MIN.
"""
import asyncio, base64, io, json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tzlab  # setup(), Bidi, PORT, LAB
from PIL import Image

ALPHAS = [0.2, 0.45, 0.7]          # popup slider 20 / 45 (default) / 70 %
DEFAULT_ALPHA = 0.45
MODES = ["dark", "light"]
# web-app window tint under the page (dotfiles/zen/userChrome.css --webapp-tint), per mode
ZEN_TINT = {"dark": (0, 0, 0, 0), "light": (0, 0, 0, 0)}  # web-app window tint: none, the page owns all tint (glass.css)
# blurred-wallpaper luminance extremes measured over all 22 live wallpapers (p5≈0, p95≈221)
BOUNDS = [(0, 0, 0), (222, 222, 222)]
PASS_MIN = 0.9                      # share of text (by chars) that must meet its APCA floor at default alpha
WALL_DIR = os.path.expanduser("~/.cache/zen-stage/glass/wall")
WALLS = ["earth-iss", "new-york-day", "liwa-dune-fields", "europe-at-night", "grand-canyon-river-valley"]

# screens: url + optional JS run after load (READ-ONLY: never send/archive/mark; open only already-read items)
SCREENS = [
    {"id": "gcal-week", "url": "https://calendar.google.com/calendar/r/week"},
    {"id": "gcal-month", "url": "https://calendar.google.com/calendar/r/month"},
    {"id": "gcal-event", "url": "https://calendar.google.com/calendar/r/week",
     "act": "document.querySelector('[data-eventid][role=button]')?.click()"},
    {"id": "gmail-inbox", "url": "https://mail.google.com/mail/u/0/#inbox"},
    {"id": "gmail-thread", "url": "https://mail.google.com/mail/u/0/#inbox",
     "act": "[...document.querySelectorAll('tr.zA')].find(r=>r.classList.contains('yO'))?.click()"},  # yO = read row
    {"id": "reader-library", "url": "https://read.readwise.io/later"},
    {"id": "reader-doc", "url": "https://read.readwise.io/archive",
     "act": "document.querySelector('a[href*=\"/read/\"]')?.click()"},
    {"id": "claude-home", "url": "https://claude.ai/new"},
    {"id": "claude-recents", "url": "https://claude.ai/recents"},
    {"id": "substack-home", "url": "https://substack.com/home"},
    {"id": "youtube-home", "url": "https://www.youtube.com/"},
    {"id": "google-search", "url": "https://www.google.com/search?q=liquid+glass+design"},
]

PROBE = r"""
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
      if (s.backgroundImage !== 'none' && !s.backgroundImage.includes('gradient')) img = true;
      const c = P(s.backgroundColor); if (c[3] > 0) layers.push(c);
      if (c[3] >= .85 && (stack[k].getAttribute('style') || '').includes('background-color')) chip = true; }  // site-coloured chip
    const fg = P(cs.color), px = parseFloat(cs.fontSize), bold = +cs.fontWeight >= 600;
    // APCA floors: <16px body Lc75 (short labels ≤20 chars = non-body Lc60), <24px Lc60, larger Lc45; bold eases one step
    const tier = (px < 16 ? (t.length <= 20 ? 1 : 0) : px < 24 ? 1 : 2) + (bold ? 1 : 0), need = [75, 60, 45, 45][Math.min(tier, 3)];
    const res = bounds.map(bd => { let bg = over(tint, bd); for (const l of layers) bg = over(l, bg); return apca(over(fg, bg), bg); });
    runs.push({ sel: sel(el), t: t.slice(0, 40), n: Math.min(t.length, 200), px: Math.round(px), need, img,
      cr: res.map(v => Math.round(v)), fg: cs.color, chip });
  }
  return JSON.stringify(runs);
})
"""

# token discovery (native render): big opaque backgrounds → which CSS custom properties resolve to that exact colour.
# Map tokens, not elements: hashed class names churn, design tokens don't. Leftovers → structural selectors (role/id/testid).
DISCOVER = r"""
(() => {
  const norm = (() => { const d = document.createElement('i'); document.body.append(d);
    return v => { d.style.color = ''; d.style.color = v; return d.style.color ? getComputedStyle(d).color : null; }; })();
  const W = innerWidth, H = innerHeight, hits = new Map();
  for (let i = 0; i < 20; i++) for (let j = 0; j < 14; j++) {
    for (const e of document.elementsFromPoint((i + .5) * W / 20, (j + .5) * H / 14)) {
      if (e === document.documentElement) break;
      const c = getComputedStyle(e).backgroundColor, a = (c.match(/[\d.]+/g) || []).map(Number);
      if (a.length && (a.length < 4 || a[3] >= .85)) { const h = hits.get(c) || { color: c, n: 0, els: new Set() };
        h.n++; h.els.add(e); hits.set(c, h); break; } }
  }
  const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.getAttribute('role') ? `[role=${e.getAttribute('role')}]` : '')
    + (e.dataset.testid ? `[data-testid=${e.dataset.testid}]` : '') + [...e.classList].slice(0, 2).map(c => '.' + c).join('');
  // causality: a token only counts if setting it to a sentinel actually changes the element (equal value ≠ used)
  const probeSheet = new CSSStyleSheet(); document.adoptedStyleSheets = [...document.adoptedStyleSheets, probeSheet];
  const drives = (tok, els) => { probeSheet.replaceSync(`:root, :root * { ${tok}: rgb(1, 2, 3) !important; }`);
    const r = els.some(e => getComputedStyle(e).backgroundColor === 'rgb(1, 2, 3)'); probeSheet.replaceSync(''); return r; };
  const out = [];
  for (const h of [...hits.values()].sort((a, b) => b.n - a.n).slice(0, 10)) {
    const cand = new Set(), scopes = new Set([document.documentElement, document.body]), els = [...h.els].slice(0, 6);
    for (const e of els) for (let x = e, d = 0; x && d < 4; x = x.parentElement, d++) scopes.add(x);
    for (const sc of scopes) { const cs = getComputedStyle(sc);
      for (const p of cs) if (p.startsWith('--')) { const v = cs.getPropertyValue(p).trim();
        if (v.length < 60 && /^(#|rgb|hsl|oklch|color|[a-z]+$)/.test(v) && norm(v) === h.color) cand.add(p); } }
    const tokens = [...cand].filter(t => drives(t, els));
    out.push({ color: h.color, share: +(h.n / 280).toFixed(2), tokens, equalOnly: [...cand].filter(t => !tokens.includes(t)).slice(0, 6),
      els: els.slice(0, 4).map(sel) });
  }
  document.adoptedStyleSheets = document.adoptedStyleSheets.filter(x => x !== probeSheet);
  // text colour census: which colours carry the text, on which elements (for sites that hard-code text colours)
  const tc = new Map(), tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n, k = 0; (n = tw.nextNode()) && k < 3000; k++) { const t = n.textContent.trim(); if (t.length < 2 || !n.parentElement) continue;
    const r = n.parentElement.getBoundingClientRect(); if (r.bottom < 0 || r.top > H || !r.width) continue;
    const c = getComputedStyle(n.parentElement).color, e = tc.get(c) || { color: c, chars: 0, els: new Map() };
    e.chars += t.length; const k2 = sel(n.parentElement).replace(/#[^.\[]+/, ''); e.els.set(k2, (e.els.get(k2) || 0) + t.length); tc.set(c, e); }
  const text = [...tc.values()].sort((a, b) => b.chars - a.chars).slice(0, 10).map(e => ({ color: e.color, chars: e.chars,
    els: [...e.els].sort((a, b) => b[1] - a[1]).slice(0, 5).map(x => x[0]) }));
  return JSON.stringify({ surfaces: out, text });
})()
"""

# unity: does the page actually LOOK like the shared interface? (objective targets, same for every site)
#  surfaces: topmost painted background at a 20×14 grid must be a glass.css tier colour (chips/inline colours/images exempt)
#  text: neutral (low-chroma) text must be one of --g-fg/-fg-2/-fg-3 (saturated = accent/status, allowed)
SURFACE_MIN, TEXT_MIN = 0.9, 0.85
UNITY = r"""
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
})()
"""


def neutral_text_conformance(runs, fgs, tol=10):
    """share of neutral text chars whose colour is a glass foreground (saturated text = accent, ignored)"""
    def rgb(c):
        m = re.findall(r"[\d.]+", c); return [float(x) for x in m[:3]] if len(m) >= 3 else None
    ok = tot = 0
    for r in runs:
        c = rgb(r["fg"])
        if not c or max(c) - min(c) > 24: continue  # chromatic → accent/status
        tot += r["n"]
        if any(f and all(abs(c[i] - f[i]) <= tol for i in range(3)) for f in fgs): ok += r["n"]
    return ok / tot if tot else 1.0


def composite(black, white, wall, tint):
    """exact: out = B + (1-α)·(wall ⊕ zen tint), α = 1 - (W-B)/255 (mean over channels)"""
    import numpy as np  # noqa: optional fast path
    B = np.asarray(black.convert("RGB"), dtype=np.float32); Wt = np.asarray(white.convert("RGB"), dtype=np.float32)
    alpha = 1 - (Wt - B).mean(axis=2, keepdims=True) / 255
    bg = np.asarray(wall.convert("RGB").resize(black.size), dtype=np.float32)
    bg = bg * (1 - tint[3]) + np.array(tint[:3], dtype=np.float32) * tint[3]
    out = np.clip(B + (1 - alpha) * bg, 0, 255).astype("uint8")
    return Image.fromarray(out), float(1 - alpha.mean())


async def shot(b, ctx, backdrop):
    await b.eval(ctx, f"document.documentElement.style.setProperty('background','{backdrop}','important')")
    await asyncio.sleep(0.35)
    s = await b.call("browsingContext.captureScreenshot", context=ctx)
    return Image.open(io.BytesIO(base64.b64decode(s["data"])))


async def run(screens, out):
    for _ in range(60):
        try:
            ws = await tzlab.websockets.connect(f"ws://127.0.0.1:{tzlab.PORT}/session", max_size=2**27); break
        except OSError: await asyncio.sleep(1)
    b = tzlab.Bidi(ws)
    await b.call("session.new", capabilities={})
    ctx = (await b.call("browsingContext.getTree"))["contexts"][0]["context"]
    await b.call("browsingContext.setViewport", context=ctx, viewport={"width": 1400, "height": 1000})
    results = []
    for sc in screens:
        try:
            await b.call("browsingContext.navigate", context=ctx, url=sc["url"], wait="complete")
        except RuntimeError as e:
            print(f"{sc['id']}: nav {e}")
        await asyncio.sleep(sc.get("settle", 7))
        if sc.get("act"):
            await b.eval(ctx, sc["act"]); await asyncio.sleep(4)
        # native baseline: detach the extension's stylesheets (headless → <link data-tz-file>), probe, reattach
        await b.eval(ctx, "window.__tz=[...document.querySelectorAll('link[data-tz-file]')];window.__tz.forEach(l=>l.remove());"
                          "document.documentElement.classList.remove('tz-initialized')")
        await asyncio.sleep(0.6)
        nat = await b.call("browsingContext.captureScreenshot", context=ctx)
        open(f"{out}/shots/{sc['id']}.native.png", "wb").write(base64.b64decode(nat["data"]))
        tokens = json.loads(await b.eval(ctx, DISCOVER) or "[]")
        json.dump(tokens, open(f"{out}/tokens-{sc['id']}.json", "w"), indent=1)
        native = {(r["sel"], r["t"]): min(r["cr"]) for r in json.loads(
            await b.eval(ctx, f"({PROBE})({json.dumps(BOUNDS)},[0,0,0,0])") or "[]")}
        await b.eval(ctx, "window.__tz.forEach(l=>document.head.append(l));document.documentElement.classList.add('tz-initialized')")
        await asyncio.sleep(0.8)
        for mode in MODES:
            for a in ALPHAS:
                await b.eval(ctx, f"document.documentElement.dataset.tzGlass='{mode}';"
                                  f"document.documentElement.style.setProperty('--tz-glass-alpha','{a}')")
                await asyncio.sleep(0.4)
                key = f"{sc['id']}.{mode}.{int(a*100)}"
                blk, wht = await shot(b, ctx, "#000"), await shot(b, ctx, "#fff")
                blk.save(f"{out}/raw/{key}.black.png"); wht.save(f"{out}/raw/{key}.white.png")
                await b.eval(ctx, "document.documentElement.style.removeProperty('background')")
                runs = json.loads(await b.eval(ctx, f"({PROBE})({json.dumps(BOUNDS)},{json.dumps(list(ZEN_TINT[mode]))})") or "[]")
                chips = [r for r in runs if r.get("chip")]; runs = [r for r in runs if not r.get("chip")]
                # target per run: its APCA floor, relaxed to the site's own native contrast (−10%) where the native
                # design is already below the floor → glass must never read worse than the original site
                for r in runs:
                    nv = native.get((r["sel"], r["t"]))
                    r["native"] = nv
                    r["target"] = r["need"] if nv is None else min(r["need"], nv * 0.9)
                uni = json.loads(await b.eval(ctx, UNITY) or "{}")
                uni["text"] = neutral_text_conformance(runs, uni.get("fgs", []))
                tot = sum(r["n"] for r in runs) or 1
                ok = [sum(r["n"] for r in runs if r["cr"][k] >= r["target"]) / tot for k in range(len(BOUNDS))]
                worst = sorted(runs, key=lambda r: min(r["cr"]) / max(r["target"], 1))[:8]
                agg = {}
                for r in runs:
                    if min(r["cr"]) < r["target"]:
                        g = agg.setdefault(r["sel"], {"sel": r["sel"], "chars": 0, "lc": r["cr"], "target": round(r["target"]), "fg": r["fg"], "t": r["t"]})
                        g["chars"] += r["n"]
                failing = sorted(agg.values(), key=lambda g: -g["chars"])[:10]
                results.append({"key": key, "screen": sc["id"], "mode": mode, "alpha": a, "url": sc["url"],
                                "texts": len(runs), "chips": len(chips), "unity": uni, "pass": [round(v, 3) for v in ok], "worst": worst, "failing": failing})
                print(f"{key:28s} texts {len(runs):3d}  contrast(black,bright) {ok[0]:4.0%} {ok[1]:4.0%}  "
                      f"unity surface {uni.get('surface', 0):4.0%} text {uni['text']:4.0%}", flush=True)
    await ws.close()
    return results


def sheets(results, out):
    walls = {w: Image.open(f"{WALL_DIR}/blur-{w}.png") for w in WALLS if os.path.exists(f"{WALL_DIR}/blur-{w}.png")}
    for scr in dict.fromkeys(r["screen"] for r in results):
        tiles = []  # row per mode, col per alpha, on the first wallpaper; then a row of all walls at default alpha (dark)
        for mode in MODES:
            row = []
            for a in ALPHAS:
                key = f"{scr}.{mode}.{int(a*100)}"
                blk, wht = Image.open(f"{out}/raw/{key}.black.png"), Image.open(f"{out}/raw/{key}.white.png")
                img, _ = composite(blk, wht, walls[WALLS[0]], ZEN_TINT[mode]); img.save(f"{out}/shots/{key}.png"); row.append(img)
            tiles.append(row)
        for mode in MODES:
            key = f"{scr}.{mode}.{int(DEFAULT_ALPHA*100)}"
            blk, wht = Image.open(f"{out}/raw/{key}.black.png"), Image.open(f"{out}/raw/{key}.white.png")
            tiles.append([composite(blk, wht, wl, ZEN_TINT[mode])[0] for wl in walls.values()])
        tw, th = 700, 500
        cols = max(len(r) for r in tiles)
        sheet = Image.new("RGB", (cols * tw, len(tiles) * th), (40, 40, 40))
        for y, row in enumerate(tiles):
            for x, im in enumerate(row):
                sheet.paste(im.resize((tw, th)), (x * tw, y * th))
        sheet.save(f"{out}/sheet-{scr}.jpg", quality=85)


def report(results, out):
    json.dump(results, open(f"{out}/report.json", "w"), indent=1)
    lines = ["| screen | mode | α | texts | contrast over black | over bright | surface unity | text unity | worst |",
             "|---|---|---|---|---|---|---|---|---|"]
    fails = []
    for r in results:
        w = r["worst"][0] if r["worst"] else None
        u = r.get("unity", {})
        lines.append(f"| {r['screen']} | {r['mode']} | {int(r['alpha']*100)} | {r['texts']} | {r['pass'][0]:.0%} | {r['pass'][1]:.0%} | "
                     f"{u.get('surface', 0):.0%} | {u.get('text', 0):.0%} | "
                     + (f"`{w['sel']}` “{w['t'][:24]}” {min(w['cr'])}:1 (need {w['need']})" if w else "") + " |")
        if r["alpha"] == DEFAULT_ALPHA and (min(r["pass"]) < PASS_MIN or u.get("surface", 0) < SURFACE_MIN or u.get("text", 0) < TEXT_MIN):
            fails.append(r["key"])
    open(f"{out}/report.md", "w").write("\n".join(lines) + f"\n\nfails (default α: contrast < {PASS_MIN:.0%}, surface unity < {SURFACE_MIN:.0%}, text unity < {TEXT_MIN:.0%}): {fails or 'none'}\n")
    return fails


def main(xpi, out, filt=""):
    os.makedirs(f"{out}/raw", exist_ok=True); os.makedirs(f"{out}/shots", exist_ok=True)
    screens = [s for s in SCREENS if re.search(filt, s["id"])]
    tzlab.subprocess.run(["pkill", "-f", "^/app/zen/zen .*--profile .*/tzlab"]); time.sleep(1)
    tzlab.setup(xpi)
    zen = tzlab.subprocess.Popen(["flatpak", "run", "--command=/app/zen/zen", "app.zen_browser.zen", "--headless", "--no-remote",
                                  "--profile", tzlab.LAB, f"--remote-debugging-port={tzlab.PORT}"],
                                 stdout=open(f"{out}/zen.log", "w"), stderr=tzlab.subprocess.STDOUT)
    try:
        results = asyncio.run(run(screens, out))
    finally:
        zen.terminate(); tzlab.subprocess.run(["pkill", "-f", "^/app/zen/zen .*--profile .*/tzlab"])
    sheets(results, out)
    fails = report(results, out)
    print(open(f"{out}/report.md").read().split("\n\n")[-1])
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main(*sys.argv[1:])
