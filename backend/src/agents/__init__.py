import pydantic_ai

# Une API gère elle-même ses logs : pas de bannière PydanticAI dans la sortie au premier appel
pydantic_ai.BANNER_ENABLED = False
