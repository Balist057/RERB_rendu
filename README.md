# Analyse du tunnel commun RER B / RER D

Projet Python pour la data science (ENSAE 2A). L'objectif est de quantifier et visualiser l'effet domino dans le tunnel partagé entre le RER B et le RER D (*Châtelet-Les Halles* - *Gare du Nord*), en utilisant le tronçon central du RER A comme référence (fréquence élevée sans partage de voies).

L'ensemble des résultats (statistiques descriptives, contagion, résilience) et la visualisation interactive des incidents passés seront regroupés dans une application **Streamlit** unique.

## Structure du dépôt

- `bot_collect/` : collecteur temps réel sur l'API PRIM (Île-de-France Mobilités), déployé sur SSP Cloud (écriture Parquet sur MinIO S3).
- `data/raw/` et `data/processed/` : répertoires locaux (ignorés par Git) contenant les snapshots bruts et les Parquet nettoyés ; si absents, `src/nettoyage.py` télécharge automatiquement depuis le bucket S3 public.
- `src/` : lecture (`lecture.py`), pipeline DuckDB de nettoyage (`nettoyage.py`) et analyses statistiques (`stats.py`).
- `notebooks/` : notebooks d'exploration (`axe1.ipynb`, `axe2.ipynb`).
- `docs/figures/` : graphiques générés localement par `src/stats.py` (ignorés par Git).
- `app.py` et `pages/` : application Streamlit multi-pages (`1_Dashboard.py`, `2_Visualisations.py`).

## Déjà réalisé

- **Collecte et stockage (`bot_collect/`)** : collecteur temps réel pour les RER A, B, D et les messages d'incidents, déployé sur SSP Cloud (Docker / Kubernetes) avec stockage Parquet sur S3.
- **Lecture et nettoyage (`src/lecture.py`, `src/nettoyage.py`)** :
  - chargement DuckDB en mode `local` (`data/raw/`) ou `s3` (fallback automatique sur S3 si les fichiers locaux sont absents) ;
  - isolation des tronçons centraux (RER A : *Charles De Gaulle-Étoile* à *Nation* ; RER B : *Denfert-Rochereau* à *Aulnay-sous-Bois* ; RER D : *Gare de Lyon* à *Saint-Denis*), uniformisation de `Châtelet-Les Halles` et tri chronologique UTC vers `Europe/Paris` ;
  - filtrage des retards aberrants (`[-15, 180]` min), création des variables (`retard_min`, `est_supprime`, `zone_tunnel`, `heure_pointe`, `tranche_horaire`) et export dans `data/processed/`.
- **Analyses Axe 1 et Axe 2 (`src/stats.py`, `notebooks/axe1.ipynb`, `notebooks/axe2.ipynb`)** :
  - comparaison macro B/D vs A (moyenne, médiane, P90/P95 hors suppressions), comparaison à *Châtelet-Les Halles*, retard ajouté dans le tunnel selon le sens, écart pointe / heures creuses et taux de suppression / limitation (`src/stats.py` génère 4 graphiques dans `docs/figures/` et un tableau récapitulatif) ;
  - exploration de la contagion dans le tunnel (`axe2.ipynb` : corrélation par fenêtres de 15 min, décalage `.shift()`, test placebo RER A à Châtelet et temps de retour sous 3 min après un pic).

## Reste à faire

- **Compléter `src/stats.py` (Axes 2 et 3)** : intégrer la contagion B/D (corrélation, lag `.shift()`, résilience) et la détection automatique des principaux incidents passés croisée avec `clean_incidents`.
- **Visualisations et application Streamlit (`app.py`, `pages/`)** :
  - intégrer les résultats d'analyse dans `pages/1_Dashboard.py` et `pages/2_Visualisations.py` ;
  - construire la carte interactive (carte géographique de Paris + schéma topologique en « H » couché avec le RER A séparé) permettant de rejouer les incidents passés minute par minute, avec un diagramme de Marey et les messages d'incidents.
- **Soutenance (`soutenance/`)** : préparer les slides LaTeX.

Rscript -e "tinytex::pdflatex('mon_fichier.tex')" pour compiler le fichier .tex (avec R ds le PATH)
