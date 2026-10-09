#!/usr/bin/env python3
"""glassreport: local HTML report for a glasslab run (results matrix, galleries, principles, mood board).

  glassreport.py RUNDIR        → RUNDIR/report.html (images: RUNDIR/gallery/*.jpg, built by glasslab runs)
Local file on purpose: screenshots show real inboxes/calendars → never published.
"""
import html, json, os, sys

PRINCIPLES = [
    ("Two layers", "Glass is the navigation layer (sidebars, top bars, menus). Content (lists, reading panes, grids) sits on a near-solid material. Apple: “Don’t use Liquid Glass in the content layer.”"),
    ("Fixed blur → floors", "Apple’s glass adapts its tint to what’s behind it; a compositor blur can’t. So every text-bearing tier has a readability floor, measured against the brightest/darkest blurred wallpaper."),
    ("Tiers, not one-offs", "window · frame (chrome) · content · popover, plus fixed fills for rows/controls. Sites only map their own tokens onto tiers; no site invents an alpha or a colour."),
    ("No glass on glass", "Panes are compensated so stacked layers land exactly on their tier’s total opacity; controls use thin overlay fills, not more glass."),
    ("Solid text", "Text colours are solid (primary / secondary / tertiary). Selection is an accent tint, not white. Status colours use Apple’s accessible variants, lightened for small text on glass."),
    ("User content on paper", "HTML email and other content with its own colours sits on a light paper sheet in both modes (as Apple Mail), instead of being recoloured."),
    ("Dark-only apps stay dark", "Apps without a light theme (Spotify) force dark glass via the site registry, rather than half-recoloured light mode."),
    ("Reduce transparency", "prefers-reduced-transparency → every tier solid, same colours."),
]
MOOD = [
    ("macOS Tahoe desktop", "https://www.apple.com/newsroom/images/2025/06/macos-tahoe-26-makes-the-mac-more-capable-productive-and-intelligent-than-ever/article/Apple-WWDC25-macOS-Tahoe-26-hero-250609_big.jpg.large.jpg", "Transparent menu bar, Dock, windows over wallpaper"),
    ("Music", "https://www.apple.com/newsroom/images/2025/06/macos-tahoe-26-makes-the-mac-more-capable-productive-and-intelligent-than-ever/article/Apple-WWDC25-macOS-Tahoe-26-Apple-Music-250609_big.jpg.large.jpg", "Floating glass sidebar over artwork"),
    ("Safari", "https://www.apple.com/newsroom/images/2025/06/macos-tahoe-26-makes-the-mac-more-capable-productive-and-intelligent-than-ever/article/Apple-WWDC25-macOS-Tahoe-26-Safari-250609_big.jpg.large.jpg", "Glass toolbar, opaque page"),
    ("Messages", "https://www.apple.com/newsroom/images/2025/06/macos-tahoe-26-makes-the-mac-more-capable-productive-and-intelligent-than-ever/article/Apple-WWDC25-macOS-Tahoe-26-Messages-250609_big.jpg.large.jpg", "Sidebar list beside conversation pane"),
    ("Notes / Shortcuts", "https://www.apple.com/newsroom/images/2025/06/macos-tahoe-26-makes-the-mac-more-capable-productive-and-intelligent-than-ever/article/Apple-WWDC25-macOS-Tahoe-26-Apple-Intelligence-Shortcuts-Notes-250609_big.jpg.large.jpg", "Text-heavy: solid reading area"),
    ("Control Center", "https://www.apple.com/newsroom/images/2025/06/macos-tahoe-26-makes-the-mac-more-capable-productive-and-intelligent-than-ever/article/Apple-WWDC25-macOS-Tahoe-26-Control-Center-250609_big.jpg.large.jpg", "Glass modules, monochrome glyphs"),
    ("Clear vs dark tint", "https://www.apple.com/newsroom/images/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/article/Apple-WWDC25-Liquid-Glass-Home-Screen-dark-tint-250609_big.jpg.large.jpg", "Tinted variant (26.1 legibility option)"),
    ("Finder (MacStories)", "https://cdn.macstories.net/cleanshot-2025-09-03-at-13-35-54-2x-1756920982278.png", "Translucent sidebar/toolbar, opaque controls"),
    ("Failure: Photos", "https://cdn.macstories.net/screenshot-2025-09-12-at-7-36-32-am-1757677001251.png", "Controls lost over imagery: what floors prevent"),
]
TIERS = [("window", "s", "s"), ("frame / chrome", "clamp(.50, s+.10, .92)", "clamp(.75, s+.10, .92)"),
         ("content", "clamp(.78, s+.25, .96)", "clamp(.88, s+.25, .96)"), ("popover", "clamp(.85, s+.35, .96) + blur", "clamp(.88, s+.35, .96) + blur"),
         ("rows / controls", "white .05 / .07, selected accent .24", "white frost .55 / .72, selected accent .10"),
         ("paper", "rgba(250,250,252,.97)", "same")]


def local(run, i, url):
    """mood images are downloaded to gallery/mood/m<i>.<ext> (offline, no hotlinking); fall back to the URL"""
    p = f"gallery/mood/m{i}.{url.rsplit('.', 1)[1]}"
    return p if os.path.exists(f"{run}/{p}") else url


def pct(v): return f"{v:.0%}"


def cell(v, target):
    cls = "ok" if v >= target else "bad"
    return f'<td class="{cls}">{pct(v)}</td>'


def main(run):
    R = json.load(open(f"{run}/report.json"))
    screens = list(dict.fromkeys(r["screen"] for r in R))
    rows = []
    for r in R:
        u = r.get("unity", {})
        rows.append(f"<tr><td>{r['screen']}</td><td>{r['mode']}</td><td>{int(r['alpha']*100)}%</td><td>{r['texts']}</td>"
                    + cell(r['pass'][0], .9) + cell(r['pass'][1], .9) + cell(u.get('surface', 0), .9) + cell(u.get('text', 0), .85) + "</tr>")
    gal = []
    for s in screens:
        imgs = [(k, f"gallery/{s}.{k}.jpg") for k in ("native", "dark.45", "light.45") if os.path.exists(f"{run}/gallery/{s}.{k}.jpg")]
        gal.append(f'<section class="shot"><h3>{s}</h3><div class="row">'
                   + "".join(f'<figure><img src="{p}"><figcaption>{html.escape(k.replace(".45", " · slider 45%"))}</figcaption></figure>' for k, p in imgs)
                   + "</div></section>")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Liquid Glass Web Apps</title>
<style>
:root{{--bg:#f5f5f7;--fg:#1c1c1e;--fg2:#55555c;--card:#fff;--line:rgba(0,0,0,.08);--ok:#248a3d;--bad:#b5000f;--acc:#007aff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111114;--fg:#f2f2f5;--fg2:#a8a8b0;--card:#1c1c20;--line:rgba(255,255,255,.1);--ok:#5fe07f;--bad:#ff9e98;--acc:#0a84ff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 Inter,system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:32px 16px 80px}}
h1{{font-size:30px;margin:0 0 4px}} h2{{margin:48px 0 12px;font-size:21px}} h3{{margin:0 0 8px;font-size:15px}}
p.lead{{color:var(--fg2);margin:0 0 24px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin:12px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left}}
td.ok{{color:var(--ok)}} td.bad{{color:var(--bad);font-weight:600}}
.row{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}} figure{{margin:0}} figure img{{width:100%;border-radius:8px;display:block}}
figcaption{{font-size:12px;color:var(--fg2);margin-top:4px}} .shot{{margin:22px 0}}
.mood img{{width:100%;height:150px;object-fit:cover;border-radius:10px}} code{{font-size:13px}}
.wide img{{width:100%;border-radius:10px}}
@media (max-width:720px){{.row{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Liquid Glass web apps</h1>
<p class="lead">Your most-used web apps on one shared glass system (transparent-zen fork + Zen web-app windows), tested for readability and sameness. Local report; screenshots show real accounts.</p>

<div class="card"><b>Use it:</b> Transparent Zen popup → <b>Glass</b>: Auto (follows desktop light/dark) · Dark · Light, and the <b>Glass opacity</b> slider (10–90%). Text-bearing surfaces have floors, so the slider never makes text unreadable. Web apps: launch from the menu (<code>webapp-*</code>) as Zen web-app windows.</div>

<h2>What's covered (ranked by your history)</h2>
<div class="card"><table><tr><th>#</th><th>Site</th><th>Visits (all / 30 d)</th><th>Status</th></tr>
<tr><td>1</td><td>Readwise Reader</td><td>2352 / 142</td><td>new style, tested (library + document)</td></tr>
<tr><td>2</td><td>Google Calendar</td><td>749 / 131</td><td>shared GM3 map, tested (week, month, event)</td></tr>
<tr><td>3</td><td>Gmail</td><td>193 / 49</td><td>rewritten, tested (inbox + thread)</td></tr>
<tr><td>4</td><td>Linear</td><td>837 / 84</td><td>not done: not logged in on Zen</td></tr>
<tr><td>5</td><td>Claude</td><td>760 / 50</td><td>new style, tested (new chat + recents)</td></tr>
<tr><td>6</td><td>X</td><td>5148 / 221</td><td>not done: not logged in on Zen</td></tr>
<tr><td>7</td><td>Google Search</td><td>4601 / 718</td><td>rewritten + www/co.uk matching fixed, tested</td></tr>
<tr><td>8</td><td>Substack</td><td>896 / 150</td><td>ported to shared tokens, tested</td></tr>
<tr><td>9</td><td>YouTube · Spotify (web)</td><td>640 / 14 · –</td><td>rewritten / ported, tested (Spotify forced dark)</td></tr>
</table></div>

<h2>Design principles (Apple Liquid Glass, adapted)</h2>
<div class="grid">{''.join(f'<div class="card"><h3>{html.escape(t)}</h3>{html.escape(d)}</div>' for t, d in PRINCIPLES)}</div>

<h2>Tiers (styles/shared/glass.css)</h2>
<div class="card"><table><tr><th>tier</th><th>dark (s = slider)</th><th>light</th></tr>
{''.join(f'<tr><td>{a}</td><td><code>{b}</code></td><td><code>{c}</code></td></tr>' for a, b, c in TIERS)}</table>
<p>Text: dark <code>#f2f2f5 / #dfdfe3 / #a8a8b0</code>, light <code>#1c1c1e / #333338 / #55555c</code>. Every site file maps only onto these.</p></div>

<h2>Mood board</h2>
<div class="grid mood">{''.join(f'<div class="card"><a href="{u}"><img src="{local(run, i, u)}" alt=""></a><h3>{html.escape(t)}</h3>{html.escape(d)}</div>' for i, (t, u, d) in enumerate(MOOD))}</div>

<h2>Test suite (scripts/glasslab.py)</h2>
<div class="card">Each screen renders headless with your cookies, captured over pure black and white → exact per-pixel colour and alpha, composited offline onto your blurred live wallpapers.
<ul><li><b>Contrast</b>: APCA per text run, composited through its real paint stack over the darkest and brightest blurred-wallpaper patch (p5/p95 over all 22 wallpapers). Target: Lc 75 body, 60 labels, 45 large; never worse than the site's own native rendering. Pass ≥ 90% of characters.</li>
<li><b>Surface unity</b>: topmost painted surface at a 20×14 grid must be a shared tier colour. Pass ≥ 90%.</li>
<li><b>Text unity</b>: neutral text must be a shared foreground. Pass ≥ 85%.</li>
<li>Exempt (reported, not scored): text on site data colours (calendar chips, labels), images, gradients, accent buttons.</li>
<li><b>Causal token discovery</b>: tokens are set to a sentinel colour to prove they actually drive a surface, before mapping them.</li></ul>
Rerun: <code>nix-shell -p "python3.withPackages(p:[p.websockets p.pillow p.numpy])" --run "python3 scripts/glasslab.py builds/*.zip OUT [filter]"</code></div>
<div class="card"><table><tr><th>screen</th><th>mode</th><th>slider</th><th>texts</th><th>contrast · dark bg</th><th>contrast · bright bg</th><th>surface unity</th><th>text unity</th></tr>{''.join(rows)}</table></div>

<h2>Screens</h2>
<p class="lead">native → dark glass → light glass, slider 45%, on earth-iss (your current wallpaper).</p>
{''.join(gal)}
<h2>Slider</h2><div class="wide"><img src="gallery/strip-slider-gmail.jpg"><p class="lead">Gmail thread at 20 / 45 / 70%: frame glass moves; content floors hold.</p></div>
<h2>Across wallpapers</h2><div class="wide"><img src="gallery/sheet-reader-doc.jpg"><p class="lead">Reader document: rows = dark/light × slider, then each mode across 5 wallpapers.</p></div>
</main></body></html>"""
    open(f"{run}/report.html", "w").write(page)
    print(f"{run}/report.html")


if __name__ == "__main__":
    main(sys.argv[1])
