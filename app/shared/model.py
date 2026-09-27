"""arma el modelo de agents sdk apuntado a groq (api compatible con openai)."""

from agents import AsyncOpenAI, OpenAIChatCompletionsModel, set_tracing_disabled

from .config import env, requerido

_CONFIGURADO = False
_MODELO = None


def construir_modelo():
    """crea el modelo que usan todos los agentes. se llama una sola vez y se
    reusa la misma instancia en el manager y en los especialistas: ningun
    agente sabe que esta hablando con groq en vez de con openai."""
    global _CONFIGURADO, _MODELO
    if _MODELO is not None:
        return _MODELO

    if not _CONFIGURADO:
        # no tenemos api key de openai, asi que apagamos el tracing por defecto
        set_tracing_disabled(True)
        _CONFIGURADO = True

    cliente = AsyncOpenAI(
        api_key=requerido("GROQ_API_KEY"),
        base_url=env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
    )
    _MODELO = OpenAIChatCompletionsModel(
        model=env("GROQ_MODEL", "openai/gpt-oss-20b"),
        openai_client=cliente,
    )
    return _MODELO
