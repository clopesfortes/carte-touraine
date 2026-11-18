"""Lecture de la configuration : config.ini en local, variable d'environnement en ligne."""
import configparser
import os
import unicodedata
from pathlib import Path

import regions

ROOT = Path(__file__).resolve().parent


class ConfigError(Exception):
    pass


def _canon(text):
    t = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower().replace("'", "").replace("’", "").strip()


def load_scope():
    """Lit regions_actives.txt. Retourne (départements, régions référencées) ou None si le fichier n'existe pas."""
    path = ROOT / "regions_actives.txt"
    if not path.exists():
        return None
    by_canon = {_canon(r): r for r in regions.REGIONS}
    chosen, indexed, rest = set(), set(), None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        name, _, flag = (x.strip() for x in line.partition(";"))
        yes = flag.lower() in ("oui", "yes", "o", "1")
        if name == "*":
            rest = yes
            continue
        region = by_canon.get(_canon(name))
        if not region:
            raise ConfigError(f"Région inconnue dans regions_actives.txt : {name}")
        chosen.add(region)
        if yes:
            indexed.add(region)
    if rest is not None:
        others = set(regions.REGIONS) - chosen
        chosen |= others
        if rest:
            indexed |= others
    deps = sorted(d for d, r in regions.DEPARTMENT_REGION.items() if r in chosen)
    return deps, indexed


def load():
    parser = configparser.ConfigParser()
    parser.read(ROOT / "config.ini", encoding="utf-8")

    def get(key, default):
        return parser.get("DATATOURISME", key, fallback=default).strip()

    api_key = os.environ.get("DATATOURISME_API_KEY", "").strip() or get("api_key", "")
    if not api_key or api_key == "COLLE_TA_CLE_API_ICI":
        raise ConfigError(
            "Clé API introuvable : renseignez api_key dans config.ini "
            "ou la variable DATATOURISME_API_KEY."
        )

    base_url = get("base_url", "https://api.datatourisme.fr/v1").rstrip("/")
    if not base_url.startswith("https://"):
        raise ConfigError("base_url doit utiliser HTTPS.")

    try:
        page_size = max(1, min(int(get("page_size", "100")), 100))
    except ValueError:
        page_size = 100

    indexed = None
    wanted = os.environ.get("DEPARTMENTS", "").strip()
    scope = None if wanted else load_scope()
    if scope:
        departments, indexed = scope
    else:
        wanted = wanted or get("departments", get("department", "37"))
        if wanted.lower() in ("all", "tous", "france"):
            departments = regions.all_departments()
        else:
            departments = [d.strip().upper() for d in wanted.split(",") if d.strip()]
    try:
        budget = int(os.environ.get("DAILY_REQUESTS", "") or get("daily_requests", "400"))
    except ValueError:
        budget = 400

    return {
        "departments": departments,
        "indexed_regions": indexed,
        "budget": budget,
        "api_key": api_key,
        "base_url": base_url,
        "endpoint": get("endpoint", "entertainmentAndEvent"),
        "department": get("department", "37"),
        "page_size": page_size,
    }


def load_supabase():
    """Retourne (url, clé secrète) ou None si Supabase n'est pas configuré."""
    parser = configparser.ConfigParser()
    parser.read(ROOT / "config.ini", encoding="utf-8")
    url = os.environ.get("SUPABASE_URL", "").strip() or parser.get("SUPABASE", "url", fallback="").strip()
    key = os.environ.get("SUPABASE_SECRET_KEY", "").strip() or parser.get("SUPABASE", "secret_key", fallback="").strip()
    if not url or not key:
        return None
    if not key.startswith("sb_secret_"):
        raise ConfigError("La clé Supabase doit commencer par sb_secret_ (clé secrète, pas publique).")
    return url, key
