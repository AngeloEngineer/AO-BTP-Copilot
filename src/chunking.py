"""
Chunking du corpus légal (Recueil ARCOP 2024) pour le RAG.

But : produire des **chunks** = unités de sens citable (article de loi) qui seront
transformées en vecteurs puis indexées (FAISS).

Problème découvert le 18/08/2026 : le PDF du recueil est en 2 colonnes ; l'extraction
PyMuPDF par défaut suit l'ordre du flux, ce qui **intercale les articles** (ex. l'ordre
4, 3, 2 au lieu de 2, 3, 4). On corrige donc en **ré-extrayant par blocs triés sur
leurs coordonnées** (y puis x), ce qui rétablit l'ordre logique (126 → 12 baisses
restantes, toutes = redémarrage de numérotation entre deux textes).

Le découpage se fait **par article** (`Article N : ...`), conformément à la décision
documentée (§17 / §38.2). Chaque article est rattaché à son **document** (directive,
loi ou décret) via une table de motifs discriminants construits sur le contenu réel.

Usage :
    python src/chunking.py --pdf data/raw/corpus_legal/*.pdf
                           --out data/processed/corpus_chunks.json
                           [--texte-ordonne data/processed/corpus_legal_texte_ordonne.txt]
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path

# --- Ré-extraction ordonnée du PDF (corrige le désordre 2 colonnes) -------

_LIGATURES = {
    "\ufb00": "ff",  # ﬀ
    "\ufb01": "fi",  # ﬁ
    "\ufb02": "fl",  # ﬂ
    "\ufb03": "ffi",  # ﬃ
    "\ufb04": "ffl",  # ﬄ
}
_APOSTROPHES = {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'}


def normaliser_ligatures(texte: str) -> str:
    """Normalise les glyphes typographiques du PDF pour fiabiliser le texte.

    - ligatures (ﬁ, ﬀ, ﬂ…) : un seul codepoint U+FB00..FB04 → lettres séparées ;
    - apostrophes/guillemets courbes (U+2018/19/1C/1D) → formes ASCII.
    Sans cela, les motifs de recherche et les futurs embeddings sont faussés.
    """
    for lig, aplat in _LIGATURES.items():
        texte = texte.replace(lig, aplat)
    for a, b in _APOSTROPHES.items():
        texte = texte.replace(a, b)
    return texte


def extraire_texte_ordonne(pdf_path: Path) -> str:
    """Extrait le texte du PDF en triant les blocs par coordonnées (y puis x).

    PyMuPDF extrait les blocs d'une page dans l'ordre du flux du fichier. Pour un
    PDF 2 colonnes, cela mélange les colonnes. Le tri (y arrondi, x) restaure
    l'ordre de lecture gauche→droite, haut→bas.
    """
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    pages: list[str] = []
    for page in doc:
        blocs = page.get_text("blocks")
        blocs.sort(key=lambda b: (round(b[1] / 12.0), b[0]))
        pages.append("\n".join(b[4].strip() for b in blocs).strip())
    return normaliser_ligatures("\n".join(p for p in pages if p))


# --- Découpage par article ---------------------------------------------------

PAT_ARTICLE = re.compile(
    r'^(?:Article|Art\.?)\s+(premier|1er|\d+)\s*[:;]?\s*(?P<titre>.*)$',
    re.IGNORECASE,
)
# Lignes parasite d'en-tête de page / artéfacts d'extraction à retirer
PAT_HEADER_PAGE = re.compile(
    r'^(DIRECTIVE|LOI|DECRET|DÉCRET)\s*N°[^\n]{0,80}$', re.IGNORECASE
)
PAT_ARTEFACT = re.compile(r'^(er|ER|e|l’|l\')$')
PAT_NUMERO_PAGE = re.compile(r'^\d{1,4}$')


@dataclass
class Article:
    """Un article découpé du corpus."""

    num: int | str          # nombre d'article (premier → 1)
    titre: str              # intitulé de l'article (après « Article N : »)
    texte: str              # corps de l'article (hors en-tête)
    ligne_debut: int        # ligne de début dans le texte ordonné (1-based)
    ligne_fin: int          # ligne de fin (inclus)
    document: str = ""      # identifiant du document (rempli après attribution)


def _nettoie_ligne(ligne: str) -> str:
    """Supprime les artéfacts d'extraction d'une ligne (sinon la retourne)."""
    s = ligne.strip()
    if not s:
        return ""
    if PAT_HEADER_PAGE.match(s) or PAT_ARTEFACT.match(s) or PAT_NUMERO_PAGE.match(s):
        return ""
    if len(s) <= 2 and not s.isalnum():
        return ""
    return s


def decouper_en_articles(texte: str) -> list[Article]:
    """Découpe le texte ordonné en articles.

    Chaque bloc va de la ligne « Article N : ... » jusqu'à la ligne précédant le
    titre d'article suivant (ou la fin du texte).
    """
    lignes = texte.split("\n")
    positions: list[tuple[int, int | str, str]] = []  # (index, num, titre)
    for i, ligne in enumerate(lignes):
        m = PAT_ARTICLE.match(ligne.strip())
        if m:
            num_raw = m.group(1)
            num: int | str = 1 if num_raw in ("premier", "1er") else int(num_raw)
            positions.append((i, num, m.group("titre").strip()))

    articles: list[Article] = []
    for k, (idx, num, titre) in enumerate(positions):
        fin = positions[k + 1][0] if k + 1 < len(positions) else len(lignes)
        corps: list[str] = []
        for j in range(idx + 1, fin):
            s = _nettoie_ligne(lignes[j])
            if s:
                corps.append(s)
        texte = " ".join(corps)
        if not texte and titre:
            # article très court : tout le corps est sur la ligne de l'en-tête
            texte = titre
            titre = ""
        articles.append(
            Article(
                num=num,
                titre=titre,
                texte=texte,
                ligne_debut=idx + 1,
                ligne_fin=fin,
            )
        )
    return articles


# --- Attribution documentaire -------------------------------------------------

# Table des textes du recueil (ordre réel de lecture, vérifié sur le contenu le
# 18/08/2026 — 14 corps de textes : 2 lois, 9 décrets, 2 directives, 1 arrêté).
# `motif` = chaîne présente dans l'article 1 du texte → sert de contrôle lors de
# l'attribution (l'attribution elle-même se fait par resets de numérotation).
DOCUMENTS: list[dict] = [
    {"id": "directive-01-2022-ppp",
     "libelle": "DIRECTIVE N° 01/2022/CM/UEMOA portant cadre juridique et "
                "institutionnel des partenariats public privé",
     "motif": "présente Directive"},
    {"id": "loi-2021-033-marches-publics",
     "libelle": "LOI N° 2021-033 du 31 décembre 2021 relative aux marchés publics",
     "motif": "règles régissant la passation, l'exécution, le contrôle et la "
              "régulation des marchés publics"},
    {"id": "decret-2022-080-code-marches-publics",
     "libelle": "DÉCRET N° 2022-080/PR du 06 juillet 2022 portant code des "
                "marchés publics",
     "motif": "Aux termes du présent décret, on entend par"},
    {"id": "decret-2022-063-arcop",
     "libelle": "DÉCRET N° 2022-063/PR du 11 mai 2022 portant attributions, "
                "organisation et fonctionnement de l'Autorité de régulation de la "
                "commande publique (ARCOP)",
     "motif": "en abrégé « ARCOP »"},
    {"id": "decret-2022-070-dnccp",
     "libelle": "DÉCRET N° 2022-070/PR du 30 mai 2022 portant attributions, "
                "organisation et fonctionnement de la direction nationale du "
                "contrôle de la commande publique (DNCCP)",
     "motif": "en abrégée DNCCP"},
    {"id": "decret-2022-092-redevance",
     "libelle": "DÉCRET N° 2022-092/PR du 25/08/2022 fixant le taux, les modalités "
                "de recouvrement et d'affectation de la redevance de régulation du "
                "système des marchés publics",
     "motif": "taux ainsi que les modalités de recouvrement et d'affectation de la "
              "redevance de régulation"},
    {"id": "decret-2019-096-maitrise-ouvrage",
     "libelle": "DÉCRET N° 2019-096/PR portant réglementation de la maîtrise "
                "d'ouvrage public déléguée",
     "motif": "la maîtrise d'ouvrage public déléguée et la maîtrise d'œuvre"},
    {"id": "decret-2019-097-ethique",
     "libelle": "DÉCRET N° 2019-097/PR portant code d'éthique et de déontologie "
                "dans la commande publique",
     "motif": "règles d'éthique et de déontologie applicables"},
    {"id": "decret-2018-171-seuils",
     "libelle": "DÉCRET N° 2018-171/PR du 22 novembre 2018 portant adoption des "
                "seuils de passation, de publication, de contrôle et "
                "d'approbation des marchés publics",
     "motif": "seuils de passation, de publication, de contrôle et d'approbation"},
    {"id": "decret-2018-028-quota",
     "libelle": "DÉCRET N° 2018-028/PR portant attribution d'un quota de marchés "
                "publics aux jeunes et femmes entrepreneurs",
     "motif": "réserve une part d'au moins vingt pour cent"},
    {"id": "arrete-087-quota",
     "libelle": "ARRÊTÉ N° 087/MEF/CAB portant rehaussement à vingt-cinq pour "
                "cent (25%) de la part des marchés publics réservée aux jeunes et "
                "femmes entrepreneurs",
     "motif": "En application de l'alinéa 2 de l'article 1 du décret"},
    {"id": "loi-2021-034-ppp",
     "libelle": "LOI N° 2021-034 du 31 décembre 2021 relative aux contrats de "
                "partenariat public-privé",
     "motif": "a pour objet de régir les contrats de partenariat public-privé"},
    {"id": "decret-2022-065-ppp",
     "libelle": "DÉCRET N° 2022-065/PR du 11 mai 2022 portant modalités de mise en "
                "œuvre des procédures de passation et d'exécution des contrats de "
                "partenariat public-privé",
     "motif": "règles qui régissent la préparation, la passation, le contrôle, "
              "l'exécution et la régulation des contrats de partenariat "
              "public-privé"},
    {"id": "decret-2022-066-unite-ppp",
     "libelle": "DÉCRET N° 2022-066/PR portant missions, attributions, "
                "organisation et fonctionnement de l'Unité de partenariat "
                "public-privé",
     "motif": "le fonctionnement de l'Unité de partenariat public-privé"},
]


def _num_article(a: Article) -> int:
    return 1 if a.num in ("premier", "1er", "1") else int(a.num)


def _texte_article(a: Article) -> str:
    """Titre + corps de l'article (le titre porte souvent une partie du sens)."""
    return f"{a.titre} {a.texte}"


def segmenter(articles: list[Article]) -> list[list[Article]]:
    """Découpe la séquence d'articles en segments = un corps de texte chacun.

    Chaque document du recueil réinitialise sa numérotation (Article
    premier/1er/1). Un « reset » (numéro inférieur au précédent) marque donc le
    début d'un nouveau texte.
    """
    segments: list[list[Article]] = []
    cur: list[Article] = [articles[0]]
    for a in articles[1:]:
        if _num_article(a) < _num_article(cur[-1]):
            segments.append(cur)
            cur = [a]
        else:
            cur.append(a)
    segments.append(cur)
    return segments


def attribuer_documents(articles: list[Article], aplatir_espaces: bool = True) -> list[Article]:
    """Attribue chaque article à son document par correspondance ordinale.

    Les segments (bornés par les resets de numérotation) apparaissent dans le
    même ordre que la table `DOCUMENTS` (ordre de lecture du recueil). Le i-ème
    segment reçoit donc le i-ème document de la table ; le motif n'est utilisé
    que comme **contrôle** (avertissement si absent du segment). Cette approche
    est robuste face aux doubles espaces d'extraction, aux variantes de
    ponctuation et aux phrases partagées entre textes.
    """
    def aplatir(s: str) -> str:
        return re.sub(r"\s+", " ", s) if aplatir_espaces else s

    segments = segmenter(articles)
    if len(segments) != len(DOCUMENTS):
        raise ValueError(
            f"{len(segments)} segments détecté(s) pour {len(DOCUMENTS)} documents"
        )

    for i, (seg, doc) in enumerate(zip(segments, DOCUMENTS)):
        texte = aplatir(" ".join(_texte_article(a) for a in seg))
        motif = aplatir(doc["motif"])
        if not re.search(re.escape(motif), texte, re.IGNORECASE):
            print(f"[chunking] avertissement : motif introuvable pour {doc['id']}")
        for a in seg:
            a.document = doc["id"]
    return articles


def resumer_attribution(articles: list[Article]) -> str:
    """Résumé lisible (document → nb articles) pour vérification."""
    par_doc: dict[str, list[Article]] = {}
    for a in articles:
        par_doc.setdefault(a.document, []).append(a)
    lignes = []
    for doc_id, arts in par_doc.items():
        lib = next((d["libelle"] for d in DOCUMENTS if d["id"] == doc_id), doc_id)
        nums = [a.num for a in arts]
        lignes.append(f"- {doc_id} ({len(arts)} articles, {nums[0]}..{nums[-1]}): {lib}")
    return "\n".join(lignes)


# --- Sortie JSON -------------------------------------------------------------


def sauver_chunks_json(articles: list[Article], out_path: Path,
                       source: str) -> None:
    """Écrit les chunks au format JSON (un objet par article)."""
    chunks = []
    for a in articles:
        chunks.append({
            "source": source,
            "document": a.document,
            "article": str(a.num),
            "titre": a.titre,
            "texte": a.texte,
            "ligne_debut": a.ligne_debut,
            "ligne_fin": a.ligne_fin,
        })
    out_path.write_text(
        json.dumps({"meta": {"nb_chunks": len(chunks)},
                    "chunks": chunks}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True,
                        help="PDF du recueil ARCOP")
    parser.add_argument("--out", type=Path, required=True,
                        help="Fichier JSON de sortie (chunks)")
    parser.add_argument("--texte-ordonne", type=Path, default=None,
                        help="Écrit aussi le texte ordonné (optionnel)")
    args = parser.parse_args()

    print(f"Ré-extraction ordonnée de {args.pdf} …")
    texte = extraire_texte_ordonne(args.pdf)
    print(f"  {len(texte)} caractères")

    if args.texte_ordonne:
        args.texte_ordonne.write_text(texte, encoding="utf-8")
        print(f"  texte ordonné écrit dans {args.texte_ordonne}")

    articles = decouper_en_articles(texte)
    print(f"Découpage : {len(articles)} articles")
    attribuer_documents(articles)
    print(resumer_attribution(articles))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    sauver_chunks_json(articles, args.out, source=str(args.pdf))
    print(f"\nChunks écrits : {args.out}")


if __name__ == "__main__":
    main()