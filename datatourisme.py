"""Récupération des événements DATAtourisme (sans dépendance externe)."""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

FIELDS = (
    "uuid,uri,label,type,isLocatedAt,hasContact,hasDescription,"
    "hasMainRepresentation,takesPlaceAt,lastUpdate"
)


class DatatourismeError(Exception):
    pass


def _get(url, api_key, attempts=3):
    request = Request(url, headers={
        "X-API-Key": api_key,
        "Accept": "application/json",
        "User-Agent": "Carte-Touraine/1.0",
    })
    last = None
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("objects"), list):
                raise DatatourismeError("Réponse inattendue de l'API (pas de liste 'objects').")
            return data
        except HTTPError as error:
            if error.code in (401, 403):
                raise DatatourismeError(f"Clé API refusée (HTTP {error.code}).") from error
            last = f"HTTP {error.code}"
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            last = str(error)
        time.sleep(2 * (attempt + 1))
    raise DatatourismeError(f"Échec après {attempts} tentatives : {last}")


def fetch_events(cfg):
    """Retourne (liste d'événements bruts, total annoncé par l'API)."""
    endpoint = f"{cfg['base_url']}/{cfg['endpoint']}"
    host = urlparse(cfg["base_url"]).hostname
    params = {
        "filters": "isLocatedAt.address.hasAddressCity.isPartOfDepartment.insee[eq]="
                   + cfg["department"],
        "page": 1,
        "page_size": cfg["page_size"],
        "lang": "fr",
        "fields": FIELDS,
    }
    url, seen_urls, seen_ids, events, total = f"{endpoint}?{urlencode(params)}", set(), set(), [], None

    while url:
        if url in seen_urls:
            raise DatatourismeError("Boucle détectée dans la pagination.")
        seen_urls.add(url)
        if urlparse(url).hostname != host:
            raise DatatourismeError("Lien de pagination vers un autre domaine refusé.")

        data = _get(url, cfg["api_key"])
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        if total is None:
            total = meta.get("total")

        for item in data["objects"]:
            if not isinstance(item, dict):
                continue
            uid = item.get("uuid")
            if uid in seen_ids:
                continue
            seen_ids.add(uid)
            events.append(item)

        print(f"  page {len(seen_urls)} : {len(events)} événements")
        nxt = meta.get("next")
        url = urljoin(url, nxt) if isinstance(nxt, str) and nxt else None

    try:
        total = int(total) if total is not None else None
    except (TypeError, ValueError):
        total = None
    return events, total
