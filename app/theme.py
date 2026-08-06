"""The CSS that turns a Streamlit page into a map application.

Streamlit stacks blocks in a padded document column. Three things undo that: the chrome is
hidden, the block container loses its padding and max-width, and every panel is a keyed
container (`st.container(key=…)` renders as `.st-key-<key>`) pinned over the map with
`position: fixed`. Panels are `pointer-events: none` so the map keeps the drag; their cards
switch them back on.
"""

from __future__ import annotations

LIGHT = {
    "ink": "#0a1d2e",
    "muted": "#5d6f80",
    "card": "rgba(255,255,255,0.93)",
    "edge": "rgba(10,29,46,0.10)",
    "accent": "#0f6fb8",
    "shadow": "0 8px 28px rgba(10,29,46,0.16)",
    "field": "rgba(255,255,255,0.72)",
}
DARK = {
    "ink": "#e8f0f7",
    "muted": "#9fb2c4",
    "card": "rgba(13,27,42,0.90)",
    "edge": "rgba(255,255,255,0.14)",
    "accent": "#5cc0ff",
    "shadow": "0 8px 28px rgba(0,0,0,0.45)",
    "field": "rgba(255,255,255,0.08)",
}


def css(night: bool) -> str:
    token = DARK if night else LIGHT
    variables = "".join(f"--{name}:{value};" for name, value in token.items())
    return f"<style>:root{{{variables}}}{_SHEET}</style>"


_SHEET = """
/* ---- full-bleed shell ---------------------------------------------------- */
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], footer { display: none !important; }
html, body, [data-testid="stAppViewContainer"] { height: 100%; overflow: hidden; }
[data-testid="stMainBlockContainer"] {
  padding: 0 !important; max-width: 100% !important;
}
[data-testid="stMain"] { overflow: hidden !important; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stApp"] { font-feature-settings: "tnum"; }

/* ---- the map is the page ------------------------------------------------- */
.st-key-mapwrap, .st-key-mapwrap [data-testid="stDeckGlJsonChart"],
.st-key-mapwrap [data-testid="stDeckGlJsonChart"] > div, .st-key-mapwrap #deckgl-wrapper {
  height: 100dvh !important; width: 100% !important;
}
.st-key-mapwrap [data-testid="stElementToolbar"] { display: none !important; }

/* ---- floating panels ------------------------------------------------------
   Each panel IS its keyed container: Streamlit closes an injected <div> at the end of the
   markdown block that opened it, so a wrapper element can never contain the widgets. */
.st-key-topbar, .st-key-sheet, .st-key-legend, .st-key-footnote {
  position: fixed; z-index: 30; color: var(--ink);
  background: var(--card); backdrop-filter: blur(14px) saturate(140%);
  border: 1px solid var(--edge); border-radius: 16px; box-shadow: var(--shadow);
  padding: 11px 13px !important;
}
.st-key-topbar { top: 12px; left: 12px; width: min(390px, calc(100vw - 24px)); }
.st-key-sheet {
  left: 12px; bottom: 12px; width: min(390px, calc(100vw - 24px));
  max-height: calc(100dvh - 230px); overflow-y: auto; padding-bottom: 14px !important;
}
.st-key-legend { right: 12px; bottom: 12px; width: max-content; }
.st-key-footnote { right: 12px; top: 12px; width: min(290px, 44vw); }

.st-key-topbar [data-testid="stVerticalBlock"], .st-key-sheet [data-testid="stVerticalBlock"],
.st-key-legend [data-testid="stVerticalBlock"] { gap: .4rem !important; }
.st-key-legend [data-testid="stElementContainer"] { width: max-content !important; }
/* the sheet scrolls vertically, which would otherwise let a long line scroll sideways too */
.st-key-sheet, .st-key-sheet * { min-width: 0; overflow-wrap: anywhere; }

/* ---- phones: one column, no panel may cover another ----------------------- */
.mobile-only { display: none; }
@media (max-width: 700px) {
  .st-key-topbar { top: 8px; left: 8px; right: 8px; width: auto; }
  .st-key-sheet {
    left: 8px; right: 8px; bottom: 8px; width: auto; max-height: 40dvh;
  }
  .st-key-legend {
    right: 8px; bottom: auto; top: 50%; transform: translateY(-50%); padding: 8px !important;
  }
  .st-key-footnote { display: none; }
  .mobile-only { display: block; }
}

/* ---- the sheet ----------------------------------------------------------- */
.sheet-kicker {
  font-size: 11px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
  color: var(--accent);
}
.sheet-title { font-size: 19px; font-weight: 700; line-height: 1.2; margin: 2px 0 8px; }
.sheet-row { display: flex; justify-content: space-between; gap: 14px; font-size: 13px;
  padding: 3px 0; border-top: 1px solid var(--edge); }
.sheet-row:first-of-type { border-top: 0; }
.sheet-row dt { color: var(--muted); }
.sheet-row dd { margin: 0; text-align: right; font-weight: 600; }
.chips { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }
.chip { font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
  background: var(--field); border: 1px solid var(--edge); color: var(--ink); }
.count { font-size: 12px; color: var(--muted); }
.count b { color: var(--ink); font-size: 15px; }

/* ---- legend -------------------------------------------------------------- */
.legend-line { display: flex; align-items: center; gap: 8px; font-size: 12px;
  color: var(--ink); padding: 2px 0; }
.dot { width: 10px; height: 10px; border-radius: 50%; box-shadow: 0 0 0 1px var(--edge); }
.note { font-size: 11px; line-height: 1.35; color: var(--muted); }
.note b { color: var(--ink); }

/* ---- widgets ------------------------------------------------------------- */
[data-testid="stTextInput"] input {
  border-radius: 999px !important; border: 1px solid var(--edge) !important;
  background: var(--field) !important; color: var(--ink) !important;
  padding: 8px 14px !important; font-size: 14px !important;
}
[data-testid="stTextInput"] div[data-baseweb="input"] { border: 0 !important; background: none; }
[data-testid="stButton"] button, [data-testid="stBaseButton-secondary"] {
  border-radius: 10px !important; border: 1px solid var(--edge) !important;
  background: var(--field) !important; color: var(--ink) !important;
  font-size: 13px !important; font-weight: 600 !important; padding: 4px 10px !important;
  min-height: 0 !important; width: 100%;
}
[data-testid="stButton"] button:hover { border-color: var(--accent) !important;
  color: var(--accent) !important; }
[data-baseweb="tag"] { border-radius: 999px !important; }
.stCheckbox, .stCheckbox p { font-size: 12.5px !important; color: var(--ink) !important; }
[data-testid="stElementContainer"] { margin: 0 !important; }
"""
