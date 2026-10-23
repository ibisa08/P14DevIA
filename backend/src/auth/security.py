from functools import lru_cache

import bcrypt


def hash_password(password: str) -> str:
    # hashpw renvoie des bytes : on stocke la chaîne décodée dans la colonne str
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        # Hash mal formé en base, ou mot de passe > 72 octets refusé par bcrypt >= 5 :
        # on répond « invalide » plutôt que de laisser remonter une erreur 500.
        return False


@lru_cache
def dummy_password_hash() -> str:
    """Hash factice comparé quand l'email est inconnu.

    Le login prend alors le même temps (~un checkpw) que l'email existe ou non :
    la durée de réponse ne permet pas de deviner quels comptes existent.
    """
    return hash_password("mot-de-passe-factice")
