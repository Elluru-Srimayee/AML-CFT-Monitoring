from pathlib import Path

from src.ingestion.loader import TransactionLoader


def test_loader_uses_sample_files_when_available(monkeypatch):
    loader = TransactionLoader(config_path="config/config.yaml")
    sample_path = loader.project_root / "data" / "raw" / "sample2.csv"

    monkeypatch.setattr("src.ingestion.loader.random.choice", lambda items: sample_path)

    resolved_path = loader._resolve_input_path()
    df = loader.load_all()

    assert resolved_path == sample_path
    assert not df.empty
    assert len(df) > 0
