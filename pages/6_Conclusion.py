import streamlit as st

st.title("Conclusion")

st.divider()
st.header("Réponse à la problématique")
st.markdown(
    """
Les trois axes vont dans le même sens :

1. **Constat (axe 1)** : B et D sont plus en retard que A, surtout lors des perturbations graves, et ce retard se crée dans le tunnel commun, particulièrement à sa sortie.
2. **Contagion (axe 2)** : les retards de B et D évoluent ensemble, le retard de B précède celui de D d'environ 15 minutes, et l'effet joue dans les deux sens. Le RER A, utilisé comme placebo, ne montre pas ce lien. B met aussi plus longtemps à revenir à la normale.
3. **Incidents (axe 3)** : 6 des 8 principaux épisodes de crise touchent B et D ensemble, avec une forte chute du nombre de trains dans le tunnel, alors que A reste stable. Quelques incidents restent toutefois propres à une seule ligne.

L'hypothèse d'un **effet domino dans le tunnel B / D** est donc **confortée par les données**.
"""
)

st.divider()
st.header("Limites")
st.markdown(
    """
- **Corrélation n'est pas causalité** : B et D diffèrent aussi de A par leur longueur, leurs branches et leur exploitation (deux opérateurs, RATP et SNCF).
- **Les liens mesurés restent modérés** : une corrélation d'environ 0,26 montre une tendance, pas une transmission systématique de chaque retard.
- **Les données temps réel sont imparfaites** : la collecte du RER D commence plus tard, il existe des trous de collecte, et le retard des trains supprimés n'est pas renseigné.
- **Plusieurs seuils sont des choix** : 3, 5 et 10 minutes, fenêtres de 15 minutes, critères de crise. Les conclusions devraient être vérifiées avec d'autres valeurs.
- **La période est courte** (un peu moins de deux mois, en automne) et s'allonge à chaque mise à jour des données : les chiffres peuvent légèrement évoluer.
"""
)

st.divider()
st.header("Pistes")
st.markdown(
    """
- Prolonger la collecte sur plusieurs saisons (hiver, vacances scolaires) et croiser les retards avec les données de météo ou de fréquentation.
"""
)

st.divider()
st.header("Usage de l'IA générative")
st.write(
    "Nous avons utilisé une IA générative pour nous aider à structurer et simplifier une partie du code "
    "et la mise en forme des graphiques. Les analyses et leur interprétation ont été réalisées par l'équipe."
)
