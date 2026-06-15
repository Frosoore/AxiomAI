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


@pytest.fixture(autouse=True)
def reset_i18n_cache():
    """Vide le cache i18n (langue courante + tables) avant ET après chaque test.

    `core.localization` met en cache la langue courante (`_CURRENT_LANG`) ; un test
    qui change de langue (ex. test_help_system) la laisserait fuiter vers les tests
    suivants. Sans ce reset, tout test qui lit du texte localisé (ex. le rapport de
    diagnostic) dépendrait de l'ordre d'exécution.
    """
    try:
        from core.localization import reload_translations
        reload_translations()
    except Exception:
        pass
    yield
    try:
        from core.localization import reload_translations
        reload_translations()
    except Exception:
        pass
