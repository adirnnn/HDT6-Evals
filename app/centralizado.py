"""arquitectura centralizada: un solo manager, los especialistas son tools.

el usuario solo habla con agente_manager. el manager decide a cual
especialista delegar (as_tool) y redacta la respuesta final con lo que le
devuelva. los especialistas nunca le hablan directo al usuario.
"""

from agents import Agent

from shared.cli import iniciar
from shared.model import construir_modelo
from shared.prompts import INSTRUCCIONES_AGENDA, INSTRUCCIONES_FAQS, instrucciones_manager
from shared.tools import agendar_cita, buscar_en_faqs, consultar_clima

modelo = construir_modelo()

agente_faqs = Agent(
    name="agente_faqs",
    instructions=INSTRUCCIONES_FAQS,
    model=modelo,
    tools=[buscar_en_faqs],
)

agente_agenda = Agent(
    name="agente_agenda",
    instructions=INSTRUCCIONES_AGENDA,
    model=modelo,
    tools=[consultar_clima, agendar_cita],
)

agente_manager = Agent(
    name="agente_manager",
    instructions=instrucciones_manager(
        "manager",
        [
            "agente_faqs: responde preguntas frecuentes del evento (usa esta tool "
            "para cualquier pregunta de informacion).",
            "agente_agenda: consulta el clima y agenda citas de salto (usa esta "
            "tool para cualquier pedido de agendar o de saber el clima de una fecha).",
        ],
    ),
    model=modelo,
    tools=[
        agente_faqs.as_tool(
            tool_name="agente_faqs",
            tool_description="responde preguntas frecuentes de Parachute S.A. sobre el evento.",
        ),
        agente_agenda.as_tool(
            tool_name="agente_agenda",
            tool_description="consulta el clima y agenda citas de salto revisando el clima antes.",
        ),
    ],
)

if __name__ == "__main__":
    iniciar(agente_manager, "centralizada")
