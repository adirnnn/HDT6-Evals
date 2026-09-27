"""utilidades compartidas entre el loader y el agente: entorno, base y embeddings."""

import os

from dotenv import load_dotenv
import psycopg
from pgvector.psycopg import register_vector

# tabla donde viven las faqs con su vector
TABLA = "faqs"

# dimension del modelo all-MiniLM-L6-v2
DIMENSION = 384

_MODELO = None


def cargar_entorno():
    # lee el .env de la raiz del repo (el mismo que usa app/)
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(raiz, ".env"))


def _url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "falta DATABASE_URL en el .env, copia .env.example a .env y revisalo"
        )
    return url


def conectar():
    # me conecto y dejo lista la extension antes de registrar el tipo vector
    conn = psycopg.connect(_url())
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    return conn


def crear_esquema(conn):
    # deja la tabla y el indice listos, se puede correr varias veces sin romper nada
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLA} (
                id        text PRIMARY KEY,
                categoria text NOT NULL,
                pregunta  text NOT NULL,
                respuesta text NOT NULL,
                metadata  jsonb,
                embedding vector({DIMENSION}) NOT NULL
            )
            """
        )
        cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {TABLA}_embedding_idx
            ON {TABLA} USING hnsw (embedding vector_cosine_ops)
            """
        )
    conn.commit()


def get_modelo(nombre=None):
    # carga el modelo de embeddings una sola vez y lo reusa
    global _MODELO
    if _MODELO is None:
        from sentence_transformers import SentenceTransformer

        nombre = nombre or os.environ.get(
            "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
        )
        _MODELO = SentenceTransformer(nombre)
    return _MODELO


def embeber(textos):
    # devuelve una lista de vectores normalizados, uno por cada texto de entrada
    modelo = get_modelo()
    vectores = modelo.encode(list(textos), normalize_embeddings=True, batch_size=64)
    return [v.tolist() for v in vectores]


def vector_literal(v):
    # pgvector acepta el formato de texto "[x,y,z]" y lo castea a vector con ::vector
    return "[" + ",".join(repr(float(x)) for x in v) + "]"
