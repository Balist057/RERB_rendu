# Analyse du tunnel commun RER B / RER D

Projet Python pour la data science (ENSAE 2A). L'objectif est de quantifier et visualiser l'effet domino dans le tunnel partagé entre le RER B et le RER D (*Châtelet-Les Halles* - *Gare du Nord*), en utilisant le tronçon central du RER A comme référence (fréquence élevée sans partage de voies).

L'ensemble des résultats (statistiques descriptives, contagion, résilience) et la visualisation interactive des incidents passés seront regroupés dans une application **Streamlit** unique.

## Structure du dépôt

- `bot_collect/` : collecteur temps réel sur l'API PRIM (Île-de-France Mobilités), déployé sur SSP Cloud (écriture Parquet sur MinIO S3).
- `data/` : snapshots Parquet bruts (`2026-11-24`) et Parquet nettoyés datés (`clean_*_2026-11-25.parquet`).
- `nettoyage/` : lecture (`lecture.py`), pipeline DuckDB de nettoyage/préparation (`nettoyage.py`) et notebook d'exploration temporaire (`nettoyage_explo.ipynb`).
- `analyse/` : analyses statistiques (comparaison macro, contagion tunnel, résilience, détection d'incidents).
- `visualisation/` : graphiques et cartes interactives.
- `soutenance/` : support de présentation (LaTeX).

## Déjà réalisé

- **Collecte et stockage (`bot_collect/`)** : collecteur temps réel pour les RER A, B, D et les messages d'incidents, déployé sur SSP Cloud (Docker / Kubernetes) avec export des fichiers Parquet dans `data/`.
- **Lecture et structuration (`nettoyage/lecture.py`)** : lecture S3/Parquet, explosion du champ JSON `stops`, conversion UTC vers `Europe/Paris`, tri chronologique des arrêts par trajet et calcul de `delay_added_sec`.
- **Pipeline de nettoyage (`nettoyage/nettoyage.py`)** :
  - chargement optimisé avec DuckDB prenant en charge `source="local"` (`2026-10-02` au `2026-11-23`) et `source="s3"` (toutes les dates disponibles depuis le `2026-10-02` sur le bucket public) ;
  - uniformisation du nom de gare `Châtelet-Les Halles` sur le RER B et isolation des tronçons centraux (RER A : *Charles De Gaulle-Étoile* à *Nation* ; RER B : *Denfert-Rochereau* à *Aulnay-sous-Bois* ; RER D : *Gare de Lyon* à *Saint-Denis*) ;
  - filtrage des retards aberrants (±24h de PRIM, `retard_min` borné à `[-15, 180]`) et création des variables `retard_min`, `est_supprime`, `zone_tunnel`, `heure_pointe` et `tranche_horaire` ;
  - export et relecture rapide des Parquet propres datés (`data/clean_*_YYYY-MM-DD.parquet`).

## Reste à faire

- **Analyses statistiques (`analyse/stats.py`)** :
  - comparaison macro B/D vs A : moyenne, médiane, P90/P95 des retards (hors suppressions), écart heures de pointe / heures creuses, taux de suppression et de retournement avant le tunnel ;
  - contagion dans le tunnel : corrélation des retards moyens par fenêtres de 10-15 min à *Châtelet-Les Halles* et *Gare du Nord*, analyse de décalage temporel (`.shift()`), temps de retour à la normale après un pic (résilience) ;
  - détection automatique des principaux incidents passés (chute de fréquence + hausse des retards), croisée avec les messages de `clean_incidents`.
- **Visualisations et application Streamlit (`visualisation/` et `app.py`)** :
  - regrouper les résultats d'analyse et la méthodologie directement dans l'application Streamlit (en remplacement de `rapport.ipynb`) ;
  - construire une carte interactive (carte géographique de Paris + schéma topologique en « H » couché avec le RER A séparé) permettant de rejouer les incidents passés minute par minute, complétée par un diagramme de Marey et les messages d'incidents.
- **Finalisation du dépôt** : remplir `requirements.txt`, supprimer les fichiers temporaires (`nettoyage/nettoyage_explo.ipynb`, `exploration.py`, `init.ipynb`, `rapport.ipynb`) et préparer les slides dans `soutenance/`.

Rscript -e "tinytex::pdflatex('mon_fichier.tex')" pour compiler le fichier .tex (avec R ds le PATH)