"""Compile paper/main.typ to paper/paper.pdf and copy it to web/paper.pdf.

Usage: uv run python paper/build.py
"""

import shutil
from pathlib import Path

import typst

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "paper/paper.pdf"
typst.compile(str(ROOT / "paper/main.typ"), output=str(out), root=str(ROOT))
shutil.copy(out, ROOT / "web/paper.pdf")
print(f"wrote {out.relative_to(ROOT)} and web/paper.pdf")
