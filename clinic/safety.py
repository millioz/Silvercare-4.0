"""Red-flag phrase scanner. This is a SAFETY NET only: it never diagnoses, it just makes sure
words that may describe an emergency are shown to staff immediately and the patient is told to
contact emergency services."""
import re

_PATTERNS = [
    r"chest (pain|tightness|pressure)", r"(can['’]?t|cannot|can not|unable to) breathe",
    r"(trouble|difficulty|hard to) breath", r"short(ness)? of breath",
    r"swelling (of|in|around) (the )?(face|lips|tongue|throat)", r"fainted|passed out|unconscious|blacked out",
    r"seizure", r"severe bleeding|vomit(ing)? blood|coughing (up )?blood",
    r"overdos|took too many|double dose|took two (doses|pills) by mistake",
    r"suicid|kill myself|want to die|end my life", r"face droop|slurred speech|sudden weakness",
    r"anaphyla|allergic reaction",
    r"가슴\s*(통증|이 아파)", r"호흡\s*곤란|숨이\s*(차|안\s*쉬)", r"자살|죽고\s*싶", r"의식을?\s*잃",
]
_RX = [re.compile(p, re.I) for p in _PATTERNS]


def red_flags(text):
    found = []
    for rx in _RX:
        m = rx.search(text or "")
        if m:
            found.append(m.group(0))
    return found


def urgent_text(number):
    return (f"If this may be an emergency, call {number} now or ask someone nearby to help. "
            "Your care team has been alerted. You do not have to handle this alone.")
