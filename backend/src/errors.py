"""Format d'erreur unique pour toute l'API : {"detail": "<message lisible>"}."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Traduction des types d'erreurs Pydantic les plus courants
VALIDATION_MESSAGES = {
    "missing": "champ obligatoire",
    "value_error": "valeur invalide",
    "string_type": "doit être une chaîne de caractères",
    "json_invalid": "JSON mal formé",
    "model_attributes_type": "objet JSON attendu",
}


def format_validation_errors(errors: list[dict]) -> str:
    """Transforme la liste d'erreurs Pydantic en une phrase lisible.

    Ex. : « Requête invalide : email (adresse email invalide), password (champ obligatoire) ».
    """
    parts = []
    for error in errors:
        # loc vaut par ex. ("body", "email") : on garde le nom du champ
        field = ".".join(str(item) for item in error["loc"] if item != "body") or "corps"
        if field == "email" and error["type"] == "value_error":
            message = "adresse email invalide"
        else:
            message = VALIDATION_MESSAGES.get(error["type"], "valeur invalide")
        parts.append(f"{field} ({message})")
    return "Requête invalide : " + ", ".join(parts)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": format_validation_errors(exc.errors())},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # Middleware et non exception_handler(Exception) : ce dernier est exécuté par
    # ServerErrorMiddleware, situé AU-DESSUS de CORSMiddleware, donc la réponse 500 n'aurait
    # pas les headers CORS et le navigateur la masquerait en simple « erreur réseau ».
    # Ce middleware doit donc être enregistré AVANT CORSMiddleware (le dernier ajouté
    # est le plus externe).
    @app.middleware("http")
    async def unhandled_error_middleware(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            # Seuls la méthode et le chemin sont journalisés : jamais les headers (token)
            logger.exception("Erreur non gérée sur %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Erreur interne du serveur"},
            )
