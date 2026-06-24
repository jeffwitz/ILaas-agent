from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

project = "ILaaS Agent"
author = "ILaaS Agent contributors"
copyright = "2026, ILaaS Agent contributors"
release = "0.1.0"
version = release

extensions = [
    "myst_parser",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"

exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
]

myst_heading_anchors = 3

html_theme = "sphinx_rtd_theme"
html_title = "ILaaS Agent"
html_baseurl = os.environ.get("READTHEDOCS_CANONICAL_URL", "")
html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 3,
    "style_external_links": True,
}

html_context = {
    "display_github": True,
    "github_user": "jeffwitz",
    "github_repo": "ILaas-agent",
    "github_version": "main",
    "conf_py_path": "/docs/",
}
