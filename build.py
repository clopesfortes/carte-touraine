"""Collecte DATAtourisme par rotation de départements, enregistre dans Supabase et génère le site.
Lancer : python build.py"""
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone

import config
import regions
import supabase_client as sb
from datatourisme import DatatourismeError, fetch_events
from normalize import normalize

OUTPUT = config.ROOT / "site" / "events.geojson"
MAX_GEOJSON = 5000   # au-delà, le fichier de secours n'est plus produit
STALE_DAYS = 10      # un événement non revu depuis ce délai n'est plus publié sur les pages


def norm_key(text):
    """Forme normalisée d'une commune (sans accents ni ponctuation, « st » devient « saint »)."""
    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower().replace("œ", "oe")
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return re.sub(r"\bste\b", "sainte", re.sub(r"\bst\b", "saint", t))


def pick_departments(wanted, state, budget):
    """Départements les plus anciennement mis à jour d'abord, dans la limite du budget de requêtes."""
    chosen, used = [], 0
    for dep in sorted(wanted, key=lambda d: ((state.get(d) or {}).get("last_synced") or "", d)):
        total = (state.get(dep) or {}).get("total")
        cost = math.ceil(total / 100) + 1 if total else 10
        if chosen and used + cost > budget:
            continue
        chosen.append(dep)
        used += cost
    return chosen, used


def collect_department(cfg, dep):
    raw, total = fetch_events(cfg, dep)
    if total is not None and len(raw) < total:
        raise DatatourismeError(f"collecte incomplète ({len(raw)}/{total})")
    if not raw and total != 0:
        raise DatatourismeError("aucun événement reçu")
    feats, rejected, cats, unmatched = [], Counter(), Counter(), Counter()
    for item in raw:
        event, reason = normalize(item)
        if reason:
            rejected[reason] += 1
            continue
        lon, lat = event.pop("lon"), event.pop("lat")
        raw_types = event.pop("raw_types")
        cats[event["category"]] += 1
        if event["category"] == "Autre":
            unmatched.update(raw_types)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                      "properties": event})
    return feats, (total if total is not None else len(raw)), rejected, cats, unmatched


def to_row(feat, dep, now):
    p, (lon, lat) = feat["properties"], feat["geometry"]["coordinates"]
    return {"id": p["id"], "source": "DATAtourisme", "title": p["title"], "locality": p["locality"],
            "lat": lat, "lon": lon, "dates": p["dates"],
            "first_start": min(d["start"] for d in p["dates"]), "last_end": max(d["end"] for d in p["dates"]),
            "description": p["description"], "image": p["image"], "url": p["url"], "category": p["category"],
            "department": dep, "region": regions.region_of(dep), "locality_norm": norm_key(p["locality"]), "last_seen": now}


def to_feature(row):
    props = {k: (row.get(k) or "") for k in ("id", "title", "locality", "description", "image", "url", "category", "department", "region")}
    props["dates"] = row["dates"]
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]}, "properties": props}


def main():
    try:
        cfg = config.load()
        supabase = config.load_supabase()
    except config.ConfigError as error:
        sys.exit(f"ERREUR : {error}")

    try:
        state = sb.get_sync_state(*supabase) if supabase else {}
    except sb.SupabaseError as error:
        sys.exit(f"ERREUR : {error}")
    chosen, estimate = pick_departments(cfg["departments"], state, cfg["budget"])
    print(f"Départements configurés : {len(cfg['departments'])} ; traités cette nuit : {len(chosen)} (environ {estimate} requêtes)")
    print(f"Liste : {', '.join(chosen)}")
    if supabase is None:
        print("ATTENTION : Supabase non configuré, aucune donnée ne sera enregistrée.")

    now = datetime.now(timezone.utc).isoformat()
    run_features, failed, done = [], [], 0
    rejected, cats, unmatched = Counter(), Counter(), Counter()
    for dep in chosen:
        try:
            feats, total, rej, c, u = collect_department(cfg, dep)
            if supabase:
                sb.upsert_events(*supabase, list({r["id"]: r for r in (to_row(f, dep, now) for f in feats)}.values()))
                sb.set_sync_state(*supabase, dep, total, "ok", now)
        except (DatatourismeError, sb.SupabaseError) as error:
            print(f"  Département {dep} ignoré : {error}")
            failed.append(dep)
            continue
        done += 1
        rejected.update(rej); cats.update(c); unmatched.update(u)
        for f in feats:
            f["properties"]["department"], f["properties"]["region"] = dep, regions.region_of(dep)
        run_features += feats
        print(f"  {dep} ({regions.region_of(dep)}) : {len(feats)} événements publiables sur {total}")

    if done == 0:
        sys.exit("ERREUR : aucun département n'a pu être collecté, le site n'est pas modifié.")
    print(f"Écartés : {dict(rejected) or 'aucun'}")
    print(f"Catégories : {dict(cats)}")
    print(f"Types non reconnus (classés « Autre ») : {dict(unmatched.most_common(10)) or 'aucun'}")
    if failed:
        print(f"ATTENTION : départements en échec cette nuit : {', '.join(failed)}")

    if supabase:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=STALE_DAYS)).isoformat()
            features = [to_feature(r) for r in sb.fetch_upcoming(*supabase, date.today().isoformat(), cutoff, cfg["indexed_regions"])]
        except sb.SupabaseError as error:
            sys.exit(f"ERREUR : {error}")
    else:
        features = sorted(run_features, key=lambda f: f["properties"]["dates"][0]["start"])
    print(f"{len(features)} événements publiés au total.")

    if len(features) <= MAX_GEOJSON:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "generated_at": now, "features": features},
                                     ensure_ascii=False), encoding="utf-8")
    else:
        OUTPUT.unlink(missing_ok=True)
        print("Fichier de secours events.geojson non produit (trop d'événements).")

    try:
        import pages
        print(f"Pages de référencement : {pages.generate(features, config.ROOT / 'site', cfg['indexed_regions'])}")
    except Exception as error:  # ne bloque jamais la collecte
        print(f"ATTENTION : pages de référencement non générées ({type(error).__name__} : {error})")


if __name__ == "__main__":
    main()
