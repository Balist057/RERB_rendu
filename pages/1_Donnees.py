import pandas as pd
import streamlit as st
from src.nettoyage import FICHIERS_BRUTS, PROCESSED_DIR, charger_donnees_propres

st.title("Pipeline de données et nettoyage")
st.write(
    "Présentation des données collectées, de leur volumétrie et des étapes de transformation "
    "entre les fichiers bruts (`data/raw`) et les tables prêtes pour l'analyse (`data/processed`)."
)

st.divider()

# Volumétrie et couverture
st.header("Volumétrie et couverture")
st.write(
    "Les données proviennent de l'API temps réel `PRIM` d'Île-de-France Mobilités, interrogée toutes les `2 minutes` "
    "et stockée sur le bucket S3 du `SSP Cloud`. Le `RER A` sert de ligne témoin (fréquence élevée, voies indépendantes) "
    "face au couple `RER B` / `RER D` qui partage le tunnel central."
)

# Chargement des 4 tables nettoyées
df_a, df_b, df_d, df_inc = charger_donnees_propres(source="local", maj=False)

sources = [
    ("RER A (témoin)", "a", df_a),
    ("RER B (tunnel)", "b", df_b),
    ("RER D (tunnel)", "d", df_d),
]

lignes_resume = []
for nom, code, df in sources:
    fichier_brut = FICHIERS_BRUTS[code]
    fichier_propre = PROCESSED_DIR / f"clean_rer_{code}.parquet"

    nb_trajets = len(pd.read_parquet(fichier_brut, columns=["journey_id"])) if fichier_brut.exists() else None
    taille_brut = round(fichier_brut.stat().st_size / (1024 * 1024), 1) if fichier_brut.exists() else None
    taille_propre = round(fichier_propre.stat().st_size / (1024 * 1024), 1) if fichier_propre.exists() else None

    lignes_resume.append({
        "Source": nom,
        "Trajets bruts": nb_trajets,
        "Taille brute (Mo)": taille_brut,
        "Arrêts propres": len(df),
        "Taille propre (Mo)": taille_propre,
        "Début": df["date"].min().strftime("%d/%m/%Y"),
        "Fin": df["date"].max().strftime("%d/%m/%Y"),
    })

# Ajout de la ligne pour les incidents RATP
fichier_inc_brut = FICHIERS_BRUTS["incidents"]
fichier_inc_propre = PROCESSED_DIR / "clean_incidents.parquet"

lignes_resume.append({
    "Source": "Incidents RATP",
    "Trajets bruts": len(df_inc),
    "Taille brute (Mo)": round(fichier_inc_brut.stat().st_size / (1024 * 1024), 1) if fichier_inc_brut.exists() else None,
    "Arrêts propres": len(df_inc),
    "Taille propre (Mo)": round(fichier_inc_propre.stat().st_size / (1024 * 1024), 1) if fichier_inc_propre.exists() else None,
    "Début": pd.to_datetime(df_inc["date"]).min().strftime("%d/%m/%Y"),
    "Fin": pd.to_datetime(df_inc["date"]).max().strftime("%d/%m/%Y"),
})

df_resume = pd.DataFrame(lignes_resume)

# Affichage du dataframa dans streamlit
st.dataframe(
    df_resume,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Trajets bruts": st.column_config.NumberColumn(format="%d"),
        "Arrêts propres": st.column_config.NumberColumn(format="%d"),
        "Taille brute (Mo)": st.column_config.NumberColumn(format="%.1f Mo"),
        "Taille propre (Mo)": st.column_config.NumberColumn(format="%.1f Mo"),
    },
)

st.divider()

# Fil conducteur : transformation des données
st.header("Étapes de préparation des données")

# Étape 1 : Brut
st.subheader("Étape 1 : Lecture depuis le S3 (`src/lecture.py`)")
st.write(
    "La fonction `update_all()` lit simplement les fichiers Parquet stockés sur le bucket S3 public du `SSP Cloud` "
    "et les enregistre en local dans `data/raw/`."
)
st.write(
    "Pour éviter de tout retélécharger à chaque fois, la mise à jour est incrémentale : si un fichier existe déjà en local, "
    "on repart de sa dernière date. Par exemple, si la dernière mise à jour s'est arrêtée au milieu de la journée, "
    "on écrase cette dernière journée potentiellement incomplète et on la relit entièrement depuis le S3 avant d'ajouter les jours suivants."
)
st.write(
    "À ce stade, **1 ligne = 1 train entier** : tous ses arrêts sont imbriqués à la suite sous forme de liste JSON "
    "dans la colonne `stops`."
)

if FICHIERS_BRUTS["b"].exists():
    df_brut_b = pd.read_parquet(FICHIERS_BRUTS["b"], columns=["date", "journey_id", "mission", "stops"]).head(2)
    df_brut_b["stops"] = df_brut_b["stops"].str.slice(0, 260) + "..."
    st.table(df_brut_b) #table et pas dataframe pour afficher toute la colonne stops

st.write("Chaque dictionnaire de la liste `stops` correspond à un arrêt et contient les champs suivants :")
st.write(
    "- `o` : ordre de l'arrêt dans le trajet (`1`, `2`, ...) ;\n"
    "- `n` : nom de la gare (`stop_name`) ;\n"
    "- `ad` : horaire théorique prévu en UTC (*aimed departure*) ;\n"
    "- `ed` : horaire estimé en temps réel en UTC (*expected departure*) ;\n"
    "- `dt` / `da` : retard au départ et à l'arrivée en secondes (négatif si le train est en avance) ;\n"
    "- `v` : numéro de voie ou de quai ;\n"
    "- `s` : statut de l'arrêt (`ON_TIME`, `CANCELLED`, etc.)"
)

# Étape 2 : DuckDB
st.subheader("Étape 2 : Restructuration et ciblage géographique (`src/nettoyage.py`)")
st.write("Avant de charger les données en mémoire, on exécute avec `DuckDB` les transformations suivantes :")
st.write(
    "- **Éclatement du JSON (`from_json` + `UNNEST`) :** déplie la liste `stops` pour passer de `1 ligne = 1 train` "
    "à `1 ligne = 1 passage en gare`."
)
st.write(
    "- **Ordonnancement chronologique (`stop_order` via `ROW_NUMBER`) :** trie les arrêts par horaire théorique "
    "(`aimed_time`) pour chaque train afin de reconstituer la séquence exacte et le sens de circulation."
)
st.write(
    "- **Calcul du retard local (`delay_added_sec` via `LAG`) :** mesure le retard gagné ou perdu entre deux arrêts "
    "consécutifs (`delay_sec(t) - delay_sec(t-1)`), pour isoler la congestion propre au tunnel."
)
st.write(
    "- **Filtrage sur les tronçons centraux (`GARES_CENTRALES`) :** conserve uniquement les gares du goulot et leurs "
    "approches (`12` gares sur le `RER B`, `5` sur le `RER D` et `5` sur le `RER A`), uniformise `Châtelet-Les Halles` "
    "et convertit les horaires en heure de Paris (`Europe/Paris`)."
)

# Aperçu d'un train juste après charger_ligne()
train_exemple = df_b[df_b["journey_id"] == df_b["journey_id"].iloc[0]].head(6)
st.write("État d'un trajet après `charger_ligne()` :")
cols_etape2 = ["stop_order", "stop_name", "aimed_time", "delay_sec", "delay_added_sec"]
st.dataframe(train_exemple[cols_etape2], use_container_width=True, hide_index=True)

# Étape 3 : Pandas
st.subheader("Étape 3 : Nettoyage statistique et variables supplémentaires (`ajout_variables`)")
st.write("On applique ensuite les règles suivantes avant d'exporter les tables finales dans `data/processed/` :")
st.write(
    "- **Filtrage des anomalies :** conversion du retard en minutes (`retard_min`) et retrait des valeurs aberrantes "
    "hors de l'intervalle `[-15, 180]` min."
)
st.write(
    "- **Indicateurs d'exploitation :** création de `est_supprime` (`status == 'CANCELLED'`) et de `zone_tunnel` "
    "(`Châtelet-Les Halles` et `Gare du Nord`)."
)
st.write(
    "- **Segmentation temporelle :** création de `heure_pointe` (`07h30–09h30` et `17h00–19h30` en semaine) et "
    "`tranche_horaire` (`Pointe matin`, `Heures creuses`, `Pointe soir`, `Soirée`, `Week-end`)."
)

st.write("Aperçu de la table finale `clean_rer_b.parquet` :")
colonnes_apercu = [
    "date", "journey_id", "stop_order", "stop_name",
    "retard_min", "delay_added_sec", "est_supprime", "zone_tunnel", "tranche_horaire",
]
st.dataframe(df_b[colonnes_apercu].head(6), use_container_width=True, hide_index=True)

st.divider()

# Gestion des incidents
st.header("Gestion des alertes incidents (`incidents.parquet`)")
st.write(
    "En parallèle des passages de trains, le collecteur enregistre les alertes trafic de l'API `PRIM`. "
    "Dans cette table, **1 ligne = 1 alerte**, avec sa ligne (`line`), son début (`first_seen`), "
    "sa fin (`last_seen`), son titre (`short_message`) et son détail (`message`)."
)
st.write(
    "Le traitement se fait en deux étapes :\n"
    "- **Extraction (`charger_incidents` dans `src/nettoyage.py`) :** lecture depuis le S3 à partir du `02/10/2026` "
    "et sauvegarde dans `data/processed/clean_incidents.parquet`.\n"
    "- **Filtrage et exploitation (`src/axe3_incidents.py` et `src/replay.py`) :** conversion des heures en `Europe/Paris`, "
    "retrait des messages de **travaux planifiés**, puis extraction de la cause (colis suspect, malaise voyageur, panne...) "
    "pour croiser chaque incident avec les chutes de débit dans le tunnel."
)

st.write("Aperçu de la table `clean_incidents.parquet` :")
cols_inc = ["line", "first_seen", "last_seen", "short_message"]
st.dataframe(df_inc[cols_inc].head(5), use_container_width=True, hide_index=True)

st.divider()

# Limites connues
st.header("Limites des données temps réel")
st.write(
    "- **Décalage de collecte :** la collecte du `RER D` et des messages d'incidents démarre le `07/10/2026` "
    "(contre le `02/10/2026` pour les `RER A` et `B`). Les analyses reposent donc sur des moyennes et des proportions."
)
st.write(
    "- **Trains supprimés :** lorsqu'un arrêt est annulé (`CANCELLED`), son retard est figé à `0` dans le flux API ; "
    "les analyses de retards portent donc uniquement sur les trains effectivement circulés."
)
st.write(
    "- **Couverture des alertes :** le flux d'incidents provient de la RATP et couvre principalement les `RER A` et `B` "
    "(les incidents propres au `RER D`, exploité par la SNCF, sont repérés via la chute de débit en Axe 3)."
)