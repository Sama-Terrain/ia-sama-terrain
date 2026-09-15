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
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = []
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
        if chunks else np.zeros((0, 384))
    )
    return chunks, embeddings


def rechercher(question, k=3, seuil=0.35):
    """
    Renvoie les k chunks de FAQ les plus proches sémantiquement de la
    question (similarité cosinus), en ne gardant que ceux au-dessus du
    seuil (pour ne pas injecter de contexte hors-sujet dans le prompt).
    """
    chunks, embeddings = get_index()
    if not chunks:
        return []

    modele = get_embedding_model()
    vecteur_question = modele.encode([question], normalize_embeddings=True)[0]
    scores = embeddings @ vecteur_question

    indices_tries = np.argsort(scores)[::-1][:k]
    return [chunks[i] for i in indices_tries if scores[i] >= seuil]
