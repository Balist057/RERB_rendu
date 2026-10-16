import duckdb

# Test
url = "https://minio.lab.sspcloud.fr/gpichonlegroux/rer-b/date%3D2026-10-09/part-0.parquet"
df = duckdb.sql(f"SELECT * FROM '{url}'").df()

def read_data(ligne, date):
    """Lire la table de donnees d'une ligne a une date"""
    url = "https://minio.lab.sspcloud.fr/gpichonlegroux/rer-" + ligne + "/date%3D" + date + "/part-0.parquet"
    df = duckdb.sql(f"SELECT * FROM '{url}'").df()
    return df

def read_data_ligne(ligne):
    # TODO : corriger
    query = f"""
    SELECT *
    FROM read_parquet('https://datalab.sspcloud.fr/s3/gpichonlegroux/rer-{ligne}/**/*.parquet', hive_partitioning = true)
    ORDER BY date DESC;
    """
    return duckdb.sql(query).df()
