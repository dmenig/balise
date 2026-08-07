"""The floating chrome: search bar, detail sheet, legend, disclaimer."""

from __future__ import annotations

import html

import pandas as pd
import pydeck as pdk
import streamlit as st

from app.data import LAYERS, Dataset, Destination, Filters, label_for, search_index

DISCLAIMER = (
    "<b>Ne pas utiliser pour la navigation.</b> Référentiel indicatif : les cartes officielles "
    "à jour restent obligatoires, et la disponibilité d'une place n'est pas connue."
)
ATTRIBUTION = (
    "Fond de carte © OpenStreetMap / CARTO · Balisage et ports : Shom (Licence Ouverte 2.0) · "
    "Mouillages : OpenStreetMap / OpenSeaMap (ODbL 1.0)"
)

DETAIL_ROWS: tuple[tuple[str, str], ...] = (
    ("category", "Catégorie"),
    ("colour", "Couleur"),
    ("shape", "Forme"),
    ("topmark", "Voyant"),
    ("light", "Feu"),
    ("depth_m", "Profondeur"),
    ("max_loa_m", "Longueur max"),
    ("max_draft_m", "Tirant d'eau max"),
    ("holding", "Tenue"),
    ("capacity", "Capacité"),
    ("visitor_capacity", "Places visiteurs"),
    ("operator", "Gestionnaire"),
    ("vhf_channel", "VHF"),
    ("phone", "Téléphone"),
    ("opening_hours", "Horaires"),
    ("services", "Services"),
    ("price_note", "Tarifs"),
)


def topbar() -> tuple[Filters, Destination | None]:
    """Returns the destination the moment a suggestion is chosen — no Enter needed.

    The field stays folded away behind its icon: the map is the app, and a search box you are
    not using is just chrome over the chart.
    """
    with st.container(key="topbar"):
        open_search = bool(st.session_state.get("search_open", False))
        if st.button("✕  Recherche" if open_search else "🔍  Rechercher", key="search_toggle"):
            open_search = not open_search
            st.session_state["search_open"] = open_search
        label = None
        if open_search:
            label = st.selectbox(
                "Recherche",
                options=list(search_index()),
                index=None,
                key="query",
                placeholder="Un port, une ville, une île…",
                label_visibility="collapsed",
            )
        chosen = st.pills(
            "Couches",
            options=list(LAYERS),
            default=list(LAYERS),
            selection_mode="multi",
            format_func=lambda key: LAYERS[key].short,
            key="layers",
            label_visibility="collapsed",
        )
        visitor = st.checkbox("Places visiteurs uniquement", key="visitor")
    destination = search_index().get(label) if label else None
    return Filters(layers=tuple(chosen or LAYERS), visitor_only=visitor), destination


def _title(record: pd.Series) -> str:
    """A missing name arrives as NaN, and NaN is a float — truthy, so `or` let it through
    and the sheet announced "nan"."""
    name = record["name"]
    return str(name) if isinstance(name, str) and name else "Sans nom"


def _row(label: str, value: object) -> str:
    return f'<div class="sheet-row"><dt>{label}</dt><dd>{html.escape(str(value))}</dd></div>'


def _detail(record: pd.Series) -> str:
    rows = "".join(
        _row(label, record[column])
        for column, label in DETAIL_ROWS
        if column in record.index and pd.notna(record[column]) and record[column] != ""
    )
    website = record.get("website")
    link = (
        f'<div class="sheet-row"><dt>Site</dt><dd>'
        f'<a href="{html.escape(str(website))}" target="_blank">ouvrir</a></dd></div>'
        if isinstance(website, str) and website.startswith("http")
        else ""
    )
    return (
        f'<div class="sheet-kicker">{html.escape(label_for(record))}</div>'
        f'<div class="sheet-title">{html.escape(_title(record))}</div>'
        f"<dl>{rows}{link}</dl>"
        f'<div class="note" style="margin-top:8px">{record["lat"]:.5f}, {record["lon"]:.5f}'
        f" · source {html.escape(str(record['source_id']))}</div>"
    )


def _summary(shown: int, total: int) -> str:
    return (
        f'<div class="count"><b>{shown:,}</b> objets affichés sur {total:,} '
        "recensés en Bretagne</div>".replace(",", " ")
    )


def sheet(dataset: Dataset, selected: pd.Series | None, shown: int) -> bool:
    """The bottom sheet. Returns True when the sailor closes the open detail."""
    closed = False
    with st.container(key="sheet"):
        if selected is not None:
            st.markdown(_detail(selected), unsafe_allow_html=True)
            closed = st.button("Fermer", key="close")
        else:
            st.markdown(_summary(shown, dataset.total), unsafe_allow_html=True)
            st.markdown(
                '<div class="note" style="margin-top:6px">Touchez un objet pour ses détails.</div>',
                unsafe_allow_html=True,
            )
    return closed


def legend() -> None:
    with st.container(key="legend"):
        lines = "".join(
            f'<div class="legend-line"><span class="dot" style="background:rgb'
            f'{layer.colour}"></span>{html.escape(layer.short)}</div>'
            for layer in LAYERS.values()
        )
        st.markdown(lines, unsafe_allow_html=True)
        st.checkbox("Mode nuit", key="night")
        # The licences and the safety notice have to stay reachable — ODbL says so — but they
        # do not have to sit on the chart. One tap, the way a transit app hides its legal text.
        with st.popover("ⓘ  À propos", use_container_width=True):
            st.markdown(
                f'<div class="note">{DISCLAIMER}</div>'
                f'<div class="note" style="margin-top:8px">{ATTRIBUTION}</div>',
                unsafe_allow_html=True,
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
