#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx2html_ped.py — převod „SZZ- Padagogika (komplet).DOCX“ do pedagogika/.

Čtvrtý zdrojový dokument. Nadpisové styly má české jako poradenství a trpí
stejnou hlavní vadou: **`Nadpis1` je zároveň nadpis otázky i nadpis sekce
uvnitř otázky** (20 z 26 začíná otázku, 6 je jen podnadpis). Hranice otázek
proto nejsou heuristika, ale ověřovaná mapa QSTART — když se dokument změní,
skript spadne a řekne to, místo aby vygeneroval rozsypané stránky.

Proti poradenství navíc:

  * dokument má **obsah polem** (styl Obsah1), jehož text je v <w:hyperlink>,
    takže z něj perex vytáhnout nejde — perexem je celý text nadpisu Nadpis1,
    což je stejně přesně znění okruhu ze zadání A21
  * tabulky jsou jen dvě a jedna z nich má **titulkový řádek přes celou šířku**
    (1 buňka), který by se jinak stal jediným záhlavím dvousloupcové tabulky
  * ze 14 vložených obrázků se nepublikuje **ani jeden** — jsou to snímek
    PowerPointu se jménem autorky v titulkové liště, logo fakulty, nevykreslitelné
    EMF a skeny knižních stránek. Schémata a tabulky z nich jsou překreslené
    nativně v tools/_doplnky_pedagogika.json, takže jsou čitelné i na mobilu
    a v tisku; u každé vynechávky je na stránce box, co tam bylo a proč.

Vykreslování se přebírá z docx2html.py a heuristika klíčových pojmů
z docx2html_spec.py, aby všechny čtyři předměty vypadaly a chovaly se stejně.

    python3 tools/docx2html_ped.py 'SZZ- Padagogika (komplet).DOCX' pedagogika [--force]
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx2html import (  # noqa: E402
    Ctx,
    esc,
    parse_document,
    render_flow,
    shell,
    split_sections,
    strip_emoji,
    topnav,
    SEC_TYPES,
)
import docx2html as D  # noqa: E402
import docx2html_spec as S  # noqa: E402

SUBJECT = "pedagogika"
LABEL = "Pedagogika"

# české názvy stylů → to, co očekává render_flow z docx2html.py.
# Obsah1/Nadpisobsahu jsou automatický obsah dokumentu — leží před první
# otázkou, takže se do stránek stejně nedostanou, ale ať se netváří jako nadpis.
STYLE_MAP = {
    "Nadpis1": "Heading1", "Nadpis2": "Heading2", "Nadpis3": "Heading3",
    "Nadpis4": "Heading4", "Nadpis5": "Heading4",
    "Odstavecseseznamem": "ListParagraph",
    "Nzev": "Title", "Normlnweb": "Normal", "Bezmezer": "Normal",
    "Obsah1": "Normal", "Obsah2": "Normal", "Nadpisobsahu": "Normal",
}

# Blok, na kterém začíná nadpis otázky, a začátek jeho textu pro kontrolu.
# Všech 20 má styl Nadpis1; zbylých 6 Nadpis1 jsou podnadpisy uvnitř otázek
# 9 a 12 a demote_inner_h1() z nich udělá sekce.
QSTART = {
    1: (47, "Pedagogika v historické perspektivě"),
    2: (318, "Výzkum v pedagogice"),
    3: (431, "Sociometrie v pedagogickém výzkumu"),
    4: (548, "Smysl a podmínky výchovy"),
    5: (666, "Metody a organizační formy vyučování"),
    6: (986, "Komunikace jako nástroj dosahování profesních cílů"),
    7: (1207, "Státní správa a samospráva ve školství"),
    8: (1352, "Pedagogické teorie v kontextu speciální pedagogiky"),
    9: (1638, "Teorie výchovy a vzdělávání z genderové perspektivy"),
    10: (1702, "Mediální gramotnost"),
    11: (1843, "Rozvíjení sociálních kompetencí"),
    12: (1948, "Výchova ve volném čase"),
    13: (2122, "Speciální pedagog jako povolání"),
    14: (2224, "Osobnost a autorita pedagoga"),
    15: (2296, "Obecné pojetí nástrojů edukační činnosti"),
    16: (2443, "Výchovný styl v kontextu typologie osobnosti pedagoga"),
    17: (2584, "Etika v životě člověka a metody etické výchovy"),
    18: (2652, "Hodnocení, evaluace"),
    19: (2827, "Filozofie výchovy v historické perspektivě"),
    20: (3137, "Koncept výchovy a vzdělávání dle J. A. Komenského"),
}

# Bloky titulní strany, které se vědomě nepublikují. Zdroj je podepsaný jménem
# autorky; ostatní tři předměty svého autora na webu neuvádějí a repozitář je
# veřejný, tak to držíme stejně. Do tools/_corrections.txt to nepatří — tam by
# se jméno muselo napsat, a tím by se do repozitáře dostalo.
# check_fidelity.py --map si tento seznam přečte z _meta_pedagogika.json.
REDACTED = {
    "23": "jméno autorky z titulní strany — osobní údaj, nepublikuje se",
}

# Nadpis3 delší než tohle není nadpis, ale věta omylem odsazená stylem
# („Výchovný cíl = základní pedagogická kategorie, kategorie historická – …“).
# Do <h3> nepatří — rozbila by obsah v levém sloupci i tisk.
LONG_HEADING = 150

# krátký titulek pro H1 a název souboru (plné znění okruhu jde do perexu)
TITLES = {
    1: ("Pedagogika v historické perspektivě", "pedagogika-historicka-perspektiva"),
    2: ("Výzkum v pedagogice", "vyzkum-v-pedagogice"),
    3: ("Sociometrie", "sociometrie"),
    4: ("Smysl a podmínky výchovy", "smysl-podminky-vychovy"),
    5: ("Metody a organizační formy vyučování", "metody-formy-vyucovani"),
    6: ("Komunikace, klima školy a třídy", "komunikace-klima-skoly"),
    7: ("Státní správa a samospráva ve školství", "statni-sprava-skolstvi"),
    8: ("Pedagogické teorie", "pedagogicke-teorie"),
    9: ("Gender ve výchově a vzdělávání", "gender-vychova-vzdelavani"),
    10: ("Mediální gramotnost", "medialni-gramotnost"),
    11: ("Rozvíjení sociálních kompetencí", "socialni-kompetence"),
    12: ("Výchova ve volném čase", "vychova-ve-volnem-case"),
    13: ("Speciální pedagog jako povolání", "specialni-pedagog-povolani"),
    14: ("Osobnost a autorita pedagoga", "osobnost-autorita-pedagoga"),
    15: ("Kázeň, svoboda a sociální patologie", "kazen-svoboda-socialni-patologie"),
    16: ("Výchovný styl a zvládání stresu", "vychovny-styl-stres"),
    17: ("Etika a etická výchova", "etika-eticka-vychova"),
    18: ("Hodnocení, evaluace, autoevaluace", "hodnoceni-evaluace"),
    19: ("Filozofie výchovy", "filozofie-vychovy"),
    20: ("J. A. Komenský", "komensky"),
}

# ---------------------------------------------------------------- obrázky
#
# Ze 14 vložených obrázků (12 unikátních) se nepublikuje ani jeden a je to
# záměr, ne chyba konverze. Schémata a tabulky, které nesly, jsou překreslené
# nativně — viz „redraw“ v tools/_doplnky_pedagogika.json.
IMAGES: dict[str, tuple[str, str, str]] = {}

# rId → proč se nepoužívá (jen pro výpis při konverzi)
SKIP_IMAGES = {
    "rId8": "logo fakulty na titulní straně",
    "rId9": "sken schématu z knihy (prosvítá text z rubu); překresleno jako HTML",
    "rId10": "sken tabulky z knihy; překreslena jako HTML tabulka",
    "rId11": "snímek PowerPointu se jménem autorky v titulkové liště a s hlavním panelem",
    "rId13": "totéž (druhé vložení téhož snímku)",
    "rId12": "snímek slidu z cizí prezentace; obsah přepsán do textu",
    "rId14": "totéž (druhé vložení téhož slidu)",
    "rId15": "sken schématu typů proměnných; překresleno jako HTML tabulka",
    "rId16": "vektorové EMF (937 kB) — prohlížeče ho nevykreslí",
    "rId17": "sken Obr. 13.1 z knihy; překresleno jako inline SVG",
    "rId18": "sken Obr. 13.2 z knihy; překresleno jako inline SVG",
    "rId19": "sken Obr. 13.3 z knihy; překresleno jako inline SVG",
    "rId20": "sken klasifikace metod z knihy; překreslena jako vnořený seznam",
    "rId21": "sken Tab. 2 z knihy; překreslena jako HTML tabulka",
}


# ---------------------------------------------------------------- pomůcky

def ptext(b: dict) -> str:
    return S.ptext(b)


def flat(s: str) -> str:
    """Text pro srovnání s mapou hranic — zdroj používá nezlomitelné mezery."""
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def normalize_styles(blocks: list[dict]) -> None:
    for b in blocks:
        if b["kind"] == "p":
            b["style"] = STYLE_MAP.get(b["style"], b["style"])
        else:
            for row in b["rows"]:
                for cell in row:
                    normalize_styles(cell)


def drop_empty_headings(body: list[dict]) -> tuple[list[dict], int]:
    """
    Nadpis bez textu by udělal prázdnou sekci s prázdnou položkou v obsahu.
    Ve zdroji jich je šest — pozůstatky po mazání.
    """
    out, n = [], 0
    for b in body:
        if b["kind"] == "p" and b["style"].startswith("Heading") and not ptext(b):
            n += 1
            continue
        out.append(b)
    return out, n


def demote_long_headings(body: list[dict]) -> int:
    """Věta odsazená stylem Nadpis3 → normální odstavec (viz LONG_HEADING)."""
    n = 0
    for b in body:
        if b["kind"] != "p" or b["style"] not in ("Heading3", "Heading4"):
            continue
        if len(ptext(b)) > LONG_HEADING:
            b["style"] = "Normal"
            n += 1
    return n


def split_table_captions(body: list[dict]) -> int:
    """
    Tabulka, jejíž první řádek má jednu buňku a další víc, má nahoře titulek
    přes celou šířku. render_table() by z něj udělal jediné záhlaví a zbytek
    tabulky by zůstal bez názvů sloupců (a bez data-label pro mobil).
    Titulek proto vyjmeme před tabulku jako samostatný odstavec.
    """
    n = 0
    for i, b in enumerate(body):
        if b["kind"] != "table" or len(b["rows"]) < 2:
            continue
        if len(b["rows"][0]) != 1 or len(b["rows"][1]) < 2:
            continue
        caption = b["rows"].pop(0)[0]
        body[i:i] = [{"kind": "p", "style": "Normal", "num": None, "lvl": 0,
                      "parts": [{"t": " ".join(ptext(p) for p in caption if ptext(p)),
                                 "b": True, "i": False}]}]
        n += 1
    return n


# ---------------------------------------------------------------- render

def footer() -> str:
    return "\n".join([
        '<footer class="foot">',
        '  <div class="wrap">',
        '    <p>%s · otázky ke státní závěrečné zkoušce · '
        'právní stav <a href="pravni-aktualnost.html">ověřen k 08/2026</a></p>' % LABEL,
        "  </div>",
        "</footer>",
    ])


# Ruční opravy a doplňky z tools/_doplnky_pedagogika.json. Drží se mimo HTML,
# aby je opětovné spuštění konvertoru nesmazalo — bez toho by se právní opravy
# a překreslené obrázky musely psát znovu po každé změně konvertoru.
FIXES: dict[str, list] = {}
BOXES: dict[str, str] = {}
NOTES: dict[str, str] = {}
TERMS: dict[str, dict] = {}


def adjust_terms(n: int, keys: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Ruční zásahy do automaticky posbíraných klíčových pojmů.

    Z klíčových pojmů se dělají kartičky a glosář, takže na jejich kvalitě
    záleží víc než na zbytku stránky. Heuristika v docx2html_spec.py občas
    urve začátek věty („Odměna může být materiální“) nebo u příjmení psaných
    verzálkami zmenší i jméno („Ellen keyová“). Opravy se drží tady, ne v HTML.

      drop   — pojmy, které se zahodí
      rename — přepsaný název pojmu (definice zůstává)
      add    — ručně dopsané dvojice pojem/definice

    Neexistující klíč v drop/rename se hlásí jako problém, aby soubor tiše
    nezestárl, až se dokument nebo heuristika změní.
    """
    cfg = TERMS.get(str(n))
    if not cfg:
        return keys, []
    drop = list(cfg.get("drop", []))
    ren = dict(cfg.get("rename", {}))
    have = {t for t, _ in keys}
    problems = ["otázka %d: pojem %r k odstranění neexistuje" % (n, t)
                for t in drop if t not in have]
    problems += ["otázka %d: pojem %r k přejmenování neexistuje" % (n, t)
                 for t in ren if t not in have]
    out = [(ren.get(t, t), d) for t, d in keys if t not in set(drop)]
    out += [(t, d) for t, d in cfg.get("add", [])]
    return out, problems


def apply_fixes(n: int, page: str) -> tuple[str, list[str]]:
    """
    Aplikuje opravy na hotovou stránku. Vrací (stránka, seznam problémů).

    Hledá se tolerantně k mezerám: zdrojový dokument je plný nezlomitelných
    mezer, takže text zkopírovaný z výstupu nemusí být totéž, co je ve stránce.
    Nenajde-li se nebo není-li jednoznačný, skript to ohlásí a skončí chybou —
    tichá vynechaná oprava je horší než žádná.
    """
    problems = []
    for find, repl in FIXES.get(str(n), []):
        pat = re.compile(r"[\s ]+".join(re.escape(p) for p in find.split()))
        hits = pat.findall(page)
        if not hits:
            problems.append("otázka %d: text pro opravu nenalezen — %r" % (n, find[:60]))
            continue
        if len(hits) > 1:
            problems.append("otázka %d: text pro opravu není jednoznačný (%d×) — %r"
                            % (n, len(hits), find[:60]))
            continue
        # nahrazujeme skutečně nalezený úsek, ať se nerozbijí nezlomitelné mezery
        found = hits[0]
        tail = repl[len(find):] if repl.startswith(find) else None
        page = page.replace(found, (found + tail) if tail is not None else repl, 1)
    return page, problems


def render_question(n, short, full, body, numfmt, prev, nxt):
    D._ids = {}
    D._ol_seen = {}
    ctx = Ctx(numfmt, {}, {})
    ctx.images = {}                       # žádný obrázek ze zdroje se nepublikuje

    keys, term_problems = adjust_terms(n, S.collect_key_terms(body))
    intro, secs = split_sections(body)

    out = topnav([("Státnice", "../index.html"), (LABEL, "index.html"),
                  ("Otázka %02d" % n, None)])
    out += [
        "",
        '<header class="qhead">',
        '  <div class="wrap">',
        '    <p class="eyebrow"><span class="qnum">%02d</span> %s · státní závěrečná zkouška</p>'
        % (n, LABEL),
        "    <h1>%s</h1>" % esc(short),
        '    <p class="lead"><em>%s</em></p>' % esc(full),
        '    <div class="qtools">',
        '      <button class="chip chip-prog" data-act="progress" data-q="%d">Označit jako naučené</button>' % n,
    ]
    if keys:
        out.append('      <button class="chip" data-act="cards">Kartičky '
                   '<span class="chip-n">%d</span></button>' % len(keys))
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

    note = NOTES.get(str(n))
    if note:
        out += ["", note]

    if keys:
        out += ["", '    <section class="sec sec-key">',
                '      <h2 id="klicove-pojmy"><span class="hemo" aria-hidden="true">🔑</span>'
                'Klíčové pojmy</h2>', "      <ul>"]
        for term, d in keys:
            out.append("        <li><strong>%s</strong> — %s</li>" % (esc(term), esc(d)))
        out += ["      </ul>", "    </section>"]

    box = BOXES.get(str(n))
    if box:
        out += ["", box]

    if intro:
        rendered = render_flow(intro, "      ", ctx)
        if rendered:
            out += ["", '    <section class="sec sec-read">'] + rendered + ["    </section>"]

    for h, sbody in secs:
        emo, htext = strip_emoji(h)
        cls = SEC_TYPES.get(emo, "read")
        out += ["", '    <section class="sec sec-%s">' % cls]
        hemo = '<span class="hemo" aria-hidden="true">%s</span>' % emo if emo else ""
        out.append('      <h2 id="%s">%s%s</h2>' % (D.ctx_id(ctx, htext), hemo, esc(htext)))
        out.extend(render_flow(sbody, "      ", ctx))
        out.append("    </section>")

    out += ["", '    <nav class="pager" aria-label="Další otázky">']
    if prev:
        out.append('      <a class="pager-l" href="%s"><span>← Předchozí</span>'
                   '<strong>%02d %s</strong></a>' % (prev[1], prev[0], esc(prev[2])))
    else:
        out.append('      <a class="pager-l" href="index.html"><span>←</span>'
                   '<strong>Přehled otázek</strong></a>')
    if nxt:
        out.append('      <a class="pager-r" href="%s"><span>Další →</span>'
                   '<strong>%02d %s</strong></a>' % (nxt[1], nxt[0], esc(nxt[2])))
    else:
        out.append('      <a class="pager-r" href="glosar.html"><span>Dál →</span>'
                   '<strong>Glosář pojmů</strong></a>')
    out += ["    </nav>", "  </main>", "</div>", "", footer()]
    return "\n".join(out), keys, len(secs), term_problems


# ---------------------------------------------------------------- main

def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    src = args[0] if args else "SZZ- Padagogika (komplet).DOCX"
    outdir = args[1] if len(args) > 1 else SUBJECT
    os.makedirs(outdir, exist_ok=True)

    existing = glob.glob(os.path.join(outdir, "otazka-*.html"))
    if existing and not force:
        print("V %s/ už je %d stránek otázek — bez --force nepřepisuji." % (outdir, len(existing)))
        return 2

    here = os.path.dirname(os.path.abspath(__file__))
    dop = os.path.join(here, "_doplnky_pedagogika.json")
    if os.path.exists(dop):
        data = json.load(open(dop, encoding="utf-8"))
        FIXES.update(data.get("fixes", {}))
        BOXES.update(data.get("boxes", {}))
        NOTES.update(data.get("notes", {}))
        TERMS.update(data.get("terms", {}))
        print("ruční doplňky: %d oprav v %d otázkách, %d boxů, %d poznámek k obrázkům, "
              "zásahy do pojmů u %d otázek"
              % (sum(len(v) for v in FIXES.values()), len(FIXES), len(BOXES),
                 len(NOTES), len(TERMS)))

    blocks, numfmt = parse_document(src)
    normalize_styles(blocks)
    print("bloků v dokumentu: %d" % len(blocks))

    S.ACRONYMS.clear()
    S.ACRONYMS.update(S.detect_acronyms(blocks))
    print("zkratek rozpoznaných v textu: %d (%s…)"
          % (len(S.ACRONYMS), ", ".join(sorted(S.ACRONYMS)[:12])))

    # --- kontrola mapy hranic ---------------------------------------------
    bad = []
    for n, (idx, want) in sorted(QSTART.items()):
        got = flat(ptext(blocks[idx])) if idx < len(blocks) else "<za koncem dokumentu>"
        if not got.startswith(want):
            bad.append("  otázka %2d: blok %d má %r, čekáno %r" % (n, idx, got[:70], want))
    if bad:
        print("MAPA HRANIC NESOUHLASÍ SE ZDROJEM — dokument se změnil:")
        print("\n".join(bad))
        print("Opravte QSTART v tools/docx2html_ped.py; generovat naslepo nemá smysl.")
        return 1
    print("mapa hranic: všech %d nadpisů otázek na svém místě" % len(QSTART))

    # --- struktura po otázkách --------------------------------------------
    order = sorted(((n, i) for n, (i, _w) in QSTART.items()), key=lambda kv: kv[1])
    bodies, demoted, dropped, longs, caps = {}, 0, 0, 0, 0
    for k, (n, start) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(blocks)
        body = list(blocks[start + 1:end])
        demoted += S.demote_inner_h1(body)
        body, d = drop_empty_headings(body)
        dropped += d
        longs += demote_long_headings(body)
        caps += split_table_captions(body)
        bodies[n] = (start, end, body)
    print("nadpisů Nadpis1 uvnitř otázek přeznačeno na sekce: %d" % demoted)
    print("prázdných nadpisů zahozeno: %d · dlouhých nadpisů na odstavec: %d" % (dropped, longs))
    print("titulkových řádků vyjmutých z tabulek: %d" % caps)
    print("obrázků vynecháno: %d (viz SKIP_IMAGES — žádný ze zdroje se nepublikuje)"
          % len(SKIP_IMAGES))

    def href(n):
        return "otazka-%02d-%s.html" % (n, TITLES[n][1])

    nums = sorted(QSTART)
    meta, bmap, total_keys = [], {}, 0
    fix_problems: list[str] = []
    thin_toc = []
    for k, n in enumerate(nums):
        start, end, body = bodies[n]
        short = TITLES[n][0]
        full = flat(ptext(blocks[start]))          # celé znění okruhu ze zadání
        prev = (nums[k - 1], href(nums[k - 1]), TITLES[nums[k - 1]][0]) if k else None
        nxt = (nums[k + 1], href(nums[k + 1]), TITLES[nums[k + 1]][0]) if k + 1 < len(nums) else None
        inner, keys, nsecs, tprobs = render_question(n, short, full, body, numfmt, prev, nxt)
        fix_problems.extend(tprobs)
        if nsecs < 2:
            thin_toc.append(n)
        page = shell(
            title="%d. %s · %s · Státnice" % (n, short, LABEL),
            desc="Otázka %d ke státní závěrečné zkoušce z pedagogiky: %s" % (n, short),
            body=inner.split("\n"),
            subject=SUBJECT,
            kind="otazka",
        )
        page, probs = apply_fixes(n, page)
        fix_problems.extend(probs)
        open(os.path.join(outdir, href(n)), "w", encoding="utf-8").write(page)
        bmap[href(n)] = [start, end]
        total_keys += len(keys)
        meta.append({"n": n, "short": short, "full": full, "href": href(n),
                     "cards": len(keys), "secs": nsecs,
                     "words": sum(len(ptext(b).split()) for b in body)})

    json.dump({"toc": {str(m["n"]): m["full"] for m in meta},
               "bounds": {str(n): QSTART[n][0] for n in QSTART},
               "drop": [], "map": bmap, "missing": [],
               "redacted": REDACTED,
               "skipped_images": SKIP_IMAGES, "questions": meta},
              open("tools/_meta_pedagogika.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("zapsáno %d otázek do %s/ · klíčových pojmů %d" % (len(meta), outdir, total_keys))
    thin = [m["n"] for m in meta if m["cards"] < 4]
    if thin:
        print("  ! málo klíčových pojmů u otázek: %s" % thin)
    if thin_toc:
        print("  ! méně než dvě sekce (chudý obsah v levém sloupci): %s" % thin_toc)
    if fix_problems:
        print("  ! RUČNÍ OPRAVY SE NEPODAŘILO APLIKOVAT:")
        for p in fix_problems:
            print("    %s" % p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
