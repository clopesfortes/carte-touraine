"""Échanges avec Supabase (API REST, sans dépendance externe)."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class SupabaseError(Exception):
    pass


def _call(url, key, path, method="GET", body=None, prefer=None):
    headers = {"apikey": key, "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = Request(f"{url.rstrip('/')}/rest/v1/{path}", data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else None
    except HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:500]
        raise SupabaseError(f"Supabase a refusé la requête (HTTP {error.code}) : {detail}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise SupabaseError(f"Échange avec Supabase impossible : {error}") from error


def fetch_all(url, key, path, page=1000):
    rows, offset = [], 0
    while True:
        sep = "&" if "?" in path else "?"
        chunk = _call(url, key, f"{path}{sep}limit={page}&offset={offset}") or []
        rows.extend(chunk)
        if len(chunk) < page:
            return rows
        offset += page


def upsert_rows(url, key, table, rows, on_conflict, chunk_size=200):
    for start in range(0, len(rows), chunk_size):
        _call(url, key, f"{table}?on_conflict={on_conflict}", "POST", rows[start:start + chunk_size],
              prefer="resolution=merge-duplicates,return=minimal")


def upsert_events(url, key, rows):
    upsert_rows(url, key, "events", rows, "id")


def get_sync_state(url, key):
    rows = fetch_all(url, key, "sync_state?select=department,last_synced,total")
    return {r["department"]: r for r in rows}


def set_sync_state(url, key, department, total, status, when):
    upsert_rows(url, key, "sync_state", [{"department": department, "last_synced": when,
                                          "total": total, "last_status": status}], "department")


def fetch_upcoming(url, key, today, seen_since):
    path = ("events?select=id,title,locality,lat,lon,dates,description,image,url,category,department,region"
            f"&source=eq.DATAtourisme&hidden=eq.false&last_end=gte.{today}&last_seen=gte.{quote(seen_since)}"
            "&order=first_start.asc,id.asc")
    return fetch_all(url, key, path)
