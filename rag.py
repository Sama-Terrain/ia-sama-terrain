from functools import lru_cache
from pathlib import Path

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

# Modèle multilingue (fonctionne bien en français), petit et rapide en CPU —
# largement suffisant pour une poignée de documents de FAQ.
NOM_MODELE = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

DOSSIER_FAQ = Path(__file__).parent / "faq"


@lru_cache(maxsize=1)
def get_embedding_model():
    """Charge le modèle d'embeddings une seule fois (singleton)."""
    return SentenceTransformer(NOM_MODELE)


def charger_documents():
    """Lit tous les fichiers texte de IA/faq/."""
    return [
        fichier.read_text(encoding="utf-8")
        for fichier in sorted(DOSSIER_FAQ.glob("*.txt"))
    ]


def split_documents(documents):
    """Découpe les documents en chunks avec LangChain."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50) #chunk_size est la taille maximale d'un chunk (en caractères) et chunk_overlap est le nombre de caractères qui se chevauchent entre deux chunks consécutifs. Cela permet de conserver un peu de contexte entre les chunks.
    chunks = []

    # On découpe chaque document en chunks et on les ajoute à la liste chunks.
    #.exetends() permet d'ajouter les éléments d'une liste à une autre liste (ici, on ajoute les chunks du document courant à la liste chunks).
    for document in documents:
        chunks.extend(splitter.split_text(document))
    return chunks


@lru_cache(maxsize=1)
def get_index():
    """Construit l'index (chunks + embeddings) une seule fois (singleton)."""
    documents = charger_documents()
    chunks = split_documents(documents)

    modele = get_embedding_model()
    embeddings = (
        modele.encode(chunks, normalize_embeddings=True)
        if chunks else np.zeros((0, 384)) #.zeros((0, 384)) crée un tableau numpy vide avec 0 lignes et 384 colonnes (la dimension des embeddings du modèle). Cela permet de gérer le cas où il n'y a pas de chunks à encoder, pour éviter une erreur lors de l'appel à modele.encode().
    )
    return chunks, embeddings


def rechercher(question, k=3, seuil=0.35):
    """
    Renvoie les k chunks de FAQ les plus proches sémantiquement de la
    question (similarité cosinus), en ne gardant que ceux au-dessus du
    seuil (pour ne pas injecter de contexte hors-sujet dans le prompt).
    """

    # Récupère les morceaux de texte (chunks) et leurs vecteurs (embeddings)
    # depuis l'index de recherche.
    chunks, embeddings = get_index() 

    if not chunks:
        return []

    # Récupère le modèle utilisé pour transformer du texte en vecteur numérique.
    modele = get_embedding_model()

    # Transforme la question de l'utilisateur en vecteur numérique.
    # normalize_embeddings=True normalise le vecteur pour faciliter la comparaison
    # avec les autres vecteurs.
    # [0] permet de récupérer le premier (et ici l'unique) vecteur généré.
    vecteur_question = modele.encode([question], normalize_embeddings=True)[0]

    # Compare le vecteur de la question avec tous les vecteurs des chunks.
    # Le symbole @ effectue ici une multiplication matricielle.
    # Comme les vecteurs sont normalisés, le résultat correspond à une
    # mesure de similarité entre la question et chaque chunk.
    scores = embeddings @ vecteur_question

    # Trie les indices des chunks selon leur score de similarité,
    # du plus élevé au plus faible.
    # [::-1] inverse l'ordre pour avoir les meilleurs scores en premier.
    # [:k] garde uniquement les k premiers résultats.
    indices_tries = np.argsort(scores)[::-1][:k]

    # Retourne les chunks correspondant aux meilleurs scores,
    # mais uniquement si leur score est supérieur ou égal au seuil défini.
    return [chunks[i] for i in indices_tries if scores[i] >= seuil]
