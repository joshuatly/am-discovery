# Frontend code — design rules apply

You are working in the frontend (Vanilla JS). The design system for this app is defined in [`../DESIGN.md`](../DESIGN.md), included below.

**Before making any visual change:**
1. Resolve every color / radius / font-size to a named token from §3 of `DESIGN.md`.
2. Apply the border-as-highlight rule (§8) for any "selected / watching / important" state.
3. Check the Don't list (§21) and iteration playbook (§22) before introducing anything new.

**Hard rules that catch the most drift:**
- Glass surfaces with backdrop-blur on the sidebar/modal. Don't drop the blur or add a third background tone.
- Buttons are 20px pills. 6px-radius square buttons read as a generic dashboard — drift.
- Border carries state. Fill carries "active CTA." Never swap.
- Gold = watching. Never reuse gold for anything else.
- Don't introduce new accent hues. Don't reuse status colors for categorical labels.

**Authoritative rendering:** the running app itself. A cross-app component sketchbook exists at `../design-guidance/index.html`, but it uses its own doc fonts/branding — don't treat it as this app's pixel truth.

---

@../DESIGN.md

---

# You are in am-discovery

Stack: Vanilla JS, no framework. Pages are functions in `page-*.js` that mount into `#main-content`. Styles in `style.css` using CSS custom properties.

**This app's identity:**
- Fan tool, music vocabulary, artwork-first mood
- Glass surfaces — `background: rgba(255,255,255,0.04)` + `1px solid rgba(255,255,255,0.08)` + `backdrop-filter: blur(24px)` on the sidebar/modal
- Left sidebar navigation with icons + status footer (refresh button, last-updated dot, metadata-source widget)
- Pink → purple accent gradient: `linear-gradient(135deg, #ff3c82, #a855f7)`
- 8 / 14 / 20 px radius scale — tiered, softer at every level
- Inter font, 13–14px body, 28px page titles
- Full-bleed 1:1 square artwork on tiles (200px grid)

**Tokens already defined in `style.css`:**
```
--bg-deep --bg-mid --bg-card --bg-card-hover --border --border-glow
--accent --accent-2 --accent-grad --gold
--text-primary --text-secondary --text-dim
--radius-sm --radius-md --radius-lg --shadow-card --shadow-glow --transition
```

Always reference by token name. Never hardcode hex.

**When adding a new page:**
1. Add a route to `app.js` and a `nav-link` to `index.html`.
2. Build the page-fn pattern (mirror `page-releases.js` or `page-watchlist.js`).
3. Reuse existing components from `components.js` (`sfChips`, `artworkEl`, `skeletonGrid`, etc.) before writing new ones.

**When adding a new storefront:**
1. First ship with the hashed palette — `sfChipInlineStyle()` in `components.js` assigns deterministically.
2. Only promote to a hardcoded `.sf-chip.<code>` CSS class if (a) it's in the top-5 by traffic and (b) the hashed color clashes with an existing canonical (HK/JP/MY/TW/SG).
3. Update `../DESIGN.md` §9 with the new code if hardcoded.

**When adding a new tag / chip:**
- Storefront-shaped (2-letter monogram, identity)? Use `.sf-chip` family.
- Pill-shaped (label/format)? Use `.modal-tag` family.
- Don't merge the two — they're different on purpose (§11).

**Watched state is three concurrent signals** (don't drop any):
1. `★` glyph top-right of artwork (`.watched-badge`)
2. Gold border on the tile (`.album-card.watched`)
3. Gold pill button on artist header (`.btn-watch.watching`)

The full design system is in `../DESIGN.md`.
