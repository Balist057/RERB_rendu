import pandas as pd
import plotly.express as px
import streamlit as st

from src.Axe1_constat_naif import LIGNES, TRANCHES
from src.dashboard_utils import COULEURS_NOMS, filtres_sidebar, mise_en_page, tracer_barres

st.title("Axe 1 : Constat")
st.write(
    "Comparaison des retards du `RER B` et du `RER D` avec ceux du `RER A` (ligne témoin) sur le tronçon central. "
    "Les graphiques distinguent les retards globaux et extrêmes (`P90`, `P95`), le retard pris spécifiquement dans le tunnel, "
    "l'effet des tranches horaires et l'évolution quotidienne (avec un seuil de `5 min` pour repérer les journées dégradées)."
)

_, df, _ = filtres_sidebar()

r = df.groupby("line")["retard_min"]
retards = pd.DataFrame({
    "Moyenne": r.mean(),
    "Médiane": r.median(),
    "P90": r.quantile(0.9),
    "P95": r.quantile(0.95),
})
tunnel = (
    df[df["stop_order"] > 1].groupby(["line", "zone_tunnel"])["delay_added_sec"].mean()
    .unstack().rename(columns={False: "Hors tunnel", True: "Dans le tunnel"})
)

c1, c2 = st.columns(2)
c1.plotly_chart(tracer_barres(retards, "Distribution des retards (tronçon central)", "Retard (min)"), width="stretch")
c2.plotly_chart(tracer_barres(tunnel, "Retard ajouté par arrêt", "Secondes"), width="stretch")

tranches = df.groupby(["line", "tranche_horaire"])["retard_min"].mean().unstack()
tranches = tranches[[t for t in TRANCHES if t in tranches.columns]]
jour = df.groupby(["date", "line"])["retard_min"].mean().unstack().rename(columns=LIGNES)
fig_jour = px.line(jour, color_discrete_map=COULEURS_NOMS, markers=True, title="Retard moyen jour par jour")
fig_jour.update_traces(marker_size=4)
fig_jour.add_hline(y=5, line_dash="dash", line_color="grey", annotation_text="Seuil 5 min")

c3, c4 = st.columns(2)
c3.plotly_chart(tracer_barres(tranches, "Retard moyen par tranche horaire", "Retard (min)"), width="stretch")
c4.plotly_chart(mise_en_page(fig_jour, "Retard (min)"), width="stretch")

st.divider()
st.markdown(
    """
**À retenir** (données du 02/10 au 26/11/2026) :

- B et D sont **2 à 3 fois plus en retard** que A, en moyenne comme à Châtelet, et même un jour ordinaire. Le 95e centile atteint environ 13 min contre 7 pour A.
- **Le retard se crée dans le tunnel**, surtout à sa sortie : B et D y perdent 27 à 41 s par arrêt quand A en rattrape 11.
- La régulation **coupe les trains** : 2 à 3,5 % des B et D sont limités en parcours, contre 0,2 % des A.
"""
)
