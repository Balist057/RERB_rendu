import pandas as pd

df_rera = pd.read_parquet("../data/rer_a_2026-11-24.parquet")
df_rerb = pd.read_parquet("../data/rer_b_2026-11-24.parquet")
df_rerd = pd.read_parquet("../data/rer_d_2026-11-24.parquet")
df_incidents = pd.read_parquet("../data/incidents_2026-11-24.parquet")