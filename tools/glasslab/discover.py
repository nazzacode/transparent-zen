"""glasslab discover / new-site: find what actually paints a site (causal token test on the native render) and scaffold
its style file, registry entry and test screen from that. See docs/GLASS.md › Adding a site."""
import asyncio, json, re
from pathlib import Path
from urllib.parse import urlsplit

from . import lab

ROOT = Path(__file__).resolve().parents[2]          # repo root
HERE = Path(__file__).parent
OUT = Path.home() / ".cache/glasslab/discover"


async def _discover(xpi, url, act=None, settle=8):
    async with lab.session(xpi, OUT / "zen.log") as pg:
        await pg.goto(url, settle, act)
        await pg.detach_styles()            # judge the site's own paint, not ours
        return await pg.probe("discover")


def discover(xpi, url, act=None):
    OUT.mkdir(parents=True, exist_ok=True)
    d = asyncio.run(_discover(xpi, url, act))
    host = urlsplit(url).hostname.removeprefix("www.")
    (OUT / f"{host}.json").write_text(json.dumps(d, indent=1))
    print(f"surfaces (top painted backgrounds, share of viewport):")
    for s in d["surfaces"]:
        print(f"  {s['share']:4.0%} {s['color']:22s} {'HARD-CODED' if s['hardcoded'] else 'tokens: ' + ', '.join(s['tokens'][:4])}  ← {s['el']} {s['rect']}")
    print("text (by characters):")
    for t in d["text"]:
        print(f"  {t['chars']:5d} {t['color']:22s} {'HARD-CODED' if t['hardcoded'] else 'tokens: ' + ', '.join(t['tokens'][:4])}  ← {', '.join(t['els'][:3])}")
    if d["redefinedAt"]:
        print("tokens redefined on inner elements (site file must cover these, or use `:root *`):\n  " + "\n  ".join(d["redefinedAt"]))
    print(f"\nfull report: {OUT / (host + '.json')}")
    return d


# ---------- scaffold ----------

PRIMITIVE = r"(gray|grey|neutral|slate|zinc|blue|red|green|yellow|orange|purple|violet|white|black|primitive|palette)[-_]?\d*$|[-_]\d{2,3}$"
SURFACE_NAME = [  # semantic surface names → tier (first match wins); geometry decides only when the name doesn't
    (r"(page|canvas|app-bg|body|backdrop|base$)", "transparent", "page background → body tint (glass.css)"),
    (r"(sidebar|nav|rail|drawer|header|toolbar|topbar)", "transparent", "chrome → frame"),
    (r"(elevat|popover|menu|dropdown|overlay|modal|dialog|tooltip)", "var(--g-popover)", "floating → popover"),
    (r"(primary|content|main|surface$|default$)", "var(--g-content)", "main surface → content"),
    (r"(secondary|tertiary|card|input|field|chip|tag|subtle|muted|well|code)", "var(--g-fill)", "inset/raised → fill"),
]
ROLE = [  # token-name → glass token (first match wins); used for inventory tokens not seen painting right now
    (r"(elevat|popover|menu|dropdown|overlay|modal|dialog|tooltip)", "var(--g-popover)"),
    (r"(hover)", "var(--g-fill-hover)"),
    (r"(selected|active|press|current)", "var(--g-fill-selected)"),
    (r"(card|secondary|tertiary|input|field|chip|tag|control|subtle)", "var(--g-fill)"),
]
TEXT_ROLE = [(r"(tertiary|placeholder|disabled|faint|quaternary)", "var(--g-fg-3)"),
             (r"(secondary|muted|subdued|subtle|dim)", "var(--g-fg-2)"),
             (r"(primary|base|default|strong|text$|-fg$)", "var(--g-fg)")]
STATUS = [(r"(error|danger|negative|destructive)", "var(--g-red)"), (r"(warning|caution)", "var(--g-orange)"),
          (r"(success|positive)", "var(--g-green)"), (r"visited", "var(--g-purple)"), (r"(link|interactive|accent)", "var(--g-blue)")]


def _match(name, table):
    return next((v for pat, v in table if re.search(pat, name, re.I)), None)


def plan(d):
    """→ (token map {token: value, comment}, structural TODOs, scopes)"""
    m, todo = {}, []
    W = 1400

    def semantic(tokens):
        """drop primitive palette tokens (--color-gray-10, --white) when a semantic token also drives: primitives are
        shared by unrelated surfaces/text, mapping them recolours the whole site"""
        sem = [t for t in tokens if not re.search(PRIMITIVE, t, re.I)]
        return sem or tokens

    for i, s in enumerate(d["surfaces"]):
        x, y, w, h = s["rect"]
        toks = semantic(s["tokens"])
        named = next(((t2, why) for t in toks for pat, t2, why in SURFACE_NAME if re.search(pat, t, re.I)), None)
        if s.get("page"):
            tier, why = "transparent", "paints <html>/<body> → body tint (glass.css)"
        elif named:
            tier, why = named
        elif w < W * 0.3 and h > 400:
            tier, why = "transparent", "narrow, tall → sidebar → frame"
        elif i == 0 or w * h > W * 300:
            tier, why = "var(--g-content)", "large pane → content"
        else:
            tier, why = "var(--g-fill)", "small surface → fill"
        if s["hardcoded"] and not s.get("page"):          # html/body are already handled by glass.css
            todo.append((s["el"], tier, f"hard-coded {s['color']}, {why}"))
        for t in toks:
            m.setdefault(t, (tier, why))
    neutral = [t for t in d["text"] if (lambda c: max(c) - min(c) <= 24)([float(v) for v in re.findall(r"[\d.]+", t["color"])[:3]])]
    for rank, t in enumerate(neutral):
        for tok in semantic(t["tokens"]):
            m.setdefault(tok, (_match(tok, TEXT_ROLE) or ["var(--g-fg)", "var(--g-fg-2)", "var(--g-fg-3)"][min(rank, 2)], f"text, rank {rank + 1} by chars"))
        if t["hardcoded"]:
            todo.append((t["els"][0], ["var(--g-fg)", "var(--g-fg-2)", "var(--g-fg-3)"][min(rank, 2)], f"hard-coded text {t['color']} (rank {rank + 1})"))
    inv = d.get("inventory", {})
    for name, _ in inv.get("bg", []):
        if name not in m and not re.search(PRIMITIVE, name, re.I) and (v := _match(name, ROLE)):
            m[name] = (v, "inventory (name)")
    for name, _ in inv.get("text", []):
        if name not in m and (v := _match(name, TEXT_ROLE)):
            m[name] = (v, "inventory (name)")
    for name, _ in inv.get("line", []):
        m.setdefault(name, ("var(--g-line)", "inventory (name)"))
    for name, _ in inv.get("status", []) + inv.get("accent", []):
        if name not in m and (v := _match(name, STATUS)) and re.search(r"(text|fg|color$|link)", name, re.I):
            m[name] = (v, "inventory (name)")
    scopes = [":root", "body"] + [s for s in d.get("redefinedAt", []) if not re.search(r"\.[A-Za-z0-9_-]{6,}\b", s) or "#" in s]
    return m, todo, scopes


def render_css(name, url, d, content_first, dark_only):
    m, todo, scopes = plan(d)
    tokenless = not any(not s["hardcoded"] for s in d["surfaces"])
    head = f"""@import url("../shared/glass.css");

/* {name}. Scaffolded by `glasslab new-site` from causal discovery of {url}
   ({len(m)} tokens mapped; review every line, then `./glasslab test {slug(name)}`).
   Rules: map the site's tokens/regions onto glass tiers only — never invent alphas or colours (docs/GLASS.md). */
"""
    body = []
    if content_first:
        body.append(":root {\n\t--g-body: var(--g-content-abs); /* content-first (feeds, search, long reading) */\n}\n")
    if m and not tokenless:
        lines = [f"\t{t}: {v} !important; /* {why} */" for t, (v, why) in m.items()]
        sel = ",\n".join(scopes) if len(scopes) > 2 else ":root,\nbody"
        body.append(f"/* token scope: where the site declares its tokens (discover › redefinedAt); use `:root, :root *` if a\n"
                    f"   screen still shows the site's own colours */\n{sel} {{\n" + "\n".join(lines) + "\n}\n")
    else:
        body.append("""/* token-less site (no token drives its surfaces): neutralise containers → re-tier by ARIA role → text */
body :where(div, section, header, nav, aside, main, footer, ul, li, table, tbody, tr, td, form):where(:not([role="button"], [role="progressbar"], [role="switch"], [style*="background"])) {
	background-color: transparent !important;
}
[role="main"] {
	background-color: var(--g-content) !important; /* TODO: confirm the main pane */
	border-radius: var(--g-radius-pane);
}
:is([role="dialog"], [role="menu"], [role="listbox"], [role="tooltip"]) {
	background-color: var(--g-popover) !important;
	backdrop-filter: var(--g-blur);
}
body,
body :where(:not([style*="color"], button, button *, [role="button"], [role="button"] *)) {
	color: var(--g-fg) !important;
}
""")
    if todo:
        body.append("/* hard-coded leftovers (discover found no driving token) — confirm selectors, prefer role/id/data-testid */\n"
                    + "\n".join(f"/* TODO {why}\n{el} {{\n\t{'color' if 'text' in why else 'background-color'}: {v} !important;\n}} */" for el, v, why in todo) + "\n")
    return head + "\n" + "\n".join(body)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def add_registry(name, host, css, dark_only):
    p = ROOT / "data/ContentScripts.json"
    s = p.read_bytes().decode()
    if f"./styles/websites/{css}" in s:
        return False
    nl = "\r\n" if "\r\n" in s else "\n"
    rx = "^https?://(www\\\\.)?" + host.replace(".", "\\\\.") + "/"
    entry = (f"\t\t}},{nl}\t\t{{{nl}\t\t\t\"name\": \"{name}\",{nl}\t\t\t\"matches\": [\"{rx}\"],{nl}"
             f"\t\t\t\"css\": [\"./styles/websites/{css}\"],{nl}" + (f"\t\t\t\"glass\": \"dark\",{nl}" if dark_only else "")
             + f"\t\t\t\"run_at\": \"document_start\",{nl}\t\t\t\"favicon\": \"https://icons.duckduckgo.com/ip3/{host}.ico\"{nl}")
    i = s.rstrip().rfind(f"\t\t}}{nl}\t]")
    p.write_bytes((s[:i] + entry + s[i:]).encode())
    json.loads(p.read_text())  # still valid
    return True


def add_screen(name, url, act, dark_only):
    p = HERE / "screens.json"
    d = json.loads(p.read_text())
    sid = f"{slug(name)}-home"
    if any(s["id"] == sid for s in d["screens"]):
        return sid
    s = {"id": sid, "url": url}
    if act:
        s["act"] = act
    if dark_only:
        s["modes"] = ["dark"]
    d["screens"].append(s)
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    return sid


def new_site(xpi, name, url, act=None, content_first=False, dark_only=False, force=False):
    host = urlsplit(url).hostname.removeprefix("www.")
    css = f"{host}.css"
    path = ROOT / "styles/websites" / css
    if path.exists() and not force:
        raise SystemExit(f"glasslab: {path} exists (use --force to overwrite)")
    d = discover(xpi, url, act)
    text = render_css(name, url, d, content_first, dark_only)
    path.write_bytes(text.replace("\n", "\r\n").encode())       # repo convention: CRLF styles
    reg = add_registry(name, host, css, dark_only)
    sid = add_screen(name, url, act, dark_only)
    print(f"\nwrote styles/websites/{css}" + ("\nregistered in data/ContentScripts.json" if reg else "")
          + f"\nscreen '{sid}' in tools/glasslab/screens.json (add more: lists, detail views, dialogs)"
          + f"\nnext: review the CSS → npm run build → ./glasslab test {slug(name)} → iterate until it passes → "
            f"./glasslab test --save-baseline {slug(name)}")
