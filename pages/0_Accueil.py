import streamlit as st

st.title("Projet RER — Analyse du goulot Châtelet / Gare du Nord")

st.divider()
st.header("Problématique")
st.write(
    "Le tunnel entre Châtelet-Les Halles et Gare du Nord est partagé par les trains du `RER B` et du `RER D`. "
    "En raison des contraintes de signalisation, ce tronçon ne peut accueillir que 6 à 7 trains simultanément. "
    "L'objectif de ce projet est d'observer comment un incident sur l'une des deux lignes provoque la saturation "
    "du tunnel et la propagation des retards sur l'ensemble du corridor."
)

st.divider()
st.header("Périmètre et données")
st.write(
    "L'étude porte sur la petite couronne parisienne, autour du tronc commun Châtelet – Gare du Nord. "
    "Le RER A est également inclus comme ligne témoin pour distinguer un incident localisé sur le goulot B/D "
    "d'une perturbation plus générale sur le réseau."
)
st.write(
    "Les données utilisées proviennent des relevés de circulation temps réel (horaires théoriques et estimés) "
    "et des alertes trafic RATP."
)

st.divider()
st.header("Navigation")
st.write("- **Dashboard** : vue d'ensemble des retards, suppressions et statistiques par ligne.")
st.write("- **Visualisations** : replay carte pour suivre le déplacement des trains et l'occupation du tunnel avant et pendant un incident.")
