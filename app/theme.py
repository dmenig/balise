"""The CSS that turns a Streamlit page into a map application.

Streamlit stacks blocks in a padded document column. Three things undo that: the chrome is
hidden, the block container loses its padding and max-width, and every panel is a keyed
container (`st.container(key=…)` renders as `.st-key-<key>`) pinned over the map with
`position: fixed`. Panels let clicks through (`pointer-events: none`) so the map keeps the
drag; the controls inside them switch it back on.
"""

from __future__ import annotations

LIGHT = {
    "ink": "#0a1d2e",
    "muted": "#6b7c8c",
    "card": "rgba(255,255,255,0.94)",
    "edge": "rgba(10,29,46,0.09)",
    "accent": "#0f6fb8",
    "on-accent": "#ffffff",
    "shadow": "0 6px 22px rgba(10,29,46,0.18)",
    "field": "rgba(10,29,46,0.05)",
    "ghost": "rgba(255,255,255,0.62)",
    "menu": "#ffffff",
    "hover": "rgba(15,111,184,0.10)",
}
DARK = {
    "ink": "#eaf2f9",
    "muted": "#93a7b9",
    "card": "rgba(15,28,42,0.94)",
    "edge": "rgba(255,255,255,0.14)",
    "accent": "#4fb3f5",
    "on-accent": "#06121e",
    "shadow": "0 6px 22px rgba(0,0,0,0.5)",
    "field": "rgba(255,255,255,0.09)",
    "ghost": "rgba(15,28,42,0.66)",
    "menu": "#132a3e",
    "hover": "rgba(79,179,245,0.18)",
}


#: The magnifier, inlined as a mask so it takes the palette's colour like any other text.
GLASS = (
    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<path d='M10 2a8 8 0 105.03 14.27l5.35 5.35 1.41-1.41-5.35-5.35A8 8 0 0010 2zm0 2a6 6 0 "
    "110 12 6 6 0 010-12z'/></svg>\")"
)


def css(night: bool, focused: bool) -> str:
    """`focused` — something is selected, so the dock shows it instead of the search.

    The search and the chips are still rendered, and hidden here rather than skipped: a
    Streamlit widget that is not drawn on a run loses its state.
    """
    token = DARK if night else LIGHT
    variables = "".join(f"--{name}:{value};" for name, value in token.items())
    focus = ".st-key-finder{display:none!important}" if focused else ""
    return f"<style>:root{{{variables}--glass:{GLASS};}}{_SHEET}{focus}</style>"


_SHEET = """
/* ---- full-bleed shell ---------------------------------------------------- */
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], footer { display: none !important; }
html, body, [data-testid="stAppViewContainer"] { height: 100%; overflow: hidden; }
[data-testid="stMainBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
[data-testid="stMain"] { overflow: hidden !important; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stApp"], [data-baseweb="popover"] {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
  font-feature-settings: "tnum";
}
[data-testid="stElementContainer"] { margin: 0 !important; }

/* ---- the map is the page ------------------------------------------------- */
.st-key-mapwrap, .st-key-mapwrap [data-testid="stDeckGlJsonChart"],
.st-key-mapwrap [data-testid="stDeckGlJsonChart"] > div, .st-key-mapwrap #deckgl-wrapper {
  height: 100dvh !important; width: 100% !important;
}
.st-key-mapwrap [data-testid="stElementToolbar"] { display: none !important; }
/* the basemap's own +/- and its credit line are chrome from another app; pinch and scroll
   already zoom, and the dock carries the credits. */
.mapboxgl-ctrl-group, .maplibregl-ctrl-group,
.mapboxgl-ctrl-attrib, .maplibregl-ctrl-attrib { display: none !important; }

/* ---- the two floating panels ----------------------------------------------
   The top of the screen is the chart, and nothing else. Everything you can touch is in the
   dock at the bottom, where a thumb reaches, plus two round buttons on the right. */
.st-key-rail, .st-key-dock, .st-key-debug {
  position: fixed; z-index: 30; color: var(--ink);
}
.st-key-rail { right: 14px; bottom: 14px; width: 46px; pointer-events: none; }
.st-key-rail button { pointer-events: auto; }
.st-key-rail [data-testid="stVerticalBlock"] { gap: 9px !important; align-items: center; }

/* ---- the dock ------------------------------------------------------------- */
.st-key-dock {
  left: 14px; bottom: 14px; width: min(400px, calc(100vw - 28px));
  max-height: calc(100dvh - 120px); overflow-y: auto;
  background: var(--card); backdrop-filter: blur(16px) saturate(150%);
  border: 1px solid var(--edge); border-radius: 22px; box-shadow: var(--shadow);
  padding: 13px 15px 15px !important;
}
.st-key-dock, .st-key-dock * { min-width: 0; overflow-wrap: anywhere; }
.st-key-dock [data-testid="stVerticalBlock"] { gap: 0 !important; }
.st-key-finder [data-testid="stElementContainer"] + [data-testid="stElementContainer"] {
  margin-top: 9px !important;
}
.handle {
  width: 38px; height: 4px; border-radius: 999px; background: var(--edge);
  margin: 0 auto 10px; display: none;
}
.fineprint { font-size: 10px; line-height: 1.35; color: var(--muted); margin-top: 10px; }
.fineprint b { color: var(--muted); }

.sheet-kicker { font-size: 11px; font-weight: 700; letter-spacing: .09em;
  text-transform: uppercase; color: var(--accent); }
.sheet-title { font-size: 21px; font-weight: 700; line-height: 1.2; margin: 3px 0 10px;
  letter-spacing: -.01em; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chips:not(:empty) { margin-bottom: 12px; }
.chip { font-size: 12px; font-weight: 600; padding: 5px 10px; border-radius: 999px;
  background: var(--field); color: var(--ink); }
.sheet-row { display: flex; justify-content: space-between; gap: 14px; font-size: 13px;
  padding: 6px 0; border-top: 1px solid var(--edge); }
.sheet-row dt { color: var(--muted); }
.sheet-row dd { margin: 0; text-align: right; font-weight: 600; }
dl { margin: 0; }
.sheet-link { display: block; margin-top: 12px; padding: 9px; border-radius: 12px;
  background: var(--accent); color: var(--on-accent) !important; text-decoration: none;
  font-size: 13.5px; font-weight: 600; text-align: center; }
.empty { font-size: 13px; color: var(--muted); padding: 2px 0 4px; }
.note { font-size: 11px; line-height: 1.4; color: var(--muted); margin-top: 10px; }
.note b { color: var(--ink); }

/* ---- the search field ------------------------------------------------------
   Every colour is stated outright. The viewer can put Streamlit itself in dark mode from the
   app menu, and inheriting its palette would paint light-on-light text inside this field. */
.st-key-finder [data-testid="stSelectbox"] { position: relative; }
.st-key-finder [role="group"] {
  border-radius: 999px !important; border: 0 !important; min-height: 44px !important;
  background: var(--field) !important;
}
.st-key-finder input {
  padding: 0 16px 0 42px !important; font-size: 15px !important; height: 44px !important;
  color: var(--ink) !important; background: transparent !important; border: 0 !important;
}
.st-key-finder input::placeholder { color: var(--muted) !important; }
.st-key-finder [data-testid="stSelectbox"]::before {
  content: ""; position: absolute; left: 17px; top: 50%; width: 16px; height: 16px;
  transform: translateY(-50%); z-index: 2; pointer-events: none; background: var(--muted);
  -webkit-mask: var(--glass) center/contain no-repeat; mask: var(--glass) center/contain no-repeat;
}
/* it is a search box, not a dropdown: the caret invites a menu that is not there */
.st-key-finder button[aria-label="Open"] { display: none !important; }

[role="listbox"], .react-aria-Popover, [data-testid="stSelectboxVirtualDropdown"] {
  background: var(--menu) !important; color: var(--ink) !important;
  border: 1px solid var(--edge) !important; border-radius: 16px !important;
  box-shadow: var(--shadow) !important; padding: 6px !important;
}
[role="option"] { color: var(--ink) !important; font-size: 14px !important;
  border-radius: 10px !important; padding: 9px 12px !important; }
[role="option"]:hover, [role="option"][aria-selected="true"], [role="option"][data-focused] {
  background: var(--hover) !important; color: var(--ink) !important;
}

/* ---- the filter chips ------------------------------------------------------
   The chips are the legend. A chip that is on wears the colour of what it draws — darkened
   just enough to carry white text at 4.5:1 — and a chip that is off goes flat and grey, so
   the row states the palette without a legend box and without shouting over the map. */
.st-key-finder [role="toolbar"] { gap: 6px !important; flex-wrap: wrap; }
.st-key-finder button[data-variant="pills"] {
  border-radius: 999px !important; border: 0 !important; min-height: 0 !important;
  padding: 6px 11px !important; background: var(--field) !important;
  transition: background .15s;
}
.st-key-finder button[data-variant="pills"] p {
  color: var(--muted) !important; font-size: 12.5px !important; font-weight: 600 !important;
}
.st-key-finder button[aria-pressed="true"] p { color: #fff !important; }
.st-key-finder [role="toolbar"] button:nth-child(1)[aria-pressed="true"] {
  background: rgb(191,54,44) !important;
}
.st-key-finder [role="toolbar"] button:nth-child(2)[aria-pressed="true"] {
  background: rgb(23,102,168) !important;
}
.st-key-finder [role="toolbar"] button:nth-child(3)[aria-pressed="true"] {
  background: rgb(166,96,10) !important;
}
.st-key-finder [role="toolbar"] button:nth-child(4)[aria-pressed="true"] {
  background: rgb(17,122,101) !important;
}
/* the fifth chip filters rather than draws, so it wears no layer's colour */
.st-key-finder [role="toolbar"] button:nth-child(5)[aria-pressed="true"] {
  background: rgb(46,62,79) !important;
}

/* ---- the round map buttons ----------------------------------------------- */
.st-key-rail button {
  width: 46px !important; height: 46px !important; min-height: 46px !important;
  padding: 0 !important; border-radius: 50% !important; border: 0 !important;
  background: var(--card) !important; color: var(--ink) !important; box-shadow: var(--shadow);
  backdrop-filter: blur(16px) saturate(150%); font-size: 18px !important;
}
.st-key-rail button p { font-size: 18px !important; color: var(--ink) !important;
  line-height: 1 !important; }
.st-key-rail button:hover, .st-key-rail button:hover p { color: var(--accent) !important; }
.st-key-rail [data-testid="stTooltipHoverTarget"] { justify-content: center !important; }

.st-key-debug {
  left: 50%; top: 14px; transform: translateX(-50%); background: var(--card);
  border-radius: 14px; padding: 10px 14px !important; box-shadow: var(--shadow);
}

/* ---- phones: the dock is a sheet ----------------------------------------- */
@media (max-width: 700px) {
  .st-key-dock {
    left: 0; right: 0; bottom: 0; width: auto; max-height: 62dvh;
    border-radius: 22px 22px 0 0; border-bottom: 0;
    padding: 10px 16px calc(18px + env(safe-area-inset-bottom)) !important;
  }
  .st-key-finder [role="toolbar"] { flex-wrap: nowrap !important; overflow-x: auto;
    scrollbar-width: none; padding-bottom: 2px; }
  .st-key-finder button[data-variant="pills"] { flex: 0 0 auto; }
  /* clear of the dock, and of the notch */
  .st-key-rail { right: 12px; bottom: auto; top: calc(14px + env(safe-area-inset-top)); }
  .handle { display: block; }
}
"""
