import streamlit as st

st.set_page_config(page_title="Projet RER", layout="wide")

pages = [
    st.Page("pages/0_Accueil.py", title="Accueil"),
    st.Page("pages/1_Donnees.py", title="Données"),
    st.Page("pages/2_Axe1_Constat.py", title="Axe 1 : Constat"),
    st.Page("pages/3_Axe2_Contagion.py", title="Axe 2 : Contagion"),
    st.Page("pages/4_Axe3_Incidents.py", title="Axe 3 : Incidents"),
    st.Page("pages/2_Visualisations.py", title="Replay carte"),
]

pg = st.navigation(pages)
pg.run()
