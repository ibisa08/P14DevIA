"""Agent de revue de presse : sans tools, il structure ce qui a été dit dans une discussion."""

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from config import get_settings


class ArticleSummary(BaseModel):
    title: str = Field(description="Titre de l'article ou du sujet traité")
    summary: str = Field(description="Synthèse de l'article en quelques phrases")
    source: str | None = Field(
        default=None, description="Média ou source, uniquement s'il est cité dans la discussion"
    )
    url: str | None = Field(
        default=None, description="URL de l'article, uniquement si elle figure dans la discussion"
    )

    @field_validator("url")
    @classmethod
    def keep_http_urls_only(cls, value: str | None) -> str | None:
        # Le front en fait un lien : on écarte tout schéma dangereux (javascript:, data:...)
        if value and value.strip().lower().startswith(("http://", "https://")):
            return value.strip()
        return None


class PressReviewOutput(BaseModel):
    title: str = Field(description="Titre de la revue de presse")
    summary: str = Field(description="Synthèse générale du sujet")
    articles: list[ArticleSummary] = Field(description="Une synthèse par article ou sujet abordé")


REVIEW_INSTRUCTIONS = """\
Tu rédiges des revues de presse pour des journalistes pigistes, en français.

À partir de l'historique d'une discussion et du sujet demandé, produis une revue de presse :
- un titre court et informatif ;
- une synthèse générale du sujet ;
- une synthèse par article ou par sujet d'actualité abordé dans la discussion.

Règles :
- Appuie-toi uniquement sur le contenu de la discussion : n'invente ni fait, ni chiffre, ni
  source, ni URL. Laisse la source et l'URL vides si elles n'apparaissent pas.
- Si la discussion contient peu d'éléments sur le sujet, dis-le dans la synthèse générale
  plutôt que de combler les manques.
- Ton neutre et factuel.
"""

# Comme l'agent de chat : modèle lu dans LLM_MODEL à chaque appel, jamais à l'import
review_agent = Agent(
    name="newsfoundry_review",
    output_type=PressReviewOutput,
    instructions=REVIEW_INSTRUCTIONS,
)


async def generate_review(topic: str, transcript: str) -> PressReviewOutput:
    """Génère une revue de presse structurée à partir de la transcription d'une discussion."""
    # La discussion est passée en texte plutôt qu'en historique brut : cet agent n'a pas de
    # tools, et un historique contenant des appels de tools (étape 6) pourrait être refusé.
    prompt = (
        f"Sujet de la revue de presse : {topic}\n\n"
        f"Historique de la discussion :\n\n{transcript}"
    )
    result = await review_agent.run(prompt, model=get_settings().llm_model)
    return result.output
