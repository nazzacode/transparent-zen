"""Headless Zen driver: throwaway profile inside the Flatpak sandbox, extension sideloaded unsigned, cookies copied from
the live profile (logged-in pages), driven over WebDriver BiDi. Never touches the user's session or focus."""
import asyncio, base64, configparser, contextlib, io, itertools, json, os, shutil, sqlite3, subprocess, time
from pathlib import Path

import websockets
from PIL import Image

APP = "app.zen_browser.zen"
SANDBOX = Path.home() / ".var/app" / APP
PORT = int(os.environ.get("GLASSLAB_PORT", 9333))  # one lab per port → parallel runs: GLASSLAB_PORT=9334 ./glasslab …
LAB = SANDBOX / f"glasslab-{PORT}"               # throwaway profile (sandbox can only read its own dir)
EXT_ID = "transparent-zen@nazzacode"
PROBES = Path(__file__).parent / "probes"
PREFS = {
    "xpinstall.signatures.required": False,
    "extensions.autoDisableScopes": 0,
    "extensions.enabledScopes": 15,
    "browser.tabs.allow_transparent_browser": True,
    "widget.transparent_windows": True,
    "zen.widget.linux.transparency": True,
    "browser.shell.checkDefaultBrowser": False,
    "zen.welcome-screen.seen": True,
    "browser.aboutwelcome.enabled": False,
    "remote.prefs.recommended": True,
    "ui.systemUsesDarkTheme": 1,
    "devtools.console.stdout.content": True,
}


def live_profile():
    """the profile Zen actually launches (profiles.ini [Install…] Default=), not a hard-coded name"""
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    ini.read(SANDBOX / ".zen/profiles.ini")
    for s in ini.sections():
        if s.startswith("Install") and "Default" in ini[s]:
            return SANDBOX / ".zen" / ini[s]["Default"]
    raise SystemExit("glasslab: no Zen profile found (run Zen once)")


def setup(xpi):
    shutil.rmtree(LAB, ignore_errors=True)
    (LAB / "extensions").mkdir(parents=True)
    shutil.copy(xpi, LAB / "extensions" / f"{EXT_ID}.xpi")
    (LAB / "user.js").write_text("".join(f'user_pref("{k}", {json.dumps(v)});\n' for k, v in PREFS.items()))
    live = live_profile()
    # live Zen holds an exclusive lock → copy raw db + WAL, then fold the WAL in on the copy
    for ext in ("", "-wal"):
        if (live / f"cookies.sqlite{ext}").exists():
            shutil.copy(live / f"cookies.sqlite{ext}", LAB / f"cookies.sqlite{ext}")
    if (LAB / "cookies.sqlite").exists():
        db = sqlite3.connect(LAB / "cookies.sqlite")
        db.execute("pragma wal_checkpoint(truncate)")
        db.close()


def kill():
    subprocess.run(["pkill", "-f", f"^/app/zen/zen .*--profile {LAB}"], check=False)


class Bidi:
    def __init__(self, ws):
        self.ws, self.ids = ws, itertools.count(1)

    async def call(self, method, **params):
        i = next(self.ids)
        await self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            m = json.loads(await self.ws.recv())
            if m.get("id") == i:
                if m.get("type") == "error":
                    raise RuntimeError(f"{method}: {m.get('message')}")
                return m["result"]

    async def eval(self, ctx, expr):
        r = await self.call("script.evaluate", expression=expr, target={"context": ctx}, awaitPromise=True)
        return r.get("result", {}).get("value")


class Page:
    """one browsing context + helpers used by every command"""

    def __init__(self, b, ctx):
        self.b, self.ctx = b, ctx

    async def eval(self, expr):
        return await self.b.eval(self.ctx, expr)

    async def probe(self, name, *args):
        """run probes/<name>.js (a function expression) with JSON args; probes return JSON strings"""
        src = (PROBES / f"{name}.js").read_text()
        return json.loads(await self.eval(f"({src})({', '.join(json.dumps(a) for a in args)})") or "null")

    async def goto(self, url, settle=7, act=None):
        try:
            await self.b.call("browsingContext.navigate", context=self.ctx, url=url, wait="complete")
        except RuntimeError as e:
            print(f"  nav: {e}")
        await asyncio.sleep(settle)
        if act:
            await self.eval(act)
            await asyncio.sleep(4)

    async def shot(self, backdrop=None):
        """screenshot; backdrop via CSSOM (Google pages enforce Trusted Types + CSP: no injected <style>)"""
        if backdrop:
            await self.eval(f"document.documentElement.style.setProperty('background','{backdrop}','important')")
            await asyncio.sleep(0.35)
        s = await self.b.call("browsingContext.captureScreenshot", context=self.ctx)
        return Image.open(io.BytesIO(base64.b64decode(s["data"])))

    async def clear_backdrop(self):
        await self.eval("document.documentElement.style.removeProperty('background')")

    async def glass(self, mode, alpha):
        await self.eval(f"document.documentElement.dataset.tzGlass='{mode}';"
                        f"document.documentElement.style.setProperty('--tz-glass-alpha','{alpha}')")
        await asyncio.sleep(0.4)

    async def detach_styles(self):
        """native render: remove the extension's stylesheets (headless → <link data-tz-file>), remember them"""
        await self.eval("window.__tz=[...document.querySelectorAll('link[data-tz-file]')];window.__tz.forEach(l=>l.remove());"
                        "document.documentElement.classList.remove('tz-initialized')")
        await asyncio.sleep(0.6)

    async def attach_styles(self):
        await self.eval("(window.__tz||[]).forEach(l=>document.head.append(l));document.documentElement.classList.add('tz-initialized')")
        await asyncio.sleep(0.8)


@contextlib.asynccontextmanager
async def session(xpi, log_path, viewport=(1400, 1000)):
    """start headless Zen with a fresh lab profile → Page; always cleaned up"""
    kill()
    time.sleep(1)
    setup(xpi)
    zen = subprocess.Popen(["flatpak", "run", "--command=/app/zen/zen", APP, "--headless", "--no-remote", "--profile", str(LAB),
                            f"--remote-debugging-port={PORT}"], stdout=open(log_path, "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                ws = await websockets.connect(f"ws://127.0.0.1:{PORT}/session", max_size=2**27)
                break
            except OSError:
                await asyncio.sleep(1)
        else:
            raise SystemExit("glasslab: Zen did not open the BiDi port")
        b = Bidi(ws)
        await b.call("session.new", capabilities={})
        ctx = (await b.call("browsingContext.getTree"))["contexts"][0]["context"]
        await b.call("browsingContext.setViewport", context=ctx, viewport={"width": viewport[0], "height": viewport[1]})
        yield Page(b, ctx)
        await ws.close()
    finally:
        zen.terminate()  # reaches only the flatpak wrapper; the sandboxed zen lives on → kill by profile
        kill()
