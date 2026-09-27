"""busqueda de faqs contra la misma tabla pgvector que llena infra/cargar.py."""

import psycopg
from pgvector.psycopg import register_vector

from .config import env, requerido

TABLA = "faqs"
_MODELO = None
_CONEXION = None


def _conectar():
    global _CONEXION
    if _CONEXION is None or _CONEXION.closed:
        conn = psycopg.connect(requerido("DATABASE_URL"))
        register_vector(conn)
        conn.autocommit = True  # aca solo hacemos SELECT
        _CONEXION = conn
    return _CONEXION


def _modelo():
    # mismo modelo que usa infra/cargar.py para llenar la tabla, tiene que
    # coincidir o los vectores no son comparables
    global _MODELO
    if _MODELO is None:
        from sentence_transformers import SentenceTransformer

        nombre = env("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
        _MODELO = SentenceTransformer(nombre)
    return _MODELO


def _vector_literal(v):
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def buscar_en_faqs_raw(consulta, k=4):
    # busqueda semantica en la tabla faqs, devuelve texto listo para el llm
    umbral = float(env("UMBRAL_SIMILITUD", "0.35"))
    k = max(1, min(int(k or 4), 10))
    vector = _modelo().encode([consulta], normalize_embeddings=True)[0]
    vector = _vector_literal(vector)

    conn = _conectar()
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, categoria, pregunta, respuesta,
                   1 - (embedding <=> %s::vector) AS score
            FROM {TABLA}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, vector, k),
        )
        filas = cur.fetchall()

    utiles = [f for f in filas if f[4] >= umbral]
    if not utiles:
        return "SIN_RESULTADOS"

    partes = []
    for id_, categoria, pregunta, respuesta, score in utiles:
        partes.append(
            f"[{id_}] categoria: {categoria} | score: {score:.2f}\n"
            f"PREGUNTA: {pregunta}\n"
            f"RESPUESTA: {respuesta}"
        )
    return "\n\n".join(partes)
