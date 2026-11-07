"""Lecture de la configuration : config.ini en local, variable d'environnement en ligne."""
import configparser
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ConfigError(Exception):
    pass


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

    return {
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
