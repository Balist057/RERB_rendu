import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.Axe1_constat_naif import COULEURS, LIGNES
from src.axe3_incidents import detecter_incidents, series_tunnel
from src.dashboard_utils import filtres_sidebar

st.title("Axe 3 : Incidents")
st.write(
    "Le tableau classe les principaux épisodes de perturbation détectés dans le tunnel (pics de retard, durée et cause officielle). "
    "Le graphique ci-dessous détaille, pour l'épisode sélectionné, l'évolution du retard par ligne et la chute du débit `B + D` "
    "par rapport au trafic habituel à `Châtelet-Les Halles`."
)

df_all_f, _, df_inc = filtres_sidebar()

if not {"rer_a", "rer_b", "rer_d"}.issubset(df_all_f["line"].unique()):
    st.info("Choisissez une période incluant les 3 lignes (RER D à partir du 07/10).")
    st.stop()

episodes = detecter_incidents(df_all_f, df_inc, top=10)
if episodes.empty:
    st.info("Aucun épisode de crise détecté sur cette période.")
    st.stop()

aff = pd.DataFrame({
    "Date": episodes["date"],
    "Créneau": episodes["debut"] + " - " + episodes["fin"],
    "Durée (min)": episodes["duree_min"],
    "Pic B": episodes["pic_B"],
    "Pic D": episodes["pic_D"],
    "Pic A": episodes["pic_A"],
    "Cause": episodes["cause"],
})
st.dataframe(aff, width="stretch", hide_index=True)

idx_ep = st.selectbox(
    "Épisode à inspecter à Châtelet",
    options=episodes.index.tolist(),
    format_func=lambda i: f"{episodes.loc[i, 'date']} ({episodes.loc[i, 'debut']} - {episodes.loc[i, 'fin']}) | {episodes.loc[i, 'cause']}",
)
ep = episodes.loc[idx_ep]
freq, retard, _, freq_ref = series_tunnel(df_all_f)
t0, t1 = ep["debut_ts"] - pd.Timedelta("1h"), ep["fin_ts"] + pd.Timedelta("1h")
r_ep, f_ep, ref_ep = retard.loc[t0:t1], freq.loc[t0:t1], freq_ref.loc[t0:t1]

fig_ep = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1, row_heights=[0.55, 0.45])
for ligne in ["rer_a", "rer_b", "rer_d"]:
    if ligne in r_ep.columns:
        fig_ep.add_trace(
            go.Scatter(
                x=r_ep.index, y=r_ep[ligne], mode="lines+markers", name=LIGNES[ligne],
                line=dict(color=COULEURS[ligne], width=2), marker=dict(size=4),
            ),
            row=1, col=1,
        )
fig_ep.add_hline(y=10, line_dash="dash", line_color="grey", row=1, col=1)
fig_ep.add_trace(go.Bar(x=f_ep.index, y=f_ep["rer_b"] + f_ep["rer_d"], name="Débit B + D", marker_color="#4C78A8", opacity=0.8), row=2, col=1)
fig_ep.add_trace(go.Scatter(x=ref_ep.index, y=ref_ep, mode="lines", name="Débit habituel", line=dict(color="#888888", dash="dash")), row=2, col=1)

fig_ep.update_yaxes(title_text="Retard (min)", row=1, col=1)
fig_ep.update_yaxes(title_text="Trains / 15 min", row=2, col=1)
fig_ep.update_layout(
    height=480,
    title=dict(text=f"Incident du {ep['date']} ({ep['debut']} - {ep['fin']}) : {ep['cause']}", x=0, y=0.97),
    margin=dict(l=10, r=10, t=85, b=20),
    legend=dict(orientation="h", y=1.03, x=0),
)
st.plotly_chart(fig_ep, width="stretch")

st.divider()
st.markdown(
    """
**À retenir** (données du 02/10 au 26/11/2026) :

- Les 8 plus gros incidents durent **de 2 h à près de 8 h** ; au pire, le nombre de trains dans le tunnel tombe à 15 % de la normale.
- **6 sur 8 touchent B et D ensemble**, alors que A reste presque toujours sous 5 min. Quelques incidents ne concernent qu'une ligne (ex. incident SNCF du 15/10 sur le D seul).
- Le 21/10, le nombre de trains est divisé par deux, D dépasse 50 min de retard puis B suit et reste perturbé plus longtemps ; le diagramme de Marey montre les B coupés avant le tunnel.
"""
)
st.caption("Pour rejouer un épisode sur la carte animée, ouvrez **Replay carte** dans le menu de gauche.")
