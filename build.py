"""Collecte DATAtourisme et écrit site/events.geojson. Lancer : python build.py"""
import json
import sys
from collections import Counter
from datetime import datetime, timezone

import config
from datatourisme import DatatourismeError, fetch_events
from normalize import normalize

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

    rejected, features = Counter(), []
    for raw in raw_events:
        event, reason = normalize(raw)
        if reason:
            rejected[reason] += 1
            continue
        lon, lat = event.pop("lon"), event.pop("lat")
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

    print(f"{len(raw_events)} reçus, {len(features)} publiés sur la carte.")
    print(f"Écartés : {dict(rejected) or 'aucun'}")


if __name__ == "__main__":
    main()
