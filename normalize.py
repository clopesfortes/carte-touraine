"""Transforme un événement DATAtourisme brut en fiche simple pour la carte."""
import re
from datetime import date


def as_list(value):
    if isinstance(value, list):
        return value
    return [value] if isinstance(value, dict) else []


def text(value):
    """Texte français d'un champ multilingue (chaîne, liste ou dict @fr/fr)."""
    if isinstance(value, dict):
        for key in ("@fr", "fr", "@en", "en"):
            if value.get(key):
                return text(value[key])
        return ""
    if isinstance(value, list):
        return next((t for t in (text(v) for v in value) if t), "")
    return value.strip() if isinstance(value, str) else ""


def parse_day(value):
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (ValueError, TypeError):
        return None


def clean_html(value):
    return " ".join(re.sub(r"<[^>]+>", " ", value or "").split())


def http_url(value):
    value = text(value)
    return value if value.startswith(("http://", "https://")) else ""


def normalize(raw, today=None):
    """Retourne (fiche, None) ou (None, motif_de_rejet)."""
    today = today or date.today()

    title = text(raw.get("label"))
    if not title:
        return None, "sans_titre"

    place = (as_list(raw.get("isLocatedAt")) or [{}])[0]
    address = (as_list(place.get("address")) or [{}])[0]
    city = address.get("hasAddressCity")
    locality = text(address.get("addressLocality")) or text(
        city.get("label") if isinstance(city, dict) else city
    )

    geo = place.get("geo") or place.get("geoPoint") or {}
    try:
        lat = float(geo.get("latitude", geo.get("lat")))
        lon = float(geo.get("longitude", geo.get("lon")))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
    except (TypeError, ValueError):
        return None, "sans_position"

    dates = []
    for slot in as_list(raw.get("takesPlaceAt")):
        start, end = parse_day(slot.get("startDate")), parse_day(slot.get("endDate"))
        if not start:
            continue
        end = end or start
        if end < start or end < today:
            continue
        dates.append({"start": start.isoformat(), "end": end.isoformat(),
                      "time": text(slot.get("startTime"))[:5]})
    if not dates:
        return None, "sans_date_a_venir"
    dates.sort(key=lambda d: d["start"])

    desc = (as_list(raw.get("hasDescription")) or [{}])[0]
    description = clean_html(text(desc.get("shortDescription")) or text(desc.get("description")))

    image = ""
    rep = (as_list(raw.get("hasMainRepresentation")) or [{}])[0]
    res = (as_list(rep.get("hasRelatedResource")) or [{}])[0]
    image = http_url(res.get("locator"))

    contact = (as_list(raw.get("hasContact")) or [{}])[0]
    url = http_url(contact.get("homepage") or contact.get("foaf:homepage"))

    return {
        "id": raw.get("uuid") or raw.get("uri") or title,
        "title": title,
        "locality": locality,
        "dates": dates[:5],
        "description": description[:300],
        "image": image,
        "url": url,
        "lon": lon,
        "lat": lat,
    }, None
