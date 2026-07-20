# Discovery Design Guidance

> **Scope:** ab-discovery (audiobook tracker) + am-discovery (music release tracker)
> **Audience:** Coding agents (Claude Code, Cursor, etc.) and the humans reading their PRs
> **Visual reference:** [`design-guidance/index.html`](./design-guidance/index.html) — rendered components, side-by-side
> **Source of truth:** this file. When the doc and code disagree, fix the doc first, then the code.

---

## 0 · How to read this

- Rules tagged **[BOTH]** apply to both apps and must stay aligned. Changing one means changing the other.
- Tags **[AB]** and **[AM]** mark deliberate divergences, not inconsistencies to "fix."
- Tokens are **named in parallel**: `--bg`, `--surface`, `--accent`. Names match across apps, values diverge. Always reference by name.

**Reading order for new work:**
1. Identify which app you're in (header check).
2. Pick the closest existing page archetype (§20) and component (§12–19).
3. Resolve every color, radius, and font size to a named token (§04).
4. Apply the border-as-highlight rule (§09) for any "selected / watching / important" state.
5. Check the Don't column (§22) and the iteration playbook (§23) before introducing anything new.

---

## 1 · The two apps

| | **ab-discovery** | **am-discovery** |
|---|---|---|
| **One sentence** | Track audiobooks across many sources, find what's missing, surface what's on Audible Plus. | Follow artists across Apple Music storefronts; get the album the moment it drops, anywhere. |
| **Mood** | Librarian's tool. Information-dense. | Fan's tool. Visually-led. |
| **Surface** | Solid panels, visible 1px border | Translucent glass, backdrop-blur |
| **Navigation** | Top tabs, single row, 3 items | Left sidebar w/ icons + status footer |
| **Imagery** | 72–80px thumbnail | Full-bleed 1:1 hero artwork |
| **Density** | Card rows · 280px min | Tile grid · 200px min |
| **Accent** | `#58a6ff` utility blue | `#ff3c82 → #a855f7` pink-purple |

**Rule:** Don't let AB drift toward AM, or vice versa. If a feature lands in both apps, render it twice — once in AB's solid-panel grammar, once in AM's glass grammar. The shared layer is **logic and tokens**, not visuals.

---

## 2 · Shared DNA (eight rules)

These are non-negotiable across both apps.

1. **Dark, layered.** Single near-black base. One surface layer above it. One subtle border. No more than two background tones in a normal view.
2. **Color carries semantics.** Red = missing. Green = in library. Amber/gold = needs attention or watch-flag. Blue = info/link. Never decorate without semantic intent.
3. **Border = highlight.** "Selected / watching / actionable" states change the *border color*, not the fill. See §9.
4. **Source/origin is identity.** Every item declares where it came from. AB uses link chips per source; AM uses colored storefront chips. Always visible, never hidden in tooltips.
5. **Filter bars are labeled.** 11px uppercase letter-spaced labels above every control. No placeholder-only fields. Reset/clear right-aligned.
6. **Summary stats up top.** Every list page leads with a row of numeric cards: big number + small uppercase label. Optionally clickable as quick-filters.
7. **Empty & loading are first-class.** Dashed-border empty box with one-line copy. Shimmer skeletons match the target component's silhouette. Never a spinner alone.
8. **Watching is gold.** The "I'm tracking this" signal is gold/amber. AB `#d29922`, AM `#f5c842`. Don't repurpose gold for anything else.

---

## 3 · Distinct lanes

| Aspect | [AB] ab-discovery | [AM] am-discovery |
|---|---|---|
| Identity | Utility / library / data-auditing | Discovery / fan / artwork-first |
| Accent | Single utility blue · `#58a6ff` | Pink → purple gradient · `#ff3c82` → `#a855f7` |
| Navigation | Top tabs · 3 items · single row | Sidebar · icon + label · status footer with refresh |
| Surface | Solid `#161b22` · visible 1px border | `rgba(255,255,255,0.04)` over deep bg · backdrop-blur |
| Imagery | 72–100px thumbnail, contained | Full-bleed square hero · artwork is the card |
| Card density | Thumb + 4–6 lines metadata + chips | Art + 2 lines + storefront chips |
| Radius scale | Flat: 4 / 6 / 8 px uniform | Tiered: 8 / 14 / 20 px |
| Type voice | System sans · 13px body · 22px page title | Inter · 13–14px body · 28px page title · gradient brand |
| Watch marker | Green switch (header) · "Watching" gold chip | Gold star on tile · gold tile border · gold pill button |
| Motion | None / minimal · static | Hover lift -3px · pulse on refresh · shimmer on load |

---

## 4 · Tokens · parallel

Both apps' stylesheets expose the same vocabulary under different CSS custom-property names. When in doubt, this table is canonical.

| Role | [AB] | [AM] | Use |
|---|---|---|---|
| `bg-base` | `--bg` · `#0e1116` | `--bg-deep` · `#0a0a0f` | Outermost canvas |
| `surface` | `--surface` · `#161b22` | `--bg-card` · `rgba(255,255,255,.04)` | Cards, panels, nav strip |
| `surface-raised` | `--surface-2` · `#1f242c` | `--bg-card-hover` · `rgba(255,255,255,.08)` | Inputs, hover, nested cards |
| `border` | `--border` · `#2a3038` | `--border` · `rgba(255,255,255,.08)` | Every component border, always 1px |
| `text` | `--text` · `#e6edf3` | `--text-primary` · `#f0f0f8` | Body, titles |
| `text-2` | `--text-dim` · `#9ba7b4` | `--text-secondary` · `#9999bb` | Bylines, meta, descriptions |
| `text-dim` | (reuses `text-dim`) | `--text-dim` · `#55556a` | Timestamps, placeholders, labels |
| `accent` | `--accent` · `#58a6ff` | `--accent` · `#ff3c82` | Links, focus rings, brand mark |
| `accent-2` | `--accent-dim` · `#1f6feb` | `--accent-2` · `#a855f7` | Primary button fill (AB) / gradient stop (AM) |
| `flag` | `--warn` · `#d29922` | `--gold` · `#f5c842` | Watching, plus-actionable border |
| `good` | `--good` · `#3fb950` | (inline) `#34d399` | Owned/in-library, success dot |
| `bad` | `--bad` · `#f85149` | (avoid; AM rarely shows "missing") | AB missing chip / AM error banner |
| `radius-sm` | 4–6 px | `--radius-sm` · 8 px | Chips, inputs, source pills |
| `radius-md` | 8 px | `--radius-md` · 14 px | Cards, sections |
| `radius-lg` | — (none) | `--radius-lg` · 20 px | Hero panels, modals (AM only) |
| `radius-pill` | 999 px | 20 / 999 px | Buttons with text, chips |
| `font-family` | System stack | `'Inter', system-ui` | Both lean neutral grotesque |

**Rule:** When adding a new component, if its role exists in the parity table, use the existing token. When adding a new token, add to *both* apps (even if you only need it in one) so parity holds.

---

## 5 · Color

### [AB] palette
`#0e1116` `#161b22` `#1f242c` `#2a3038` `#e6edf3` `#9ba7b4` `#58a6ff` `#1f6feb` `#3fb950` `#d29922` `#f85149`

### [AM] palette
`#0a0a0f` `#12121a` `rgba(255,255,255,.04)` `rgba(255,255,255,.08)` `#f0f0f8` `#9999bb` `#55556a` `#ff3c82` `#a855f7` `#f5c842`
Gradient: `linear-gradient(135deg, #ff3c82, #a855f7)`

**DO** tint via low-opacity overlays: status chips and sf-chips use `rgba(accent, 0.2)` as background and the solid accent as text. Universal across both apps.

**DON'T** introduce a new accent hue. Need a new categorical color → storefront palette (§10). Need to highlight → use the accent already in the app.

---

## 6 · Typography

[AB] **System stack** · `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ...`
| | |
|---|---|
| Page title | 22 / 600 |
| Section | 16 / 600 |
| Card title | 14 / 600 |
| Body | 13 / 400 |
| Secondary | 12 / 400 dim |
| Label | 11 / 600 uppercase / 0.04em |

[AM] **Inter** · `'Inter', system-ui, sans-serif`
| | |
|---|---|
| Page title | 28 / 700 / -0.5px |
| Section | 18 / 700 |
| Card title | 14 / 600 / 1.4 |
| Body | 13 / 400 / 1.5 |
| Secondary | 12 / 500 |
| Label | 10 / 700 uppercase / 0.5px |

**Rule:** AM's scale runs one step larger and one step bolder than AB. That's deliberate — it matches the "fan, browsing" mood. Don't drag AB's scale up or soften AM's scale.

---

## 7 · Space & radius

Spacing scale (shared):
- `4px` — chip→chip, icon→label (tight)
- `6–8px` — inside a chip; row→row in a card
- `12px` — card padding; between filter labels
- `16px` — page sections; card padding
- `20–24px` — page margin; between major blocks
- `32–36px` — page top padding (main content)

Radius:
- [AB] flat utility: 4 / 6 / 8 px
- [AM] tiered: 8 / 14 / 20 px (tiles 14, hero panels and modals 20)

---

## 8 · Surface treatment

[AB] **Solid + 1px border.** `background: #161b22; border: 1px solid #2a3038; border-radius: 8px`. No shadow. The border *is* the visual division. Never `backdrop-filter`.

[AM] **Glass + low-opacity border.** `background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; backdrop-filter: blur(24px)`. Hover bumps card-bg opacity to 0.08.

If you reach for blur in AB, you're drifting. Use a raised surface (`--surface-2`) instead.

---

## 9 · The border-as-highlight rule

When something is **watching**, **selected**, **actionable**, **under review**, or otherwise different — the cue is a colored 1px border, optionally paired with a small glow shadow. **The fill stays the same as a default item.**

Examples in production:
- [AB] `.summary-card.active` → `border-color: var(--accent)` + 1px inset shadow
- [AB] `.book-card.plus-actionable` → `border-color: var(--warn)` (amber)
- [AB] `.merge-target-option.selected` → `border-color: var(--accent)`
- [AM] `.album-card.watched` → `border-color: var(--gold)` + `box-shadow: 0 0 16px rgba(245,200,66,0.15)`
- [AM] `.btn-watch.watching` → `border-color: var(--gold); background: rgba(245,200,66,0.2)` (note: filled because it's a *button*, not content)

**DO:** Border swaps color. Fill unchanged. Glow optional.
**DON'T:** Filled background for content state — reads as "selected button," not "needs attention."

Reserve filled accent backgrounds for **active CTAs** (primary buttons, active nav tab), not for content state.

---

## 10 · Source / storefront system

[AB] **Sources are routes.** Neutral grey pill + `↗` glyph. The user's action is "open one of these." Distinct colors would imply distinct meaning. Examples: `Audible US ↗`, `Audible JP ↗`, `Hoopla ↗`, `Audiobookshelf ↗`.

[AM] **Storefronts are identity.** 2-letter monogram pill, one color per region. Catalogs differ per storefront — knowing *where* is the discovery signal.

[AM] storefront palette:
| Code | Class type | Background / Foreground |
|---|---|---|
| HK | hardcoded | `rgba(255,60,130,.2)` / `#ff3c82` |
| JP | hardcoded | `rgba(255,80,60,.2)` / `#ff503c` |
| MY | hardcoded | `rgba(60,200,100,.2)` / `#3cc864` |
| TW | hardcoded | `rgba(100,150,255,.2)` / `#6496ff` |
| SG | hardcoded | `rgba(255,200,60,.2)` / `#ffc83c` |
| US | hashed | `rgba(180,100,255,.2)` / `#b464ff` |
| MO | hashed | `rgba(255,140,0,.2)` / `#ff8c00` |
| CN | hashed | `rgba(0,200,200,.2)` / `#00c8c8` |
| *others* | hashed | hash(code) % 12 → 12-hue palette (stable per code) |

```js
const SF_CSS_KNOWN = new Set(["hk", "jp", "my", "tw", "sg"]);
const SF_PALETTE = [/* 12 entries — see components.js */];
```

**Rule:** When adding a new storefront to AM, first ship via the hashed palette (free, no review needed). Only promote to a hardcoded class if (a) it's in the top-5 by user traffic and (b) the hashed color clashes with an adjacent canonical.

---

## 11 · Status grammar

| Status | Color | [AB] example | [AM] example |
|---|---|---|---|
| **Missing** (not yet found) | red `#f85149` | `Missing` chip | — (AM has no "missing"; new releases just appear) |
| **Owned** (in library) | green `#3fb950` | `In library` chip | — (collection-status implied via gold star) |
| **Actionable** (act now) | amber `#d29922` | `Available via Audible Plus` chip | `FUTURE RELEASE` tag |
| **Info / format / link** | blue `#58a6ff` | `Audiobook` chip | `LOSSLESS` tag |
| **Watching** (tracking) | gold | Gold "Watching" chip · green watch-toggle | Gold star + gold tile border + gold pill |
| **Category** (secondary tag) | purple `#a855f7` | `Book` chip | — (no purple chip; uses neutral) |
| **Language** (locale tag) | cyan `#79c0ff` | `english` chip | — (replaced by storefront chips) |

**Rule:** A chip's color *is* its meaning. If you reach for amber to mean "user-uploaded" or green to mean "japanese," stop. Find or extend a chip type. Don't reuse a semantic color for new semantics.

### [AM] Watchlist collection status

AM's watchlist tags each followed artist with a **collection status** — a curation state distinct from the watching flag (a watched artist always has a status). Rendered as a tint-20% chip (`.collection-status-badge`) on the artist row and as filter pills (`.cs-filter-btn`) above the list. Four states, defined in `utils.js` (`COLLECTION_STATUS_LABELS`, `COLLECTION_TRANSITIONS`) and `db.COLLECTION_STATUSES`:

| Status | Meaning | Chip color |
|---|---|---|
| `new` | Just added, not started | neutral grey `#a0a0aa` |
| `in_progress` | Actively collecting | blue `#508cff` |
| `complete` | Fully collected | green `#3cc864` |
| `new_release` | Complete but has a fresh drop to grab | amber `#ffaa28` |

This reuses the app's status semantics (grey = idle, blue = info/active, green = done, amber = act-now) rather than inventing hues. It is **not** the watching signal — that stays gold (§17). When adding a new collection state, extend both `utils.js` and `db.COLLECTION_STATUSES`, add a `.status-<code>` color, and update this table.

---

## 12 · Chips

[AB] **Single family.** 11px · pill (radius 999) · matched tints (bg + fg + border):

```css
.chip {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-dim);
  border: 1px solid var(--border);
}
.chip.missing { background: #3a1f1f; color: var(--bad); border-color: #5b2a2a; }
.chip.audiobook { background: #1a2640; color: var(--accent); border-color: #1f3158; }
.chip.in-library { background: #143620; color: var(--good); border-color: #1d4f30; }
.chip.plus { background: #3a2f10; color: var(--warn); border-color: #5d4715; }
```

[AM] **Two families:**
- `.sf-chip` — storefront monogram. 9px / weight 700 / radius 4 / uppercase / letter-spacing 0.5
- `.modal-tag` — rounded pill, 11px / weight 600 / radius 20 / 4×10 padding / neutral by default

Don't merge them — they're different on purpose.

---

## 13 · Buttons & inputs

[AB]
- Radius **6px** (square-ish utility)
- 6×12 padding · 13px font
- Variants: default (surface-2), primary (accent-dim fill, white), danger (red fill)
- Inputs match button radius

[AM]
- Radius **20px** pill (tappable, app-store feel)
- 8×16 padding · 13px font / weight 600
- Variants: default (transparent + border), primary (gradient fill), watch (gold border), fetch (purple border)
- Input pill: 10×14 padding, glass surface, accent focus border

**Rule:** Pill buttons in AB = drift. Square buttons in AM = drift.

---

## 14 · Filter bar

Shared pattern, two surface treatments.

[AB] Labeled native `<select>` controls in a single bordered row. Label above (11px uppercase 0.04em letter-spacing). Reset right-aligned via `margin-left: auto`.

[AM] Stacked pill rows grouped by `REGION` / `TYPE` / `SORT` labels. Each pill is `radius:999; bg:card; border:soft`. Active pill: gradient fill, no border.

**Active state cue is identical: filled accent background.**

---

## 15 · Summary stats [AB]

AB-only pattern. Every list page leads with these. They double as quick-filters: click → grid filters.

```css
.summary-card .num { font-size: 20px; font-weight: 600; }
.summary-card .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-dim); }
.summary-card.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent) inset; }
```

Compact variant: `.summary-card-compact .num { font-size: 16px }`, label 10px.

**If AM needs summary stats** (it already does inline: "67 releases in database"), wrap the same number/label structure in a glass panel, radius 14, no border-highlight active state.

---

## 16 · Item cards

[AB] **Book card · 280–320px wide**
2-col grid: `grid-template-columns: 72px 1fr; gap: 12px`. Cover 72×72 with `object-fit: contain`. Meta column: title (14/600) · byline (12/dim) · chips (wrap) · sources (wrap).

[AM] **Album tile · 180–200px wide**
Full-bleed square artwork on top. 12px info pad. Title 13/600 (truncate). Artist 12/500 in accent. Meta-row: date (11/dim) + sf-chips. Star top-right when watched. Track count chip bottom-right of artwork.

**Rule:** Aspect of the artwork frame is a hard constant. 1:1 square in both apps. Never crop, never letterbox, never introduce 2:3 portrait. If a source returns weird aspect, `object-fit: contain` on a square slot.

---

## 17 · Watch indicator

The one piece of state that lives in both apps. **Color is always gold.** Shape differs by app vocabulary.

[AB] On author/work pages, in the meta strip:
- A switch (database-like, two-state) — track green when on, neutral when off
- The "Watching" *chip* itself is gold (`--warn`)

[AM] On album tile + artist header — three concurrent signals:
- ★ glyph top-right of artwork
- Gold border on the tile
- Gold pill button ("★ Watching")

**Don't swap shapes.** AB switch = data-model boolean. AM star = collector's flag.

---

## 18 · Navigation

The most-different surface. Don't merge them.

[AB] Top tabs. Brand at left (bold text, no logo). Tab links inline. Active state: `--surface-2` fill + full text color. No icons.

[AM] Left sidebar. Brand: ♫ icon + "AM Discovery" gradient-fill text. Nav links: icon + label, 13/500. Active: linear-gradient bg with 0.15 alpha + 1px accent border. Footer carries: metadata-source widget (storefront pills) · status dot · refresh button.

**Rule:** If AB gains more than 5 top-level pages, move to a sidebar — but it must look like an *AB* sidebar (solid `#161b22`, no gradient brand, no glow), not an AM sidebar. Mimicking AM chrome is the most common drift.

---

## 19 · Modals & detail

[AB] Native `<dialog>` element. Backdrop `rgba(0,0,0,.6)`. 360px min / 90vw max / 24px padding. Title 16/600 · `.field` (label 12/dim + control stacked, 4px gap) · actions row right-aligned.

Almost always **task dialogs** (merge / delete / alias).

[AM] Floating glass card. Backdrop `rgba(0,0,0,.7)` + 6px blur. 560px max / 90vh max / radius 20. Compact header: 130px artwork thumb + meta + action pill row. Tracklist as numbered list. Footer: "✨ Discover Similar" gradient button.

Almost always **content surfaces** (rich album detail).

If you need content-rich UI in AB, use a side panel — keep dialogs for confirmations.

---

## 20 · Page archetypes

### A · List page [BOTH]
Most common. Examples: AB "All Books," AM "New Releases," AM "All Albums."

Structure:
1. Page header — title left, optional CTA right
2. Summary stats row — **required in AB**, compact cards
3. Filter bar — labeled controls, one row/panel
4. Result count — "16142 works," small uppercase, above grid
5. Grid — `auto-fill, minmax(180–280px, 1fr)`, 12–20px gap
6. Pagination — centered, numbered, ellipsis when long
7. Empty / loading — dashed-border empty box; shimmer skeleton grid

### B · Detail page [BOTH]
Hero subject + child list. Examples: AB Author page, AM Artist page.

- **Hero header.** [AB] 100px square avatar · name · 3-line clamped description w/ "See more" · categories + watch toggle inline. [AM] 56–72px round avatar · name · genre · region · action pills (Open in AM, MusicBrainz, Watching, Fetch).
- **Optional artist-note block** [AM] — "In the artist's words."
- **Stats sub-row** [AB] — compact summary cards.
- **Filter bar** scoped to subject.
- **Child grid** — same item card as list page.

### C · Watchlist / table page [BOTH]
Many subjects in scannable rows.

- Header: title + "Add" button + search top-right
- Filter strip: smaller than list-page bar
- Body:
  - [AB] Native `<table.data>` with sticky header. Author thumbnail + name. Status chips inline.
  - [AM] Card list. 44px avatar + name + alt-name + date. "Unwatch" pill right.
- Alpha index: sticky A–Z rail on right; letters enabled only when present.

### D · Admin / settings page
- 220px left sidebar + content
- Sidebar groups with uppercase 10px labels (APP / AUTHOR / WORK / ATTRIBUTION / LOG)
- Items 12/dim, active gets accent fill
- Single focused form/panel per route — one job per route

---

## 21 · Voice & tone

[AB] **Plain, technical, slightly dry.** The user is auditing data; respect that.
- ✓ "Tracked works" · "Missing audio" · "Originally published" · "Merge two watchlist authors"
- ✗ "Books you're loving" · "Find your next listen" · "Cozy new arrivals 📚"

Page titles are nouns ("Admin", "All Books"). Action buttons are verbs ("Mark Complete", "Manage aliases"). No emoji in body.

[AM] **A bit more warmth.** Still concise.
- ✓ "Latest albums discovered across JP · TW · MY · HK · SG · US" · "In the artist's words" · "✨ Discover Similar"
- ✗ "Heat-of-the-moment hot drops 🔥🔥🔥" · "Today's bops"

Single emoji as button icon is OK (♫ ⭐ ✨ ↓). Sentence-case body. Title Case section headers. Gradients only on brand + primary buttons.

**Numbers are first-class content.** Both apps over-index on counts: "16142 works", "67 releases in database", "1509 authors", "8+34". Always show counts near the data — never bury them in a tooltip. New list → count goes above it.

---

## 22 · Do / Don't

| # | Topic | DO | DON'T |
|---|---|---|---|
| 1 | Highlighting an item | Border swap + optional glow. Fill stays neutral. | Filled background — reads as "selected button" not "needs attention." |
| 2 | New categorical color | Use storefront palette (§10) — hashed assigns automatically. | Reuse status green/red — collides with "owned"/"missing" semantics. |
| 3 | Adding a button (AB) | 6px radius. Match AB inputs. | Pill buttons in AB read as AM and pull the page toward the wrong app. |
| 4 | Showing a count | "16142 works" above the grid, always present. | "(showing many items)" — vague labels in a data-auditing app are an engineering smell. |
| 5 | Empty state | Dashed border. One short line. Direct. | "Oops! 😕 …discovery adventure!" — cutesy copy is wrong everywhere. |
| 6 | Mixing surface treatments | AB stays solid; AM stays glass. | Adding `backdrop-filter` in AB or removing it in AM. |
| 7 | New accent color | Reuse existing palette at different alpha. | Introduce a new hue — both palettes are already saturated with semantics. |
| 8 | Match the other app | Borrow a pattern, not the chrome. | Importing AM's sidebar wholesale into AB (or vice versa). |

---

## 23 · Iteration playbook

### A · "Add a new page to <app>"
1. Pick an archetype from §20. Don't invent a new one without a written reason.
2. Reuse the app's navigation surface — add to existing nav list, same active style.
3. Page header: 22/600 (AB) or 28/700 (AM) + optional one-line subtitle.
4. If summary stats apply: existing card component.
5. Filter bar from §14. Every filter labeled. Reset top-right.
6. Reuse existing item card (§16). If the data doesn't fit, ask before introducing a new shape.

### B · "Add a new state / chip type"
1. Is it really new? Many "new states" map to existing (missing / actionable / owned / watching / category / language).
2. If yes, pick from status grammar (§11) — never invent a new accent hue.
3. Build the chip with the canonical recipe: tint-20% background + solid foreground + matching border.
4. If state implies card-level highlight, use border-color (§9), not background-fill.
5. **Document it in `DESIGN.md`.** A chip that isn't in §11 is undefined behavior for future agents.

### C · "Add a new source / storefront"
- [AM] Use the hash palette automatically (free). Verify no clash with an adjacent canonical in common UI rows. Only promote to hardcoded class if traffic + clash justifies.
- [AB] Source pills are neutral. Add to the source filter list and per-card source row. No new color needed.

### D · "Make <app> feel more like <other app>"
1. Pause. The apps are deliberately different. Confirm the user means "borrow a specific pattern" — not "rebrand."
2. If a specific pattern: identify which lane (§3) is changing. Update *only* that lane.
3. If a rebrand: v2-scale change. Revise `DESIGN.md` first, then code.

### E · "Add a new accent / brand color"
1. Don't. Both palettes are saturated with semantics on every hue.
2. New categorical color → extend storefront palette (§10).
3. New interactive accent → use the existing accent at different lightness/saturation.

### F · "Add a new component"
1. Check §12–19. Most "new" components are a variation. Use the closest match with a variant class.
2. If truly new: build it once per app, using each app's tokens. Add parity to `DESIGN.md`.
3. Match radius, surface style, and type scale to the host app — never the other app.

---

## 24 · Agent cheat-sheet

```
ab-discovery   ::= utility, audiobooks, librarian's tool
                  bg #0e1116  surface #161b22  accent #58a6ff (blue)
                  top tabs · solid panels · 4/6/8 radius · system sans · 13px body
                  thumbnail 72×72 in 2-col card row

am-discovery   ::= expressive, music, fan's tool
                  bg #0a0a0f  glass card  accent #ff3c82 → #a855f7 (pink→purple)
                  sidebar · glass/blur surfaces · 8/14/20 radius · Inter · 13-14px body
                  full-bleed square artwork tiles 200px

SHARED RULES (both apps)
border = highlight                → selected/watching/actionable swaps border color, never fill
gold = watching                   → AB #d29922 / AM #f5c842 — never repurpose
red = missing                     → AB only ("Missing" chip)
green = in-library / success      → chip + watch-toggle on
amber = actionable now            → "Available via Plus", "Future release"
blue = info / format / link       → "Audiobook" chip, "LOSSLESS" tag
filter bars labeled               → 11px uppercase, never placeholder-only
counts above lists                → "16142 works", "67 releases in database"

SOURCE / STOREFRONT
AB sources are routes      → neutral grey pill + ↗ glyph
AM storefronts are identity → 2-letter monogram, colored
  hardcoded: HK pink · JP red-orange · MY green · TW blue · SG amber
  others   : hashed palette of 12 hues (US purple · MO orange · CN cyan · ...)

BEFORE ADDING ANYTHING
1. exists already? → reuse
2. needs new color? → use storefront palette, not status palette
3. needs new state? → must map to §11 grammar
4. needs new component? → match host app's radius/surface/scale, not the other app
5. trying to merge ab + am visuals? → STOP. read §3.

THE ONE LINE
Same brain, different faces. Tokens in parallel, visuals in distinct lanes,
state on the edge of the card, never in the fill.
```

---

## When to update this file

- **Before** adding tokens, accent colors, chip types, or page archetypes.
- **Before** rebranding either app.
- **After** discovering an undocumented pattern that's already been built (back-fill it).
- **Never** during a small one-off styling change.

If this document is wrong, fix this document first, then the code. The doc is the source of truth — drift in code is the failure mode this whole file exists to prevent.
