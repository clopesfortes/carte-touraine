"""Envoi des événements dans Supabase (API REST, sans dépendance externe)."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SupabaseError(Exception):
    pass


def upsert_events(url, secret_key, rows, chunk_size=200):
    """Insère ou met à jour les lignes (clé : id). first_seen est conservé."""
    endpoint = f"{url.rstrip('/')}/rest/v1/events?on_conflict=id"
    for start in range(0, len(rows), chunk_size):
        body = json.dumps(rows[start:start + chunk_size], ensure_ascii=False).encode("utf-8")
        request = Request(endpoint, data=body, method="POST", headers={
            "apikey": secret_key,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        })
        try:
            urlopen(request, timeout=60).read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            raise SupabaseError(f"Supabase a refusé l'envoi (HTTP {error.code}) : {detail}") from error
        except (URLError, TimeoutError) as error:
            raise SupabaseError(f"Connexion à Supabase impossible : {error}") from error
