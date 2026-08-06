"""S-57 decoding and the French plain-language layer (docs/01, docs/08, docs/10)."""

from __future__ import annotations

import pytest
from balise_api.s57 import CLASS_LABELS, UnknownS57Code, decode, decode_many, navaid_label
from balise_api.s57.labels import describe_light


def test_a_lateral_buoy_reads_like_a_chart() -> None:
    assert navaid_label("boylat", decode("catlam", 1)) == "Bouée latérale bâbord"
    assert navaid_label("boylat", decode("catlam", 2)) == "Bouée latérale tribord"
    assert navaid_label("bcncar", decode("catcam", 3)) == "Balise cardinale sud"


def test_multi_valued_colours_are_split_the_shom_way() -> None:
    assert decode_many("colour", "2,1") == ["noir", "blanc"]
    assert decode_many("colour", None) == []
    assert decode_many("colour", 3) == ["rouge"]


def test_catspm_keeps_the_unassigned_38_hole() -> None:
    # S-57 Appendix A assigns no 38. Closing the hole shifts every later code by one and
    # relabels real Bretagne marks, so these four anchors pin the numbering down.
    assert decode("catspm", 37) == "passage de bac"
    assert decode("catspm", 50) == "entrée interdite"
    assert decode("catspm", 55) == "ferme marine"
    assert decode("catspm", 56) == "récif artificiel"
    with pytest.raises(UnknownS57Code):
        decode("catspm", 38)


def test_list_typed_categories_decode_every_value() -> None:
    # SHOM publishes `catspm="16,50"` on real special-purpose marks.
    assert decode_many("catspm", "16,50") == ["alignement", "entrée interdite"]
    assert decode_many("cathaf", "5,4") == ["port de plaisance", "port de pêche"]


def test_an_unknown_code_raises_instead_of_rendering_an_unlabelled_mark() -> None:
    with pytest.raises(UnknownS57Code):
        decode("catlam", 99)
    with pytest.raises(UnknownS57Code):
        decode("nosuchattribute", 1)


def test_empty_values_decode_to_nothing() -> None:
    assert decode("catlam", None) is None
    assert decode("catlam", "") is None


def test_a_real_shom_light_becomes_a_readable_signature() -> None:
    # Verbatim properties from BALISAGE_BDD_WFS:lights (2026-08-06).
    described = describe_light(
        {"litchr": 2, "colour": "6", "siggrp": "(5)", "sigper": 20, "valnmr": 1, "sectr1": None}
    )
    assert described is not None
    assert described.text == "Fl(5) J 20s 1M"
    assert described.character == "à éclats"
    assert (described.period_s, described.range_nm, described.colour) == (20.0, 1.0, "jaune")
    assert described.sectors is False


def test_a_mark_without_a_light_has_none() -> None:
    assert describe_light(None) is None
    assert describe_light({}) is None


def test_every_ingested_class_has_a_french_label() -> None:
    from balise_ingest.normalisers.shom import NAV_AID_LAYERS

    assert all(layer in CLASS_LABELS for layer in NAV_AID_LAYERS)
    assert CLASS_LABELS["morfac"] == "Installation d'amarrage"
