import streamlit as st

st.set_page_config(page_title="Projet RER", layout="wide")

pages = [
    st.Page("pages/0_Accueil.py", title="Accueil"),
    st.Page("pages/1_Donnees.py", title="Données"),
    st.Page("pages/1_Dashboard.py", title="Dashboard"),
    st.Page("pages/2_Visualisations.py", title="Replay carte"),
]

pg = st.navigation(pages)
pg.run()