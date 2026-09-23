from pathlib import Path

from medical_learning_system.sources import SourceManifest, sha256_file


def test_source_manifest():
    source = SourceManifest(
        source_id="book-1",
        title="Example Medical Book",
        edition="1",
        publication_year=2025,
    )
    assert source.source_id == "book-1"


def test_sha256_file(tmp_path: Path):
    path = tmp_path / "source.txt"
    path.write_text("medical-learning-system", encoding="utf-8")
    assert len(sha256_file(path)) == 64
