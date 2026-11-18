"""Pages statiques pour le référencement : une page par commune, « ce week-end » et plan du site.
La carte reste la page d'accueil ; ces pages sont des portes d'entrée lisibles par Google."""
import html
import json
import os
import re
import shutil
import unicodedata

import regions
from collections import Counter, defaultdict
from datetime import date, timedelta

SITE_URL = os.environ.get("SITE_URL", "https://clopesfortes.github.io/carte-touraine").rstrip("/")
BRAND = "ACTIFF"
MIN_EVENTS = 3          # nombre minimal d'événements pour créer la page d'une commune
MAX_PER_PAGE = 100
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
esc = html.escape


def key(text):
    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower().replace("œ", "oe")
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return re.sub(r"\bste\b", "sainte", re.sub(r"\bst\b", "saint", t))


def long_date(iso):
    d = date.fromisoformat(iso)
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def when(d):
    return long_date(d["start"]) if d["start"] == d["end"] else f"du {long_date(d['start'])} au {long_date(d['end'])}"


def card(f):
    p = f["properties"]
    d = p["dates"][0]
    out = [f'<article><h2>{esc(p["title"])}</h2>',
           f'<p class="m">{esc(p.get("category") or "Autre")} · {esc(p["locality"])} · {esc(when(d))}'
           + (f' à {esc(d["time"])}' if d.get("time") else "") + "</p>"]
    if p.get("description"):
        out.append(f'<p>{esc(p["description"])}</p>')
    if p.get("url"):
        out.append(f'<p><a href="{esc(p["url"])}" target="_blank" rel="noopener nofollow">Plus d’informations</a></p>')
    return "".join(out) + "</article>"


def event_ld(f):
    p, (lon, lat) = f["properties"], f["geometry"]["coordinates"]
    d = p["dates"][0]
    ld = {"@type": "Event", "name": p["title"], "startDate": d["start"], "endDate": d["end"],
          "eventStatus": "https://schema.org/EventScheduled",
          "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
          "location": {"@type": "Place", "name": p["locality"],
                       "address": {"@type": "PostalAddress", "addressLocality": p["locality"], "addressCountry": "FR"},
                       "geo": {"@type": "GeoCoordinates", "latitude": lat, "longitude": lon}}}
    if p.get("description"):
        ld["description"] = p["description"]
    if p.get("image"):
        ld["image"] = [p["image"]]
    if p.get("url"):
        ld["url"] = p["url"]
    return ld


def render(path, root, title, description, h1, intro, feats):
    feats = feats[:MAX_PER_PAGE]
    ld = json.dumps({"@context": "https://schema.org", "@graph": [event_ld(f) for f in feats]}, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{SITE_URL}/{path}">
<script type="application/ld+json">{ld}</script>
<style>body{{max-width:46rem;margin:0 auto;padding:1rem 1.2rem 3rem;font:16px/1.6 system-ui,sans-serif;color:#1d2b2a;background:#f6f8f5}}
h1,h2{{font-family:Georgia,serif}}h2{{font-size:1.1rem;margin:0}}article{{padding:.8rem 0;border-bottom:1px solid #d4d9d0}}
.m{{color:#4b5b5a;font-size:.9rem;margin:.2rem 0}}a{{color:#1f6f78}}
.btn{{display:inline-block;padding:.5rem 1rem;background:#1f6f78;color:#fff;border-radius:4px;text-decoration:none}}</style></head>
<body><p><a class="btn" href="{root}">Voir sur la carte</a></p><h1>{esc(h1)}</h1><p>{esc(intro)}</p>
{''.join(card(f) for f in feats)}
<p><a href="{root}">← Retour à la carte {BRAND}</a> · <a href="{root}mentions.html">Mentions légales</a></p></body></html>"""


def territory(props):
    return regions.territory_of(props.get("department") or "") or props.get("region") or "France"


def generate(features, site, indexed=None):
    today = date.today()
    pub = [f for f in features if indexed is None or f["properties"].get("region") in indexed]
    shutil.rmtree(site / "commune", ignore_errors=True)
    (site / "commune").mkdir(parents=True, exist_ok=True)
    for old in site.glob("ce-week-end*.html"):
        old.unlink()

    groups, names = defaultdict(list), defaultdict(Counter)
    for f in pub:
        p = f["properties"]
        k = (key(p["locality"]), p.get("department") or "")
        if k[0]:
            groups[k].append(f)
            names[k][p["locality"]] += 1
    homonyms = Counter(k for k, _ in groups)

    urls, links, n_communes = [f"{SITE_URL}/", f"{SITE_URL}/mentions.html"], [], 0
    for (k, dep), feats in sorted(groups.items()):
        if len(feats) < MIN_EVENTS:
            continue
        name = names[(k, dep)].most_common(1)[0][0]
        slug = k.replace(" ", "-") + (f"-{dep.lower()}" if homonyms[k] > 1 else "")
        terr, n = territory(feats[0]["properties"]), len(feats)
        cats = ", ".join(f"{c} {t.lower()}" for t, c in Counter(f["properties"].get("category") or "Autre" for f in feats).most_common(3))
        page = render(f"commune/{slug}.html", "../", f"Événements à {name} ({n} à venir) – {terr} – {BRAND}",
                      f"{n} événements à venir à {name} ({terr}) : dates, lieux et descriptions, avec la carte interactive {BRAND}.",
                      f"Événements à {name}", f"{n} événements à venir à {name} ({terr}). Au programme : {cats}.", feats)
        (site / "commune" / f"{slug}.html").write_text(page, encoding="utf-8")
        urls.append(f"{SITE_URL}/commune/{slug}.html")
        links.append(f'<a href="commune/{slug}.html">{esc(name)}</a>')
        n_communes += 1

    wd = today.weekday()
    start = today if wd >= 5 else today + timedelta(days=5 - wd)
    end = today if wd == 6 else start + timedelta(days=1)
    s0, e0 = start.isoformat(), end.isoformat()
    by_terr = defaultdict(list)
    for f in pub:
        if any(d["start"] <= e0 and d["end"] >= s0 for d in f["properties"]["dates"]):
            by_terr[territory(f["properties"])].append(f)
    week_links = []
    for terr, feats in sorted(by_terr.items()):
        fname = "ce-week-end.html" if terr == "Touraine" else f"ce-week-end-{key(terr).replace(' ', '-')}.html"
        when_txt = f"du {long_date(s0)} au {long_date(e0)}" if s0 != e0 else f"le {long_date(s0)}"
        (site / fname).write_text(render(fname, "./", f"Que faire ce week-end : {terr} – {BRAND}",
                                         f"{len(feats)} événements ce week-end ({terr}) : marchés, concerts, spectacles, sorties. Dates et lieux.",
                                         f"Ce week-end : {terr}", f"{len(feats)} événements {when_txt}.", feats), encoding="utf-8")
        urls.append(f"{SITE_URL}/{fname}")
        week_links.append(f'<a href="{fname}">Ce week-end : {esc(terr)}</a>')

    index = site / "index.html"
    if index.exists() and (links or week_links):
        block = ('<!--COMMUNES--><details id="communes-seo"><summary>Parcourir par commune</summary><p>'
                 + " · ".join(week_links + links) + "</p></details><!--/COMMUNES-->")
        text = re.sub(r"<!--COMMUNES-->.*?<!--/COMMUNES-->", lambda m: block, index.read_text(encoding="utf-8"), flags=re.S)
        index.write_text(text, encoding="utf-8")

    sitemap = "".join(f"<url><loc>{u}</loc><lastmod>{today.isoformat()}</lastmod></url>" for u in urls)
    (site / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                      + sitemap + "</urlset>", encoding="utf-8")
    return {"communes": n_communes, "week_end": len(week_links), "urls_sitemap": len(urls)}
