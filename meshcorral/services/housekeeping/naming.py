"""Conservative token/suffix rules, not substring matching."""
import re
_SUFFIX = re.compile(r"(?:[ _-]+(?:copy|backup|old|temp|tmp|new)(?:[ _-]*[0-9]+)?|[ ]*\([0-9]+\)|[ _-]+v[0-9]+)$", re.I)
_FINAL = re.compile(r"(?:^|[ _-])final[0-9]*[ _-]+final[0-9]*(?:$|[ _-])", re.I)

def normalized_stem(stem):
    value = stem.casefold().strip()
    for _ in range(8):
        reduced = _SUFFIX.sub("", value).strip(" _-")
        if reduced == value or not reduced:
            break
        value = reduced
    return value

def naming_issue(stem):
    if _FINAL.search(stem):
        return "Repeated final/version marker"
    match = _SUFFIX.search(stem)
    if match and not re.fullmatch(r"[ _-]+v[0-9]+", match.group(), re.I):
        return "Copy, revision, or temporary suffix: " + match.group().strip()
    if stem.casefold() in {"copy", "backup", "old", "temp", "tmp"}:
        return "Generic temporary name"
    return None
