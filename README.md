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
  - `replay.py` : préparation des données sur le corridor petite couronne (trains et incidents) pour le replay.
- `rapport.ipynb` : rapport complet regroupant les données, les 3 axes d'analyse et la conclusion.
- `notebooks/` : notebooks d'exploration (`axe1.ipynb`, `axe2.ipynb`).
- `docs/` : documentation du pipeline (`pipeline_donnees.md`) et figures générées dans `docs/figures/` (ignorées par Git).
- `app.py` et `pages/` : application Streamlit multi-pages (`1_Dashboard.py`, `2_Visualisations.py`).

## Installation et exécution

```bash
pip install -r requirements.txt
python src/Axe1_constat_naif.py
python src/axe2_contagion.py
python src/axe3_incidents.py
```

Si `data/processed/` est vide (après un clone), les scripts téléchargent et nettoient automatiquement les données depuis le bucket S3 public. Pour rafraîchir les données locales avec les derniers jours collectés :

```bash
python -c "from src.nettoyage import preparer_donnees; preparer_donnees(maj=True)"
```

## Déjà réalisé

- **Collecte et pipeline de données** (`bot_collect/`, `src/lecture.py`, `src/nettoyage.py`, `docs/pipeline_donnees.md`) : collecte continue SSP Cloud, synchronisation incrémentale S3, filtrage des tronçons centraux et des retards aberrants (`[-15, 180]` min), création des variables d'analyse et fonction `charger_jour_complet()` toutes gares.
- **Analyses complètes (Axes 1, 2 et 3)** (`src/Axe1_constat_naif.py`, `src/axe2_contagion.py`, `src/axe3_incidents.py`, `rapport.ipynb`) :
  - Axe 1 : retards moyens et P95, contrôle à *Châtelet-Les Halles*, retard ajouté entrée vs sortie de tunnel et par tranche horaire, suppressions/limitations, 8 journées noires sur B et D (0 sur A).
  - Axe 2 : corrélation B/D à Châtelet (brute et sur résidus hors effet d'heure : `0,22` vs `0,02` sur A), décalage maximal à `+15 min`, asymétrie Sud/Nord, contagion réciproque B/D vs placebo A, temps de retour sous 3 min.
  - Axe 3 : détection automatique des principaux incidents passés, association aux causes officielles, suivi débit vs retard et diagramme de Marey.
- **Préparation du replay** (`src/coordonnees_gares.py`, `data/gares_coords.csv`, `src/replay.py`) : coordonnées GPS des gares et extraction optimisée des trajets/incidents sur le corridor petite couronne.

## Reste à faire

- **Interface Streamlit (`app.py`, `pages/1_Dashboard.py`, `pages/2_Visualisations.py`)** : connecter les graphiques des 3 axes et le replay interactif basé sur `src/replay.py` (carte géographique / schéma topologique et diagramme de Marey).
- **Soutenance** : préparer les slides LaTeX.

Rscript -e "tinytex::pdflatex('mon_fichier.tex')" pour compiler le fichier .tex (avec R ds le PATH)
