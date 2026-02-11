"""MkDocs hook to rewrite internal links from root markdown files.

The include-markdown plugin rewrites relative URLs so that a link like
[text](CONTRIBUTING.md) in README.md becomes [text](../CONTRIBUTING.md)
when included from docs/index.md. This hook catches both forms and
rewrites them to the correct docs-relative paths.
"""

import re

LINK_MAP = {
    "README.md": "index.md",
    "INSTALL.md": "installation.md",
    "USAGE.md": "usage.md",
    "AGENTS.md": "agents.md",
    "CONTRIBUTING.md": "contributing.md",
    "CLAUDE.md": "claude.md",
    "cloud/setup.md": "cloud-setup.md",
}


def on_page_markdown(markdown, **kwargs):
    for old, new in LINK_MAP.items():
        # Match both ../FILE.md and FILE.md, with optional anchor
        markdown = re.sub(
            rf"\]\((?:\.\./)?" + re.escape(old) + r"(#[^)]*)?\)",
            rf"]({new}\1)",
            markdown,
        )
    return markdown
