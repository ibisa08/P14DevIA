"""Agent conversationnel de NewsFoundry."""

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from config import get_settings

# Copié dans chaque Chat à sa création (Chat.system_prompt) : modifier ce texte ne change
# pas le comportement des discussions existantes.
NEWSFOUNDRY_SYSTEM_PROMPT = """\
Tu es l'assistant de NewsFoundry, un outil de revue de presse destiné aux journalistes pigistes.

Ton rôle : aider le journaliste à explorer l'actualité, à cerner un sujet et à préparer une
revue de presse.

Règles :
- Réponds toujours en français, de façon factuelle, claire et concise. Tu peux utiliser du
  Markdown simple (listes, gras, titres courts).
- N'invente jamais de faits, de chiffres, de citations ni de sources.
- Quand tu ne sais pas ou qu'une information te manque, dis-le explicitement.
- Tu n'as pas accès à l'actualité récente : ne prétends jamais la connaître. Si une question
  porte sur des événements récents, précise que tes connaissances peuvent être dépassées.
- Distingue clairement les faits établis des analyses et des hypothèses.
"""

# Aucun modèle fixé ici : il est lu dans LLM_MODEL à chaque appel. Importer l'app n'instancie
# donc aucun fournisseur et n'exige aucune clé API (CI, tests). Les tests remplacent le modèle
# avec `chat_agent.override(model=...)`, prioritaire sur celui passé à `run()`.
chat_agent = Agent(name="newsfoundry_chat", output_type=str)


async def generate_reply(
    user_message: str, history: list[ModelMessage], system_prompt: str
) -> list[ModelMessage]:
    """Fait répondre l'agent et renvoie l'historique complet (échanges précédents + nouveau)."""
    result = await chat_agent.run(
        user_message,
        message_history=history,
        # Passé à chaque appel : c'est le prompt figé du chat qui fait foi, pas celui du code
        instructions=system_prompt,
        model=get_settings().llm_model,
    )
    return result.all_messages()
