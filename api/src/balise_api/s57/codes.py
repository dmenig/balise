"""S-57 code lists → French plain language.

An unknown code raises (docs/10): rendering an unlabelled mark is worse than failing the job.
"""

from __future__ import annotations


class UnknownS57Code(ValueError):
    def __init__(self, attribute: str, code: str) -> None:
        super().__init__(f"unknown S-57 code {code!r} for attribute {attribute!r}")
        self.attribute = attribute
        self.code = code


CLASS_LABELS: dict[str, str] = {
    "bcnlat": "Balise latérale",
    "bcncar": "Balise cardinale",
    "bcnisd": "Balise de danger isolé",
    "bcnsaw": "Balise d'eaux saines",
    "bcnspp": "Balise spéciale",
    "boylat": "Bouée latérale",
    "boycar": "Bouée cardinale",
    "boyisd": "Bouée de danger isolé",
    "boysaw": "Bouée d'eaux saines",
    "boyspp": "Bouée spéciale",
    "boyinb": "Bouée d'installation",
    "lndmrk": "Amer",
    "lights": "Feu",
    "morfac": "Installation d'amarrage",
    "pilpnt": "Point de pilotage",
    "daymar": "Marque de jour",
    "topmar": "Voyant",
    "fogsig": "Signal de brume",
    "silktk": "Silo ou réservoir",
    "sistat": "Station de signaux de trafic",
    "sistaw": "Station de signaux d'avertissement",
    "rtpbcn": "Balise radar répondeuse",
    "radsta": "Station radar",
    "rdosta": "Station radio",
    "aisatn": "Aide à la navigation AIS",
    "forstc": "Ouvrage fortifié",
    "pylons": "Pylône",
    "ofsplf": "Plateforme au large",
    "vegatn": "Végétation",
    "newobj": "Objet non classé",
    "achare": "Zone de mouillage",
    "hrbfac": "Installation portuaire",
    "berths": "Poste d'amarrage",
    "smcfac": "Services pour la plaisance",
}

_COLOUR = {
    1: "blanc",
    2: "noir",
    3: "rouge",
    4: "vert",
    5: "bleu",
    6: "jaune",
    7: "gris",
    8: "brun",
    9: "ambre",
    10: "violet",
    11: "orange",
    12: "magenta",
    13: "rose",
}

_COLPAT = {
    1: "bandes horizontales",
    2: "bandes verticales",
    3: "bandes diagonales",
    4: "damier",
    5: "bandes",
    6: "liseré",
}

_BOYSHP = {
    1: "conique",
    2: "cylindrique",
    3: "sphérique",
    4: "à fuseau (pilier)",
    5: "espar",
    6: "tonne",
    7: "super-bouée",
    8: "bouée de glace",
}

_BCNSHP = {
    1: "perche",
    2: "balise en fascines",
    3: "tourelle",
    4: "balise en treillis",
    5: "balise sur pieux",
    6: "cairn",
    7: "balise flottante",
}

_CATLAM = {
    1: "bâbord",
    2: "tribord",
    3: "chenal préféré à tribord",
    4: "chenal préféré à bâbord",
}

_CATCAM = {1: "nord", 2: "est", 3: "sud", 4: "ouest"}

_CATSPM = {
    1: "zone de tir",
    2: "cible",
    3: "navire cible",
    4: "champ de démagnétisation",
    5: "barge",
    6: "câble",
    7: "zone de dépôt",
    8: "émissaire",
    9: "bouée océanographique (ODAS)",
    10: "enregistrement",
    11: "mouillage d'hydravions",
    12: "zone de loisirs",
    13: "privée",
    14: "amarrage",
    15: "LANBY",
    16: "alignement",
    17: "base de mesure",
    18: "avis",
    19: "dispositif de séparation du trafic",
    20: "mouillage interdit",
    21: "accostage interdit",
    22: "dépassement interdit",
    23: "trafic bidirectionnel interdit",
    24: "vitesse réduite (pas de vagues)",
    25: "limitation de vitesse",
    26: "arrêt obligatoire",
    27: "avertissement général",
    28: "signal sonore obligatoire",
    29: "tirant d'air limité",
    30: "tirant d'eau maximal",
    31: "largeur limitée",
    32: "courant fort",
    33: "accostage autorisé",
    34: "ligne électrique aérienne",
    35: "bord de chenal",
    36: "téléphone",
    37: "passage de bac",
    38: "pipeline",
    39: "mouillage",
    40: "zone de dégagement",
    41: "contrôle",
    42: "plongée",
    43: "balise refuge",
    44: "fonds malsains",
    45: "zone de yachting",
    46: "héliport",
    47: "GPS",
    48: "zone d'atterrissage d'hydravions",
    49: "entrée interdite",
    50: "travaux en cours",
    51: "objet de destination inconnue",
    52: "tête de puits",
    53: "séparation de chenal",
    54: "ferme marine",
    55: "récif artificiel",
}

_TOPSHP = {
    1: "cône pointe en haut",
    2: "cône pointe en bas",
    3: "sphère",
    4: "deux sphères",
    5: "cylindre",
    6: "panneau",
    7: "croix de Saint-André",
    8: "croix droite",
    9: "cube pointe en haut",
    10: "deux cônes pointes opposées",
    11: "deux cônes bases opposées",
    12: "losange",
    13: "deux cônes pointes en haut",
    14: "deux cônes pointes en bas",
    15: "balai pointe en haut",
    16: "balai pointe en bas",
    17: "pavillon",
    18: "sphère au-dessus d'un losange",
    19: "carré",
    20: "rectangle horizontal",
    21: "rectangle vertical",
    22: "trapèze grande base en bas",
    23: "trapèze grande base en haut",
    24: "triangle pointe en haut",
    25: "triangle pointe en bas",
    26: "cercle",
    27: "deux croix droites",
    28: "T",
    29: "triangle pointe en haut sur cercle",
    30: "croix droite sur cercle",
    31: "losange sur cercle",
    32: "cercle sur triangle pointe en haut",
    33: "autre forme",
}

_LITCHR = {
    1: ("fixe", "F"),
    2: ("à éclats", "Fl"),
    3: ("à long éclat", "LFl"),
    4: ("scintillant", "Q"),
    5: ("scintillant rapide", "VQ"),
    6: ("scintillant ultra-rapide", "UQ"),
    7: ("isophase", "Iso"),
    8: ("à occultations", "Oc"),
    9: ("scintillant discontinu", "IQ"),
    10: ("scintillant rapide discontinu", "IVQ"),
    11: ("scintillant ultra-rapide discontinu", "IUQ"),
    12: ("morse", "Mo"),
    13: ("fixe et éclats", "FFl"),
    14: ("éclat et long éclat", "FlLFl"),
    15: ("occultations et éclat", "OcFl"),
    16: ("fixe et long éclat", "FLFl"),
    17: ("occultations alternées", "Al.Oc"),
    18: ("longs éclats alternés", "Al.LFl"),
    19: ("éclats alternés", "Al.Fl"),
    20: ("groupes alternés", "Al.Gr"),
    21: ("deux feux fixes verticaux", "2F"),
    22: ("deux feux fixes horizontaux", "2F"),
    25: ("scintillant et long éclat", "Q+LFl"),
    26: ("scintillant rapide et long éclat", "VQ+LFl"),
    27: ("scintillant ultra-rapide et long éclat", "UQ+LFl"),
    28: ("alternatif", "Al"),
    29: ("fixe et éclats alternés", "Al.FFl"),
}

_CATMOR = {
    1: "duc-d'Albe",
    2: "duc-d'Albe de déviation",
    3: "bollard",
    4: "quai d'amarrage",
    5: "pieu",
    6: "chaîne ou câble d'amarrage",
    7: "bouée de mouillage",
}

_CATACH = {
    1: "mouillage libre",
    2: "mouillage grande profondeur",
    3: "mouillage pétrolier",
    4: "mouillage explosifs",
    5: "mouillage de quarantaine",
    6: "mouillage d'hydravions",
    7: "mouillage plaisance",
    8: "corps-morts plaisance",
    9: "mouillage 24 h",
    10: "mouillage à durée limitée",
    11: "mouillage réservé",
    12: "mouillage d'attente",
}

_CATLMK = {
    1: "cairn",
    2: "cimetière",
    3: "cheminée",
    4: "antenne parabolique",
    5: "mât de pavillon",
    6: "torchère",
    7: "mât",
    8: "manche à air",
    9: "monument",
    10: "colonne",
    11: "plaque commémorative",
    12: "obélisque",
    13: "statue",
    14: "croix",
    15: "dôme",
    16: "radar",
    17: "tour",
    18: "moulin à vent",
    19: "éolienne",
    20: "clocher ou minaret",
    21: "gros rocher à terre",
}

_CATHAF = {
    1: "terminal roulier",
    2: "parc à bois",
    3: "gare maritime (bac)",
    4: "port de pêche",
    5: "port de plaisance",
    6: "base navale",
    7: "terminal pétrolier",
    8: "terminal passagers",
    9: "chantier naval",
    10: "terminal à conteneurs",
    11: "terminal vraquier",
    12: "syncrolift",
    13: "portique cavalier",
    14: "port de plaisance sans services",
}

_RESTRN = {
    1: "mouillage interdit",
    2: "mouillage réglementé",
    3: "pêche interdite",
    4: "pêche réglementée",
    5: "chalutage interdit",
    6: "chalutage réglementé",
    7: "entrée interdite",
    8: "entrée réglementée",
    9: "dragage interdit",
    10: "dragage réglementé",
    11: "plongée interdite",
    12: "plongée réglementée",
    13: "pas de vagues",
    14: "zone à éviter",
    15: "construction interdite",
    16: "rejets interdits",
    17: "rejets réglementés",
    18: "rejets industriels interdits",
    19: "rejets industriels réglementés",
    20: "transbordement de cargaison interdit",
    21: "transbordement de cargaison réglementé",
    22: "dragage de fond interdit",
    23: "dragage de fond réglementé",
    24: "arrêt interdit",
    25: "arrêt réglementé",
    26: "débarquement interdit",
    27: "débarquement réglementé",
}

_CONVIS = {1: "remarquable", 2: "non remarquable"}

CODE_LISTS: dict[str, dict[int, str]] = {
    "colour": _COLOUR,
    "colpat": _COLPAT,
    "boyshp": _BOYSHP,
    "bcnshp": _BCNSHP,
    "catlam": _CATLAM,
    "catcam": _CATCAM,
    "catspm": _CATSPM,
    "topshp": _TOPSHP,
    "catmor": _CATMOR,
    "catach": _CATACH,
    "catlmk": _CATLMK,
    "cathaf": _CATHAF,
    "restrn": _RESTRN,
    "convis": _CONVIS,
    "litchr": {code: label for code, (label, _) in _LITCHR.items()},
}

LIGHT_ABBREVIATIONS: dict[int, str] = {code: abbr for code, (_, abbr) in _LITCHR.items()}


def is_known_class(s57_class: str) -> bool:
    return s57_class in CLASS_LABELS


def decode(attribute: str, code: str | int | None) -> str | None:
    """Decode one S-57 code. `None`/empty in, `None` out; unknown code raises."""
    if code is None or code == "":
        return None
    table = CODE_LISTS.get(attribute)
    if table is None:
        raise UnknownS57Code(attribute, str(code))
    try:
        numeric = int(str(code).strip())
    except ValueError as exc:
        raise UnknownS57Code(attribute, str(code)) from exc
    if numeric not in table:
        raise UnknownS57Code(attribute, str(code))
    return table[numeric]


def decode_many(attribute: str, raw: str | int | None) -> list[str]:
    """SHOM packs multi-valued attributes as `"2,1"`."""
    if raw is None or raw == "":
        return []
    parts = [part for part in str(raw).replace(";", ",").split(",") if part.strip()]
    return [label for part in parts if (label := decode(attribute, part)) is not None]
