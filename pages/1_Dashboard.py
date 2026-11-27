import pandas as pd
import plotly.express as px
import streamlit as st

from src.Axe1_constat_naif import COULEURS, LIGNES, TRANCHES, charger
from src.axe2_contagion import grille_15min, temps_de_retour

st.title("Dashboard")
COULEURS_NOMS = {LIGNES[k]: v for k, v in COULEURS.items()}


@st.cache_data
def get_donnees():
    return charger()


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


df_all, df_actifs = get_donnees()
d_min, d_max = df_all["date"].min().date(), df_all["date"].max().date()

with st.sidebar:
    st.header("Filtres")
    plage = st.date_input("Période", value=(d_min, d_max), min_value=d_min, max_value=d_max)
    deb, fin = plage if isinstance(plage, tuple) and len(plage) == 2 else (plage[0], plage[0]) if isinstance(plage, tuple) else (plage, plage)
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

tab1, tab2, tab3 = st.tabs(["Axe 1 : Constat", "Axe 2 : Contagion", "Axe 3 : Incidents"])

with tab1:
    r = df.groupby("line")["retard_min"]
    retards = pd.DataFrame({"Moyenne": r.mean(), "Médiane": r.median(), "P90": r.quantile(0.9), "P95": r.quantile(0.95)})
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

with tab2:
    chat = grille_15min(df[df["stop_name"] == "Châtelet-Les Halles"])
    if not {"rer_a", "rer_b", "rer_d"}.issubset(chat.columns) or len(chat) < 10:
        st.info("Pas assez de passages simultanés sur A, B et D à Châtelet.")
    else:
        def fmt_min(v):
            return "-" if pd.isna(v) else f"{v:.0f} min"

        corr = chat.corr()
        corr_res = (chat - chat.groupby(chat.index.hour).transform("mean")).corr()
        ret = {l: temps_de_retour(chat[l]).median() for l in ["rer_a", "rer_b", "rer_d"]}

        m1, m2, m3 = st.columns(3)
        m1.metric("Corrélation B / D", f"{corr.loc['rer_b', 'rer_d']:.2f}", f"Placebo B / A : {corr.loc['rer_b', 'rer_a']:.2f}", delta_color="off")
        m2.metric("Corrélation hors heure", f"{corr_res.loc['rer_b', 'rer_d']:.2f}", f"Placebo B / A : {corr_res.loc['rer_b', 'rer_a']:.2f}", delta_color="off")
        m3.metric("Retour médian (> 10 min)", f"B {fmt_min(ret['rer_b'])} / D {fmt_min(ret['rer_d'])}", f"RER A : {fmt_min(ret['rer_a'])}", delta_color="off")

        decals = list(range(-4, 5))
        df_dec = pd.DataFrame({
            "B(t) -> D(t + Δ)": [chat["rer_b"].corr(chat["rer_d"].shift(-d)) for d in decals],
            "B(t) -> A(t + Δ)": [chat["rer_b"].corr(chat["rer_a"].shift(-d)) for d in decals],
        }, index=[d * 15 for d in decals])
        fig_dec = px.line(
            df_dec, markers=True, title="Corrélation décalée à Châtelet (15 min)",
            color_discrete_map={"B(t) -> D(t + Δ)": COULEURS["rer_d"], "B(t) -> A(t + Δ)": COULEURS["rer_a"]},
        )
        fig_dec.add_vline(x=0, line_dash="dash", line_color="grey")
        mise_en_page(fig_dec, "Corrélation")
        fig_dec.update_xaxes(title_text="Décalage (min)", tickvals=[d * 15 for d in decals])

        _, col_sel = st.columns(2)
        decl = col_sel.radio("Ligne déclencheuse", ["RER B", "RER D"], horizontal=True)
        src = "rer_b" if decl == "RER B" else "rer_d"
        tgt = "rer_d" if decl == "RER B" else "rer_b"
        etats = pd.cut(chat[src], [-999, 3, 10, 999], labels=["Fluide (< 3 min)", "Ralenti (3-10 min)", "Perturbé (> 10 min)"])
        dom = chat.groupby(etats, observed=False)[[tgt, "rer_a"]].mean().T

        c1, c2 = st.columns(2)
        c1.plotly_chart(fig_dec, width="stretch")
        c2.plotly_chart(tracer_barres(dom, f"Retard selon l'état du {decl}", "Retard moyen (min)"), width="stretch")

with tab3:
    st.info("Incidents en cours d'ajout.")
