"""
Tests de la réservation assistée, sans base de données ni LLM : les modules
db et llm sont remplacés par des doublures avant l'import.

Lancement : python -m unittest test_reservation_assistee
"""

import json
import sys
import types
import unittest
from datetime import datetime, time, timedelta, timezone

DEMAIN = datetime.now(timezone.utc).date() + timedelta(days=1)

TERRAINS = [
    {"id": 1, "nom": "Almadies Foot Club", "ville": "Almadies"},
    {"id": 2, "nom": "Elite Arena", "ville": "Parcelles Assainies"},
]

# Demain à 20h : seul Almadies Foot Club est libre.
CRENEAUX_LIBRES = [
    {"id": 10, "terrain_id": 1, "date": DEMAIN, "heure_debut": time(20), "heure_fin": time(21),
     "prix": 30000, "nom": "Almadies Foot Club", "ville": "Almadies"},
]


def _executer(sql, **params):
    if "creneaux_creneau" in sql:
        return [c for c in CRENEAUX_LIBRES if c["date"] == params["jour"] and c["heure_debut"] == params["heure"]]
    return TERRAINS


sys.modules["db"] = types.SimpleNamespace(executer=_executer)
sys.modules["llm"] = types.SimpleNamespace(demander_au_llm=None)

import reservation_assistee as ra  # noqa: E402


def llm_repond(date_iso, heure, terrain_id):
    """Simule un LLM qui renvoie le JSON donné."""
    ra.demander_au_llm = lambda *a, **k: json.dumps({"date": date_iso, "heure": heure, "terrain_id": terrain_id})


class ReservationAssisteeTests(unittest.TestCase):

    def test_demande_le_jour_puis_l_heure(self):
        llm_repond(None, None, None)
        self.assertIn("quel jour", ra.repondre("Je veux réserver", [])["texte"])
        llm_repond(DEMAIN.isoformat(), None, None)
        self.assertIn("quelle heure", ra.repondre("demain", ["Je veux réserver"])["texte"])

    def test_demande_le_terrain_si_absent(self):
        llm_repond(DEMAIN.isoformat(), "20:00", None)
        reponse = ra.repondre("Je veux réserver demain à 20h", [])
        self.assertIn("Quel terrain", reponse["texte"])
        self.assertIn("Almadies Foot Club", reponse["texte"])

    def test_propose_le_creneau_verifie_sans_reserver(self):
        llm_repond(DEMAIN.isoformat(), "20:00", 1)
        reponse = ra.repondre("Le terrain Almadies", ["Je veux réserver demain à 20h"])
        self.assertEqual(reponse["proposition"]["prix"], 30000)
        self.assertIn("Voulez-vous confirmer", reponse["texte"])
        self.assertEqual(reponse["liens"][0]["url"], f"/terrains/1?date={DEMAIN.isoformat()}&creneau=10")

    def test_terrain_occupe_propose_les_autres(self):
        llm_repond(DEMAIN.isoformat(), "20:00", 2)
        reponse = ra.repondre("Elite Arena", ["Je veux réserver demain à 20h"])
        self.assertIsNone(reponse["proposition"])
        self.assertIn("Almadies Foot Club", reponse["texte"])

    def test_valeurs_inventees_par_le_llm_ignorees(self):
        llm_repond("2030-01-01", "25:00", 99)
        self.assertIn("quel jour", ra.repondre("je veux reserver", [])["texte"])

    def test_llm_indisponible(self):
        def panne(*a, **k):
            raise RuntimeError("LLM indisponible")
        ra.demander_au_llm = panne
        reponse = ra.repondre("je veux reserver", [])
        self.assertEqual(reponse["liens"][0]["url"], "/terrains")

    def test_autres_sujets_laisses_au_chatbot_general(self):
        self.assertFalse(ra.est_parcours_reservation("Je veux voir mes réservations", []))
        self.assertFalse(ra.est_parcours_reservation("Comment annuler ?", ["Je veux réserver"]))
        self.assertTrue(ra.est_parcours_reservation("Le terrain Almadies", ["Je veux réserver demain"]))


if __name__ == "__main__":
    unittest.main()
