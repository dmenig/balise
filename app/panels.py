"""The floating chrome: search bar, detail sheet, legend, disclaimer."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app.data import LAYERS, Dataset, Filters, label_for, search

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


def topbar() -> Filters:
    with st.container(key="topbar"):
        st.text_input(
            "Recherche",
            key="query",
            placeholder="Rechercher un port, un mouillage, une balise…",
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
    return Filters(layers=tuple(chosen or LAYERS), visitor_only=visitor)


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
        f'<div class="sheet-title">{html.escape(str(record["name"] or "Sans nom"))}</div>'
        f"<dl>{rows}{link}</dl>"
        f'<div class="note" style="margin-top:8px">{record["lat"]:.5f}, {record["lon"]:.5f}'
        f" · source {html.escape(str(record['source_id']))}</div>"
    )


def _summary(shown: int, total: int) -> str:
    return (
        f'<div class="count"><b>{shown:,}</b> objets affichés sur {total:,} '
        "recensés en Bretagne</div>".replace(",", " ")
    )


def sheet(dataset: Dataset, selected: pd.Series | None, shown: int) -> str | None:
    """The bottom sheet. Returns a uid when the sailor picks a search result."""
    picked: str | None = None
    with st.container(key="sheet"):
        if selected is not None:
            st.markdown(_detail(selected), unsafe_allow_html=True)
            if st.button("Fermer", key="close"):
                picked = ""
        else:
            st.markdown(_summary(shown, dataset.total), unsafe_allow_html=True)
            picked = _results(dataset)
        # On a phone the top-right panel is folded away, so the disclaimer rides in the sheet.
        st.markdown(
            f'<div class="note mobile-only" style="margin-top:8px">{DISCLAIMER}</div>',
            unsafe_allow_html=True,
        )
    return picked


def _results(dataset: Dataset) -> str | None:
    query = str(st.session_state.get("query", ""))
    hits = search(dataset, query)
    if not query.strip():
        st.markdown(
            '<div class="note" style="margin-top:6px">Touchez un objet sur la carte pour ses '
            "détails, ou cherchez un port ci-dessus.</div>",
            unsafe_allow_html=True,
        )
        return None
    if hits.empty:
        st.markdown('<div class="note">Aucun résultat.</div>', unsafe_allow_html=True)
        return None
    for _, row in hits.iterrows():
        if st.button(f"{row['name']} — {label_for(row)}", key=f"hit-{row['uid']}"):
            return str(row["uid"])
    return None


def legend() -> bool:
    """Returns True when the sailor asks to go back to the whole-Bretagne view."""
    with st.container(key="legend"):
        lines = "".join(
            f'<div class="legend-line"><span class="dot" style="background:rgb'
            f'{layer.colour}"></span>{html.escape(layer.short)}</div>'
            for layer in LAYERS.values()
        )
        st.markdown(lines, unsafe_allow_html=True)
        home = st.button("Vue d'ensemble", key="home")
        st.checkbox("Mode nuit", key="night")
    return home


def footnote() -> None:
    with st.container(key="footnote"):
        st.markdown(
            f'<div class="note">{DISCLAIMER}</div>'
            f'<div class="note" style="margin-top:6px;font-size:10px">{ATTRIBUTION}</div>',
            unsafe_allow_html=True,
        )
