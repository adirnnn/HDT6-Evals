"""resume reports/reporte.json (salida de promptfoo) en tablas markdown.

uso:  python evals/resumen.py [reports/reporte.json]

agrupa cada assertion en las cuatro familias que pide la hoja (factuality,
deterministicas, latencia, tool execution) mas las de rag, y cuenta cuantas
pasaron por funcionalidad (faqs / agenda). tambien saca la latencia p50 / p95
de cada funcionalidad y los reintentos 429 que vio el agente.
"""

import io
import json
import os
import sys
from collections import defaultdict

_FAMILIAS = {
    "factuality": "Factuality",
    "llm-rubric": "Factuality",
    "context-faithfulness": "RAG (faithfulness)",
    "contains": "Deterministicas",
    "icontains": "Deterministicas",
    "icontains-any": "Deterministicas",
    "not-icontains": "Deterministicas",
    "regex": "Deterministicas",
    "not-regex": "Deterministicas",
    "latency": "Latencia",
    "python": "Tool execution",
}
_ORDEN = ["Factuality", "RAG (faithfulness)", "Deterministicas", "Latencia", "Tool execution"]


def _funcionalidad(descripcion):
    return "agenda" if descripcion.startswith("agenda") else "faqs"


def _percentil(valores, p):
    if not valores:
        return 0
    valores = sorted(valores)
    k = max(0, min(len(valores) - 1, round(p / 100 * (len(valores) - 1))))
    return valores[k]


def main(ruta):
    with io.open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    resultados = datos["results"]["results"]

    casos = defaultdict(lambda: [0, 0])
    familias = defaultdict(lambda: [0, 0])
    latencias = defaultdict(list)
    reintentos = defaultdict(int)
    errores = 0

    for r in resultados:
        func = _funcionalidad(r["testCase"].get("description", ""))
        casos[func][1] += 1
        if r.get("success"):
            casos[func][0] += 1
        if r.get("error") and not (r.get("gradingResult") or {}).get("componentResults"):
            errores += 1
        meta = (r.get("response") or {}).get("metadata") or {}
        if r.get("latencyMs"):
            latencias[func].append(r["latencyMs"])
        reintentos[func] += meta.get("reintentos_429", 0) or 0
        for c in (r.get("gradingResult") or {}).get("componentResults", []):
            familia = _FAMILIAS.get(c["assertion"]["type"], c["assertion"]["type"])
            familias[(familia, func)][1] += 1
            if c.get("pass"):
                familias[(familia, func)][0] += 1

    def celda(par):
        ok, total = par
        return f"{ok}/{total} ({ok / total:.0%})" if total else "-"

    print("| Funcionalidad | Casos que pasan | Latencia p50 | Latencia p95 | Reintentos 429 |")
    print("|---|---|---|---|---|")
    for func in ("faqs", "agenda"):
        lat = latencias[func]
        print(
            f"| {func} | {celda(casos[func])} | {_percentil(lat, 50) / 1000:.1f} s "
            f"| {_percentil(lat, 95) / 1000:.1f} s | {reintentos[func]} |"
        )
    print()
    print("| Familia de eval | FAQs | Agenda |")
    print("|---|---|---|")
    for familia in _ORDEN:
        print(f"| {familia} | {celda(familias[(familia, 'faqs')])} | {celda(familias[(familia, 'agenda')])} |")
    if errores:
        print(f"\ncasos con error del provider: {errores}")


if __name__ == "__main__":
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(raiz, "reports", "reporte.json"))
