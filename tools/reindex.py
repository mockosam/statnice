#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reindex.py — přegeneruje assets/data.js z hotových HTML stránek.

Index se čte z **vygenerovaného HTML**, ne ze .docx — ruční úpravy stránek se
tedy do hledání i kartiček propíšou. Spusťte kdykoli po úpravě obsahu:

    python3 tools/reindex.py

Co se do indexu dostane:
  * nadpis stránky, perex a všechny nadpisy H2/H3 (včetně jejich id)
  * dvojice „pojem — definice“ ze sekce Klíčové pojmy a z glosáře (kartičky)
  * plný text stránky pro fulltextové hledání
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from html.parser import HTMLParser

SKIP_TAGS = {"script", "style", "svg", "template"}
BLOCK_TAGS = {
    "p", "li", "h1", "h2", "h3", "h4", "div", "section", "aside", "tr", "td", "th",
    "dt", "dd", "br", "nav", "header", "footer", "main", "table", "ul", "ol", "dl", "summary",
}
CAPTURE_TAGS = {"h1", "h2", "h3", "li", "dt", "dd"}
# prázdné prvky nemají koncovou značku, takže se nesmí ukládat na zásobník
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, str, set]] = []
        self.caps: list[dict] = []
        self.skip = 0
        self.body: dict = {}
        self.title = ""
        self.lead_parts: list[str] = []
        self.in_lead = False
        self.heads: list[tuple[int, str, str]] = []
        self.terms: list[tuple[str, str]] = []
        self.text: list[str] = []
        self._pending_dt = None
        self.updepth = 0     # jsme uvnitř poznámky „Aktualizace 2026“?

    # -- pomůcky ---------------------------------------------------------
    def _anc(self, tag=None, eid=None, cls=None) -> bool:
        for t, i, c in self.stack:
            if tag and t != tag:
                continue
            if eid and i != eid:
                continue
            if cls and cls not in c:
                continue
            return True
        return False

    def _in_main(self) -> bool:
        return self._anc(eid="obsah")

    def _in_key(self) -> bool:
        """Jsme v sekci klíčových pojmů (nadpis s 🔑) nebo ve žlutém boxu?"""
        return self._anc(cls="sec-key") or self._anc(cls="key")

    # -- HTMLParser ------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "body":
            self.body = a
        if tag in SKIP_TAGS:
            self.skip += 1
            return
        if tag in VOID_TAGS:
            if tag == "br":
                self.text.append(" ")
                for c in self.caps:
                    c["buf"].append(" ")
            return
        cls = set((a.get("class") or "").split())
        self.stack.append((tag, a.get("id") or "", cls))
        if tag == "details" and "upd" in cls:
            self.updepth += 1
        if tag == "p" and "lead" in cls:
            self.in_lead = True
        if tag in CAPTURE_TAGS:
            self.caps.append({"tag": tag, "id": a.get("id") or "", "buf": []})

    def handle_startendtag(self, tag, attrs):
        if tag not in SKIP_TAGS:
            if tag == "br":
                self.text.append(" ")
                for c in self.caps:
                    c["buf"].append(" ")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if tag == "p":
            self.in_lead = False
        # zavřít odpovídající zachytávač
        for i in range(len(self.caps) - 1, -1, -1):
            if self.caps[i]["tag"] == tag:
                cap = self.caps.pop(i)
                self._finish(cap, tag)
                break
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if tag == "details" and "upd" in self.stack[i][2]:
                    self.updepth = max(0, self.updepth - 1)
                del self.stack[i:]
                break
        if tag in BLOCK_TAGS:
            self.text.append("\n")

    def _finish(self, cap, tag):
        txt = re.sub(r"\s+", " ", "".join(cap["buf"])).strip()
        if not txt:
            return
        if tag == "h1" and not self.title:
            self.title = txt
        elif tag in ("h2", "h3"):
            self.heads.append((2 if tag == "h2" else 3, cap["id"], txt))
        elif tag == "li" and self._in_key():
            m = re.match(r"^([\s\S]*?)\s[—–]\s([\s\S]+)$", txt)
            if m:
                self.terms.append((m.group(1).strip(), m.group(2).strip()))
        elif tag == "dt":
            self._pending_dt = txt
        elif tag == "dd" and self._pending_dt:
            # <dl> používá i přehled literatury — z bibliografie kartičky nechceme
            if self.body.get("data-kind") == "glosar":
                self.terms.append((self._pending_dt, txt))
            self._pending_dt = None

    def handle_data(self, data):
        if self.skip:
            return
        # poznámky o změnách proti zdroji do nadpisů ani kartiček nepatří,
        # ve fulltextu je ale chceme mít
        if not self.updepth:
            for c in self.caps:
                c["buf"].append(data)
        if self.in_lead:
            self.lead_parts.append(data)
        if self._in_main() or self.in_lead:
            self.text.append(data)

    # -- výsledek --------------------------------------------------------
    def result(self, url: str) -> dict:
        text = re.sub(r"[ \t]+", " ", "".join(self.text))
        text = re.sub(r"\s*\n\s*", " · ", text)
        text = re.sub(r"(\s·\s)+", " · ", text).strip(" ·")
        lead = re.sub(r"\s+", " ", "".join(self.lead_parts)).strip()
        m = re.search(r"otazka-(\d+)", os.path.basename(url))
        doc = {
            "s": self.body.get("data-subject", ""),
            "k": self.body.get("data-kind", ""),
            "t": self.title,
            "u": url.replace(os.sep, "/"),
            "h": [h[2] for h in self.heads],
            "hid": [h[1] for h in self.heads],
            "c": [list(t) for t in self.terms],
            "x": text,
        }
        if m:
            doc["n"] = int(m.group(1))
        if lead:
            doc["d"] = lead
        return doc


LABELS = {
    "otazka": "Otázka",
    "glosar": "Glosář",
    "zakony": "Zákony",
    "jak-pracovat": "Průvodce",
    "aktualizace-2026": "Aktualizační dodatek",
    "pravni-aktualnost": "Právní audit",
    "karticky": "Kartičky",
    "subject-index": "Přehled předmětu",
    "hub": "Rozcestník",
}

# stránky, které nemají obsahovou hodnotu pro hledání
EXCLUDE_KINDS = {"hub", "subject-index", "karticky"}


def main() -> int:
    root = os.getcwd()
    files = sorted(glob.glob("*.html")) + sorted(glob.glob(os.path.join("*", "*.html")))
    docs = []
    skipped = []
    for path in files:
        p = Page()
        p.feed(open(path, encoding="utf-8").read())
        doc = p.result(path)
        if not doc["t"]:
            skipped.append((path, "bez <h1>"))
            continue
        if doc["k"] in EXCLUDE_KINDS:
            skipped.append((path, "vynecháno (%s)" % doc["k"]))
            continue
        docs.append(doc)

    docs.sort(key=lambda d: (d["s"], 0 if "n" in d else 1, d.get("n", 0), d["u"]))

    out = {"labels": LABELS, "docs": docs}
    js = (
        "/* Generováno skriptem tools/reindex.py — needitujte ručně.\n"
        "   Po úpravě obsahu stránek spusťte znovu: python3 tools/reindex.py */\n"
        "window.STATNICE_DATA = "
        + json.dumps(out, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )
    os.makedirs("assets", exist_ok=True)
    open(os.path.join("assets", "data.js"), "w", encoding="utf-8").write(js)

    cards = sum(len(d["c"]) for d in docs)
    words = sum(len(d["x"].split()) for d in docs)
    print("index: %d stránek · %d kartiček · ~%d slov · %.0f kB" % (
        len(docs), cards, words, len(js.encode("utf-8")) / 1024))
    for path, why in skipped:
        print("  – %-52s %s" % (path, why))
    empty = [d["u"] for d in docs if len(d["x"]) < 200]
    if empty:
        print("  ! podezřele málo textu: %s" % ", ".join(empty))
    return 0


if __name__ == "__main__":
    sys.exit(main())
