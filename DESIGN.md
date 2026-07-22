# AM Discovery — Design System

> **Scope:** the am-discovery frontend (`frontend/`).
> **Audience:** Coding agents (Claude Code, Cursor, etc.) and the humans reading their PRs.
> **Source of truth:** this file. When the doc and code disagree, fix the doc first, then the code.

---

## 0 · How to read this

- Every color, radius, and font size resolves to a **named token** (§3). Reference tokens by name, never by raw hex.
- The design language is fixed and deliberate — a music fan's tool, artwork-first, glass surfaces, pink→purple accent. Don't drift it toward a generic dashboard.

**Reading order for new work:**
1. Pick the closest existing page archetype (§19) and component (§11–18).
2. Resolve every color, radius, and font size to a named token (§3).
3. Apply the border-as-highlight rule (§8) for any "selected / watching / important" state.
4. Check the Don't column (§21) and the iteration playbook (§22) before introducing anything new.

> **Note:** A cross-app visual reference lives in `design-guidance/index.html` (it renders am-discovery components alongside a sibling app for parity). It uses its own doc fonts and branding, so treat it as a component sketchbook — the real, authoritative rendering is always the running app itself.

---

## 1 · The app

| | **am-discovery** |
|---|---|
| **One sentence** | Follow artists across Apple Music storefronts; get the album the moment it drops, anywhere. |
| **Mood** | Fan's tool. Visually-led. |
| **Surface** | Translucent glass, backdrop-blur |
| **Navigation** | Left sidebar w/ icons + status footer |
| **Imagery** | Full-bleed 1:1 hero artwork |
| **Density** | Tile grid · 200px min |
| **Accent** | `#ff3c82 → #a855f7` pink-purple gradient |
| **Type** | Inter · 13–14px body · 28px page title · gradient brand |
| **Motion** | Hover lift −3px · pulse on refresh · shimmer on load |

---

## 2 · Core rules (non-negotiable)

1. **Dark, layered.** Single near-black base (`--bg-deep`). One glass surface layer above it (`--bg-card`). One subtle border (`--border`). No more than two background tones in a normal view.
2. **Color carries semantics.** Green = in library/success. Gold = watching. Amber = needs attention / future release. Blue = info. Never decorate without semantic intent (§10).
3. **Border = highlight.** "Selected / watching / actionable" states change the *border color*, not the fill. See §8.
4. **Storefront is identity.** Every album declares which storefront(s) it came from via colored `sf-chip` monograms — always visible, never hidden in tooltips (§9).
5. **Filter bars are labeled.** Uppercase letter-spaced labels above every control group. No placeholder-only fields. Reset/clear right-aligned (§13).
6. **Counts are first-class.** Show the number near the data ("67 releases in database"). New list → count goes above it (§14, §20).
7. **Empty & loading are first-class.** Dashed-border empty box with one-line copy. Shimmer skeletons match the target component's silhouette. Never a spinner alone.
8. **Watching is gold.** The "I'm tracking this" signal is gold `--gold` (`#f5c842`). Don't repurpose gold for anything else (§16).

---

## 3 · Tokens

Defined in `frontend/style.css` under `:root`. This table is canonical — always reference by name.

| Token | Value | Use |
|---|---|---|
| `--bg-deep` | `#0a0a0f` | Outermost canvas |
| `--bg-mid` | `#12121a` | Secondary flat surface |
| `--bg-card` | `rgba(255,255,255,.04)` | Cards, panels, nav strip (glass) |
| `--bg-card-hover` | `rgba(255,255,255,.08)` | Inputs, hover, nested cards |
| `--border` | `rgba(255,255,255,.08)` | Every component border, always 1px |
| `--border-glow` | `rgba(255,60,130,.4)` | Focus / accent glow edge |
| `--accent` | `#ff3c82` | Links, focus rings, brand mark, artist name |
| `--accent-2` | `#a855f7` | Gradient stop / fetch action |
| `--accent-grad` | `linear-gradient(135deg,#ff3c82,#a855f7)` | Brand text, primary buttons, active nav/pill |
| `--gold` | `#f5c842` | Watching flag (star, tile border, watch pill) |
| `--text-primary` | `#f0f0f8` | Body, titles |
| `--text-secondary` | `#9999bb` | Bylines, meta, descriptions |
| `--text-dim` | `#55556a` | Timestamps, placeholders, labels |
| `--radius-sm` | `8px` | Chips, inputs, sf-pills |
| `--radius-md` | `14px` | Cards, sections, tiles |
| `--radius-lg` | `20px` | Hero panels, modals, pill buttons |
| `--shadow-card` | `0 4px 24px rgba(0,0,0,.4)` | Card elevation |
| `--shadow-glow` | `0 0 20px rgba(255,60,130,.2)` | Accent glow |
| `--transition` | `0.2s ease` | Default transition |
| `--sidebar-w` | `240px` (64px collapsed) | Sidebar width |

**Rule:** When adding a component, if its role exists above, use the existing token. Adding a new token is a design decision — document it here first.

---

## 4 · Color

Palette: `#0a0a0f` `#12121a` `rgba(255,255,255,.04)` `rgba(255,255,255,.08)` `#f0f0f8` `#9999bb` `#55556a` `#ff3c82` `#a855f7` `#f5c842`
Gradient: `linear-gradient(135deg, #ff3c82, #a855f7)`

**DO** tint via low-opacity overlays: status chips and sf-chips use `rgba(accent, 0.2)` as background and the solid accent as text.

**DON'T** introduce a new accent hue. Need a new categorical color → storefront palette (§9). Need to highlight → use the accent already defined.

---

## 5 · Typography

**Inter** · `'Inter', system-ui, sans-serif`

| | |
|---|---|
| Page title | 28 / 700 / -0.5px |
| Section | 18 / 700 |
| Card title | 14 / 600 / 1.4 |
| Body | 13 / 400 / 1.5 |
| Secondary | 12 / 500 |
| Label | 10 / 700 uppercase / 0.5px |

The scale runs deliberately large and bold — it matches the "fan, browsing" mood. Gradient fill is reserved for the brand mark and primary buttons only.

---

## 6 · Space & radius

Spacing scale:
- `4px` — chip→chip, icon→label (tight)
- `6–8px` — inside a chip; row→row in a card
- `12px` — card padding; between filter labels
- `16px` — page sections; card padding
- `20–24px` — page margin; between major blocks
- `32–36px` — page top padding (main content)

Radius (tiered): `8 / 14 / 20 px` — tiles 14, hero panels and modals 20, chips/inputs 8, text buttons 20 (pill).

---

## 7 · Surface treatment

**Glass + low-opacity border.** `background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; backdrop-filter: blur(24px)`. Hover bumps card-bg opacity to `0.08`. The sidebar and modal carry the blur; flat panels can use `--bg-mid` when blur isn't wanted.

---

## 8 · The border-as-highlight rule

When something is **watching**, **selected**, **actionable**, or otherwise different — the cue is a colored 1px border, optionally paired with a small glow shadow. **The fill stays the same as a default item.**

Examples in production:
- `.album-card.watched` → `border-color: var(--gold)` + `box-shadow: 0 0 16px rgba(245,200,66,0.15)`
- `.btn-watch.watching` → `border-color: var(--gold); background: rgba(245,200,66,0.2)` (filled because it's a *button*, not content)

**DO:** Border swaps color. Fill unchanged. Glow optional.
**DON'T:** Filled background for a *content* state — reads as "selected button," not "needs attention."

Reserve filled accent/gradient backgrounds for **active CTAs** (primary buttons, active nav link, active filter pill), not for content state.

---

## 9 · Storefront system

**Storefronts are identity.** Catalogs differ per region, so *where* an album appears is the discovery signal. Rendered as a 2-letter monogram `sf-chip` (9px / weight 700 / radius 4 / uppercase / letter-spacing 0.5), one color per region.

Hardcoded classes (`.sf-chip.<code>` in `style.css`) — the top-traffic regions:

| Code | Background / Foreground |
|---|---|
| HK | `rgba(255,60,130,.2)` / `#ff3c82` |
| JP | `rgba(255,80,60,.2)` / `#ff503c` |
| MY | `rgba(60,200,100,.2)` / `#3cc864` |
| TW | `rgba(100,150,255,.2)` / `#6496ff` |
| SG | `rgba(255,200,60,.2)` / `#ffc83c` |

Everything else is assigned deterministically from a 12-hue hashed palette (`SF_PALETTE` in `components.js`, via `sfChipInlineStyle()`):

```js
const SF_CSS_KNOWN = new Set(["hk", "jp", "my", "tw", "sg"]);
const SF_PALETTE = [/* 12 entries — see components.js */];
```

**Rule:** When adding a new storefront, first ship via the hashed palette (free, no CSS needed). Only promote to a hardcoded `.sf-chip.<code>` class if (a) it's in the top-5 by traffic and (b) the hashed color clashes with an adjacent canonical. Then update this table.

---

## 10 · Status grammar

A chip's color *is* its meaning. Don't reuse a semantic color for new semantics.

| Status | Color | Example |
|---|---|---|
| **Actionable** (act now) | amber | `FUTURE RELEASE` tag |
| **Info / format / link** | blue `#58a6ff` | `LOSSLESS` tag |
| **Success / in-library** | green `#34d399` | success dot |
| **Watching** (tracking) | gold `#f5c842` | Gold star + gold tile border + gold pill |

New releases just *appear* — there is no "missing" state and no red content chip; red is reserved for error banners.

### Watchlist collection status

The watchlist tags each followed artist with a **collection status** — a curation state distinct from the watching flag (a watched artist always has a status). Rendered as a tint-20% chip (`.collection-status-badge`) on the artist row and as filter pills (`.cs-filter-btn`) above the list. Four states, defined in `utils.js` (`COLLECTION_STATUS_LABELS`, `COLLECTION_TRANSITIONS`) and `db.COLLECTION_STATUSES`:

| Status | Meaning | Chip color |
|---|---|---|
| `new` | Just added, not started | neutral grey `#a0a0aa` |
| `in_progress` | Actively collecting | blue `#508cff` |
| `complete` | Fully collected | green `#3cc864` |
| `new_release` | Complete but has a fresh drop to grab | amber `#ffaa28` |

This reuses the app's status semantics (grey = idle, blue = info/active, green = done, amber = act-now) rather than inventing hues. It is **not** the watching signal — that stays gold (§16). When adding a new collection state, extend both `utils.js` and `db.COLLECTION_STATUSES`, add a `.status-<code>` color, and update this table.

**Rule:** If you reach for amber to mean "user-uploaded" or green to mean a genre, stop. Find or extend a chip type — never repurpose a semantic color.

---

## 11 · Chips

Two families, kept distinct on purpose:

- `.sf-chip` — storefront monogram. 9px / weight 700 / radius 4 / uppercase / letter-spacing 0.5. Colored per region (§9).
- `.modal-tag` — rounded pill, 11px / weight 600 / radius 20 / 4×10 padding / neutral by default. Used for formats (`LOSSLESS`, `DOLBY ATMOS`), release type, and other labels.
- `.collection-status-badge` / `.cs-filter-btn` — watchlist curation states (§10).

Don't merge `.sf-chip` and `.modal-tag` — they're different shapes for different meanings.

---

## 12 · Buttons & inputs

- Radius **20px** pill (tappable, app-store feel)
- 8×16 padding · 13px font / weight 600
- Variants: default (transparent + border), primary (gradient fill), watch (gold border), fetch (purple border)
- Input pill: 10×14 padding, glass surface, accent focus border

**Rule:** 6px-radius square buttons read as a different app — keep buttons pill-shaped.

---

## 13 · Filter bar

Stacked pill rows grouped by labels (e.g. `REGION` / `TYPE` / `SORT`). Each pill is `radius:999; bg:card; border:soft`. Active pill: gradient fill, no border. Every control group carries an uppercase letter-spaced label; nothing is placeholder-only.

---

## 14 · Counts & summary

The app over-indexes on counts: "67 releases in database", result counts above every grid. Wrap a big-number/small-uppercase-label pair in a glass panel (radius 14) when a summary block is wanted — no border-highlight active state needed. Always show the count near the data; never bury it in a tooltip.

---

## 15 · Item cards

**Album tile · 180–200px wide.** Full-bleed square artwork on top (`object-fit: contain` on a 1:1 slot — never crop, letterbox, or go portrait). 12px info pad. Title 13/600 (truncate). Artist 12/500 in `--accent`. Meta-row: date (11/dim) + `sf-chips`. Star top-right (`.watched-badge`) when watched. Track-count chip bottom-right of the artwork. Seed sprout `🌱` top-left (`.seed-badge`) when the release is flagged as missing from MusicBrainz (`mb_seed_status === "needs_seeding"` and not hidden). When artwork is missing/blocked, `placeholderEl` renders a `♫` glass tile.

**Artwork-corner glyphs** are emoji indicators, one per reserved corner — `★` watched (top-right), `🌱` needs-seeding (top-left), track-count chip (bottom-right). One glyph per corner; don't stack. The emoji shape carries the meaning, so the glyph itself sits outside the §10 color grammar. For legibility over busy artwork they get a chip backing: the star is a bare drop-shadowed glyph, while `.seed-badge` and `.track-count-chip` sit on a dark glass disc/pill (`rgba(0,0,0,0.6)` + blur). `.seed-badge` adds an amber ring (`rgba(255,170,40,0.6)`) — amber = actionable (§10), because a needs-seeding release is an act-now item; it is **not** gold (that stays the watch flag, §16).

**Artist card · circular artwork.** Round avatar + name + genre, navigates to the in-app artist page.

**Rule:** The 1:1 square (tiles) / circle (artists) artwork frame is a hard constant.

---

## 16 · Watch indicator

**Color is always gold.** Three concurrent signals — don't drop any:
1. `★` glyph top-right of artwork (`.watched-badge`)
2. Gold border on the tile (`.album-card.watched`)
3. Gold pill button on the artist header (`.btn-watch.watching`)

Gold is the collector's flag; it means "I'm tracking this" and nothing else.

---

## 17 · Navigation

Left sidebar. Brand: ♫ icon + "AM Discovery" gradient-fill text. Nav links: icon + label, 13/500. Active: linear-gradient background at 0.15 alpha + 1px accent border. Footer carries the metadata-source widget (storefront pills), a status dot + last-updated, and the refresh button. Collapses to a 64px icon rail on small screens.

---

## 18 · Modals & detail

Floating glass card. Backdrop `rgba(0,0,0,.7)` + 6px blur. 560px max / 90vh max / radius 20. Compact header: ~130px artwork thumb + meta + action pill row. Tracklist as a numbered list (music videos separated from song tracks). Footer: "✨ Discover Similar" gradient button. Modals are **content surfaces** (rich album detail), not task dialogs.

---

## 19 · Page archetypes

### A · List page
Examples: New Releases, All Albums.
1. Page header — title left (28/700), optional CTA right
2. Filter bar — labeled pill groups (§13)
3. Result count — "16142 releases", small uppercase, above grid (§14)
4. Grid — `auto-fill, minmax(180–200px, 1fr)`, 12–20px gap, tiles from §15
5. Pagination — centered, numbered, ellipsis when long
6. Empty / loading — dashed-border empty box; shimmer skeleton grid

### B · Detail page (Artist)
Hero subject + child list.
- **Hero header** — 56–72px round avatar · name · genre · region · action pills (Open in AM, MusicBrainz, Watching, Fetch).
- **Optional artist-note block** — "In the artist's words."
- **Filter bar** scoped to the artist — view toggle, release-type pills, and a `🌱 Needs seeding` toggle pill (only shown when the artist has releases flagged for MusicBrainz seeding).
- **Child grid** — same album tile as the list page.

### C · Watchlist page
Many artists in scannable rows.
- Header: title + "Add" button + search top-right
- Filter strip: collection-status pills (§10) + sort
- Body: card list — 44px avatar + name + alt-name + date, collection-status badge, "Unwatch" pill right
- Alpha index: sticky A–Z rail on the right; letters enabled only when present

### D · Admin / Settings page
- Left sub-nav + content pane; one job per route
- Admin (MusicBrainz seeding): Artists + Releases tabs
- Settings: config, timezone, notifications, CLI Scheduler
- Uppercase small labels on groups; active item gets accent fill

---

## 20 · Voice & tone

**A bit of warmth, still concise.**
- ✓ "Latest albums discovered across JP · TW · MY · HK · SG · US" · "In the artist's words" · "✨ Discover Similar"
- ✗ "Heat-of-the-moment hot drops 🔥🔥🔥" · "Today's bops"

Single emoji as a button icon is OK (♫ ⭐ ✨ ↓). Sentence-case body. Title Case section headers. Gradients only on the brand mark + primary buttons.

**Numbers are first-class content.** Always show counts near the data — "67 releases in database". New list → count goes above it.

---

## 21 · Do / Don't

| # | Topic | DO | DON'T |
|---|---|---|---|
| 1 | Highlighting an item | Border swap + optional glow. Fill stays neutral. | Filled background — reads as "selected button" not "needs attention." |
| 2 | New categorical color | Use the storefront palette (§9) — hashed assigns automatically. | Reuse status green/amber — collides with existing semantics. |
| 3 | Adding a button | 20px pill. Match existing buttons. | 6px square buttons pull the page toward a generic dashboard. |
| 4 | Showing a count | "16142 releases" above the grid, always present. | Vague labels like "(showing many items)". |
| 5 | Empty state | Dashed border. One short line. Direct. | Cutesy copy ("Oops! 😕 …"). |
| 6 | Surface | Glass + backdrop-blur on sidebar/modal. | Dropping the blur or piling on more than two background tones. |
| 7 | New accent color | Reuse the existing palette at a different alpha. | Introduce a new hue — the palette is already saturated with semantics. |

---

## 22 · Iteration playbook

### A · "Add a new page"
1. Pick an archetype from §19. Don't invent a new one without a written reason.
2. Add a route in `app.js` and a `nav-link` in `index.html`, same active style (§17).
3. Page header 28/700 + optional one-line subtitle.
4. Filter bar from §13 — every group labeled, reset right-aligned.
5. Reuse the existing album/artist card (§15). If the data doesn't fit, ask before introducing a new shape.

### B · "Add a new state / chip type"
1. Is it really new? Most map to existing (actionable / info / success / watching / collection-status).
2. If yes, pick a color from status grammar (§10) — never invent a new accent hue.
3. Build the chip with the canonical recipe: tint-20% background + solid foreground + matching border.
4. If the state implies card-level highlight, use `border-color` (§8), not background fill.
5. **Document it here.** A chip that isn't in §10/§11 is undefined behavior for future agents.

### C · "Add a new storefront"
- Use the hashed palette automatically (free). Verify no clash with an adjacent canonical in common rows. Only promote to a hardcoded class if traffic + clash justify it, then update §9.

### D · "Add a new component"
1. Check §11–18. Most "new" components are a variation — use the closest match with a variant class.
2. If truly new: build it with the app's tokens, matching radius / surface / type scale. Add it to this doc.

### E · "Add a new accent / brand color"
1. Don't. The palette is saturated with semantics on every hue.
2. New categorical color → extend the storefront palette (§9).
3. New interactive accent → use the existing accent at a different lightness/saturation.

---

## 23 · Agent cheat-sheet

```
am-discovery ::= expressive, music, fan's tool
  bg #0a0a0f · glass card · accent #ff3c82 → #a855f7 (pink→purple)
  sidebar · glass/blur surfaces · 8/14/20 radius · Inter · 13-14px body
  full-bleed square artwork tiles ~200px

CORE RULES
border = highlight        → selected/watching/actionable swaps border color, never fill
gold = watching           → #f5c842 — never repurpose (star + tile border + pill)
green = in-library/success
amber = actionable now     → "FUTURE RELEASE", new_release status
blue = info / format / link → "LOSSLESS" tag
filter bars labeled        → uppercase, never placeholder-only
counts above lists         → "67 releases in database"

STOREFRONT (identity, 2-letter colored monogram)
  hardcoded: HK pink · JP red-orange · MY green · TW blue · SG amber
  others   : 12-hue hashed palette (stable per code)

COLLECTION STATUS (watchlist curation, tint-20% chip)
  new grey · in_progress blue · complete green · new_release amber

BEFORE ADDING ANYTHING
1. exists already?  → reuse
2. new color?       → storefront palette, not the status palette
3. new state?       → must map to §10 grammar
4. new component?   → match the app's radius/surface/scale

THE ONE LINE
Artwork-first, glass surfaces, state on the edge of the card, never in the fill.
```

---

## When to update this file

- **Before** adding tokens, accent colors, chip types, or page archetypes.
- **Before** any rebrand.
- **After** discovering an undocumented pattern that's already been built (back-fill it).
- **Never** during a small one-off styling change.

If this document is wrong, fix this document first, then the code. The doc is the source of truth — drift in code is the failure mode this whole file exists to prevent.
