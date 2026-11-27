import pandas as pd
import plotly.express as px
import streamlit as st

from src.Axe1_constat_naif import COULEURS, LIGNES, charger
from src.axe3_incidents import charger_incidents

COULEURS_NOMS = {LIGNES[k]: v for k, v in COULEURS.items()}


@st.cache_data
def get_donnees():
    return (*charger(), charger_incidents())


def filtres_sidebar():
    df_all, df_actifs, df_inc = get_donnees()
    d_min, d_max = df_all["date"].min().date(), df_all["date"].max().date()

    with st.sidebar:
        st.header("Filtres")
        plage = st.date_input("Période", value=(d_min, d_max), min_value=d_min, max_value=d_max)
        deb, fin = (
            plage if isinstance(plage, tuple) and len(plage) == 2
            else (plage[0], plage[0]) if isinstance(plage, tuple)
            else (plage, plage)
        )
        sens = st.radio("Sens B / D (A gardé en témoin)", ["Tous", "Nord", "Sud"], horizontal=True)

    ts_deb, ts_fin = pd.Timestamp(deb), pd.Timestamp(fin)
    df_all_f = df_all[df_all["date"].between(ts_deb, ts_fin)]
    df = df_actifs[df_actifs["date"].between(ts_deb, ts_fin)]
    if sens != "Tous":
        df_all_f = df_all_f[(df_all_f["line"] == "rer_a") | (df_all_f["direction"] == sens)]
        df = df[(df["line"] == "rer_a") | (df["direction"] == sens)]

    if df.empty:
        st.warning("Aucune donnée pour ces filtres.")
        st.stop()

    return df_all_f, df, df_inc


def mise_en_page(fig, ylab, height=360):
    fig.update_layout(
        height=height,
        title=dict(x=0, y=0.97),
        margin=dict(l=10, r=10, t=80, b=20),
        legend=dict(orientation="h", y=1.03, x=0, title=None),
        yaxis_title=ylab,
        xaxis_title=None,
    )
    return fig


def tracer_barres(tab, titre, ylab):
    df_m = tab.rename(index=LIGNES).rename_axis("Ligne").reset_index().melt(id_vars="Ligne", var_name="Cat")
    fig = px.bar(
        df_m, x="Cat", y="value", color="Ligne", barmode="group",
        text_auto=".1f", color_discrete_map=COULEURS_NOMS, title=titre,
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    return mise_en_page(fig, ylab)
