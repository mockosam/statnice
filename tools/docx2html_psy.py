#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx2html_psy.py — jednorázový převod dokumentu „SZO PSYCHOLOGIE.docx“ do HTML.

Proč samostatný skript a ne docx2html.py? Zdrojový dokument má úplně jinou
strukturu než etopedie:

  * názvy stylů jsou české (Nadpis1, Odstavecseseznamem, Normlnweb)
  * nadpisové styly se prakticky nepoužívají (2× Nadpis1 na 2429 bloků)
  * podnadpisy jsou jen TUČNÉ ODSTAVCE
  * hranice otázek jsou obyčejné odstavce „N. Název“, které se pletou
    s číslovanými seznamy → musí se párovat s obsahem dokumentu
  * nejsou barevné boxy ani glosář, zato jsou citace v textu a dva obrázky

Vykreslování (inline formátování, seznamy, tabulky, šablona stránky) se přebírá
z docx2html.py, aby oba předměty vypadaly stejně.

    python3 tools/docx2html_psy.py 'SZO PSYCHOLOGIE.docx' psychologie [--force]
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import zipfile
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx2html import (  # noqa: E402
    Ctx,
    deaccent,
    esc,
    footer as _etop_footer,
    parse_document,
    render_flow,
    shell,
    slugify,
    topnav,
)
import docx2html as D  # noqa: E402

SUBJECT = "psychologie"

# české názvy stylů → to, co očekává render_flow z docx2html.py
STYLE_MAP = {
    "Nadpis1": "Heading1", "Nadpis2": "Heading2", "Nadpis3": "Heading3", "Nadpis4": "Heading3",
    "Odstavecseseznamem": "ListParagraph",
    "Normlnweb": "Normal", "Normlnweb0": "Normal",
}

SLUGS = {
    1: "uceni-pojeti",
    2: "uceni-vlivy-smysluplne",
    3: "teorie-uceni",
    4: "socialni-uceni-socializace",
    5: "kognitivni-procesy",
    6: "vykonove-vlastnosti-inteligence",
    7: "postoje-charakter",
    8: "hodnoceni-vykonu-zaka",
    9: "socialni-percepce-chyby",
    10: "motivace-k-uceni",
    11: "specialni-pedagog",
    12: "zak-nadani-heterogenita",
    13: "selhavajici-zaci",
    14: "socialni-zpevnovani",
    15: "klima-skoly",
    16: "tridni-klima",
    17: "rizeni-socialnich-skupin",
    18: "interakce-moralni-vyvoj",
    19: "komunikace-bariery",
}

# obrázky: rId → (název souboru, popisek, alt). Logo fakulty se nepoužívá.
IMAGES = {
    "rId8": (
        "maslowova-pyramida.jpeg",
        "Maslowova hierarchie potřeb — sedmistupňová podoba s kognitivními a estetickými potřebami.",
        "Pyramida potřeb podle Maslowa. Odspodu: fyziologické potřeby (hlad, žízeň); "
        "potřeby bezpečí; potřeby sounáležitosti a lásky; potřeby uznání; kognitivní potřeby "
        "(vědět, rozumět, zkoumat); estetické potřeby (symetrie, řád, krása); "
        "na vrcholu potřeby seberealizace.",
    ),
}
SKIP_IMAGES = {"rId7"}          # logo Pedagogické fakulty UJEP


# ---------------------------------------------------------------- pomůcky

def ptext(b: dict) -> str:
    if b["kind"] == "table":
        return ""
    return "".join(p.get("t", "") for p in b["parts"]).strip()


def is_bold(b: dict) -> bool:
    if b["kind"] == "table":
        return False
    runs = [p for p in b["parts"] if p.get("t", "").strip()]
    return bool(runs) and all(p.get("b") for p in runs)


def is_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.75


def norm_cmp(s: str) -> str:
    """Text pro fuzzy porovnání s obsahem — bez diakritiky, interpunkce a mezer."""
    return re.sub(r"[^a-z0-9]", "", deaccent(s).lower())


# ---------------------------------------------------------------- struktura

def normalize_styles(blocks: list[dict]) -> None:
    for b in blocks:
        if b["kind"] == "p":
            b["style"] = STYLE_MAP.get(b["style"], b["style"])
        else:
            for row in b["rows"]:
                for cell in row:
                    normalize_styles(cell)


def extract_toc(blocks: list[dict]) -> "OrderedDict[int, str]":
    """Obsah na začátku dokumentu: odstavce „N. Název“ před výkladem."""
    toc: OrderedDict[int, str] = OrderedDict()
    for b in blocks[:80]:
        m = re.match(r"^(\d{1,2})\.\s+(.{10,})$", ptext(b))
        if m:
            n = int(m.group(1))
            if 1 <= n <= 19 and n not in toc:
                toc[n] = re.sub(r"\s+", " ", m.group(2)).strip()
    return toc


def find_boundaries(blocks: list[dict], toc: dict, first: int) -> dict:
    """
    Najde blok, kde začíná každá otázka. Samotný vzor „N. …“ nestačí — stejně
    vypadají položky číslovaných seznamů. Kandidát proto musí odpovídat názvu
    z obsahu a ležet za předchozí nalezenou otázkou.
    """
    bounds: dict[int, int] = {}
    cursor = first
    for n in sorted(toc):
        want = norm_cmp(toc[n])[:34]
        best = None
        for i in range(cursor, len(blocks)):
            t = ptext(blocks[i])
            if len(t) < 8:
                continue
            m = re.match(r"^(\d{1,2})[\.\s]\s*(.+)$", t)
            cand = norm_cmp(m.group(2)) if m and int(m.group(1)) == n else norm_cmp(t)
            if cand[:34] == want:
                best = i
                break
        if best is not None:
            bounds[n] = best
            cursor = best + 1
    return bounds


def unlist_definitions(blocks: list[dict]) -> int:
    """
    Odstavec uvozený „=“ je definice předchozího nadpisu, ne položka seznamu.
    Vyřadíme ho ze seznamu, aby se nevykresloval jako odrážka „• = …“.
    """
    n = 0
    for b in blocks:
        if b["kind"] == "p" and ptext(b).startswith("=") and (b.get("num") or b["style"] == "ListParagraph"):
            b["style"], b["num"] = "Normal", None
            n += 1
    return n


def promote_headings(blocks: list[dict]) -> int:
    """
    Tučný odstavec, který není položkou seznamu a není delší než 90 znaků,
    slouží v tomto dokumentu jako podnadpis.

    Úroveň se rozhoduje pro každou otázku zvlášť: má-li aspoň dva nadpisy
    verzálkami, jsou verzálky H2 a ostatní H3 (zdroj tedy rozlišuje dvě
    úrovně). Jinak jsou všechny nadpisy H2 — jednoúrovňová struktura je
    lepší než stránka bez jediného H2, kde nefunguje obsah v levém sloupci.
    """
    cands = []
    for b in blocks:
        if b["kind"] != "p" or b.get("num") or not is_bold(b):
            continue
        t = ptext(b)
        if not t or len(t) > 90:
            continue
        if re.match(r"^\d{1,2}[\.\)]\s", t) and len(t) < 20:   # „1. “ u krátkých položek
            continue
        cands.append(b)
    two_levels = sum(1 for b in cands if is_caps(ptext(b))) >= 2
    for b in cands:
        b["style"] = "Heading2" if (not two_levels or is_caps(ptext(b))) else "Heading3"
    return len(cands)


"""
Poznámka k výčtům: tento dokument přiděluje číslování (w:numPr) odstavcům se
stylem Normal — 1722 odstavců z 2429. Ve Wordu to jsou odrážky, jen bez stylu
ListParagraph. Řeší to `is_list_item()` v docx2html.py; žádná heuristika nad
délkou a velikostí písmen tady není potřeba.
"""


# ---------------------------------------------------------------- citace

CIT_RE = re.compile(r"\(([^()]{3,150}?\d{4}[^()]{0,30})\)")
PAGE_RE = re.compile(r"s\.\s*([\d\s\-–,]+)")


def parse_citations(text: str) -> list[tuple[str, str, str]]:
    """Z textu vytáhne (autoři, rok, strany). Sloučené citace rozdělí na ';'."""
    out = []
    for m in CIT_RE.finditer(text):
        for part in m.group(1).split(";"):
            ym = re.search(r"\b(1[89]\d\d|20\d\d)\b", part)
            if not ym:
                continue
            authors = part[: ym.start()].strip(" ,;&")
            if not authors or not re.search(r"[A-ZŠČŘŽÝÁÍÉÚŮŇŤĎ]", authors):
                continue
            pages = ""
            pm = PAGE_RE.search(part[ym.end():])
            if pm:
                pages = re.sub(r"\s+", "", pm.group(1)).strip(",")
            out.append((re.sub(r"\s+", " ", authors), ym.group(1), pages))
    return out


def cite_key(authors: str, year: str) -> str:
    """Sjednotí zápis autorů, aby se varianty téhož díla nerozpadly na dvě položky."""
    a = authors.strip()
    a = re.sub(r"^(?:podle|viz|srov\.?|např\.?|dle)\s+", "", a, flags=re.I)
    a = re.sub(r"\ba\s+kolektiv\b|\bet\s+al\.?", "a kol.", a, flags=re.I)
    a = re.sub(r"\bkol\.?\s*$", "a kol.", a) if re.search(r"\bkol\.?\s*$", a) and " a kol" not in a else a
    a = re.sub(r"\s+", " ", a).strip(" ,;&")
    return "%s, %s" % (a, year)


def collect_sources(blocks: list[dict]) -> "OrderedDict[str, list[str]]":
    """Zdroje citované v úseku dokumentu → seřazené, s čísly stran."""
    found: OrderedDict[str, list[str]] = OrderedDict()
    for b in blocks:
        text = ptext(b) if b["kind"] == "p" else " ".join(
            ptext(p) for row in b["rows"] for cell in row for p in cell)
        for authors, year, pages in parse_citations(text):
            key = cite_key(authors, year)
            found.setdefault(key, [])
            if pages and pages not in found[key]:
                found[key].append(pages)
    return OrderedDict(sorted(found.items(), key=lambda kv: deaccent(kv[0]).lower()))


# ---------------------------------------------------------------- definice → kartičky

# nadpisy, které jsou vlastně začátkem věty, nedávají použitelný pojem
STEM_RE = re.compile(
    r"\b(označujeme|rozlišujeme|rozdělujeme|patří|jsou to|dělíme|vychází|zahrnuje[mn]e|"
    r"má podobu|podle|jedná se)\b", re.I)


def collect_definitions(blocks: list[dict]) -> list[tuple[str, str]]:
    """
    Dvojice pojem/definice pro kartičky. Dokument nemá sekci klíčových pojmů,
    ale platí, že za podnadpisem často následuje jeho definice — buď uvozená
    „=“, nebo začínající malým písmenem, takže věta pokračuje z nadpisu.
    """
    pairs = []
    for i, b in enumerate(blocks):
        if b["kind"] != "p" or b["style"] not in ("Heading2", "Heading3"):
            continue
        term = ptext(b).rstrip(" :").strip()
        if not (3 <= len(term) <= 55) or len(term.split()) > 6 or STEM_RE.search(term):
            continue
        for j in range(i + 1, min(i + 3, len(blocks))):
            nb = blocks[j]
            if nb["kind"] != "p" or nb["style"] in ("Heading2", "Heading3"):
                break
            t = ptext(nb)
            if not t:
                continue
            if t.startswith("="):
                t = t.lstrip("= ").strip()
            elif not (t[0].islower() and not re.match(r"^(a |ale |nebo |např|tj\.|tzn|proto)", t)):
                break
            if len(t) >= 30 and not t.endswith(","):
                pairs.append((term, t.rstrip()))
            break
    # jeden pojem jednou
    seen, out = set(), []
    for term, d in pairs:
        k = deaccent(term).lower()
        if k in seen:
            continue
        seen.add(k)
        out.append((term, d))
    return out


# ---------------------------------------------------------------- render

def split_title(full: str) -> tuple[str, str]:
    """Dlouhý název z obsahu → krátký titulek pro H1 + plné znění jako perex."""
    short = re.split(r"\s+[-–—]\s+|\s*\(", full, maxsplit=1)[0].strip(" .,")
    if len(short) < 9 or len(short) > 74:
        short = full[:70].rsplit(" ", 1)[0]
    return short.strip(" .,"), full


def img_html(rid: str, up: str = "") -> str:
    if rid in SKIP_IMAGES or rid not in IMAGES:
        return ""
    fname, caption, alt = IMAGES[rid]
    return (
        '\n      <figure class="fig">'
        '\n        <img src="%simg/%s" alt="%s" loading="lazy">'
        '\n        <figcaption>%s</figcaption>'
        '\n      </figure>' % (up, fname, esc(alt), esc(caption))
    )


BIB = {}
# ručně psané boxy „Doplněno 2026“ (kontrola aktuálnosti), klíč = číslo otázky.
# Drží se v datovém souboru, aby je opětovné spuštění konvertoru nesmazalo.
EXTRA = {}


def bib_slug(key: str) -> str:
    return "d-" + slugify(key, 46)


def sources_box(sources: dict, ind: str) -> list[str]:
    if not sources:
        return []
    out = [
        '%s<aside class="box src">' % ind,
        '%s  <h4><span class="bemo" aria-hidden="true">📚</span>Zdroje k této otázce</h4>' % ind,
        "%s  <ul>" % ind,
    ]
    unresolved = 0
    for key, pages in sources.items():
        rec = BIB.get(key) or {}
        p = (" <span class=\"src-pages\">s. %s</span>" % esc(", ".join(pages))) if pages else ""
        if rec.get("title"):
            body = '<a href="literatura.html#%s">%s</a>. <em>%s.</em> %s%s' % (
                bib_slug(key), esc(key), esc(rec["title"]), esc(rec["imprint"]), p)
        else:
            unresolved += 1
            body = '<a href="literatura.html#%s">%s</a>%s' % (bib_slug(key), esc(key), p)
        out.append("%s    <li>%s</li>" % (ind, body))
    note = ("Zdrojový dokument uváděl jen zkrácené citace; plné údaje byly dohledány. "
            "Celý seznam je v <a href=\"literatura.html\">přehledu literatury</a>.")
    if unresolved:
        note += " U %d z těchto citací se úplný záznam ověřit nepodařilo." % unresolved
    out += ["%s  </ul>" % ind, '%s  <p class="src-note">%s</p>' % (ind, note), "%s</aside>" % ind]
    return out


def footer() -> str:
    return "\n".join([
        '<footer class="foot">',
        '  <div class="wrap">',
        '    <p>Psychologie · otázky ke státní závěrečné zkoušce · '
        'aktuálnost <a href="aktualnost.html">ověřena k 08/2026</a></p>',
        "  </div>",
        "</footer>",
    ])


def render_question(n, short, full, body, ctx_base, prev, nxt):
    D._ids = {}
    ctx = Ctx(ctx_base["numfmt"], {}, {})
    ctx.images = {rid: img_html(rid) for rid in IMAGES}
    sources = collect_sources(body)
    defs = collect_definitions(body)

    out = topnav([("Státnice", "../index.html"), ("Psychologie", "index.html"),
                  ("Otázka %02d" % n, None)])
    out += [
        "",
        '<header class="qhead">',
        '  <div class="wrap">',
        '    <p class="eyebrow"><span class="qnum">%02d</span> Psychologie · státní závěrečná zkouška</p>' % n,
        "    <h1>%s</h1>" % esc(short),
        '    <p class="lead">%s</p>' % esc(full),
        '    <div class="qtools">',
        '      <button class="chip chip-prog" data-act="progress" data-q="%d">Označit jako naučené</button>' % n,
    ]
    if defs:
        out.append('      <button class="chip" data-act="cards">Kartičky <span class="chip-n">%d</span></button>'
                   % len(defs))
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

    # klíčové pojmy z definic „=“ — kvůli kartičkám ve stejné podobě jako u etopedie
    if defs:
        out += ["", '    <section class="sec sec-key">',
                '      <h2 id="klicove-pojmy"><span class="hemo" aria-hidden="true">🔑</span>Klíčové pojmy</h2>',
                "      <ul>"]
        for term, d in defs:
            out.append("        <li><strong>%s</strong> — %s</li>" % (esc(term), esc(d)))
        out += ["      </ul>", "    </section>"]

    out += ["", '    <section class="sec sec-read">']
    out.extend(render_flow(body, "      ", ctx))
    out.append("    </section>")
    extra = EXTRA.get(str(n))
    if extra:
        out += ["", extra]
    out += [""] + sources_box(sources, "    ")

    out += ["", '    <nav class="pager" aria-label="Další otázky">']
    if prev:
        out.append('      <a class="pager-l" href="%s"><span>← Předchozí</span><strong>%02d %s</strong></a>'
                   % (prev[1], prev[0], esc(prev[2])))
    else:
        out.append('      <a class="pager-l" href="index.html"><span>←</span><strong>Přehled otázek</strong></a>')
    if nxt:
        out.append('      <a class="pager-r" href="%s"><span>Další →</span><strong>%02d %s</strong></a>'
                   % (nxt[1], nxt[0], esc(nxt[2])))
    else:
        out.append('      <a class="pager-r" href="literatura.html"><span>Dál →</span><strong>Literatura</strong></a>')
    out += ["    </nav>", "  </main>", "</div>", "", footer()]
    return "\n".join(out), sources, defs


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    src = args[0] if args else "SZO PSYCHOLOGIE.docx"
    outdir = args[1] if len(args) > 1 else SUBJECT
    os.makedirs(outdir, exist_ok=True)
    existing = glob.glob(os.path.join(outdir, "otazka-*.html"))
    if existing and not force:
        print("V %s/ už je %d stránek otázek — bez --force nepřepisuji." % (outdir, len(existing)))
        sys.exit(2)

    here = os.path.dirname(os.path.abspath(__file__))
    bibpath = os.path.join(here, "_bib_psychologie.json")
    if os.path.exists(bibpath):
        BIB.update({k: v for k, v in json.load(open(bibpath, encoding="utf-8")).items()
                    if not k.startswith("_")})
    extrapath = os.path.join(here, "_doplnky_psychologie.json")
    if os.path.exists(extrapath):
        EXTRA.update(json.load(open(extrapath, encoding="utf-8")))

    blocks, numfmt = parse_document(src)
    normalize_styles(blocks)
    toc = extract_toc(blocks)
    first_content = max(i for i, b in enumerate(blocks[:80]) if re.match(r"^\d{1,2}\.\s", ptext(b))) + 1
    bounds = find_boundaries(blocks, toc, first_content)
    unlisted = unlist_definitions(blocks)

    # Struktura se dovozuje po jednotlivých otázkách — úroveň nadpisů se
    # rozhoduje z toho, jak nadpisy vypadají v rámci té které otázky.
    order_tmp = sorted(bounds.items(), key=lambda kv: kv[1])
    promoted = 0
    for i, (_qn, st) in enumerate(order_tmp):
        en = order_tmp[i + 1][1] if i + 1 < len(order_tmp) else len(blocks)
        promoted += promote_headings(blocks[st + 1:en])

    print("definic vyřazených ze seznamů: %d" % unlisted)
    print("obsah: %d otázek · hranice nalezeny pro %d · podnadpisů z tučného textu: %d"
          % (len(toc), len(bounds), promoted))
    missing = [n for n in toc if n not in bounds]
    if missing:
        print("  ! bez vypracovaného textu ve zdroji: %s" % missing)

    # obrázky
    imgdir = os.path.join(outdir, "img")
    os.makedirs(imgdir, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        for rid, (fname, _c, _a) in IMAGES.items():
            m = re.search(r'Id="%s"[^>]*Target="([^"]+)"' % rid, rels)
            if not m:
                continue
            data = z.read("word/" + m.group(1).lstrip("/"))
            open(os.path.join(imgdir, fname), "wb").write(data)
            print("  obrázek: img/%s (%d kB)" % (fname, len(data) // 1024))

    ctx_base = {"numfmt": numfmt}
    order = sorted(bounds.items(), key=lambda kv: kv[1])
    meta, bmap = [], {}

    def href(n):
        return "otazka-%02d-%s.html" % (n, SLUGS[n])

    for idx, (n, start) in enumerate(order):
        end = order[idx + 1][1] if idx + 1 < len(order) else len(blocks)
        body = blocks[start + 1:end]
        short, full = split_title(toc[n])
        nums = sorted(toc)
        pi = nums.index(n)
        prev = None
        for k in reversed(nums[:pi]):
            prev = (k, href(k), split_title(toc[k])[0]); break
        nxt = None
        for k in nums[pi + 1:]:
            nxt = (k, href(k), split_title(toc[k])[0]); break
        inner, sources, defs = render_question(n, short, full, body, ctx_base, prev, nxt)
        page = shell(
            title="%d. %s · Psychologie · Státnice" % (n, short),
            desc="Otázka %d ke státní závěrečné zkoušce z psychologie: %s" % (n, short),
            body=inner.split("\n"),
            subject=SUBJECT,
            kind="otazka",
        )
        open(os.path.join(outdir, href(n)), "w", encoding="utf-8").write(page)
        bmap[href(n)] = [start, end]
        meta.append({"n": n, "short": short, "full": full, "href": href(n),
                     "sources": {k: v for k, v in sources.items()}, "cards": len(defs)})

    json.dump({"toc": toc, "bounds": bounds, "missing": missing, "map": bmap,
               "front": [ptext(b) for b in blocks[:first_content] if ptext(b)],
               "questions": meta},
              open("tools/_meta_psychologie.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    # ---- stránka Literatura ------------------------------------------------
    allsrc: dict[str, list[int]] = {}
    pages_of: dict[str, list[str]] = {}
    for m in meta:
        for k, pages in m["sources"].items():
            allsrc.setdefault(k, []).append(m["n"])
            for p in pages:
                pages_of.setdefault(k, [])
                if p not in pages_of[k]:
                    pages_of[k].append(p)

    known = [k for k in allsrc if (BIB.get(k) or {}).get("title")]
    unknown = [k for k in allsrc if not (BIB.get(k) or {}).get("title")]

    lit = topnav([("Státnice", "../index.html"), ("Psychologie", "index.html"),
                  ("Literatura", None)])
    lit += [
        "",
        '<header class="qhead qhead-plain">',
        '  <div class="wrap">',
        '    <p class="eyebrow">Citovaná díla · Psychologie</p>',
        "    <h1>Literatura</h1>",
        '    <p class="lead">Přehled všech %d děl, na která se zdrojový text odvolává. '
        'U každého je uvedeno, ve kterých otázkách je citováno.</p>' % len(allsrc),
        "  </div>",
        "</header>",
        "",
        '<div class="wrap layout">',
        '  <aside class="side"><nav class="toc" aria-label="Obsah stránky"></nav></aside>',
        '  <main id="obsah" class="content">',
        "",
        '    <aside class="box warn">',
        '      <h4><span class="bemo" aria-hidden="true">⚠️</span>Odkud údaje jsou</h4>',
        '      <p>Zdrojový dokument uváděl citace <strong>jen ve zkrácené podobě</strong> — '
        '„(Čáp, 1997, s. 62)“ — a seznam literatury neobsahoval vůbec. Plné bibliografické '
        'údaje jsou proto <strong>dohledané</strong>, ne přejaté z dokumentu.</p>',
        '      <p>Ověřit se podařilo <strong>%d z %d</strong> děl. U zbývajících %d '
        'je uvedena jen zkrácená citace tak, jak ji uvádí zdroj — dohledávat je '
        'odhadem by do studijního materiálu vneslo nepravdivé údaje.</p>'
        % (len(known), len(allsrc), len(unknown)),
        "    </aside>",
        "",
        '    <section class="sec sec-read">',
        '      <h2 id="overena-dila">Díla s ověřeným záznamem <span class="h-count">%d</span></h2>' % len(known),
        '      <dl class="glist">',
    ]
    for k in sorted(known, key=lambda s: deaccent(s).lower()):
        rec = BIB[k]
        qs = ", ".join("<a href=\"%s\">%d</a>" % (href(n), n) for n in sorted(allsrc[k]))
        pg = (" · s. " + ", ".join(pages_of.get(k, []))) if pages_of.get(k) else ""
        lit += [
            '        <div class="gitem" id="%s">' % bib_slug(k),
            "          <dt>%s</dt>" % esc(k),
            "          <dd><em>%s.</em> %s. ISBN %s.<br><span class=\"src-pages\">Citováno v otázkách %s%s</span>%s</dd>"
            % (esc(rec["title"]), esc(rec["imprint"]), esc(rec["isbn"]), qs, pg,
               ('<br><span class="src-pages">%s</span>' % esc(rec["note"])) if rec.get("note") else ""),
            "        </div>",
        ]
    lit += ["      </dl>", "    </section>", "",
            '    <section class="sec sec-warn">',
            '      <h2 id="neoverena-dila">Citace bez ověřeného záznamu <span class="h-count">%d</span></h2>' % len(unknown),
            '      <p>Tyto citace zdroj uvádí, ale úplný bibliografický záznam se ověřit nepodařilo. '
            'Ověřte je prosím podle svých studijních materiálů nebo v katalogu knihovny.</p>',
            '      <dl class="glist">']
    for k in sorted(unknown, key=lambda s: deaccent(s).lower()):
        rec = BIB.get(k) or {}
        qs = ", ".join("<a href=\"%s\">%d</a>" % (href(n), n) for n in sorted(allsrc[k]))
        pg = (" · s. " + ", ".join(pages_of.get(k, []))) if pages_of.get(k) else ""
        extra = ('<br><span class="src-pages">%s</span>' % esc(rec["note"])) if rec.get("note") else ""
        lit += [
            '        <div class="gitem" id="%s">' % bib_slug(k),
            "          <dt>%s</dt>" % esc(k),
            '          <dd><span class="src-pages">Citováno v otázkách %s%s</span>%s</dd>' % (qs, pg, extra),
            "        </div>",
        ]
    lit += ["      </dl>", "    </section>", "",
            '    <nav class="pager" aria-label="Další stránky">',
            '      <a class="pager-l" href="index.html"><span>←</span><strong>Přehled otázek</strong></a>',
            '      <a class="pager-r" href="aktualnost.html"><span>Dál →</span><strong>Aktuálnost materiálu</strong></a>',
            "    </nav>", "  </main>", "</div>", "", footer()]

    open(os.path.join(outdir, "literatura.html"), "w", encoding="utf-8").write(shell(
        title="Literatura · Psychologie · Státnice",
        desc="Přehled %d děl citovaných ve zpracovaných otázkách z psychologie." % len(allsrc),
        body=lit, subject=SUBJECT, kind="literatura"))

    print("zapsáno %d otázek · kartiček %d · citovaných děl %d (ověřeno %d, neověřeno %d)"
          % (len(meta), sum(m["cards"] for m in meta), len(allsrc), len(known), len(unknown)))
