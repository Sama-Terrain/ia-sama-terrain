import os

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# Le service IA lit directement dans la même base Postgres que Django (lecture
# seule) : c'est plus simple que de dupliquer les modèles, et ça garantit
# qu'on travaille toujours sur de vraies données, jamais mockées.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://sama_user:sama_password@db:5432/sama_terrain",
)

engine = create_engine(DATABASE_URL)


def executer(sql, **params):
    """Exécute une requête SELECT et renvoie la liste des lignes (dicts)."""
    with engine.connect() as connexion:
        resultat = connexion.execute(text(sql), params)
        return [dict(ligne._mapping) for ligne in resultat]


def executer_ecriture(sql, **params):
    """Exécute une requête UPDATE/INSERT (aucune ligne renvoyée) et commit."""
    with engine.begin() as connexion:
        connexion.execute(text(sql), params)
