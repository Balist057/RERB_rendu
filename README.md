# Analyse du tunnel commun RER B / RER D

Projet Python pour la data science (ENSAE 2A). L'objectif est de quantifier et visualiser l'effet domino dans le tunnel partagé entre le RER B et le RER D (*Châtelet-Les Halles* - *Gare du Nord*), en utilisant le tronçon central du RER A comme référence (fréquence élevée sans partage de voies).

L'ensemble des résultats (statistiques descriptives, contagion, résilience) et la visualisation interactive des incidents passés seront regroupés dans une application **Streamlit** unique.

## Structure du dépôt

- `bot_collect/` : collecteur temps réel sur l'API PRIM (Île-de-France Mobilités), déployé sur SSP Cloud (écriture Parquet sur MinIO S3).
- `data/` : snapshots Parquet des passages RER A, B, D et des messages d'incidents (`2026-11-24`).
- `analyse/` : lecture et conversion des données (`lecture.py`), nettoyage (`nettoyage.py`, `nettoyage_explo.ipynb`) et analyses statistiques.
- `visualisation/` : graphiques et cartes interactives.
- `soutenance/` : support de présentation (LaTeX).

## Déjà réalisé

- **Collecte et stockage** : mise en place du collecteur temps réel `bot_collect/` pour les RER A, B, D et les messages d'incidents, déploiement continu sur SSP Cloud (Docker / Kubernetes) et export des fichiers Parquet dans `data/`.
- **Lecture et structuration (`analyse/lecture.py`)** : lecture S3/Parquet, explosion du champ JSON `stops`, conversion UTC vers `Europe/Paris`, tri chronologique des arrêts par trajet et calcul de `delay_added_sec`.
- **Exploration et prototypage du nettoyage (`analyse/nettoyage_explo.ipynb`)** :
  - filtrage sur la période commune complète (`2026-10-02` au `2026-11-23`) ;
  - uniformisation du nom de gare `Châtelet-Les Halles` sur le RER B et isolation des tronçons centraux (RER A : *Charles De Gaulle-Étoile* à *Nation* ; RER B : *Denfert-Rochereau* à *Aulnay-sous-Bois* ; RER D : *Gare de Lyon* à *Saint-Denis*) ;
  - création des variables `retard_min`, `est_supprime`, `zone_tunnel`, `heure_pointe` et `tranche_horaire` ;
  - repérage des anomalies PRIM (décalages aberrants de ±24h sur certains trajets et `delay_sec` figé à 0 sur les arrêts `CANCELLED`).

## Reste à faire

- **Scripts d'analyse (`analyse/`, deux fichiers `.py` à compléter/créer)** :
  - `analyse/nettoyage.py` : consolider les étapes validées dans le notebook et filtrer les retards aberrants (±24h), puis supprimer `analyse/nettoyage_explo.ipynb` ;
  - un second module (ex. `analyse/stats.py`) pour les analyses statistiques :
    - comparaison macro B/D vs A : moyenne, médiane, P90/P95 des retards (hors suppressions), écart heures de pointe / heures creuses, taux de suppression et de retournement avant le tunnel ;
    - contagion dans le tunnel : corrélation des retards moyens par fenêtres de 10-15 min à *Châtelet-Les Halles* et *Gare du Nord*, analyse de décalage temporel (`.shift()`), temps de retour à la normale après un pic (résilience) ;
    - détection automatique des principaux incidents passés (chute de fréquence + hausse des retards), croisée avec les messages de `df_incidents`.
- **Visualisations et application Streamlit (`visualisation/` et `app.py`)** :
  - regrouper les résultats d'analyse et la méthodologie directement dans l'application Streamlit (en remplacement de `rapport.ipynb`) ;
  - construire une carte interactive (géographique et/ou schéma topologique en « H » couché) permettant de rejouer les incidents passés minute par minute, complétée par les messages d'incidents et un diagramme de Marey.
- **Finalisation du dépôt** : remplir `requirements.txt`, supprimer les fichiers temporaires (`analyse/nettoyage_explo.ipynb`, `exploration.py`, `init.ipynb`, `rapport.ipynb`) et préparer les slides dans `soutenance/`.
