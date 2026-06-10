import pytest
import sys
from PySide6.QtWidgets import QApplication

@pytest.fixture(scope="session", autouse=True)
def q_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def isolated_axiom_data_dir(tmp_path, monkeypatch):
    """Aucun test ne doit écrire dans le vrai ~/AxiomAI (saves/, vector/, …).

    Passe par la variable d'env (et non paths.configure) : un test qui fait son
    propre configure() garde la priorité, et un paths.reset() en cours de test
    retombe sur l'env — donc toujours sur tmp, jamais sur le HOME réel.
    """
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "axiom_data"))
    yield
