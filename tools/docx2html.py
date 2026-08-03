#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx2html.py — jednorázový převod studijního materiálu z .docx do statického HTML.

Tento skript byl použit k prvotnímu vygenerování stránek v adresáři etopedie/.
Zdrojem pravdy je od té doby **vygenerované HTML**, ne .docx — pokud skript
spustíte znovu, přepíše ruční úpravy. Ponechán je pro případ, že budete chtít
naimportovat další předmět z Wordu.

Použití:
    python3 tools/docx2html.py source/etopedie_statnice_prehledne.docx etopedie

Co skript pozná ve zdrojovém dokumentu:
  * Heading1                     → samostatná stránka (otázka / glosář / zákony / dodatek)
  * Heading2 / Heading3          → sekce a podsekce, generuje se jim id pro odkazy a obsah
  * odstavec hned za Heading1    → perex (lead) otázky
  * tabulka 1×1                  → barevný box; typ se určí z emoji na začátku (📌🔑⚖️💡⚠️🔗)
  * ostatní tabulky              → <table> s <thead> z prvního řádku (v tomto dokumentu
                                   je první řádek vždy celý tučný)
  * ListParagraph + numId        → <ul> (numId s formátem bullet) nebo <ol> (decimal)
  * tučné / kurzivní běhy textu  → <strong> / <em>
  * „č. N“ uvnitř boxu 🔗        → odkaz na příslušnou otázku
"""

from __future__ import annotations

import glob
import html
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import OrderedDict

WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ANS = "http://schemas.openxmlformats.org/drawingml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"w": WNS, "a": ANS, "r": RNS}
W = "{%s}" % WNS
A = "{%s}" % ANS
R = "{%s}" % RNS

# emoji na začátku boxu → CSS třída + čitelný název typu
BOX_TYPES = OrderedDict(
    [
        ("📌", ("sum", "Shrnutí")),
        ("🔑", ("key", "Klíčové pojmy")),
        ("⚖️", ("law", "Legislativa")),
        ("⚖", ("law", "Legislativa")),
        ("💡", ("tip", "Tip ke zkoušce")),
        ("⚠️", ("warn", "Pozor")),
        ("⚠", ("warn", "Pozor")),
        ("🔗", ("link", "Souvislosti")),
    ]
)

# emoji na začátku nadpisu H2 → CSS třída sekce
SEC_TYPES = {"🔑": "key", "⚖️": "law", "⚖": "law", "📖": "read", "💡": "tip", "⚠️": "warn", "📅": "upd"}

EMOJI_RE = re.compile(
    "^[\U0001F300-\U0001FAFF☀-➿←-⇿⬀-⯿️‍]+"
)

# ručně zvolené názvy souborů — čitelnější než plná automatická transliterace nadpisu
SLUGS = {
    1: "etopedie-jako-obor",
    2: "socializace-moralni-vyvoj",
    3: "strategie-riziko-problem-porucha",
    4: "diagnostika-pch",
    5: "etiologie-pch",
    6: "edukace-zaku-pch",
    7: "skolska-zarizeni-nvp",
    8: "cile-nvp-diagnostika",
    9: "kurikularni-dokumenty-standardy",
    10: "osobnost-pedagoga",
    11: "rodina-riziko-pch",
    12: "rodina-pch-postpece",
    13: "ospod-prava-ditete",
    14: "adhd-add-odd",
    15: "agrese-sikana",
    16: "lez-zaskolactvi-kradeze",
    17: "emocni-poruchy",
    18: "prevence-socializace",
    19: "poradenstvi-odmeny-tresty",
    20: "zavislostni-chovani",
}

# ostatní kapitoly dokumentu → cílový soubor
SPECIAL_PAGES = {
    "Jak s tímto materiálem pracovat": "jak-pracovat",
    "Obsah": "jak-pracovat",
    "Závěrečný glosář klíčových pojmů": "glosar",
    "Klíčové zákony — rychlý přehled": "zakony",
    "Závěrečná poznámka": "zakony",
    "Aktualizační dodatek (stav k dubnu 2026)": "aktualizace-2026",
}


# ---------------------------------------------------------------- pomůcky

def strip_emoji(s: str) -> tuple[str, str]:
    """Oddělí úvodní emoji od textu. Vrací (emoji, zbytek)."""
    m = EMOJI_RE.match(s)
    if not m:
        return "", s.strip()
    return m.group(0).strip(), s[m.end():].strip()


def deaccent(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def slugify(s: str, maxlen: int = 56) -> str:
    s = deaccent(strip_emoji(s)[1]).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > maxlen:                     # zkrátit, ale ne uprostřed slova
        s = s[:maxlen].rsplit("-", 1)[0]
    return s.strip("-") or "sekce"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ---------------------------------------------------------------- parsování docx

def run_parts(run) -> list[dict]:
    """Jeden <w:r> → seznam částí textu (kvůli <w:br> uvnitř běhu)."""
    rpr = run.find("w:rPr", NS)

    def on(tag):
        if rpr is None:
            return False
        el = rpr.find("w:" + tag, NS)
        return el is not None and el.get(W + "val") not in ("0", "false", "none")

    bold, ital = on("b"), on("i")
    out, buf = [], []
    for node in run.iter():
        if node.tag == A + "blip":                      # vložený obrázek
            rid = node.get(R + "embed")
            if rid:
                out.append({"img": rid})
            continue
        tag = node.tag[len(W):] if node.tag.startswith(W) else node.tag
        if tag == "t":
            buf.append(node.text or "")
        elif tag == "br":
            out.append({"t": "".join(buf), "b": bold, "i": ital})
            out.append({"br": True})
            buf = []
    if buf:
        out.append({"t": "".join(buf), "b": bold, "i": ital})
    return out


def parse_para(p) -> dict:
    ppr = p.find("w:pPr", NS)
    style, num, lvl = "Normal", None, 0
    if ppr is not None:
        el = ppr.find("w:pStyle", NS)
        if el is not None:
            style = el.get(W + "val")
        npr = ppr.find("w:numPr", NS)
        if npr is not None:
            el = npr.find("w:numId", NS)
            if el is not None:
                num = el.get(W + "val")
            el = npr.find("w:ilvl", NS)
            if el is not None:
                lvl = int(el.get(W + "val") or 0)
    parts = []
    for run in p.findall("w:r", NS):
        parts.extend(run_parts(run))
    return {"kind": "p", "style": style, "num": num, "lvl": lvl, "parts": parts}


def parse_table(tbl) -> dict:
    rows = []
    for tr in tbl.findall("w:tr", NS):
        rows.append([[parse_para(p) for p in tc.findall("w:p", NS)] for tc in tr.findall("w:tc", NS)])
    return {"kind": "table", "rows": rows}


def parse_document(docx_path: str) -> tuple[list[dict], dict]:
    with zipfile.ZipFile(docx_path) as z:
        doc = ET.fromstring(z.read("word/document.xml"))
        numbering = ET.fromstring(z.read("word/numbering.xml"))

    # numId → formát prvního seznamové úrovně (bullet / decimal / …)
    absfmt = {}
    for an in numbering.findall("w:abstractNum", NS):
        lv = {}
        for l in an.findall("w:lvl", NS):
            f = l.find("w:numFmt", NS)
            lv[int(l.get(W + "ilvl") or 0)] = f.get(W + "val") if f is not None else "bullet"
        absfmt[an.get(W + "abstractNumId")] = lv
    numfmt = {}
    for n in numbering.findall("w:num", NS):
        a = n.find("w:abstractNumId", NS)
        numfmt[n.get(W + "numId")] = absfmt.get(a.get(W + "val"), {})

    blocks = []

    def walk(el):
        for child in el:
            tag = child.tag[len(W):] if child.tag.startswith(W) else child.tag
            if tag == "p":
                blocks.append(parse_para(child))
            elif tag == "tbl":
                blocks.append(parse_table(child))
            elif tag == "sdt":
                inner = child.find("w:sdtContent", NS)
                walk(inner if inner is not None else child)

    walk(doc.find("w:body", NS))
    return blocks, numfmt


# ---------------------------------------------------------------- text bloků

def para_text(b: dict) -> str:
    return "".join(p.get("t", "\n") for p in b["parts"]).strip()


def cell_text(cell: list[dict]) -> str:
    return " ".join(t for t in (para_text(p) for p in cell) if t)


# ---------------------------------------------------------------- render inline

class Ctx:
    """Kontext převodu jedné stránky — potřebný pro odkazy mezi otázkami a do glosáře."""

    def __init__(self, numfmt, qhrefs, glossary, cur_q=None, in_link_box=False, mode=""):
        self.numfmt = numfmt
        self.qhrefs = qhrefs          # číslo otázky → název souboru
        self.glossary = glossary      # normalizovaný pojem → id v glosáři
        self.gl_ids = {}              # přesný pojem → id (plní se v pre-passu)
        self.cur_q = cur_q
        self.in_link_box = in_link_box
        self.mode = mode              # "glosar" zapne jiný render seznamů
        self.glossary_hits = set()


# „č. 7“, „č. 11–12“ v boxech 🔗 ·  „(otázka 2, 6)“ v glosáři
CROSSREF_RE = re.compile(r"(č\.\s*)(\d{1,2})(\s*[–-]\s*)?(\d{1,2})?")
QREF_RE = re.compile(r"(otázk\w*\s+)(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)")


def _qlink(n: str, ctx: Ctx) -> str:
    href = ctx.qhrefs.get(int(n))
    if not href or int(n) == ctx.cur_q:
        return n
    return '<a href="%s">%s</a>' % (href, n)


def link_crossrefs(text_html: str, ctx: Ctx) -> str:
    """V boxu 🔗 promění „č. 7“ / „č. 11–12“ na odkazy na dané otázky."""

    def sub(m):
        pre, a, dash, b = m.group(1), m.group(2), m.group(3), m.group(4)
        if b and dash:
            return pre + _qlink(a, ctx) + dash + _qlink(b, ctx)
        return pre + _qlink(a, ctx)

    return CROSSREF_RE.sub(sub, text_html)


def link_qrefs(text_html: str, ctx: Ctx) -> str:
    """V glosáři promění „(otázka 14)“ nebo „(otázka 2, 6)“ na odkazy."""

    def sub(m):
        nums = re.sub(r"\d{1,2}", lambda d: _qlink(d.group(0), ctx), m.group(2))
        return m.group(1) + nums

    return QREF_RE.sub(sub, text_html)


def inline(b: dict, ctx: Ctx, glossary_term: bool = False) -> str:
    """Odstavec → inline HTML (<strong>, <em>, <br>, odkazy)."""
    out = []
    for part in b["parts"]:
        if part.get("br"):
            out.append("<br>\n")
            continue
        if part.get("img"):
            # obrázky vkládá volající přes ctx.images (rId → hotový HTML)
            out.append(getattr(ctx, "images", {}).get(part["img"], ""))
            continue
        t = part.get("t", "")
        if not t:
            continue
        s = esc(t)
        if part.get("b"):
            s = "<strong>%s</strong>" % s
        if part.get("i"):
            s = "<em>%s</em>" % s
        out.append(s)
    res = "".join(out)
    res = re.sub(r"\s+<br>", "<br>", res)
    if ctx.in_link_box:
        res = link_crossrefs(res, ctx)
    if ctx.mode == "glosar":
        res = link_qrefs(res, ctx)
    if glossary_term:
        res = link_glossary(res, ctx)
    return res.strip()


def norm_term(s: str) -> str:
    s = strip_emoji(s)[1]
    s = re.sub(r"\(.*?\)", "", s)          # (M. Sovák) apod.
    s = re.sub(r"\s+", " ", deaccent(s).lower()).strip(" .,;:–—×*")
    return s


def link_glossary(item_html: str, ctx: Ctx) -> str:
    """V seznamu klíčových pojmů obalí pojem odkazem do glosáře, pokud tam existuje."""
    m = re.match(r"^(.*?)(\s*[—–]\s)", item_html, re.S)   # pojem končí u „ — “
    if not m:
        return item_html
    head, tail = item_html[: m.end(1)], item_html[m.end(1):]

    def wrap(inner: str) -> str | None:
        gid = ctx.glossary.get(norm_term(re.sub(r"<[^>]+>", "", inner)))
        if not gid:
            return None
        ctx.glossary_hits.add(gid)
        return '<a class="gref" href="glosar.html#%s">%s</a>' % (gid, inner)

    # je-li pojem tučný, vložíme odkaz dovnitř <strong>, aby se značky nekřížily
    ms = re.match(r"^(<strong>)(.*?)(</strong>)(.*)$", head, re.S)
    if ms:
        linked = wrap(ms.group(2))
        if linked is None:
            return item_html
        return ms.group(1) + linked + ms.group(3) + ms.group(4) + tail
    linked = wrap(head)
    return item_html if linked is None else linked + tail


# ---------------------------------------------------------------- render bloků

def render_glossary(items: list[dict], ind: str, ctx: Ctx) -> list[str]:
    """Položky glosáře → <dl> s ukotvenými hesly, aby na ně šlo odkazovat a filtrovat je."""
    out = ['%s<dl class="glist">' % ind]
    for it in items:
        plain = para_text(it)
        term_plain = re.split(r"\s[—–]\s", plain, maxsplit=1)[0]
        gid = ctx.gl_ids.get(term_plain) or ("p-" + slugify(term_plain, 48))
        body = inline(it, ctx)
        m = re.match(r"^(.*?)(\s*[—–]\s)(.*)$", body, re.S)
        term_html, definition = (m.group(1), m.group(3)) if m else (body, "")
        out += [
            '%s  <div class="gitem" id="%s">' % (ind, gid),
            "%s    <dt>%s</dt>" % (ind, term_html),
        ]
        if definition:
            out.append("%s    <dd>%s</dd>" % (ind, definition))
        out.append("%s  </div>" % ind)
    out.append("%s</dl>" % ind)
    return out


def render_list(items: list[dict], ind: str, ctx: Ctx, key_terms: bool = False) -> list[str]:
    """Souvislá řada ListParagraph se stejným numId → (vnořený) <ul>/<ol>."""
    num = items[0]["num"]
    fmt = ctx.numfmt.get(num, {})
    out = []

    # formát číslování z Wordu → značka seznamu
    OL = {"decimal": "", "lowerLetter": ' type="a"', "upperLetter": ' type="A"',
          "lowerRoman": ' type="i"', "upperRoman": ' type="I"'}

    def emit(idx: int, level: int, pad: str) -> int:
        f = fmt.get(level, "bullet")
        tag, attr = ("ol", OL[f]) if f in OL else ("ul", "")
        out.append("%s<%s%s>" % (pad, tag, attr))
        while idx < len(items):
            it = items[idx]
            if it["lvl"] < level:
                break
            if it["lvl"] > level:
                idx = emit(idx, level + 1, pad + "  ")
                continue
            body = inline(it, ctx, glossary_term=key_terms)
            out.append("%s  <li>%s</li>" % (pad, body))
            idx += 1
        out.append("%s</%s>" % (pad, tag))
        return idx

    emit(0, items[0]["lvl"], ind)
    return out


def render_box(tbl: dict, ind: str, ctx: Ctx) -> list[str]:
    """Tabulka 1×1 → barevný box."""
    paras = tbl["rows"][0][0]
    paras = [p for p in paras if para_text(p) or any(x.get("br") for x in p["parts"])]
    if not paras:
        return []
    head, rest = paras[0], paras[1:]
    emo, title = strip_emoji(para_text(head))
    cls, kind = BOX_TYPES.get(emo, ("note", "Poznámka"))

    sub = Ctx(ctx.numfmt, ctx.qhrefs, ctx.glossary, ctx.cur_q, in_link_box=(cls == "link"))
    out = ['%s<aside class="box %s">' % (ind, cls)]
    out.append(
        '%s  <h4><span class="bemo" aria-hidden="true">%s</span>%s</h4>'
        % (ind, emo, esc(title))
    )
    out.extend(render_flow(rest, ind + "  ", sub))
    ctx.glossary_hits |= sub.glossary_hits
    out.append("%s</aside>" % ind)
    return out


def render_table(tbl: dict, ind: str, ctx: Ctx) -> list[str]:
    """Datová tabulka → <table> v obalu, který na mobilu umožní vodorovné posouvání."""
    rows = tbl["rows"]
    head, body = rows[0], rows[1:]
    labels = [cell_text(c) for c in head]
    out = ['%s<div class="table-wrap">' % ind, "%s  <table>" % ind, "%s    <thead>" % ind, "%s      <tr>" % ind]
    for c in head:
        out.append("%s        <th>%s</th>" % (ind, esc(cell_text(c))))
    out += ["%s      </tr>" % ind, "%s    </thead>" % ind, "%s    <tbody>" % ind]
    for tr in body:
        out.append("%s      <tr>" % ind)
        for i, c in enumerate(tr):
            label = labels[i] if i < len(labels) else ""
            inner = " ".join(
                x for x in (inline(p, ctx) for p in c if para_text(p)) if x
            )
            out.append('%s        <td data-label="%s">%s</td>' % (ind, esc(label), inner))
        out.append("%s      </tr>" % ind)
    out += ["%s    </tbody>" % ind, "%s  </table>" % ind, "%s</div>" % ind]
    return out


def render_flow(blocks: list[dict], ind: str, ctx: Ctx, key_terms: bool = False) -> list[str]:
    """Plochý seznam bloků → HTML; seskupuje položky seznamů."""
    out, i = [], 0
    while i < len(blocks):
        b = blocks[i]
        if b["kind"] == "table":
            rows = b["rows"]
            if len(rows) == 1 and len(rows[0]) == 1:
                out.extend(render_box(b, ind, ctx))
            else:
                out.extend(render_table(b, ind, ctx))
            i += 1
            continue
        if b["style"] == "ListParagraph":
            num = b["num"]
            group = []
            while (
                i < len(blocks)
                and blocks[i]["kind"] == "p"
                and blocks[i]["style"] == "ListParagraph"
                and blocks[i]["num"] == num
            ):
                group.append(blocks[i])
                i += 1
            if ctx.mode == "glosar":
                out.extend(render_glossary(group, ind, ctx))
            else:
                out.extend(render_list(group, ind, ctx, key_terms=key_terms))
            continue
        if b["style"] == "Heading3":
            out.append("%s<h3 id=\"%s\">%s</h3>" % (ind, ctx_id(ctx, para_text(b)), esc(strip_emoji(para_text(b))[1])))
            i += 1
            continue
        txt = inline(b, ctx)
        # zahodíme jen odstavce, které nenesou nic než zlomy řádku
        if txt and re.sub(r"(<br>|\s)+", "", txt):
            if txt.lstrip().startswith("<figure"):
                out.append("%s%s" % (ind, txt.strip()))       # obrázek nepatří do <p>
            else:
                # odstavec uvozený „=“ je v poznámkách definice předchozího nadpisu
                cls = ' class="defn"' if para_text(b).startswith("=") else ""
                out.append("%s<p%s>%s</p>" % (ind, cls, txt))
        i += 1
    return out


_ids: dict[str, int] = {}
# id, která si drží samotná šablona stránky — nadpis je nesmí přebít
RESERVED_IDS = {"obsah", "gq", "gcount", "prog-label", "deck-list", "deck-list-q"}


def ctx_id(ctx: Ctx, text: str) -> str:
    """Unikátní id v rámci stránky."""
    base = slugify(text)
    if base in RESERVED_IDS:
        base += "-sekce"
    n = _ids.get(base, 0)
    _ids[base] = n + 1
    return base if n == 0 else "%s-%d" % (base, n + 1)


# ---------------------------------------------------------------- skládání stránek

def split_chapters(blocks: list[dict]) -> tuple[list[dict], list[tuple[str, list[dict]]]]:
    """Rozdělí dokument podle Heading1. Vrací (blok před prvním H1, [(nadpis, bloky)])."""
    front, chapters, cur = [], [], None
    for b in blocks:
        if b["kind"] == "p" and b["style"] == "Heading1":
            cur = (para_text(b), [])
            chapters.append(cur)
            continue
        (cur[1] if cur else front).append(b)
    return front, chapters


def split_sections(body: list[dict]) -> tuple[list[dict], list[tuple[str, list[dict]]]]:
    """Rozdělí tělo kapitoly podle Heading2 na (úvod, [(nadpis, bloky)])."""
    intro, secs, cur = [], [], None
    for b in body:
        if b["kind"] == "p" and b["style"] == "Heading2":
            cur = (para_text(b), [])
            secs.append(cur)
            continue
        (cur[1] if cur else intro).append(b)
    return intro, secs


# ---------------------------------------------------------------- šablona stránky

FONTS = (
    "https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400"
    "&family=Fraunces:opsz,wght@9..144,600;9..144,700&family=JetBrains+Mono:wght@400;600&display=swap"
)

FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
    "%3Crect width='64' height='64' rx='14' fill='%230f1117'/%3E"
    "%3Cpath d='M14 24l18-8 18 8-18 8-18-8zm4 12v9c0 4 6 7 14 7s14-3 14-7v-9l-14 6-14-6z' fill='%23a78bfa'/%3E"
    "%3C/svg%3E"
)

ICON_SEARCH = (
    '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5"/>'
    '<path d="M12.8 12.8 17 17"/></svg>'
)
ICON_THEME = (
    '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="4.2"/>'
    '<path d="M10 1.6v2.2M10 16.2v2.2M1.6 10h2.2M16.2 10h2.2M4.1 4.1l1.6 1.6'
    'M14.3 14.3l1.6 1.6M15.9 4.1l-1.6 1.6M5.7 14.3l-1.6 1.6"/></svg>'
)


def shell(*, title, desc, body, up="../", subject="etopedie", kind="", cls="", scripts=True):
    """Obalí obsah stránky společnou hlavičkou, navigací a patičkou."""
    head = [
        "<!doctype html>",
        '<html lang="cs">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>%s</title>" % esc(title),
        '<meta name="description" content="%s">' % html.escape(desc, quote=True),
        '<link rel="icon" href="%s">' % FAVICON,
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link rel="stylesheet" href="%s">' % FONTS,
        '<link rel="stylesheet" href="%sassets/style.css">' % up,
        # nastaví motiv ještě před vykreslením, aby stránka neproblikla
        "<script>try{var t=localStorage.getItem('statnice.theme')||"
        "(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark');"
        "document.documentElement.dataset.theme=t}catch(e){}</script>",
        "</head>",
        '<body data-subject="%s" data-kind="%s" data-up="%s"%s>'
        % (subject, kind, up, (' class="%s"' % cls) if cls else ""),
    ]
    tail = ["</body>", "</html>", ""]
    if scripts:
        tail = [
            '<script src="%sassets/data.js"></script>' % up,
            '<script src="%sassets/app.js"></script>' % up,
        ] + tail
    return "\n".join(head + body + tail)


def topnav(crumbs, up="../"):
    """crumbs = [(text, href|None), …]; poslední je aktuální stránka."""
    out = [
        '<a class="skiplink" href="#obsah">Přeskočit na obsah</a>',
        '<nav class="topnav" aria-label="Hlavní navigace">',
        '  <div class="wrap topnav-in">',
    ]
    for i, (text, href) in enumerate(crumbs):
        if i:
            out.append('    <span class="crumb-sep" aria-hidden="true">/</span>')
        if href:
            out.append('    <a class="crumb" href="%s">%s</a>' % (href, esc(text)))
        else:
            out.append('    <span class="crumb crumb-cur">%s</span>' % esc(text))
    out += [
        '    <span class="grow"></span>',
        '    <button class="iconbtn" data-act="search" aria-label="Hledat v materiálu">%s</button>' % ICON_SEARCH,
        '    <button class="iconbtn" data-act="theme" aria-label="Přepnout světlý a tmavý režim">%s</button>'
        % ICON_THEME,
        "  </div>",
        "</nav>",
    ]
    return out


# ---------------------------------------------------------------- stránky otázek

def render_question(num, title, body, ctx_base, prev, nxt):
    """Jedna otázka → HTML."""
    global _ids
    _ids = {}
    intro, secs = split_sections(body)

    qhrefs = ctx_base["qhrefs"]
    ctx = Ctx(ctx_base["numfmt"], qhrefs, ctx_base["glossary"], cur_q=num)

    # perex = první čistě textový odstavec před prvním boxem
    lead = ""
    rest_intro = []
    for b in intro:
        if not lead and b["kind"] == "p" and b["style"] == "Normal" and para_text(b):
            lead = inline(b, ctx)
            continue
        rest_intro.append(b)

    nkey = 0
    for h, sb in secs:
        if strip_emoji(h)[0] == "🔑":
            nkey = sum(1 for b in sb if b["kind"] == "p" and b["style"] == "ListParagraph")

    out = topnav(
        [("Státnice", "../index.html"), ("Etopedie", "index.html"), ("Otázka %02d" % num, None)]
    )
    out += [
        "",
        '<header class="qhead">',
        '  <div class="wrap">',
        '    <p class="eyebrow"><span class="qnum">%02d</span> Etopedie · státní závěrečná zkouška</p>' % num,
        "    <h1>%s</h1>" % esc(title),
    ]
    if lead:
        out.append('    <p class="lead">%s</p>' % lead)
    out += [
        '    <div class="qtools">',
        '      <button class="chip chip-prog" data-act="progress" data-q="%d">Označit jako naučené</button>' % num,
    ]
    if nkey:
        out.append(
            '      <button class="chip" data-act="cards">Kartičky <span class="chip-n">%d</span></button>' % nkey
        )
    out += [
        '      <button class="chip" data-act="expand">Rozbalit vše</button>',
        '      <button class="chip" data-act="print">Tisk / PDF</button>',
        "    </div>",
        "  </div>",
        "</header>",
        "",
        '<div class="wrap layout">',
        '  <aside class="side">',
        '    <nav class="toc" aria-label="Obsah otázky"></nav>',
        "  </aside>",
        '  <main id="obsah" class="content">',
    ]

    out.extend(render_flow(rest_intro, "    ", ctx))

    for h, sbody in secs:
        emo, htext = strip_emoji(h)
        cls = SEC_TYPES.get(emo, "read")
        out += ["", '    <section class="sec sec-%s">' % cls]
        hemo = '<span class="hemo" aria-hidden="true">%s</span>' % emo if emo else ""
        out.append('      <h2 id="%s">%s%s</h2>' % (ctx_id(ctx, htext), hemo, esc(htext)))
        out.extend(render_flow(sbody, "      ", ctx, key_terms=(emo == "🔑")))
        out.append("    </section>")

    out += ["", '    <nav class="pager" aria-label="Další otázky">']
    if prev:
        out.append(
            '      <a class="pager-l" href="%s"><span>← Předchozí</span><strong>%02d %s</strong></a>'
            % (prev[1], prev[0], esc(prev[2]))
        )
    else:
        out.append('      <a class="pager-l" href="index.html"><span>←</span><strong>Přehled otázek</strong></a>')
    if nxt:
        out.append(
            '      <a class="pager-r" href="%s"><span>Další →</span><strong>%02d %s</strong></a>'
            % (nxt[1], nxt[0], esc(nxt[2]))
        )
    else:
        out.append('      <a class="pager-r" href="glosar.html"><span>Dál →</span><strong>Glosář pojmů</strong></a>')
    out += ["    </nav>", "  </main>", "</div>", "", footer()]
    return "\n".join(out), nkey


def footer():
    return "\n".join(
        [
            '<footer class="foot">',
            '  <div class="wrap">',
            '    <p>Etopedie · přehledný materiál ke státní závěrečné zkoušce · '
            'právní stav <a href="pravni-aktualnost.html">ověřen k 08/2026</a></p>',
            "  </div>",
            "</footer>",
        ]
    )


def render_simple(title, chapters, ctx_base, *, kind, eyebrow, lead=None, crumb=None):
    """Obecná obsahová stránka (glosář, zákony, dodatek, jak pracovat)."""
    global _ids
    _ids = {}
    mode = "glosar" if kind == "glosar" else ""
    ctx = Ctx(ctx_base["numfmt"], ctx_base["qhrefs"], ctx_base["glossary"], mode=mode)
    ctx.gl_ids = ctx_base.get("gl_ids", {})
    # u jediné kapitoly použijeme jako H1 přímo její název ze zdroje
    h1 = strip_emoji(chapters[0][0])[1] if len(chapters) == 1 else title
    out = topnav([("Státnice", "../index.html"), ("Etopedie", "index.html"), (crumb or title, None)])
    out += [
        "",
        '<header class="qhead qhead-plain">',
        '  <div class="wrap">',
        '    <p class="eyebrow">%s</p>' % esc(eyebrow),
        "    <h1>%s</h1>" % esc(h1),
    ]
    if lead:
        out.append('    <p class="lead">%s</p>' % lead)
    if kind == "glosar":
        out += [
            '    <div class="gfilter">',
            '      <input type="search" id="gq" placeholder="Filtrovat pojmy…" '
            'autocomplete="off" aria-label="Filtrovat pojmy">',
            '      <span class="gcount" id="gcount"></span>',
            "    </div>",
        ]
    out += ["  </div>", "</header>", "", '<div class="wrap layout">',
            '  <aside class="side">', '    <nav class="toc" aria-label="Obsah stránky"></nav>',
            "  </aside>", '  <main id="obsah" class="content">']

    for ch_title, body in chapters:
        intro, secs = split_sections(body)
        # Má-li stránka víc kapitol, dostane každá vlastní H2; u jediné kapitoly
        # už její název nese H1 stránky, takže se neopakuje.
        if len(chapters) > 1:
            emo, htext = strip_emoji(ch_title)
            out += ["", '    <section class="sec sec-read">']
            out.append('      <h2 id="%s">%s%s</h2>' % (
                ctx_id(ctx, htext),
                '<span class="hemo" aria-hidden="true">%s</span>' % emo if emo else "", esc(htext)))
            out.extend(render_flow(intro, "      ", ctx))
            out.append("    </section>")
        else:
            out.extend(render_flow(intro, "    ", ctx))
        for h, sbody in secs:
            emo, htext = strip_emoji(h)
            cls = SEC_TYPES.get(emo, "read")
            out += ["", '    <section class="sec sec-%s">' % cls]
            hemo = '<span class="hemo" aria-hidden="true">%s</span>' % emo if emo else ""
            out.append('      <h2 id="%s">%s%s</h2>' % (ctx_id(ctx, htext), hemo, esc(htext)))
            out.extend(render_flow(sbody, "      ", ctx))
            out.append("    </section>")

    out += ["  </main>", "</div>", "", footer()]
    return "\n".join(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    src = args[0] if args else "source/etopedie_statnice_prehledne.docx"
    outdir = args[1] if len(args) > 1 else "etopedie"
    os.makedirs(outdir, exist_ok=True)

    # Zdrojem pravdy je vygenerované HTML — bez --force nic nepřepisujeme,
    # aby se neztratily ruční úpravy (např. právní opravy a boxy „Aktualizace 2026“).
    existing = [p for p in glob.glob(os.path.join(outdir, "*.html"))]
    if existing and not force:
        print("V %s/ už je %d stránek." % (outdir, len(existing)))
        print("Skript by je přepsal a smazal ruční úpravy. Pokud to opravdu chcete,")
        print("spusťte ho znovu s přepínačem --force.")
        sys.exit(2)

    blocks, numfmt = parse_document(src)
    front, chapters = split_chapters(blocks)
    bytitle = OrderedDict(chapters)

    # --- mapa otázek -------------------------------------------------------
    questions = []
    for title, body in chapters:
        m = re.match(r"^(\d{1,2})\.\s*(.+)$", title)
        if m:
            n = int(m.group(1))
            questions.append((n, m.group(2).strip(), body))
    qhrefs = {n: "otazka-%02d-%s.html" % (n, SLUGS[n]) for n, _, _ in questions}

    # --- mapa glosáře (pojem → id) ----------------------------------------
    glossary, gl_ids, seen = {}, {}, {}
    gl_body = bytitle.get("Závěrečný glosář klíčových pojmů", [])
    for b in gl_body:
        if b["kind"] == "p" and b["style"] == "ListParagraph":
            term = re.split(r"\s[—–]\s", para_text(b), maxsplit=1)[0]
            gid = "p-" + slugify(term, 48)
            n = seen.get(gid, 0)
            seen[gid] = n + 1
            if n:
                gid = "%s-%d" % (gid, n + 1)
            gl_ids[term] = gid
            glossary.setdefault(norm_term(term), gid)

    ctx_base = {"numfmt": numfmt, "qhrefs": qhrefs, "glossary": glossary, "gl_ids": gl_ids}

    # --- otázky ------------------------------------------------------------
    written = []
    meta = []
    for idx, (n, title, body) in enumerate(questions):
        prev = (questions[idx - 1][0], qhrefs[questions[idx - 1][0]], questions[idx - 1][1]) if idx else None
        nxt = (
            (questions[idx + 1][0], qhrefs[questions[idx + 1][0]], questions[idx + 1][1])
            if idx + 1 < len(questions)
            else None
        )
        inner, nkey = render_question(n, title, body, ctx_base, prev, nxt)
        desc = "Otázka %d ke státní závěrečné zkoušce z etopedie: %s" % (n, title)
        page = shell(
            title="%d. %s · Etopedie · Státnice" % (n, title),
            desc=desc,
            body=inner.split("\n"),
            kind="otazka",
        )
        path = os.path.join(outdir, qhrefs[n])
        open(path, "w", encoding="utf-8").write(page)
        written.append(path)
        meta.append({"n": n, "title": title, "href": qhrefs[n], "keys": nkey})

    # --- ostatní kapitoly --------------------------------------------------
    groups = OrderedDict()
    for title, body in chapters:
        slug = SPECIAL_PAGES.get(strip_emoji(title)[1])
        if slug:
            groups.setdefault(slug, []).append((title, body))

    # slug → (H1 u víckapitolových stránek, nadtitulek, perex, název v navigaci)
    PAGE_META = {
        "jak-pracovat": (
            "Průvodce materiálem",
            "Úvod · Etopedie",
            "Struktura otázek, význam barevných boxů a doporučená strategie přípravy.",
            "Jak pracovat",
        ),
        "glosar": (
            "Glosář",
            "Rejstřík · Etopedie",
            "Abecední přehled pojmů z celého materiálu. Pište do filtru a seznam se zúží.",
            "Glosář",
        ),
        "zakony": (
            "Klíčové zákony",
            "Legislativa · Etopedie",
            "Předpisy, jejichž čísla se u státnic cení nejvíc.",
            "Zákony",
        ),
        "aktualizace-2026": (
            "Aktualizační dodatek",
            "Novely a MKN-11 · Etopedie",
            "Změny v klasifikaci a legislativě od doby vzniku původního textu (stav dubna 2026).",
            "Aktualizace",
        ),
    }
    for slug, chs in groups.items():
        title, eyebrow, lead, crumb = PAGE_META[slug]
        inner = render_simple(title, chs, ctx_base, kind=slug, eyebrow=eyebrow, lead=esc(lead), crumb=crumb)
        page = shell(
            title="%s · Etopedie · Státnice" % title,
            desc=lead,
            body=inner.split("\n"),
            kind=slug,
        )
        path = os.path.join(outdir, slug + ".html")
        open(path, "w", encoding="utf-8").write(page)
        written.append(path)

    # --- souhrn pro další kroky -------------------------------------------
    import json

    open("tools/_meta.json", "w", encoding="utf-8").write(
        json.dumps(
            {"questions": meta, "glossary_terms": len(glossary), "front": [para_text(b) for b in front if para_text(b)]},
            ensure_ascii=False,
            indent=1,
        )
    )
    print("zapsáno %d stránek do %s/" % (len(written), outdir))
    print("otázek: %d · pojmů v glosáři: %d · kartiček: %d" % (
        len(meta), len(glossary), sum(m["keys"] for m in meta)))
