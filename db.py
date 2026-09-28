import os
# on importe create_engine et text de sqlalchemy pour se connecter à la base de données Postgres et exécuter des requêtes SQL.
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

# On utilise SQLAlchemy pour exécuter des requêtes SQL brutes sur la base de données Postgres.
#**params permet de passer des paramètres à la requête SQL, ce qui est plus sûr que de concaténer des chaînes de caractères (risque d'injection SQL).
def executer(sql, **params):
    """Exécute une requête SELECT et renvoie la liste des lignes (dicts)."""
    with engine.connect() as connexion:
        resultat = connexion.execute(text(sql), params)
        return [dict(ligne._mapping) for ligne in resultat] #_mapping est un attribut de l'objet Row de SQLAlchemy qui permet d'accéder aux colonnes de la ligne sous forme de dictionnaire. Cela permet de convertir chaque ligne du résultat en un dictionnaire, ce qui est plus pratique à manipuler dans le code Python.


def executer_ecriture(sql, **params):
    """Exécute une requête UPDATE/INSERT (aucune ligne renvoyée) et commit."""
    with engine.begin() as connexion:
        connexion.execute(text(sql), params)
