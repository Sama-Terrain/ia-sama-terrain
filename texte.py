import unicodedata


def enlever_accents(texte):
    """
    Retire les accents ("réservation" -> "reservation") pour comparer les
    messages sans dépendre de la façon dont l'utilisateur les tape (beaucoup
    écrivent sans accents, surtout sur mobile).
    """
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    )


def normaliser(texte):
    """Minuscules + sans accents : forme utilisée pour toutes les comparaisons."""
    return enlever_accents(texte.lower())
