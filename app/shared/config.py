"""configuracion compartida: variables de entorno y constantes del negocio."""

import os

from dotenv import load_dotenv

# coordenadas fijas de la pista de aterrizaje (pedidas por la hoja de trabajo)
LATITUD = 14.013722
LONGITUD = -90.771611

# zona horaria del evento, se usa para calcular "hoy" y las fechas de las citas
ZONA_HORARIA = "America/Guatemala"

# open-meteo permite prediccion hasta 16 dias hacia adelante
MAX_DIAS_PREDICCION = 16

_CARGADO = False


def cargar_entorno():
    # lee el .env de la raiz del repo, una sola vez por proceso
    global _CARGADO
    if _CARGADO:
        return
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(raiz, ".env"))
    _CARGADO = True


def env(nombre, default=None):
    cargar_entorno()
    return os.environ.get(nombre, default)


def requerido(nombre):
    valor = env(nombre)
    if not valor:
        raise RuntimeError(
            f"falta la variable {nombre} en el .env de la raiz, copia .env.example a .env y revisala"
        )
    return valor
