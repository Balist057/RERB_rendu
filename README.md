# Analyse du tunnel commun RER B / RER D

Projet Python pour la data science (ENSAE 2A). L'objectif est de quantifier et visualiser l'effet domino dans le tunnel partagé entre le RER B et le RER D (*Châtelet-Les Halles* - *Gare du Nord*), en prenant le tronçon central du RER A comme référence (fréquence élevée sans partage de voies).

## Structure du dépôt

- `bot_collect/` : collecteur temps réel sur l'API PRIM (Île-de-France Mobilités), déployé sur SSP Cloud (écriture Parquet sur MinIO S3).
- `data/` : référentiel géographique des gares (`gares_coords.csv`), plus `raw/` et `processed/` (ignorés par Git, régénérés automatiquement depuis le bucket S3 public).
- `src/` :
  - `lecture.py` : accès S3 anonyme et mise à jour incrémentale de `data/raw/`.
  - `nettoyage.py` : pipeline DuckDB de préparation des tronçons centraux (`data/processed/`) et `charger_jour_complet()` pour charger toutes les gares sur une journée.
  - `Axe1_constat_naif.py` : comparaison macro B/D vs A (retards, Châtelet, entrée/sortie tunnel, tranches horaires, suppressions/limitations, journées noires).
  - `axe2_contagion.py` : contagion dans le tunnel (corrélations, résidus hors saisonnalité horaire, décalage `.shift()`, sens Nord/Sud, effet domino réciproque B/D vs placebo A, résilience).
  - `axe3_incidents.py` : détection automatique des principaux incidents passés, extraction des causes officielles, débit vs retard et diagramme de Marey.
  - `coordonnees_gares.py` : construction de `data/gares_coords.csv` depuis l'open data IDFM.
  - `replay.py` : préparation corridor, interpolation des trains, état du tunnel et carte animée Plotly pour le replay.
  - `dashboard_utils.py` : chargement en cache, filtres latéraux et mise en forme Plotly partagés entre les pages d'axes.
- `rapport.ipynb` : rapport complet regroupant les données, les 3 axes d'analyse et la conclusion.
- `notebooks/` : notebooks d'exploration (`axe1.ipynb`, `axe2.ipynb`).
- `docs/` : documentation du pipeline (`pipeline_donnees.md`) et figures générées dans `docs/figures/` (ignorées par Git).
- `app.py` et `pages/` : application Streamlit multi-pages (`0_Accueil.py`, `1_Donnees.py`, `2_Axe1_Constat.py`, `3_Axe2_Contagion.py`, `4_Axe3_Incidents.py`, `5_Replays.py`, `6_Conclusion.py`).

## Installation et exécution

```bash
pip install -r requirements.txt
streamlit run app.py
```

Le rapport complet s'exécute également de bout en bout dans `rapport.ipynb` (*Restart & Run All*), ou script par script :

```bash
python src/Axe1_constat_naif.py
python src/axe2_contagion.py
python src/axe3_incidents.py
```

Si `data/processed/` est vide (après un clone), les scripts téléchargent et nettoient automatiquement les données depuis le bucket S3 public. Pour rafraîchir les données locales avec les derniers jours collectés :

```bash
python -c "from src.nettoyage import preparer_donnees; preparer_donnees(maj=True)"
```

## Principaux résultats

- **Constat (Axe 1)** : les RER B et D sont 2 à 3 fois plus en retard que le RER A (`3,3` et `3,1` min contre `1,3` min ; P95 à `~13` min vs `7` min) et le surcroît se forme dans le tunnel (`+27 s` et `+41 s` par arrêt contre `-11 s` sur le A), avec `2 %` à `3,5 %` de trains limités avant le tunnel.
- **Contagion (Axe 2)** : les retards de B et D à Châtelet sont corrélés (`0,26`, et `0,22` hors effet d'heure contre `0,02` avec le placebo A), le retard de B précède celui de D de `15 min`, et la contagion joue dans les deux sens (`~7 min` quand l'autre ligne dépasse `10 min`, contre `~1 min` sur A).
- **Incidents et replay (Axe 3)** : 6 des 8 plus gros épisodes détectés touchent simultanément B et D avec chute du débit dans le tunnel, alors que le RER A reste sous `5 min`.
