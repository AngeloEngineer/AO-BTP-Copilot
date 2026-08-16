"""
Tests du téléchargement de documents — partie pure (sans réseau).

On teste la transformation URL -> nom de fichier local, qui est la seule logique
déterministe sans accès réseau. Le téléchargement lui-même se valide à l'exécution
réelle (J1, poste avec accès réseau).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from download_documents import _local_filename  # noqa: E402


def test_local_filename():
    assert _local_filename("https://arcop.tg/wp-content/uploads/2026/02/1-DAO-TravauxFnal-1.docx") == (
        "1-DAO-TravauxFnal-1.docx"
    )


def test_local_filename_with_query_string():
    assert _local_filename("https://example.org/file.pdf?token=abc") == "file.pdf"


def test_local_filename_no_extension():
    assert _local_filename("https://example.org/2026/02/DAO") == "DAO.bin"


def test_local_filename_sanitizes_windows_illegal_chars():
    name = _local_filename("https://example.org/upload/foo:bar?x=y")
    assert ':' not in name

def test_local_filename_with_spaces_in_url():
    name = _local_filename("https://example.org/upload/a b c.docx")
    assert name == "a b c.docx"


if __name__ == "__main__":
    test_local_filename()
    test_local_filename_with_query_string()
    test_local_filename_no_extension()
    test_local_filename_sanitizes_windows_illegal_chars()
    test_local_filename_with_spaces_in_url()
    print("Tous les tests locaux passent.")