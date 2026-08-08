"""The chrome: one dock at the bottom of the screen, and two round buttons.

The top of the screen is the chart. Everything you can touch is in the dock — where you are
going, what you are looking for, and, the moment you tap something, what it is. The chips
wear the colour of what they draw, so there is no legend.

Nothing on screen credits the sources: the safety notice and the licence line were removed on
request. The attribution ODbL and the Licence Ouverte ask for now lives only in the repository
— README and docs/04.
"""

from __future__ import annotations

import html

import pandas as pd
import pydeck as pdk
import streamlit as st

from app.data import (
    LAYERS,
    Dataset,
    Destination,
    Filters,
    label_for,
    light_of,
    search_index,
    services_of,
)

VISITOR = "visitor"

#: The three facts that go in the sheet's chip row, in order of preference.
CHIPS: tuple[tuple[str, str], ...] = (
    ("visitor_capacity", "{} places visiteurs"),
    ("vhf_channel", "VHF {}"),
    ("depth_m", "{} m de fond"),
    ("max_loa_m", "{} m max"),
    ("max_draft_m", "{} m de tirant d'eau"),
    ("colour", "{}"),
    ("light", "Feu {}"),
    ("holding", "Tenue : {}"),
)
DETAIL_ROWS: tuple[tuple[str, str], ...] = (
    ("category", "Catégorie"),
    ("shape", "Forme"),
    ("topmark", "Voyant"),
    ("light", "Feu"),
    ("depth_m", "Profondeur"),
    ("max_loa_m", "Longueur max"),
    ("max_draft_m", "Tirant d'eau max"),
    ("holding", "Tenue"),
    ("capacity", "Capacité"),
    ("operator", "Gestionnaire"),
    ("phone", "Téléphone"),
    ("opening_hours", "Horaires"),
    ("services", "Services"),
    ("price_note", "Tarifs"),
)


def _chip_label(key: str) -> str:
    """No icon: a chip that is on wears the colour of what it draws, which is the legend."""
    return "Visiteurs" if key == VISITOR else LAYERS[key].short


def dock(selected: pd.Series | None) -> tuple[Filters, Destination | None]:
    """The one panel, at the bottom of the screen where a thumb reaches.

    Nothing sits over the map: the top of the screen is the chart. The dock holds where you
    are going and what you are looking for — and the moment you tap something, its details
    take the dock's place until you tap the water again. The search and the chips are still
    rendered underneath, hidden by CSS rather than skipped, so Streamlit keeps their state.
    """
    with st.container(key="dock"):
        st.markdown('<div class="handle"></div>', unsafe_allow_html=True)
        if selected is not None:
            st.markdown(_detail(selected), unsafe_allow_html=True)
        with st.container(key="finder"):
            label = st.selectbox(
                "Recherche",
                options=list(search_index()),
                index=None,
                key="query",
                placeholder="Où allez-vous ?",
                label_visibility="collapsed",
            )
            chosen = st.pills(
                "Filtres",
                options=[*LAYERS, VISITOR],
                default=list(LAYERS),
                selection_mode="multi",
                format_func=_chip_label,
                key="filters",
                label_visibility="collapsed",
            )
    picked = tuple(chosen or ())
    destination = search_index().get(label) if label else None
    filters = Filters(
        layers=tuple(key for key in picked if key != VISITOR),
        visitor_only=VISITOR in picked,
    )
    return filters, destination


def rail(night: bool) -> str:
    """The three map buttons. Returns the action the sailor tapped."""
    with st.container(key="rail"):
        home = st.button("⌖", key="rail_home", help="Vue d'ensemble")
        dark = st.button("☀" if night else "☾", key="rail_night", help="Jour / nuit")
    return "home" if home else "night" if dark else ""


def _value(record: pd.Series, column: str) -> str:
    """What the column says, in words. Empty when the record does not carry it."""
    if column not in record.index:
        return ""
    raw = record[column]
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    if column == "light":
        return light_of(raw)  # Shom ships the whole S-57 light record; a chart shows one line
    if column == "services":
        return services_of(str(raw))
    if isinstance(raw, float) and raw.is_integer():
        return str(int(raw))  # 3.0 is a depth of three metres, not of "3.0"
    return str(raw).strip()


def _capitalised(text: str) -> str:
    """`str.capitalize` would lowercase the rest, and `Fl(2)R` is not `fl(2)r`."""
    return text[:1].upper() + text[1:]


def _heading(record: pd.Series) -> tuple[str, str, set[str]]:
    """Kicker, title, and the columns the title used up so the rows do not repeat them.

    A mark with no name is called what it is — "Tourelle bâbord" — never "Sans nom". (A
    missing name arrives as NaN, and NaN is a float: truthy, so `or` let it through and the
    card used to announce "nan".)
    """
    name = record["name"]
    if isinstance(name, str) and name:
        return label_for(record), name, set()
    spoken = " ".join(w for w in (_value(record, "shape"), _value(record, "category")) if w)
    if spoken:
        return "", _capitalised(spoken), {"shape", "category"}
    return "", _capitalised(label_for(record)), set()


def _detail(record: pd.Series) -> str:
    kicker, title, spent = _heading(record)
    values = {column: _value(record, column) for column, _ in (*CHIPS, *DETAIL_ROWS)}
    used = [column for column, _ in CHIPS if values[column] and column not in spent][:3]
    chips = "".join(
        f'<span class="chip">{html.escape(_capitalised(template.format(values[column])))}</span>'
        for column, template in CHIPS
        if column in used
    )
    rows = "".join(
        f'<div class="sheet-row"><dt>{label}</dt><dd>{html.escape(values[column])}</dd></div>'
        for column, label in DETAIL_ROWS
        if column not in used and column not in spent and values[column]
    )
    website = record.get("website")
    link = (
        f'<a class="sheet-link" href="{html.escape(str(website))}" target="_blank">Site du port</a>'
        if isinstance(website, str) and website.startswith("http")
        else ""
    )
    # Most harbours carry nothing but a name: say so, rather than showing an empty card.
    empty = '<div class="empty">Aucun détail publié pour ce point.</div>' if not rows else ""
    # The position is the one thing every sailor copies out; which of our tables the row came
    # from is our business, not theirs.
    position = (
        f'<div class="sheet-row"><dt>Position</dt>'
        f"<dd>{record['lat']:.4f}, {record['lon']:.4f}</dd></div>"
    )
    return (
        (f'<div class="sheet-kicker">{html.escape(kicker)}</div>' if kicker else "")
        + f'<div class="sheet-title">{html.escape(title)}</div>'
        + f'<div class="chips">{chips}</div>'
        + f"{empty}<dl>{rows}{position}</dl>{link}"
    )


def diagnostics(dataset: Dataset) -> None:
    """`?debug=1` — what the host is actually doing, for when the app misbehaves remotely."""
    if not st.query_params.get("debug"):
        return
    rows = {
        "streamlit": st.__version__,
        "pydeck": pdk.__version__,
        "pandas": pd.__version__,
        "config.toml lu": st.get_option("theme.primaryColor") == "#0f6fb8",
        "thème visiteur": getattr(getattr(st.context, "theme", None), "type", "?"),
        "objets": dataset.total,
    }
    with st.container(key="debug"):
        st.markdown(
            '<div class="note"><b>Diagnostic</b></div>'
            + "".join(f'<div class="note">{k} : <b>{v}</b></div>' for k, v in rows.items()),
            unsafe_allow_html=True,
        )
