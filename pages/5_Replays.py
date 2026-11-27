import datetime
import pandas as pd
import streamlit as st
from src.replay import (
    CAPACITE_MAX_TUNNEL,
    MODES_REPLAY,
    charger_incidents_perturbations,
    charger_journee_corridor,
    construire_carte_replay,
    extraire_dates_disponibles,
    preparer_segments,
)

st.title("Replay RER")

HEURES_PRESETS = {
    "Pointe matin (08:00)": datetime.time(8, 0),
    "Matinée creuse (10:30)": datetime.time(10, 30),
    "Midi (12:30)": datetime.time(12, 30),
    "Pointe soir (17:30)": datetime.time(17, 30),
    "Soirée (20:30)": datetime.time(20, 30),
}

@st.cache_data
def get_incidents():
    return charger_incidents_perturbations()

@st.cache_data
def get_journee(date_str: str):
    return charger_journee_corridor(date_str)

# Barre latérale
df_incidents = get_incidents()
with st.sidebar:
    st.header("Source du replay")
    source_mode = st.radio(
        "Point de départ",
        options=["Depuis un incident", "Date & heure libres"],
        horizontal=True,
    )

    st.divider()
    inc_sel = None
    t_annonce = None

    if source_mode == "Depuis un incident":
        st.subheader("Filtres des incidents")

        # RER B sélectionné par défaut
        lignes_dispo = sorted(df_incidents["line"].dropna().unique().tolist())
        defaut_lignes = ["rer_b"] if "rer_b" in lignes_dispo else lignes_dispo
        lignes_filtrees = st.multiselect(
            "Ligne(s) de l'alerte",
            options=lignes_dispo,
            default=defaut_lignes,
            format_func=lambda x: x.upper().replace("_", " "),
        )
        st.caption(
            "Les alertes textuelles PRIM ne couvrent que les RER A et B (flux SNCF du RER D absent). "
            "Les trains du RER D restent affichés sur la carte ; utilisez « Date & heure libres » pour un incident propre au D."
        )

        # Filtrage par ligne puis par catégorie d'incident
        df_par_ligne = df_incidents[df_incidents["line"].isin(lignes_filtrees)]
        categories_dispo = ["Toutes"] + sorted(df_par_ligne["categorie"].unique().tolist())
        categorie_choisie = st.selectbox("Catégorie d'incident", options=categories_dispo)

        df_inc_filtre = (
            df_par_ligne
            if categorie_choisie == "Toutes"
            else df_par_ligne[df_par_ligne["categorie"] == categorie_choisie]
        )
        st.caption(f"{len(df_inc_filtre)} incident(s) disponible(s)")

        if df_inc_filtre.empty:
            st.warning("Aucun incident ne correspond à ces filtres.")
            st.stop()

        inc_idx = st.selectbox(
            "Incident à rejouer",
            options=df_inc_filtre.index.tolist(),
            format_func=lambda i: df_inc_filtre.loc[i, "label"],
        )

        # Démarrer avant l'annonce pour voir le début réel de la saturation
        marge_avant_min = st.slider(
            "Démarrer avant l'annonce (min)",
            min_value=0, max_value=30, value=5, step=5,
            help="Reculer de 15 min permet de voir la formation du bouchon avant l'annonce officielle.",
        )

        inc_sel = df_incidents.loc[inc_idx]
        t_annonce = inc_sel["t_debut"].floor("min")
        t_start = t_annonce - pd.Timedelta(minutes=marge_avant_min)
        date_str = t_start.strftime("%Y-%m-%d")

    else:
        st.subheader("Créneau libre")
        date_choisie = st.selectbox(
            "Date",
            options=extraire_dates_disponibles(df_incidents),
            format_func=lambda d: d.strftime("%d/%m/%Y"),
        )
        moment_journee = st.selectbox(
            "Moment de la journée",
            options=list(HEURES_PRESETS.keys()) + ["Heure personnalisée"],
        )

        if moment_journee == "Heure personnalisée":
            heure_choisie = st.time_input("Heure de début", value=datetime.time(8, 30), step=300)
        else:
            heure_choisie = HEURES_PRESETS[moment_journee]

        date_str = date_choisie.strftime("%Y-%m-%d")
        t_start = pd.Timestamp(datetime.datetime.combine(date_choisie, heure_choisie)).tz_localize("Europe/Paris")

    st.divider()
    st.subheader("Paramètres du replay")

    mode_choisi = st.radio(
        "Fenêtre d'observation",
        options=list(MODES_REPLAY.keys()),
        index=1,
    )
    mode_config = MODES_REPLAY[mode_choisi]
    duree_min = mode_config["duree_min"]
    afficher_rer_a = st.checkbox("Afficher le RER A (ligne témoin)", value=False)

# Chargement et préparation des circulations
t_end = t_start + pd.Timedelta(minutes=duree_min)
lignes_actives = ["rer_b", "rer_d"] + (["rer_a"] if afficher_rer_a else [])

df_jour_all = get_journee(date_str)
if df_jour_all.empty:
    st.warning(f"Aucune donnée de circulation enregistrée dans data/raw pour le {date_str}.")
    st.stop()

df_jour = df_jour_all[df_jour_all["line"].isin(lignes_actives)].copy()
segs_affichage = preparer_segments(df_jour)
segs_bd = preparer_segments(df_jour_all[df_jour_all["line"].isin(["rer_b", "rer_d"])])

# Carte animée + Détails de l'incident
col_map, col_info = st.columns([2.4, 1])

with col_map:
    fig_map = construire_carte_replay(
        df_jour=df_jour,
        segs_affichage=segs_affichage,
        segs_bd=segs_bd,
        lignes_actives=lignes_actives,
        t_start=t_start,
        mode_config=mode_config,
        t_annonce=t_annonce,
    )
    st.plotly_chart(fig_map, width='stretch', config={"displayModeBar": False})

with col_info:
    if inc_sel is not None:
        st.subheader("Incident sélectionné")
        st.error(
            f"**{inc_sel['line'].upper().replace('_', ' ')}** · *{inc_sel['categorie']}* — {t_annonce.strftime('%d/%m/%Y')}\n\n"
            f"**Annonce :** {inc_sel['t_debut'].strftime('%H:%M')} → {inc_sel['t_fin'].strftime('%H:%M')}\n\n"
            f"**Replay :** {t_start.strftime('%H:%M')} → {t_end.strftime('%H:%M')} "
            f"*(début {marge_avant_min} min avant l'annonce)*\n\n"
            f"{inc_sel['message']}"
        )
    else:
        st.subheader("Créneau observé")
        st.info(
            f"**Date :** {t_start.strftime('%d/%m/%Y')}\n\n"
            f"**Fenêtre :** {t_start.strftime('%H:%M')} → {t_end.strftime('%H:%M')} ({duree_min} min)\n\n"
            f"Observation libre du trafic sur le corridor RER B / RER D."
        )

    df_fenetre = df_jour[df_jour["expected_time"].between(t_start, t_end)]
    if not df_fenetre.empty:
        st.metric(f"Retard moyen ({duree_min} min)", f"{df_fenetre['retard_min'].mean():.1f} min")
        nb_suppr = df_fenetre[df_fenetre["est_supprime"]]["journey_id"].nunique()
        st.metric("Trains supprimés sur la période", nb_suppr)