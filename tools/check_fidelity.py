#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_fidelity.py — ověří, že se při převodu z .docx neztratil žádný text.

Pro každý odstavec a každou buňku tabulky ve zdrojovém dokumentu zkontroluje,
že se jejich text nachází na odpovídající vygenerované stránce. Porovnává se
text bez mezer a bez emoji, takže na přeformátování ani na obalení do značek
kontrola nereaguje.

    python3 tools/check_fidelity.py                       # etopedie (kapitoly podle Heading1)
    python3 tools/check_fidelity.py --map tools/_meta_psychologie.json \
            'SZO PSYCHOLOGIE.docx' psychologie            # předmět bez nadpisových stylů

Režim --map se použije tam, kde se kapitoly nedají poznat ze stylů; konvertor
v takovém případě uloží mapu „výstupní soubor → rozsah bloků“.
"""

from __future__ import annotations

import glob
import html as html_mod
import json
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
        c for c in s if not (0x1F300 <= ord(c) <= 0x1FAFF or c in "☀➿️‍⚖⚠📌📖🔑💡🔗📅📚")
    )
    # číslo na začátku je v HTML jen ozdoba (odznak u otázky, CSS counter u <ol>)
    s = re.sub(r"^\s*\d{1,2}[\.\)]\s*", "", s)
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


def load_corrections(outdir: str | None = None) -> dict[str, str]:
    """
    tools/_corrections.txt → {squashed původní text: „stránka — důvod“}.

    Soubor je společný pro všechny předměty. Je-li zadán outdir, vezmou se jen
    řádky, jejichž stránka v tom předmětu existuje — jinak by kontrola jednoho
    předmětu hlásila řádky ostatních předmětů jako zastaralé.
    """
    out: dict[str, str] = {}
    cpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_corrections.txt")
    if not os.path.exists(cpath):
        return out
    for line in open(cpath, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or line.count("|") < 2:
            continue
        page, reason, original = (p.strip() for p in line.split("|", 2))
        if outdir:
            # „predmet/soubor.html“ patří jen tomu předmětu; „soubor.html“ se hledá
            # v adresáři právě kontrolovaného předmětu
            if "/" in page:
                if os.path.dirname(page).rstrip("/") != outdir.rstrip("/"):
                    continue
            elif not os.path.exists(os.path.join(outdir, page)):
                continue
        out[squash(original)] = "%s — %s" % (page, reason)
    return out


def report_corrections(fixed: list[str], corrections: dict[str, str]) -> None:
    if fixed:
        print("vědomě opraveno %d (právní aktualizace, viz tools/_corrections.txt):" % len(fixed))
        for f in sorted(set(fixed)):
            print("  ~ %s" % f)
    stale = [v for v in corrections.values() if v not in fixed]
    if stale:
        print("POZOR — těmto řádkům v tools/_corrections.txt už nic neodpovídá (zastaralé?):")
        for s in sorted(set(stale)):
            print("  ? %s" % s)


def check_by_map(blocks, meta, outdir) -> int:
    """
    Kontrola pro předmět, u kterého konvertor uložil mapu „soubor → rozsah bloků“.
    Text, který má být na konkrétní stránce, se hledá tam; ostatní kdekoli na webu.
    """
    bmap = meta.get("map", {})
    # Bloky, které se vědomě nepublikují kvůli osobním údajům. Na rozdíl od
    # tools/_corrections.txt se tu neuvádí původní text — ten by se tím dostal
    # do repozitáře, což je přesně to, čemu se vynecháním předchází.
    redacted = {int(k): v for k, v in meta.get("redacted", {}).items()}
    # Bloky, které konvertor vědomě zahodil jako typografii bez obsahu —
    # osiřelý nadpis, řádek hvězdiček oddělující otázky. Na rozdíl od
    # tools/_corrections.txt se u nich nic neopravuje, prostě do stránky nepatří.
    dropped = {int(i) for i in meta.get("drop", [])}
    covered = set()
    everywhere = squash("".join(
        page_text(p) for p in sorted(glob.glob("*.html") + glob.glob(os.path.join(outdir, "*.html")))))
    corrections = load_corrections(outdir)
    fixed: list[str] = []
    total = missing = 0
    problems: list[tuple[str, str]] = []

    for fname, (start, end) in sorted(bmap.items(), key=lambda kv: kv[1][0]):
        path = os.path.join(outdir, fname)
        if not os.path.exists(path):
            problems.append((fname, "(stránka neexistuje)"))
            continue
        hay = squash(page_text(path))
        for i in range(start, end):
            covered.add(i)
            if i in dropped:
                continue
            for text in units([blocks[i]]):
                total += 1
                needle = squash(text)
                if needle and needle not in hay:
                    if needle in corrections:
                        fixed.append(corrections[needle])
                        continue
                    missing += 1
                    problems.append((fname, text))

    # bloky mimo mapu (titulní strana, obsah, nezpracovaná otázka) — hledáme kdekoli
    outside = 0
    for i, b in enumerate(blocks):
        if i in covered or i in dropped:
            continue
        if i in redacted:
            fixed.append("blok %d — %s" % (i, redacted[i]))
            continue
        for text in units([b]):
            total += 1
            outside += 1
            needle = squash(text)
            if needle and needle not in everywhere:
                if needle in corrections:
                    fixed.append(corrections[needle])
                    continue
                missing += 1
                problems.append(("(mimo mapu, blok %d)" % i, text))

    print("kontrolováno %d textových jednotek (%d mimo mapu kapitol)" % (total, outside))
    report_corrections(fixed, corrections)
    if meta.get("missing"):
        print("ve zdroji není vypracována otázka: %s" % meta["missing"])
    if problems:
        print("CHYBÍ %d:" % missing)
        for where, text in problems[:30]:
            print("  [%s] %s" % (where, text[:118]))
        if len(problems) > 30:
            print("  … a další %d" % (len(problems) - 30))
        return 1
    print("OK — veškerý text ze .docx je na vygenerovaných stránkách")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    mapfile = None
    if "--map" in argv:
        k = argv.index("--map")
        mapfile = argv[k + 1]
        del argv[k:k + 2]
    src = argv[0] if argv else "source/etopedie_statnice_prehledne.docx"
    outdir = argv[1] if len(argv) > 1 else "etopedie"
    blocks, _ = parse_document(src)

    if mapfile:
        return check_by_map(blocks, json.load(open(mapfile, encoding="utf-8")), outdir)

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
    corrections = load_corrections(outdir)

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
