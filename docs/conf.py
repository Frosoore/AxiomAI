# Sphinx configuration for the axiomai-engine documentation site.
#
# Build (from the repo root):
#   English : .venv/bin/sphinx-build -b html docs docs/_build/html/en
#   French  : .venv/bin/sphinx-build -b html -D language=fr docs docs/_build/html/fr
#
# Translations live in docs/locales/<lang>/LC_MESSAGES/*.po (gettext workflow,
# managed with sphinx-intl). Anything not yet translated falls back to English.

import os
import sys

# Make the `axiom` package importable by autodoc (repo root).
sys.path.insert(0, os.path.abspath(".."))

from axiom import __version__  # noqa: E402

# -- Project information -----------------------------------------------------

project = "Axiom Engine"
author = "Pinpanicaille and Frosoore"
copyright = "2026, Pinpanicaille and Frosoore"  # noqa: A001
version = __version__
release = __version__

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",       # Google-style docstrings (Args:/Returns:/Raises:)
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "myst_parser",               # hand-written pages are Markdown
]

myst_enable_extensions = ["colon_fence", "deflist"]

templates_path = ["_templates"]
exclude_patterns = ["_build", "locales", "Thumbs.db", ".DS_Store"]

# Heavy runtime dependencies are mocked so the docs build anywhere (CI included)
# without installing chromadb / torch / the Gemini SDK.
autodoc_mock_imports = [
    "chromadb",
    "sentence_transformers",
    "rank_bm25",
    "google",
    "google.genai",
    "httpx",
    "requests",
    "tomlkit",
]

autodoc_member_order = "bysource"
autodoc_typehints = "description"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- Internationalisation ----------------------------------------------------

language = "en"
locale_dirs = ["locales"]
gettext_compact = False  # one .po file per source document

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_title = f"Axiom Engine {__version__}"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

# The language switcher partial (docs/_templates/sidebar/language.html) links
# the current page to its twin in the other language: /en/... <-> /fr/...
html_theme_options = {
    "source_repository": "https://github.com/Frosoore/AxiomAI",
    "source_branch": "main",
    "source_directory": "docs/",
    "sidebar_hide_name": False,
}

html_sidebars = {
    "**": [
        "sidebar/brand.html",
        "sidebar/language.html",
        "sidebar/search.html",
        "sidebar/scroll-start.html",
        "sidebar/navigation.html",
        "sidebar/scroll-end.html",
    ]
}
