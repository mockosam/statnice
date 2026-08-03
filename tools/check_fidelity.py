#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_fidelity.py — ověří, že se při převodu z .docx neztratil žádný text.

Pro každý odstavec a každou buňku tabulky ve zdrojovém dokumentu zkontroluje,
že se jejich text nachází na odpovídající vygenerované stránce. Porovnává se
text bez mezer a bez emoji, takže na přeformátování ani na obalení do značek
kontrola nereaguje.

    python3 tools/check_fidelity.py [source/…docx] [etopedie]
"""

from __future__ import annotations

import glob
import html as html_mod
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx2html import (  # noqa: E402
    SLUGS,
    SPECIAL_PAGES,
    cell_text,
    para_text,
    parse_document,
    split_chapters,
    strip_emoji,
)


def page_text(path: str) -> str:
    src = open(path, encoding="utf-8").read()
    src = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", src)
    src = re.sub(r"(?s)<!--.*?-->", " ", src)
    src = re.sub(r"<[^>]+>", " ", src)
    return html_mod.unescape(src)


def squash(s: str) -> str:
    """Text pro porovnání: bez mezer, bez emoji, sjednocené uvozovky a pomlčky."""
    s = unicodedata.normalize("NFC", s).lower()   # velikost písmen řeší CSS, neporovnáváme ji
    s = s.replace(" ", " ").replace("​", "")
    s = s.replace("„", '"').replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    # pomlčky zahodíme — v HTML slouží jako oddělovač (např. <dt>pojem</dt><dd>definice</dd>)
    s = re.sub(r"[–—−-]", "", s)
    s = "".join(
        c for c in s if not (0x1F300 <= ord(c) <= 0x1FAFF or c in "☀➿️‍⚖⚠📌📖🔑💡🔗📅")
    )
    return re.sub(r"\s+", "", s)


def units(body) -> list[str]:
    """Textové jednotky kapitoly: odstavce a buňky tabulek."""
    out = []
    for b in body:
        if b["kind"] == "table":
            for row in b["rows"]:
                for cell in row:
                    for p in cell:
                        t = para_text(p)
                        if t:
                            out.append(t)
        else:
            t = para_text(b)
            if t:
                out.append(t)
    return out


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else "source/etopedie_statnice_prehledne.docx"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "etopedie"
    blocks, _ = parse_document(src)
    front, chapters = split_chapters(blocks)

    # kapitola → cílový soubor
    targets: dict[int, str] = {}
    for i, (title, _) in enumerate(chapters):
        m = re.match(r"^(\d{1,2})\.\s", title)
        if m:
            n = int(m.group(1))
            targets[i] = "otazka-%02d-%s.html" % (n, SLUGS[n])
        else:
            slug = SPECIAL_PAGES.get(strip_emoji(title)[1])
            if slug:
                targets[i] = slug + ".html"

    cache: dict[str, str] = {}

    def haystack(fname: str) -> str:
        if fname not in cache:
            cache[fname] = squash(page_text(os.path.join(outdir, fname)))
        return cache[fname]

    # obálku (titulní stránku dokumentu) hledáme kdekoli v projektu
    allpages = squash(
        "".join(page_text(p) for p in sorted(glob.glob("*.html") + glob.glob(outdir + "/*.html")))
    )

    # seznam vědomých právních oprav — ty se nehlásí jako ztracený obsah
    corrections: dict[str, str] = {}
    cpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_corrections.txt")
    if os.path.exists(cpath):
        for line in open(cpath, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or line.count("|") < 2:
                continue
            page, reason, original = (p.strip() for p in line.split("|", 2))
            corrections[squash(original)] = "%s — %s" % (page, reason)

    total = missing = 0
    problems: list[tuple[str, str]] = []
    fixed: list[str] = []

    for i, (title, body) in enumerate(chapters):
        fname = targets.get(i)
        if not fname:
            problems.append(("(kapitola bez cílového souboru)", title))
            continue
        hay = haystack(fname)
        for text in [title] + units(body):
            total += 1
            needle = squash(text)
            if needle and needle not in hay:
                if needle in corrections:
                    fixed.append(corrections[needle])
                    continue
                missing += 1
                problems.append((fname, text))

    for text in (para_text(b) for b in front):
        if not text:
            continue
        total += 1
        if squash(text) not in allpages:
            missing += 1
            problems.append(("(titulní strana)", text))

    print("kontrolováno %d textových jednotek" % total)
    if fixed:
        print("vědomě opraveno %d (právní aktualizace, viz tools/_corrections.txt):" % len(fixed))
        for f in sorted(set(fixed)):
            print("  ~ %s" % f)
    stale = [v for k, v in corrections.items() if v not in fixed]
    if stale:
        print("POZOR — tyto řádky v tools/_corrections.txt už nic neodpovídá (zastaralé?):")
        for s in sorted(set(stale)):
            print("  ? %s" % s)
    if problems:
        print("CHYBÍ %d:" % missing)
        for where, text in problems[:40]:
            print("  [%s] %s" % (where, text[:120]))
        if len(problems) > 40:
            print("  … a další %d" % (len(problems) - 40))
        return 1
    print("OK — veškerý text ze .docx je na vygenerovaných stránkách")
    return 0


if __name__ == "__main__":
    sys.exit(main())
