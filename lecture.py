import duckdb

duckdb.execute("CREATE OR REPLACE SECRET (TYPE S3, KEY_ID '', SECRET '', ENDPOINT 'minio.lab.sspcloud.fr', URL_STYLE 'path');")


def read_data(ligne, date):
    """Lire la table de donnees d'une ligne a une date"""
    url = f"https://minio.lab.sspcloud.fr/gpichonlegroux/rer-{ligne}/date%3D{date}/part-0.parquet"
    return duckdb.sql(f"SELECT * FROM '{url}'").df()


def read_data_ligne(ligne):
    """Lire l'integralite des donnees d'une ligne sur toutes les dates"""
    return duckdb.sql(f"SELECT * FROM 's3://gpichonlegroux/rer-{ligne}/date=*/*.parquet' ORDER BY date DESC").df()

print(read_data_ligne("b"))