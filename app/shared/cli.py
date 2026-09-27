"""loop de terminal del agente (Bye / Ctrl+C, historial de la conversacion).

no sabe nada de la arquitectura: solo recibe el agente de entrada en iniciar().
los evals no pasan por aca, llaman al agente directo desde evals/provider.py.
"""

import asyncio
import sys

from agents import Runner

SALIDAS = {"bye", "adios", "adiós", "salir"}


def _despedida():
    print("\nAgente> Gracias por tu interes en Parachute S.A. Hasta pronto.\n")


async def _loop(agente_inicial, nombre_arquitectura):
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    print("=" * 60)
    print(f" Parachute S.A. | arquitectura {nombre_arquitectura}")
    print(f" agente de entrada: {agente_inicial.name}")
    print('  Escribe "Bye" o presiona Ctrl+C para salir.')
    print("=" * 60 + "\n")

    historial = []
    agente_actual = agente_inicial

    while True:
        try:
            pregunta = input("Tu> ").strip()
        except EOFError:
            break

        if not pregunta:
            continue
        if pregunta.lower() in SALIDAS:
            break

        historial = historial + [{"role": "user", "content": pregunta}]

        try:
            resultado = await Runner.run(agente_actual, historial)
            print(f"\nAgente> {resultado.final_output}\n")
            historial = resultado.to_input_list()
            # si hubo un handoff, la conversacion se queda con quien la tomo
            agente_actual = resultado.last_agent
        except Exception as e:  # noqa: BLE001  un error de api no debe tumbar el loop
            historial = historial[:-1]  # saco la pregunta que fallo
            print(f"\nAgente> Ocurrio un error al responder: {e}\n")

    _despedida()


def iniciar(agente_inicial, nombre_arquitectura):
    try:
        asyncio.run(_loop(agente_inicial, nombre_arquitectura))
    except KeyboardInterrupt:
        _despedida()
