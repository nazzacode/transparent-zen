"""glasslab — liquid-glass site styles toolkit (docs/GLASS.md).

  ./glasslab test [FILTER] [--save-baseline] [--compare] [--build]   readability + unity matrix over screens.json
  ./glasslab discover URL [--act JS]                                  what actually paints a site (causal tokens)
  ./glasslab new-site NAME URL [--content-first] [--dark-only]        scaffold style + registry + test screen
  ./glasslab wallpapers DIR|FILE…                                     backdrops + contrast bounds from your wallpapers
  ./glasslab report [RUN]                                             local HTML report (default: latest run)
"""
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = Path.home() / ".cache/glasslab/runs"


def xpi(build):
    if build:
        subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)
    zips = sorted((ROOT / "builds").glob("*.zip"), key=lambda p: p.stat().st_mtime)
    if not zips:
        raise SystemExit("glasslab: no build in builds/ (npm run build, or pass --build)")
    return zips[-1]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="glasslab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test"); t.add_argument("filter", nargs="?", default="")
    t.add_argument("--save-baseline", action="store_true"); t.add_argument("--compare", action="store_true")
    t.add_argument("--build", action="store_true"); t.add_argument("--out")
    d = sub.add_parser("discover"); d.add_argument("url"); d.add_argument("--act"); d.add_argument("--build", action="store_true")
    n = sub.add_parser("new-site"); n.add_argument("name"); n.add_argument("url"); n.add_argument("--act")
    n.add_argument("--content-first", action="store_true"); n.add_argument("--dark-only", action="store_true")
    n.add_argument("--force", action="store_true"); n.add_argument("--build", action="store_true")
    w = sub.add_parser("wallpapers"); w.add_argument("paths", nargs="+"); w.add_argument("--blur", type=int, default=22)
    r = sub.add_parser("report"); r.add_argument("run", nargs="?")
    a = ap.parse_args(argv)

    if a.cmd == "test":
        from . import suite
        return suite.main(xpi(a.build), a.filter, a.out, a.save_baseline, a.compare)
    if a.cmd == "discover":
        from . import discover
        discover.discover(xpi(a.build), a.url, a.act)
    if a.cmd == "new-site":
        from . import discover
        discover.new_site(xpi(a.build), a.name, a.url, a.act, a.content_first, a.dark_only, a.force)
    if a.cmd == "wallpapers":
        from . import wallpapers
        wallpapers.main(a.paths, a.blur)
    if a.cmd == "report":
        from . import report
        run = Path(a.run) if a.run else max(RUNS.iterdir(), key=lambda p: p.stat().st_mtime)
        report.main(run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
