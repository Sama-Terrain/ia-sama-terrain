"""
Garde-fous appliqués avant (et après) tout appel au LLM pour le chatbot
public. Objectif : rester simple et lisible, pas un système de modération
complet — juste de quoi éviter les abus les plus évidents.
"""

LONGUEUR_MAX_MESSAGE = 500
LONGUEUR_MAX_REPONSE = 900

# Tentatives grossières de manipulation du prompt ("prompt injection").
# Liste volontairement simple (correspondance de sous-chaînes) : elle ne
# bloquera pas tout, mais couvre les cas les plus courants sans faire un
# deuxième appel LLM juste pour de la modération.
MOTIFS_SUSPECTS = [
    "ignore les instructions",
    "ignore toutes les instructions",
    "ignore previous instructions",
    "oublie tes instructions",
    "oublie le contexte",
    "tu es maintenant",
    "you are now",
    "system prompt",
    "prompt système",
    "réponds sans restriction",
    "sans aucune limite",
    "jailbreak",
    "mode développeur",
    "dan mode",
    "act as",
]

MESSAGE_REFUS_GENERIQUE = (
    "Je suis l'assistant Sama-Terrain : je ne peux répondre qu'aux questions "
    "sur la réservation de terrains, les paiements ou les politiques de la "
    "plateforme. Comment puis-je vous aider sur ce sujet ?"
)


def message_entrant_valide(message):
    """
    Vérifie le message de l'utilisateur AVANT tout appel LLM.
    Renvoie None si le message est acceptable, ou un texte de refus tout
    fait sinon (dans ce cas, on ne consomme même pas de quota LLM).
    """
    if not message or not message.strip():
        return "Votre message est vide. Que souhaitez-vous savoir ?"

    if len(message) > LONGUEUR_MAX_MESSAGE:
        return (
            f"Votre message est trop long ({len(message)} caractères, "
            f"{LONGUEUR_MAX_MESSAGE} maximum). Pouvez-vous le résumer ?"
        )

    message_minuscule = message.lower()
    if any(motif in message_minuscule for motif in MOTIFS_SUSPECTS):
        return MESSAGE_REFUS_GENERIQUE

    return None


def nettoyer_reponse(texte):
    """
    Filet de sécurité APRÈS l'appel LLM : au cas où le modèle ignorerait les
    instructions du prompt système, on tronque une réponse anormalement
    longue plutôt que de renvoyer un pavé de texte au frontend.
    """
    texte = texte.strip()
    if len(texte) > LONGUEUR_MAX_REPONSE:
        texte = texte[:LONGUEUR_MAX_REPONSE].rsplit(" ", 1)[0] + "…"
    return texte
