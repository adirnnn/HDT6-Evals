"""programa de carga: parsea el corpus de faqs, calcula embeddings y llena la tabla."""

import json
import os
import re
import sys

from db import cargar_entorno, conectar, crear_esquema, embeber, vector_literal, TABLA

# fuerzo utf-8 en la salida para que los acentos se vean bien en cualquier consola
for _flujo in (sys.stdout, sys.stderr):
    try:
        _flujo.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# los bloques del corpus vienen separados por una linea de guiones
SEPARADOR = re.compile(r"^-{5,}\s*$", re.MULTILINE)

# un patron por campo, todos estan en su propia linea con la etiqueta al inicio
CAMPOS = {
    "id": re.compile(r"^ID:\s*(.+)$", re.MULTILINE),
    "categoria": re.compile(r"^CATEGOR[IÍ]A:\s*(.+)$", re.MULTILINE),
    "pregunta": re.compile(r"^PREGUNTA:\s*(.+)$", re.MULTILINE),
    "respuesta": re.compile(r"^RESPUESTA:\s*(.+)$", re.MULTILINE),
    "metadata": re.compile(r"^METADATA:\s*(\{.*\})\s*$", re.MULTILINE),
}


def parsear(texto):
    # recorro cada bloque y armo un diccionario por ficha
    fichas = []
    for bloque in SEPARADOR.split(texto):
        if "ID:" not in bloque or "PREGUNTA:" not in bloque:
            continue

        ficha = {}
        for clave, patron in CAMPOS.items():
            m = patron.search(bloque)
            ficha[clave] = m.group(1).strip() if m else ""

        if not ficha["id"] or not ficha["pregunta"]:
            continue

        # la metadata viene como json en una sola linea, si falla la dejo vacia
        try:
            ficha["metadata"] = json.loads(ficha["metadata"]) if ficha["metadata"] else {}
        except json.JSONDecodeError:
            ficha["metadata"] = {}

        fichas.append(ficha)
    return fichas


def ruta_corpus():
    ruta = os.environ.get("CORPUS_FILE", "Corpus_FAQs_Parachute_SA_2026.txt")
    if os.path.isabs(ruta):
        return ruta
    aqui = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(aqui, ruta)


def main():
    cargar_entorno()

    ruta = ruta_corpus()
    if not os.path.exists(ruta):
        sys.exit(f"no encontre el corpus en: {ruta}")

    with open(ruta, encoding="utf-8") as f:
        fichas = parsear(f.read())

    print(f"fichas parseadas: {len(fichas)}")
    if len(fichas) < 100:
        sys.exit("salieron muy pocas fichas, algo anda mal con el parseo del corpus")

    print("calculando embeddings (la primera vez descarga el modelo, aguanta un toque)...")
    vectores = embeber([f["pregunta"] for f in fichas])

    filas = [
        (
            f["id"],
            f["categoria"],
            f["pregunta"],
            f["respuesta"],
            json.dumps(f["metadata"], ensure_ascii=False),
            vector_literal(v),
        )
        for f, v in zip(fichas, vectores)
    ]

    conn = conectar()
    crear_esquema(conn)
    with conn.cursor() as cur:
        # truncate para que correr el loader de nuevo no duplique nada
        cur.execute(f"TRUNCATE {TABLA}")
        cur.executemany(
            f"""
            INSERT INTO {TABLA}
                (id, categoria, pregunta, respuesta, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s, %s::vector)
            """,
            filas,
        )
    conn.commit()

    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TABLA}")
        total = cur.fetchone()[0]
    conn.close()

    print(f"listo: {total} FAQs cargadas en la tabla {TABLA}")


if __name__ == "__main__":
    main()
