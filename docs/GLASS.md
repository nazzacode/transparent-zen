# Liquid Glass site styles

Websites rendered as translucent "liquid glass" over the blurred desktop (Zen + Hyprland blur), one shared design
system for every site, verified by a headless test suite (`glasslab`).

## Layout

| path | role |
|---|---|
| `styles/shared/glass.css` | **single source of truth**: tiers, alphas, colours, fills, text, status, paper, reduced-transparency |
| `styles/shared/gm3.css` | Google Material 3 token map, shared by Google apps (Calendar, Gmail, …) |
| `styles/websites/<host>.css` | per site: maps the site's own tokens/regions onto glass tiers. Nothing else |
| `data/ContentScripts.json` | site registry: `matches` (unanchored RegExp, first hit wins), `css`, optional `"glass": "dark"` (forced mode) |
| `src/main/transparent-zen.ts` | sets `:root[data-tz-glass=dark\|light]` (auto = `prefers-color-scheme`) and `--tz-glass-alpha` (popup slider) |
| `tools/glasslab/` | test suite + discovery + scaffolding (`./glasslab …`), `screens.json`, `baseline.json`, JS `probes/` |

## Design rules (Apple Liquid Glass, adapted)

1. **Two layers.** Glass is the navigation layer (sidebars, top bars, menus). Content (lists, reading panes, grids) sits on a near-solid material.
2. **Fixed blur → floors.** Apple's glass adapts to what's behind it; a compositor blur can't, so every text-bearing tier has a readability floor.
3. **Tiers, not one-offs.** Site files map onto tiers; they never invent an alpha or a colour.
4. **No glass on glass.** Panes are compensated so stacked layers land on their tier's total opacity; controls use thin fills.
5. **Solid text.** Primary / secondary / tertiary colours; selection = accent tint; status = accessible system colours.
6. **User content on paper.** HTML email and similar keep their own colours on `--g-paper`.
7. **Dark-only apps stay dark** (`"glass": "dark"` in the registry).
8. **If you restyle a control's fill, you own its label colour**; never recolour filled buttons you didn't re-fill.

## Tiers (`s` = slider 0.10–0.90)

| token | tier | dark | light |
|---|---|---|---|
| `--g-window` | page backdrop | `s` | `s` |
| `--g-frame` | app shell, sidebars, top bars (default `body`) | `clamp(.50, s+.10, .92)` | `clamp(.75, s+.10, .92)` |
| `--g-content` | pane inside the frame (compensated) | total `clamp(.78, s+.25, .96)` | total `clamp(.88, s+.25, .96)` |
| `--g-content-abs` | content tier, absolute (content-first `--g-body`) | same total | same total |
| `--g-popover` | menus, dialogs, tooltips (+ `--g-blur`) | `clamp(.85, s+.35, .96)` | `clamp(.88, s+.35, .96)` |
| `--g-fill` / `-hover` / `-selected` | rows, controls | white .05 / .07, accent .24 | white frost .55 / .72, accent .10 |
| `--g-paper` | user content with own colours | `rgba(250,250,252,.97)` | same |
| `--g-fg` / `-2` / `-3` | text | `#f2f2f5 / #dfdfe3 / #a8a8b0` | `#1c1c1e / #333338 / #55555c` |

Also `--g-line(-strong)`, `--g-accent`, `--g-red/orange/green/blue/purple`, `--g-scrim`, `--g-shadow`, `--g-highlight`,
`--g-radius-pane/card`, `--g-pad-card`. `--g-body` picks the body tint (default frame; content-first sites:
`var(--g-content-abs)`; sites that suppress body backgrounds: `transparent` + tint their shell).

## Adding a site

```sh
nix-shell                                   # node + python deps (or let ./glasslab enter it for you)
./glasslab wallpapers ~/Pictures/wallpapers  # once: backdrops + contrast bounds from your own wallpapers
./glasslab new-site "Linear" https://linear.app/team/inbox
```

`new-site` opens the page headless with your Zen cookies (log in to the site in Zen first), then:

1. **Discovers causally** what paints the page: each candidate design token is set to a sentinel colour inline and only
   counts if the element actually changes (equal values aren't proof; Gmail *looks* GM3 but hard-codes).
2. **Scaffolds** `styles/websites/<host>.css`: driving tokens mapped to tiers (largest pane → content, narrow tall →
   frame, names → popover/fills/text roles), token scope from where the site redefines tokens, and `TODO` blocks for
   hard-coded leftovers. A token-less site gets the *neutralise → re-tier by role → text* template.
3. **Registers** the site (`^https?://(www\.)?host/`) and adds a test screen to `screens.json`.

Then iterate:

```sh
npm run build && ./glasslab test linear     # look at the run's sheet-*.jpg too, not only the numbers
./glasslab discover https://linear.app/…    # any time a screen shows the site's own colours
./glasslab test --save-baseline linear      # when it passes: numbers-only baseline (safe to commit)
./glasslab test --compare                   # before committing any shared change: no regressions anywhere
```

Add more screens per site (list, detail, dialog, settings) — each new screen catches new surfaces.
Keep `act` scripts **read-only** (never send, archive, mark read; open only already-read items).

Selector preference when no token exists: ARIA role → id → `data-testid` → long-stable classes (Gmail `zA/zE/a3s`) →
semantic framework classes (Encore `encore-text-*`). Never hashed classes.

## Test suite

`./glasslab test [FILTER]` — every screen × dark/light × slider 10 / 45 / 90 %:

- **Capture**: the page over pure black and pure white → exact per-pixel colour and alpha → composited offline onto the
  blurred wallpapers (`sheet-<screen>.jpg`, `shots/`). CSP-proof (no backdrop injected into the page).
- **Contrast**: every visible text run, APCA through its real paint stack (incl. covering pseudo-elements) over the
  darkest and brightest blurred-wallpaper patch (`wallpapers` bounds, p5/p95). Target: Lc 75 body · 60 labels and
  controls · 45 large text, relaxed to the site's **native** contrast ×0.9 where its own design is lower — glass may
  never read worse than the original site. Pass ≥ 90 % of characters.
- **Surface unity**: topmost painted surface on a 20×14 grid must be a `glass.css` tier colour. Pass ≥ 90 %.
- **Text unity**: neutral (low-chroma) text must be a shared foreground. Pass ≥ 85 %.
- **Exemptions** (reported, not scored): text on site data colours (calendar chips, labels), images/gradients, accent
  fills — **void if glass changed the text's colour**; a screen fails if > 10 % of its text is exempted for images.
- Native twins are matched by selector + text + position. Results: `~/.cache/glasslab/runs/<time>/{summary.md,results.json}`
  (local: contains page text). `./glasslab report` → local HTML report with galleries. Never publish runs/reports.

Exit code ≠ 0 on any failure at the default slider or any regression (`--compare`). Extremes are reported.

## Gotchas (each cost an evening)

- Google pages enforce Trusted Types + CSP: inject nothing as HTML; probes use CSSOM only.
- Google redefines GM3 tokens on inner elements → GM3 overrides need `:root, :root *`. GM3 uses *surface* and *inverse*
  tokens as label colours on chips → inline-coloured subtrees restore Google's light tokens (calendar.google.css).
- Some sites suppress `body` backgrounds (YouTube) → `--g-body: transparent`, tint the app shell instead.
- `:root *` custom-property blocks cost memory on huge DOMs: scope tokens where the site declares them (`discover`
  › redefinedAt; Reader: `:root, body, #document-text-content`).
- Spotify paints text from hashed classes (no tokens) → Encore semantic classes; forced dark.
- Cloudflare-protected sites (claude.ai) may serve a bot check to the headless lab; open the site in Zen to refresh
  its clearance cookie, then rerun.
