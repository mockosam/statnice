#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_glosar_psy.py — sestaví psychologie/glosar.html z definic v otázkách.

Zdrojový dokument psychologie **žádný glosář neobsahuje** (na rozdíl od etopedie,
kde je samostatná kapitola se 105 hesly). Tento rejstřík je proto sestavený
z dvojic „pojem — definice“, které se v textu jednotlivých otázek našly.

Čte hotové HTML (přes vygenerovaný index assets/data.js), takže se do rejstříku
propíšou i ruční úpravy otázek. Spouštějte po tools/reindex.py:

    python3 tools/reindex.py && python3 tools/make_glosar_psy.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx2html import FAVICON, FONTS, ICON_SEARCH, ICON_THEME, esc, slugify  # noqa: E402

SUBJECT = "psychologie"
OUT = os.path.join(SUBJECT, "glosar.html")

# hesla, která nejsou pojmy — číslované podnadpisy, výčty, začátky vět
SKIP_RE = re.compile(
    r"^\d+[\.\)]"                                        # „1. Bariéry na straně…“
    r"|^(rozvoj|speciální|učení)$"                       # příliš obecná jednoslovná
    r"|^(vlastnosti|formy|znaky|aspekty|dimenze|pozitivní znaky|"
    r"vnější činitelé|vnitřní činitelé|rizikové osobnostní rysy)\b"
    r"|^(dělí|patří|rozlišuj|zahrnuj|vychází|skládá|projevuj|připisované)",  # věta, ne pojem
    re.I)


def deacc(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def titlecase(s: str) -> str:
    """VERZÁLKY → normální podoba; ostatní ponecháme, jak jsou."""
    letters = [c for c in s if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return s[:1].upper() + s[1:].lower()
    return s


def main() -> int:
    js = open("assets/data.js", encoding="utf-8").read()
    data = json.loads(js[js.index("=") + 1:].rstrip().rstrip(";"))

    entries: dict[str, dict] = {}
    for doc in data["docs"]:
        if doc.get("s") != SUBJECT or not doc.get("c"):
            continue
        for term, definition in doc["c"]:
            term = titlecase(term.strip(" :"))
            if SKIP_RE.match(term) or len(term) < 4:
                continue
            rec = {"term": term, "def": definition.strip(),
                   "q": doc.get("n"), "url": doc["u"].split("/")[-1]}
            base = deacc(term).lower()
            # skloňovaná varianta téhož pojmu („charakter“ / „charakterem“):
            # jeden zápis je předponou druhého a liší se nejvýš o 3 znaky
            dup = None
            for k in entries:
                if (k.startswith(base) or base.startswith(k)) and abs(len(k) - len(base)) <= 3:
                    dup = k
                    break
            if dup:
                old = entries[dup]
                # ponecháme kratší (1. pád) podobu pojmu a obsáhlejší definici
                entries[dup] = {
                    **old,
                    "term": old["term"] if len(old["term"]) <= len(term) else term,
                    "def": old["def"] if len(old["def"]) >= len(definition) else definition.strip(),
                }
                continue
            entries[base] = rec

    items = sorted(entries.values(), key=lambda e: (deacc(e["term"]).lower(), e["term"]))

    # rozdělení po písmenech
    groups: dict[str, list] = {}
    for e in items:
        groups.setdefault(deacc(e["term"])[:1].upper(), []).append(e)

    body = []
    body.append('<a class="skiplink" href="#obsah">Přeskočit na obsah</a>')
    body += [
        '<nav class="topnav" aria-label="Hlavní navigace">',
        '  <div class="wrap topnav-in">',
        '    <a class="crumb" href="../index.html">Státnice</a>',
        '    <span class="crumb-sep" aria-hidden="true">/</span>',
        '    <a class="crumb" href="index.html">Psychologie</a>',
        '    <span class="crumb-sep" aria-hidden="true">/</span>',
        '    <span class="crumb crumb-cur">Glosář</span>',
        '    <span class="grow"></span>',
        '    <button class="iconbtn" data-act="search" aria-label="Hledat v materiálu">%s</button>' % ICON_SEARCH,
        '    <button class="iconbtn" data-act="theme" aria-label="Přepnout světlý a tmavý režim">%s</button>'
        % ICON_THEME,
        "  </div>",
        "</nav>",
        "",
        '<header class="qhead qhead-plain">',
        '  <div class="wrap">',
        '    <p class="eyebrow">Rejstřík · Psychologie</p>',
        "    <h1>Glosář pojmů</h1>",
        '    <p class="lead">%d pojmů s definicemi, jak je uvádí text jednotlivých otázek. '
        'Pište do filtru a seznam se zúží.</p>' % len(items),
        '    <div class="gfilter">',
        '      <input type="search" id="gq" placeholder="Filtrovat pojmy…" autocomplete="off" '
        'aria-label="Filtrovat pojmy">',
        '      <span class="gcount" id="gcount"></span>',
        "    </div>",
        "  </div>",
        "</header>",
        "",
        '<div class="wrap layout">',
        '  <aside class="side"><nav class="toc" aria-label="Obsah stránky"></nav></aside>',
        '  <main id="obsah" class="content">',
        "",
        '    <aside class="box warn">',
        '      <h4><span class="bemo" aria-hidden="true">⚠️</span>Odkud tento rejstřík je</h4>',
        '      <p>Zdrojový dokument psychologie <strong>glosář neobsahuje</strong>. Tento seznam '
        'je sestavený z definic nalezených v textu otázek — u každého hesla je odkaz na otázku, '
        'ze které pochází. Není to tedy autorský rejstřík, ale pomůcka pro rychlé hledání.</p>',
        "    </aside>",
    ]

    for letter in sorted(groups, key=lambda c: deacc(c)):
        body += ["", '    <section class="sec sec-read">',
                 '      <h2 id="%s">%s</h2>' % (slugify("litera-" + letter), esc(letter)),
                 '      <dl class="glist">']
        for e in groups[letter]:
            gid = "p-" + slugify(e["term"], 48)
            src = ('<a href="%s">otázka %d</a>' % (e["url"], e["q"])) if e["q"] else ""
            body += [
                '        <div class="gitem" id="%s">' % gid,
                "          <dt>%s</dt>" % esc(e["term"]),
                "          <dd>%s <span class=\"src-pages\">(%s)</span></dd>" % (esc(e["def"]), src),
                "        </div>",
            ]
        body += ["      </dl>", "    </section>"]

    body += ["", '    <nav class="pager" aria-label="Další stránky">',
             '      <a class="pager-l" href="index.html"><span>←</span><strong>Přehled otázek</strong></a>',
             '      <a class="pager-r" href="karticky.html"><span>Dál →</span><strong>Kartičky</strong></a>',
             "    </nav>", "  </main>", "</div>", "",
             '<footer class="foot">', '  <div class="wrap">',
             '    <p>Psychologie · otázky ke státní závěrečné zkoušce · '
             'aktuálnost <a href="aktualnost.html">ověřena k 08/2026</a></p>',
             "  </div>", "</footer>"]

    head = [
        "<!doctype html>", '<html lang="cs">', "<head>", '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Glosář pojmů · Psychologie · Státnice</title>",
        '<meta name="description" content="Rejstřík %d psychologických pojmů s definicemi, '
        'sestavený z textu otázek ke státní závěrečné zkoušce.">' % len(items),
        '<link rel="icon" href="%s">' % FAVICON,
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link rel="stylesheet" href="%s">' % FONTS,
        '<link rel="stylesheet" href="../assets/style.css">',
        "<script>try{var t=localStorage.getItem('statnice.theme')||"
        "(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');"
        "document.documentElement.dataset.theme=t}catch(e){}</script>",
        "</head>",
        '<body data-subject="psychologie" data-kind="glosar" data-up="../">',
    ]
    tail = ['<script src="../assets/data.js"></script>',
            '<script src="../assets/app.js"></script>', "</body>", "</html>", ""]

    open(OUT, "w", encoding="utf-8").write("\n".join(head + body + tail))
    print("%s: %d hesel v %d písmenných sekcích" % (OUT, len(items), len(groups)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
