import os

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def demander_au_llm(messages, temperature=0.4):
    """
    Envoie une conversation (liste de {role, content}) à OpenRouter et
    renvoie le texte de la réponse.

    Pas de modèle entraîné en interne : toute la "réflexion" est déléguée
    à ce LLM externe, qu'on nourrit avec de vraies données (stats de
    réservation, terrains réels) calculées côté Python.
    """
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY manquante : ajoute-la dans IA/.env")

    reponse = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": temperature,
        },
        # Les modèles gratuits d'OpenRouter peuvent être très lents en
        # période de forte affluence (jusqu'à 30-40s de latence observée) :
        # un timeout trop court fait retomber sur le message de secours
        # alors que le modèle aurait fini par répondre.
        timeout=45,
    )
    reponse.raise_for_status()
    donnees = reponse.json()

    # Sous forte charge, certains modèles gratuits renvoient un HTTP 200
    # avec un corps d'erreur (pas de "choices") au lieu d'un vrai 4xx/5xx :
    # on le détecte explicitement pour avoir un message clair dans les logs
    # plutôt qu'un KeyError opaque.
    if "choices" not in donnees:
        raise RuntimeError(f"Réponse OpenRouter inattendue (pas de 'choices') : {donnees}")

    return donnees["choices"][0]["message"]["content"].strip()
