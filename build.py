"""Collecte DATAtourisme et écrit site/events.geojson. Lancer : python build.py"""
import json
import sys
from collections import Counter
from datetime import datetime, timezone

import config
from datatourisme import DatatourismeError, fetch_events
from normalize import normalize
from supabase_client import SupabaseError, upsert_events

OUTPUT = config.ROOT / "site" / "events.geojson"


def main():
    try:
        cfg = config.load()
        print(f"Collecte DATAtourisme (département {cfg['department']})...")
        raw_events, total = fetch_events(cfg)
    except (config.ConfigError, DatatourismeError) as error:
        sys.exit(f"ERREUR : {error}")

    if not raw_events:
        sys.exit("ERREUR : aucun événement reçu, le site n'est pas modifié.")
    if total is not None and len(raw_events) < total:
        sys.exit(f"ERREUR : collecte incomplète ({len(raw_events)}/{total}), le site n'est pas modifié.")

    rejected, features, categories, unmatched = Counter(), [], Counter(), Counter()
    for raw in raw_events:
        event, reason = normalize(raw)
        if reason:
            rejected[reason] += 1
            continue
        lon, lat = event.pop("lon"), event.pop("lat")
        raw_types = event.pop("raw_types")
        categories[event["category"]] += 1
        if event["category"] == "Autre":
            unmatched.update(raw_types)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": event,
        })

    if not features:
        sys.exit(f"ERREUR : aucun événement publiable. Motifs : {dict(rejected)}")

    features.sort(key=lambda f: f["properties"]["dates"][0]["start"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "features": features,
    }, ensure_ascii=False), encoding="utf-8")

    print(f"{len(raw_events)} reçus, {len(features)} publiables.")
    print(f"Écartés : {dict(rejected) or 'aucun'}")
    print(f"Catégories : {dict(categories)}")
    print(f"Types non reconnus (classés « Autre ») : {dict(unmatched.most_common(10)) or 'aucun'}")

    try:
        supabase = config.load_supabase()
    except config.ConfigError as error:
        sys.exit(f"ERREUR : {error}")

    if supabase is None:
        print("ATTENTION : Supabase non configuré, envoi ignoré (la carte utilise events.geojson).")
        return

    now = datetime.now(timezone.utc).isoformat()
    rows = {}
    for f in features:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"]
        rows[p["id"]] = {
            "id": p["id"], "source": "DATAtourisme", "title": p["title"],
            "locality": p["locality"], "lat": lat, "lon": lon, "dates": p["dates"],
            "first_start": min(d["start"] for d in p["dates"]),
            "last_end": max(d["end"] for d in p["dates"]),
            "description": p["description"], "image": p["image"], "url": p["url"],
            "category": p["category"],
            "last_seen": now,
        }
    try:
        upsert_events(*supabase, list(rows.values()))
    except SupabaseError as error:
        sys.exit(f"ERREUR : {error}")
    print(f"{len(rows)} événements enregistrés dans Supabase.")


if __name__ == "__main__":
    main()
