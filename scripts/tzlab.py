#!/usr/bin/env python3
"""tzlab: headless Zen test rig for transparency — never touches the live session/focus.

  tzlab.py XPI OUTDIR URL [URL...]

Throwaway profile (flatpak sandbox home), unsigned XPI sideloaded, cookies copied from the
live profile (logged-in pages), driven via WebDriver BiDi. Per URL:
  <slug>.png   screenshot with magenta root → pink = see-through, solid = opaque
  <slug>.json  opaque coverage (grid sample) + top offending elements (selector, bg, area)
Run inside: nix-shell -p "python3.withPackages(p:[p.websockets])"
"""
import asyncio, base64, itertools, json, os, re, shutil, sqlite3, subprocess, sys, time
import websockets

HOME = os.path.expanduser("~")
SANDBOX = f"{HOME}/.var/app/app.zen_browser.zen"
LIVE = f"{SANDBOX}/.zen/bufv3znx.Default (release)"
LAB = f"{SANDBOX}/tzlab"
PORT = 9333
EXT_ID = "transparent-zen@nazzacode"

PREFS = {
    "xpinstall.signatures.required": False,
    "extensions.autoDisableScopes": 0,
    "extensions.enabledScopes": 15,
    "browser.tabs.allow_transparent_browser": True,
    "widget.transparent_windows": True,
    "zen.widget.linux.transparency": True,
    "toolkit.legacyUserProfileCustomizations.stylesheets": True,
    "browser.shell.checkDefaultBrowser": False,
    "zen.welcome-screen.seen": True,
    "browser.aboutwelcome.enabled": False,
    "remote.prefs.recommended": True,
    "ui.systemUsesDarkTheme": 1,
    "devtools.console.stdout.chrome": True,  # extension/background errors → zen.log
    "devtools.console.stdout.content": True,  # match DMS dark; extension palette is dark-only
}

# grid-sample which elements paint opaque backgrounds over the page (JS, runs in page)
PROBE = r"""
(() => {
  const W = innerWidth, H = innerHeight, N = 24, M = 16, hits = new Map();
  let opaque = 0, total = 0;
  const alpha = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return c === 'transparent' ? 0 : 1;
    const p = m[1].split(/[ ,\/]+/).filter(Boolean); return p.length > 3 ? parseFloat(p[3]) : 1; };
  const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') +
    [...e.classList].slice(0, 3).map(c => '.' + c).join('');
  for (let i = 0; i < N; i++) for (let j = 0; j < M; j++) {
    const x = (i + .5) * W / N, y = (j + .5) * H / M; total++;
    for (const e of document.elementsFromPoint(x, y)) {
      if (e === document.documentElement) break;
      if (/^(IMG|VIDEO|CANVAS|SVG|PICTURE|IFRAME)$/.test(e.tagName)) break;
      const cs = getComputedStyle(e), a = alpha(cs.backgroundColor);
      if (a >= 0.85 || cs.backgroundImage.includes('gradient')) {
        opaque++; const k = sel(e), r = e.getBoundingClientRect();
        const h = hits.get(k) || { sel: k, bg: cs.backgroundColor, n: 0, w: Math.round(r.width), h: Math.round(r.height) };
        h.n++; hits.set(k, h); break;
      }
    }
  }
  return JSON.stringify({ url: location.href, opaquePct: Math.round(100 * opaque / total),
    offenders: [...hits.values()].sort((a, b) => b.n - a.n).slice(0, 12) });
})()
"""
MAGENTA = "document.head.insertAdjacentHTML('beforeend','<style id=tzlab>html:root:root{background:#f0f!important}</style>')"


def setup(xpi):
    shutil.rmtree(LAB, ignore_errors=True)
    os.makedirs(f"{LAB}/extensions")
    shutil.copy(xpi, f"{LAB}/extensions/{EXT_ID}.xpi")
    with open(f"{LAB}/user.js", "w") as f:
        f.writelines(f'user_pref("{k}", {json.dumps(v)});\n' for k, v in PREFS.items())
    # live Zen holds an exclusive lock → copy raw db + WAL, then fold WAL in on the copy
    for ext in ("", "-wal"):
        if os.path.exists(f"{LIVE}/cookies.sqlite{ext}"):
            shutil.copy(f"{LIVE}/cookies.sqlite{ext}", f"{LAB}/cookies.sqlite{ext}")
    db = sqlite3.connect(f"{LAB}/cookies.sqlite")
    print("cookies:", db.execute("select count(*) from moz_cookies").fetchone()[0], flush=True)
    db.execute("pragma wal_checkpoint(truncate)"); db.close()


class Bidi:
    def __init__(self, ws): self.ws, self.ids = ws, itertools.count(1)

    async def call(self, method, **params):
        i = next(self.ids)
        await self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            m = json.loads(await self.ws.recv())
            if m.get("id") == i:
                if m.get("type") == "error": raise RuntimeError(f"{method}: {m.get('message')}")
                return m["result"]

    async def eval(self, ctx, expr):
        r = await self.call("script.evaluate", expression=expr, target={"context": ctx}, awaitPromise=True)
        return r.get("result", {}).get("value")


async def run(urls, out, settle):
    for _ in range(60):
        try:
            ws = await websockets.connect(f"ws://127.0.0.1:{PORT}/session", max_size=2**26); break
        except OSError: await asyncio.sleep(1)
    b = Bidi(ws)
    await b.call("session.new", capabilities={})
    ctx = (await b.call("browsingContext.getTree"))["contexts"][0]["context"]
    await b.call("browsingContext.setViewport", context=ctx, viewport={"width": 1400, "height": 1000})
    for url in urls:
        slug = re.sub(r"[^a-z0-9]+", "-", url.split("://", 1)[-1].lower()).strip("-")[:60]
        try:
            await b.call("browsingContext.navigate", context=ctx, url=url, wait="complete")
        except RuntimeError as e:
            print(f"{slug}: nav {e}")
        await asyncio.sleep(settle)
        await b.eval(ctx, MAGENTA)
        await asyncio.sleep(0.5)
        probe = json.loads(await b.eval(ctx, PROBE) or "{}")
        shot = await b.call("browsingContext.captureScreenshot", context=ctx)
        open(f"{out}/{slug}.png", "wb").write(base64.b64decode(shot["data"]))
        json.dump(probe, open(f"{out}/{slug}.json", "w"), indent=1)
        if os.environ.get("TZ_JS"):
            print(f"{slug} js:", await b.eval(ctx, os.environ["TZ_JS"]))
        print(f"{slug}: opaque {probe.get('opaquePct')}%  →  " +
              ", ".join(f"{o['sel']}({o['n']})" for o in probe.get("offenders", [])[:5]))
    await ws.close()


def main(xpi, out, *urls, settle=float(os.environ.get("TZ_SETTLE", 6))):
    os.makedirs(out, exist_ok=True)
    subprocess.run(["pkill", "-f", "^/app/zen/zen .*--profile .*/tzlab"])  # stale lab from a killed run
    time.sleep(1)
    setup(xpi)
    zen = subprocess.Popen(["flatpak", "run", "--command=/app/zen/zen", "app.zen_browser.zen",
                            "--headless", "--no-remote", "--profile", LAB, f"--remote-debugging-port={PORT}"],
                           stdout=(log := open(f"{out}/zen.log", "w")), stderr=subprocess.STDOUT)
    try:
        asyncio.run(run(urls, out, settle))
    finally:
        # terminate() only reaches the flatpak wrapper; the sandboxed zen lives on → kill by profile
        zen.terminate()
        subprocess.run(["pkill", "-f", "^/app/zen/zen .*--profile .*/tzlab"])


if __name__ == "__main__":
    main(*sys.argv[1:])
