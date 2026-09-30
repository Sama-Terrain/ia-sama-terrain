"""
Réservation assistée par conversation (chatbot de la page d'accueil).

Trois étapes, chacune avec un rôle bien séparé :

1. L'IA COMPREND : le LLM lit la conversation et renvoie la date, l'heure
   et le terrain demandés, au format JSON. On vérifie ensuite chaque valeur.
2. La PLATEFORME VÉRIFIE : une requête SQL sur les vrais créneaux dit si le
   créneau est libre et à quel prix (jamais le LLM).
3. L'UTILISATEUR CONFIRME : on ne crée aucune réservation et on ne lance
   aucun paiement. On renvoie seulement un lien vers la fiche du terrain,
   où l'amateur confirme et paie avec le parcours habituel.
"""

import json
import logging
from datetime import date, datetime, time, timedelta, timezone

from db import executer
from garde_fous import message_entrant_valide
from llm import demander_au_llm
from texte import normaliser

logger = logging.getLogger("sama_ia")

# On ne cherche que dans les 14 prochains jours.
HORIZON_JOURS = 14

JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# Sujets gérés par le chatbot général (FAQ), pas par la réservation assistée.
AUTRES_SUJETS = ["mes reservation", "ma reservation", "annul", "rembours", "abonnement", "gerant"]


def est_parcours_reservation(message, historique):
    """True si l'utilisateur parle de réserver (maintenant ou juste avant)."""
    if any(sujet in normaliser(message) for sujet in AUTRES_SUJETS):
        return False
    return any("reserv" in normaliser(m) for m in historique + [message])


def repondre(message, historique):
    """Renvoie {"texte", "liens", "proposition"} pour le chatbot."""
    aujourdhui = datetime.now(timezone.utc).date()  # le Sénégal est en UTC
    terrains = executer("SELECT id, nom, ville FROM terrains_terrain WHERE actif = true")

    # L'historique vient du navigateur : on lui applique les mêmes
    # garde-fous qu'au message courant.
    messages = [m for m in historique[-5:] if not message_entrant_valide(m)] + [message]

    # Étape 1 : l'IA comprend la demande.
    try:
        demande = extraire_demande(messages, aujourdhui, terrains)
    except Exception:
        logger.exception("Extraction LLM échouée pour la réservation assistée")
        return reponse(
            "Je n'arrive pas à analyser votre demande pour le moment. "
            "Vous pouvez chercher un terrain directement.",
            [{"label": "Rechercher un terrain", "url": "/terrains"}],
        )

    if not demande["date"]:
        return reponse(f"Pour quel jour souhaitez-vous réserver ? (dans les {HORIZON_JOURS} prochains jours)")
    if not demande["heure"]:
        return reponse("À quelle heure souhaitez-vous jouer ?")

    jour, heure = demande["date"], demande["heure"]
    quand = f"le {JOURS_SEMAINE[jour.weekday()]} {jour.strftime('%d/%m')} à {heure.strftime('%Hh%M')}"

    if jour == aujourdhui and heure <= datetime.now(timezone.utc).time():
        return reponse("Cette heure est déjà passée. Quelle autre heure vous conviendrait ?")

    # Étape 2 : la plateforme vérifie les vrais créneaux libres.
    creneaux = executer(
        """
        SELECT c.id, c.terrain_id, c.date, c.heure_debut, c.heure_fin, c.prix, t.nom, t.ville
        FROM creneaux_creneau c
        JOIN terrains_terrain t ON t.id = c.terrain_id
        WHERE t.actif = true AND c.statut = 'disponible'
          AND c.date = :jour AND c.heure_debut = :heure
          -- L'assistant propose le terrain complet (portion 0), et seulement
          -- si aucune de ses portions n'est déjà prise à cette heure.
          AND c.portion = 0
          AND NOT EXISTS (
            SELECT 1 FROM creneaux_creneau p
            WHERE p.terrain_id = c.terrain_id AND p.date = c.date
              AND p.heure_debut = c.heure_debut AND p.portion > 0
              AND p.statut <> 'disponible'
          )
        """,
        jour=jour,
        heure=heure,
    )

    if not creneaux:
        return reponse(f"Aucun terrain n'est disponible {quand}. Voulez-vous essayer une autre heure ?")

    liens_terrains = [lien(c, f"Voir {c['nom']}") for c in creneaux[:3]]
    liste_terrains = "\n".join(f"- {c['nom']} ({c['ville']}) : {fcfa(c['prix'])}" for c in creneaux)

    if not demande["terrain_id"]:
        return reponse(f"Quel terrain souhaitez-vous réserver ? Disponibles {quand} :\n{liste_terrains}", liens_terrains)

    creneau = next((c for c in creneaux if c["terrain_id"] == demande["terrain_id"]), None)
    if creneau is None:
        return reponse(
            f"Ce terrain n'est pas disponible {quand}, mais ceux-ci le sont :\n{liste_terrains}",
            liens_terrains,
        )

    # Étape 3 : l'utilisateur confirme lui-même sur la fiche du terrain.
    lien_confirmation = lien(creneau, "Confirmer sur la page du terrain")
    return {
        "texte": (
            f"Le créneau {quand} au terrain {creneau['nom']} est disponible pour "
            f"{fcfa(creneau['prix'])}. Voulez-vous confirmer ? Cliquez sur le bouton ci-dessous "
            "pour finaliser vous-même la réservation et le paiement de l'avance."
        ),
        "liens": [lien_confirmation],
        "proposition": {
            "creneau_id": creneau["id"],
            "terrain_id": creneau["terrain_id"],
            "terrain": creneau["nom"],
            "ville": creneau["ville"],
            "date": creneau["date"].isoformat(),
            "heure_debut": creneau["heure_debut"].strftime("%Hh%M"),
            "heure_fin": creneau["heure_fin"].strftime("%Hh%M"),
            "prix": creneau["prix"],
            "url": lien_confirmation["url"],
        },
    }


def extraire_demande(messages, aujourdhui, terrains):
    """
    Demande au LLM de transformer la conversation en JSON, puis vérifie
    chaque valeur : une valeur invalide est remplacée par None.
    """
    liste_terrains = "\n".join(f"- id {t['id']} : {t['nom']} ({t['ville']})" for t in terrains)
    conversation = "\n".join(f"- {m}" for m in messages)

    texte = demander_au_llm(
        [
            {
                "role": "system",
                "content": (
                    "Tu extrais une demande de réservation de terrain de mini-foot. "
                    "Les messages peuvent être en français ou en wolof. Réponds UNIQUEMENT "
                    'avec ce JSON : {"date": "AAAA-MM-JJ", "heure": "HH:MM", "terrain_id": entier}. '
                    "Mets null pour une information non donnée, n'invente rien. "
                    "Le terrain peut être cité par son nom ou son quartier. "
                    "Si l'utilisateur change d'avis, garde sa dernière demande."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Aujourd'hui : {JOURS_SEMAINE[aujourdhui.weekday()]} {aujourdhui.isoformat()}.\n"
                    f"Terrains :\n{liste_terrains}\n\n"
                    f"Messages de l'utilisateur (du plus ancien au plus récent) :\n{conversation}"
                ),
            },
        ],
        temperature=0,
    )

    # Le LLM entoure parfois le JSON de texte : on ne garde que {...}.
    donnees = json.loads(texte[texte.find("{"):texte.rfind("}") + 1])

    demande = {"date": None, "heure": None, "terrain_id": None}

    try:
        jour = date.fromisoformat(str(donnees.get("date")))
        if aujourdhui <= jour <= aujourdhui + timedelta(days=HORIZON_JOURS):
            demande["date"] = jour
    except ValueError:
        pass

    try:
        demande["heure"] = time.fromisoformat(str(donnees.get("heure")))
    except ValueError:
        pass

    if donnees.get("terrain_id") in [t["id"] for t in terrains]:
        demande["terrain_id"] = donnees["terrain_id"]

    return demande


def reponse(texte, liens=None):
    return {"texte": texte, "liens": liens or [], "proposition": None}


def lien(creneau, label):
    """Lien vers la fiche du terrain, avec la date et le créneau présélectionnés."""
    return {
        "label": label,
        "url": f"/terrains/{creneau['terrain_id']}?date={creneau['date'].isoformat()}&creneau={creneau['id']}",
    }


def fcfa(montant):
    return f"{montant:,}".replace(",", " ") + " FCFA"
