import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from embeddings import (  # noqa: E402
    MockEmbedder,
    charger_chunks,
    creer_embedder,
    texte_chunk,
)

CHUNKS_TEST = [
    {"source": "recueil.pdf", "document": "decret-2022-080-code-marches-publics",
     "article": "1", "titre": "Définitions",
     "texte": "Aux termes du présent décret, on entend par achat public."},
    {"source": "recueil.pdf", "document": "decret-2022-080-code-marches-publics",
     "article": "2", "titre": "Objet",
     "texte": "Le présent décret fixe les seuils de passation des marchés."},
    {"source": "recueil.pdf", "document": "directive-01-2022-ppp",
     "article": "12", "titre": "Appel d'offres ouvert",
     "texte": "L'appel d'offres ouvert en une étape choisit l'offre la plus avantageuse."},
]


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    import index_rag

    chunks = [dict(c) for c in CHUNKS_TEST]
    embed = MockEmbedder(dim=8)
    return index_rag.IndexRAG.construire(embed, chunks)


def test_mock_embedder_deterministe():
    embed = MockEmbedder(dim=8)
    v1 = embed.embeddings(["marchés publics"])
    v2 = embed.embeddings(["marchés publics"])
    v3 = embed.embeddings(["autre chose"])
    assert v1 == v2
    assert v1 != v3
    assert len(v1[0]) == 8


def test_creer_embedder_backends():
    assert isinstance(creer_embedder("mock"), MockEmbedder)
    with pytest.raises(ValueError):
        creer_embedder("inconnu")


def test_texte_chunk_inclut_titre():
    t = texte_chunk({"titre": "Objet", "texte": "le corps", "article": "1"})
    assert t == "Objet le corps"


def test_construire_index_metadonnees(index):
    assert len(index) == len(CHUNKS_TEST)
    assert index.dim == 8
    assert [m["article"] for m in index.metadonnees] == ["1", "2", "12"]


def test_rechercher_top1(index):
    r = index.rechercher("appel d'offres ouvert en une étape", k=1)
    # avec MockEmbedder le rang n'est pas sémantique : on vérifie la structure
    assert len(r) == 1
    assert r[0]["article"] in {"1", "2", "12"}
    assert r[0]["document"] in {c["document"] for c in CHUNKS_TEST}
    assert "score" in r[0]


def test_rechercher_retourne_k(index):
    r = index.rechercher("seuils de passation", k=2)
    assert len(r) == 2
    assert all("texte" in x for x in r)


def test_sauvegarde_rechargement(tmp_path, index):
    import index_rag

    index.sauvegarder(tmp_path, config={"backend": "mock", "dim": 8})
    assert (tmp_path / "index.faiss").exists()
    assert (tmp_path / "meta.json").exists()
    assert (tmp_path / "config.json").exists()

    reload = index_rag.IndexRAG.charger(tmp_path, MockEmbedder(dim=8))
    assert len(reload) == len(CHUNKS_TEST)
    r = reload.rechercher("appel d'offres ouvert en une étape", k=1)
    assert len(r) == 1
    assert r[0]["article"] in {"1", "2", "12"}


def test_construire_sans_chunks_erreur():
    import index_rag

    with pytest.raises(ValueError):
        index_rag.IndexRAG.construire(MockEmbedder(), [])


def test_charger_chunks(tmp_path):
    p = tmp_path / "chunks.json"
    p.write_text(json.dumps({"meta": {"nb_chunks": 1}, "chunks": CHUNKS_TEST[:1]}),
                 encoding="utf-8")
    assert len(charger_chunks(p)) == 1


def test_resoudre_backend(tmp_path):
    import index_rag

    # backend explicite → pas de lecture du disque
    assert index_rag.resoudre_backend(tmp_path, "local") == "local"
    # auto + config.json présent → lit le backend du build
    (tmp_path / "config.json").write_text(
        json.dumps({"backend": "mock", "dim": 8}), encoding="utf-8")
    assert index_rag.resoudre_backend(tmp_path, "auto") == "mock"
    # auto + pas de config.json → erreur claire
    with pytest.raises(FileNotFoundError):
        index_rag.resoudre_backend(tmp_path / "inexistant", "auto")


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data" / "processed"
         / "corpus_chunks.json").exists(),
    reason="corpus_chunks.json non généré",
)
def test_integration_corpus_reel_mock(tmp_path):
    """Indexe le vrai corpus avec MockEmbedder : vérifie la chaîne entière."""
    import index_rag

    from embeddings import charger_chunks

    chunks = charger_chunks(Path("data/processed/corpus_chunks.json"))
    index = index_rag.IndexRAG.construire(MockEmbedder(dim=32), chunks)
    assert len(index) == 647
    r = index.rechercher("appel d'offres ouvert en une étape", k=3)
    # le mock trie par hash (pas sémantique) → on vérifie la chaîne, pas le rang
    assert len(r) == 3
    assert all("document" in x and "article" in x and "score" in x for x in r)
    # après sauvegarde/rechargement, la recherche fonctionne encore
    index.sauvegarder(tmp_path)
    reload = index_rag.IndexRAG.charger(tmp_path, MockEmbedder(dim=32))
    assert len(reload) == 647
    assert len(reload.rechercher("approbation des marchés", k=5)) == 5


if __name__ == "__main__":
    test_mock_embedder_deterministe()
    test_creer_embedder_backends()
    test_texte_chunk_inclut_titre()
    print("tests locaux (fixtures non exécutées ici) : OK")
