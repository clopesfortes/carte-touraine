# Carte Touraine

Carte des événements à venir en Indre-et-Loire, alimentée par DATAtourisme (Licence Ouverte 2.0).
Aucune dépendance Python : Python 3.9 ou plus suffit.

## En local
1. Copiez `config.example.ini` en `config.ini` et collez votre clé API.
2. `python build.py` (crée `site/events.geojson`)
3. `python -m http.server -d site` puis ouvrez http://localhost:8000

## Mise en ligne (GitHub Pages, gratuit)
1. Créez un dépôt GitHub et envoyez-y ce dossier (`config.ini` est ignoré par `.gitignore` : la clé ne part pas).
2. Dépôt > Settings > Secrets and variables > Actions > New repository secret :
   nom `DATATOURISME_API_KEY`, valeur = votre clé.
3. Dépôt > Settings > Pages > Source : **GitHub Actions**.
4. Onglet Actions > « Collecte et mise en ligne » > Run workflow.
   L'adresse du site s'affiche à la fin. La carte se met ensuite à jour chaque jour.

## Si la carte est vide
Le journal du build indique les motifs d'écart (`sans_position`, `sans_date_a_venir`, `sans_titre`).
