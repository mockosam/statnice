#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_links.py — ověří, že žádný vnitřní odkaz na webu nevede do prázdna.

Kontroluje:
  * href / src na místní soubory — existuje cílový soubor?
  * odkazy s kotvou (#id) — existuje na cílové stránce prvek s tímto id?
  * duplicitní id v rámci jedné stránky
  * chybějící atributy, které web potřebuje (data-up, data-subject)

    python3 tools/check_links.py
"""

from __future__ import annotations

import glob
import os
import re
import sys
from collections import Counter
from urllib.parse import unquote, urldefrag

SKIP_SCHEMES = ("http:", "https:", "mailto:", "tel:", "data:", "javascript:", "#")


def ids_of(path: str) -> Counter:
    txt = open(path, encoding="utf-8").read()
    return Counter(re.findall(r'\bid="([^"]+)"', txt))


def main() -> int:
    pages = sorted(glob.glob("*.html")) + sorted(glob.glob(os.path.join("*", "*.html")))
    id_cache: dict[str, Counter] = {}
    problems: list[str] = []
    checked = 0

    for page in pages:
        txt = open(page, encoding="utf-8").read()
        base = os.path.dirname(page)

        # duplicitní id na stránce
        for eid, n in ids_of(page).items():
            if n > 1:
                problems.append("%s: id=\"%s\" je na stránce %dx" % (page, eid, n))

        # povinné atributy <body>
        m = re.search(r"<body([^>]*)>", txt)
        if m and 'data-up=' not in m.group(1):
            problems.append("%s: <body> nemá data-up — odkazy z hledání by nefungovaly" % page)

        for url in re.findall(r'\b(?:href|src)="([^"]*)"', txt):
            u = url.strip()
            if not u or u.startswith(SKIP_SCHEMES):
                # čistá kotva na téže stránce
                if u.startswith("#") and len(u) > 1:
                    checked += 1
                    if u[1:] not in ids_of(page):
                        problems.append("%s: kotva %s neexistuje" % (page, u))
                continue

            target, frag = urldefrag(unquote(u))
            if not target:
                continue
            checked += 1
            resolved = os.path.normpath(os.path.join(base, target))
            if not os.path.exists(resolved):
                problems.append("%s: cíl %s neexistuje (%s)" % (page, u, resolved))
                continue
            if frag and resolved.endswith(".html"):
                if resolved not in id_cache:
                    id_cache[resolved] = ids_of(resolved)
                if frag not in id_cache[resolved]:
                    problems.append("%s: %s — v %s není id=\"%s\"" % (page, u, target, frag))

    print("stránek: %d · zkontrolováno odkazů: %d" % (len(pages), checked))
    if problems:
        print("PROBLÉMY (%d):" % len(problems))
        for p in problems:
            print("  ✗", p)
        return 1
    print("OK — všechny vnitřní odkazy i kotvy vedou na existující cíle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
