#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx2html_psychopedie.py — převod „PSYCHOPEDIE - OTÁZKY STÁTNICE.docx“ do psychopedie/.

Pátý zdrojový dokument a strukturně nejchudší z celé pětice. Word v něm hlásí
78 stran a 28 tisíc slov, ale **styl `Nadpis1` v něm není použit ani jednou**
a nadpisových odstavců je na celý dokument dvaadvacet. Proti předchozím čtyřem
dokumentům se proto řeší tohle:

  * **Hranice otázek nejsou ve stylech.** Nadpis otázky má styl `Default`
    (u otázky 7 `Normal`) a od dalšího textu ho odděluje jen řádek hvězdiček.
    Naivní regex `^\\d+\\.` nestačí — bloky 308–311 („1.Učení podmiňováním“…)
    mají týž styl a udělaly by falešné hranice. Mapa QSTART je proto ověřovaná
    proti textu, stejně jako u poradenství a pedagogiky.
  * **Nadpis otázek 9 a 17 je rozdělený do dvou odstavců.** Perex se z jednoho
    bloku vzít nedá, TITLE_SPAN říká, kolik bloků se má spojit.
  * **Podnadpisy jsou verzálkové a tučné odstavce**, ne styly. Bez jejich
    přeznačení na `Heading2` by většina stránek neměla jediné H2, tedy ani obsah
    v levém sloupci — `initToc()` v app.js obsah s méně než dvěma nadpisy maže.
  * **Verzálky prostrkané mezerami** (`R E P R E S I V N Í`) jsou v dokumentu
    typografie dělaná ručně. Do textu se srážejí zpátky na jedno slovo, jinak
    by je nenašlo hledání ani kartičky.
  * **Čtyři otázky jsou jen nadpis** — 9, 18, 19 a 20 nemají mezi hvězdičkami
    nic. Tři z nich (9, 18, 20) jsou přitom skutečné okruhy zadání A21, takže
    jsou dopsané v `written` v tools/_doplnky_psychopedie.json; otázka 19
    v bloku psychopedie zadání A21 vůbec není (je to poradenství, okruh 1),
    takže je z ní rozcestník na už hotový předmět.
  * **Ze pěti obrázků se nepublikuje ani jeden**, ale dva z nich jsou text
    vyfotografovaný jako obrázek a ten se přepisuje do HTML — viz SKIP_IMAGES.

Vykreslování se přebírá z docx2html.py a heuristika klíčových pojmů
z docx2html_spec.py, aby všech pět předmětů vypadalo a chovalo se stejně.

    python3 tools/docx2html_psychopedie.py [zdroj.docx] [psychopedie] [--force]

Bez argumentů si zdroj najde globem — jméno souboru je v repozitáři uložené
v NFD (`OTA` + U+0301), takže zapsané v NFC ho open() nenajde.
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

SUBJECT = "psychopedie"
LABEL = "Psychopedie"

SRC_GLOB = "PSYCHOPEDIE*.docx"

# české názvy stylů → to, co očekává render_flow z docx2html.py.
# `Default` je v tomto dokumentu styl nadpisů otázek i běžného textu, takže se
# mapuje na Normal a nadpisy se poznávají výhradně podle mapy QSTART.
STYLE_MAP = {
    "Nadpis1": "Heading1", "Nadpis2": "Heading2", "Nadpis3": "Heading3",
    "Nadpis4": "Heading4", "Nadpis5": "Heading4",
    "Odstavecseseznamem": "ListParagraph",
    "Nzev": "Title", "Normlnweb": "Normal", "Bezmezer": "Normal",
    "Default": "Normal", "Zkladntext2": "Normal", "Zkladntext": "Normal",
}

# Blok, na kterém začíná nadpis otázky, a začátek jeho textu pro kontrolu.
# Ověřeno proti dokumentu; 19× styl Default, u otázky 7 styl Normal.
QSTART = {
    1: (1, "1. Psychopedie - předmět, úkoly, cíle, postavení v systému věd."),
    2: (132, "2. Výchova dítěte s mentálním postižením."),
    3: (203, "3. Vzdělávací systém ve vzdělávání dětí a žáků s mentálním postižením"),
    4: (305, "4. Proces učení mentálně postižených s ohledem na specifika"),
    5: (499, "5. Alternativní vzdělávací programy."),
    6: (575, "6. Volný čas a zájmová činnost jedinců s mentálním postižením."),
    7: (784, "7. Metody a formy práce s dospělým člověkem s mentálním postižením."),
    8: (849, "8. Zapojení jedinců s mentálním postižením do spolurozhodování"),
    9: (930, "9. Mezinárodní organizace zastupující osoby s mentálním postižením"),
    10: (934, "10. Partnerství a sexualita u lidí s mentálním postižením."),
    11: (1026, "11. Problematika zaměstnávání lidí s mentálním postižením."),
    12: (1069, "12. Trénink dovedností potřebných k získání a udržení"),
    13: (1107, "13. Naplňování potřeb a specifické služby pro osoby"),
    14: (1174, "14. Diagnostika v psychopedii."),
    15: (1259, "15. Charakteristika pervazivních vývojových poruch."),
    16: (1370, "16. Specifika vzdělávání dětí s poruchami autistického spektra."),
    17: (1411, "17. Využití alternativní komunikace u dospělých a seniorů."),
    18: (1481, "18. Rozdílnost ve využití alternativní a augmentativní komunikace"),
    19: (1488, "19. Poradenství pro osoby se zdravotním postižením"),
    20: (1493, "20. Poradenství pro osoby marginalizované"),
}

# Kolik bloků tvoří nadpis otázky. Ve zdroji je u otázek 9 a 17 rozlomený
# na dva odstavce; bez spojení by perex skončil v půlce věty a druhá polovina
# by se vykreslila jako první odstavec textu.
TITLE_SPAN = {9: 2, 17: 2}

# Otázky, které ve zdroji nejsou vypracované — mezi dvěma řádky hvězdiček
# je jen nadpis. Text stránek je v `written` v tools/_doplnky_psychopedie.json,
# check_fidelity.py --map si tento seznam přečte z _meta_psychopedie.json.
MISSING = [9, 18, 19, 20]

# Otázka 19 není v bloku psychopedie zadání A21 (je to poradenství, okruh 1),
# takže se nedopisuje — vede na už hotový předmět.
BRIDGE = {
    19: ("poradenstvi/otazka-01-poradenske-sluzby-legislativa.html",
         "Poradenské služby a legislativa"),
}

# Nadpis delší než tohle není nadpis, ale věta omylem vyznačená tučně.
LONG_HEADING = 150

# krátký titulek pro H1 a název souboru (plné znění okruhu jde do perexu)
TITLES = {
    1: ("Psychopedie jako obor, klasifikace a etiologie", "psychopedie-obor-klasifikace"),
    2: ("Výchova dítěte s mentálním postižením a raná péče", "vychova-rana-pece"),
    3: ("Vzdělávací systém a podpůrná opatření", "vzdelavaci-system-podpurna-opatreni"),
    4: ("Proces učení a vyučovací metody", "proces-uceni-metody"),
    5: ("Alternativní vzdělávací programy a AAK", "alternativni-programy-aak"),
    6: ("Volný čas a profesní orientace", "volny-cas-profesni-orientace"),
    7: ("Práce s dospělým člověkem s mentálním postižením", "dospeli-strukturovane-uceni"),
    8: ("Sebeobhajování a občanská advokacie", "sebeobhajovani-advokacie"),
    9: ("Organizace a vládní dokumenty", "organizace-vladni-dokumenty"),
    10: ("Partnerství, sexualita a rodičovství", "partnerstvi-sexualita-rodicovstvi"),
    11: ("Zaměstnávání lidí s mentálním postižením", "zamestnavani-mentalni-postizeni"),
    12: ("Tranzitní program a nácvik pracovních dovedností", "tranzitni-program"),
    13: ("Stárnutí a služby pro seniory s mentálním postižením", "stari-sluzby-seniori"),
    14: ("Diagnostika v psychopedii", "diagnostika-v-psychopedii"),
    15: ("Poruchy autistického spektra — charakteristika", "pas-charakteristika"),
    16: ("Vzdělávání dětí s PAS a TEACCH program", "pas-vzdelavani-teacch"),
    17: ("Piktogramy, Makaton, Bliss a VOKS", "piktogramy-makaton-bliss-voks"),
    18: ("AAK u dětí a dospělých, technické pomůcky", "aak-deti-dospeli-pomucky"),
    19: ("Speciálně pedagogické poradenství", "specialne-pedagogicke-poradenstvi"),
    20: ("Poradenství pro osoby ohrožené sociálním vyloučením", "poradenstvi-socialni-vylouceni"),
}

# ------------------------------------------------------------------ zadání A21
#
# Číslování dokumentu neodpovídá zadání a není to posun jako u poradenství
# a pedagogiky, ale permutace: okruh 1 zadání je otázka 18 dokumentu.
# Mapa se propisuje do _meta_psychopedie.json, aby z ní index.html
# a pravni-aktualnost.html mohly postavit druhý seznam otázek.
A21 = {
    1: ([18], "AAK u dětí a dospělých, PC s hlasovým výstupem"),
    2: ([5], "Alternativní vzdělávací programy, sociální čtení, AAK"),
    3: ([1], "Pojetí psychopedie, historie, klasifikace MKN / DSM / MKF"),
    4: ([16], "Vzdělávání dětí s PAS, TEACCH, sociální dovednosti"),
    5: ([9], "Mezinárodní organizace, sdružení v ČR, vládní dokumenty"),
    6: ([17], "Piktogramy, Bliss, Makaton, Lormova abeceda, VOKS"),
    7: ([6, 7], "Volný čas, profesní orientace, práce s dospělými"),
    8: ([2], "Výchova dítěte s MP, raná péče, předškolní věk"),
    9: ([3], "Vzdělávací systém, RVP ZV, IVP, podpůrná opatření"),
    10: ([8], "Spolurozhodování, občanská advokacie, sebeobhajování"),
    11: ([11], "Zaměstnávání, zákon o zaměstnanosti, zákoník práce"),
    12: ([12], "Nácvik pracovních dovedností, tranzitní program"),
    13: ([15], "Pervazivní vývojové poruchy dle MKN, PAS"),
    14: ([14], "Diagnostika v psychopedii"),
    15: ([10, 13], "Partnerství a sexualita, stáří a specifické služby"),
    16: ([20], "Poradenství pro marginalizované a sociálně znevýhodněné"),
    17: ([4], "Proces učení, druhy učení, metody čtení a psaní, IVP"),
}

# ---------------------------------------------------------------- obrázky
#
# Nepublikuje se ani jeden z pěti a je to záměr, ne chyba konverze. Dva z nich
# ale nejsou obrázky — je to **text vyfotografovaný jako obrázek**, a ten se
# přepisuje do HTML (viz `notes` v tools/_doplnky_psychopedie.json). Jako
# obrázek by byl nedostupný hledání, kartičkám, čtečkám i tisku.
IMAGES: dict[str, tuple[str, str, str]] = {}

# rId → proč se nepoužívá (jen pro výpis při konverzi)
SKIP_IMAGES = {
    "rId9": "text jako obrázek — výčet starších výrazů pro mentální retardaci; "
            "přepsán do HTML v otázce 1",
    "rId10": "snímek webové stránky s odkazy na Wikipedii („Dějiny psychopedie "
             "v českých zemích“); časová osa přepsána do HTML v otázce 1",
    "rId31": "cizí sada 12 piktogramů z Google Images, bez doložené licence; "
             "reprezentativní řádek překreslen jako inline SVG v otázce 17",
    "rId32": "makatonové znaky s anglickými popisky (I, Me, You, Where?); "
             "Makaton je licencovaný systém — popsán textem v otázce 17",
    "rId33": "ruční skica Blissu na milimetrovém papíře; skládací logika "
             "překreslena jako inline SVG v otázce 17",
}


# ---------------------------------------------------------------- pomůcky

def ptext(b: dict) -> str:
    return S.ptext(b)


def flat(s: str) -> str:
    """Text pro srovnání s mapou hranic — zdroj používá nezlomitelné mezery."""
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _html(v) -> str:
    """Doplňky se dají psát jako string i jako pole řádků (čitelnější diff)."""
    return "\n".join(v) if isinstance(v, list) else v


def normalize_styles(blocks: list[dict]) -> None:
    for b in blocks:
        if b["kind"] == "p":
            b["style"] = STYLE_MAP.get(b["style"], b["style"])
        else:
            for row in b["rows"]:
                for cell in row:
                    normalize_styles(cell)


STARS_RE = re.compile(r"^[*\s]{10,}$")


def is_stars(b: dict) -> bool:
    """Oddělovač otázek — řádek 70+ hvězdiček. Do stránky nepatří."""
    return b["kind"] == "p" and bool(STARS_RE.match(ptext(b)))


# „R E P R E S I V N Í“ / „CH A R I T A T I V N Í“ — prostrkané verzálky.
# Slovo se pozná tak, že jsou to skoro jen jednotlivá velká písmena.
SPACED_RE = re.compile(r"(?:(?:[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{1,2})\s+){3,}"
                       r"[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{1,2}")


def _unspace(m: re.Match) -> str:
    return re.sub(r"\s+", "", m.group(0))


def unspace_caps(blocks: list[dict]) -> int:
    """
    Prostrkané verzálky srazí zpátky na slovo.

    Zdroj tak sází osmičlennou osu vývojových stádií péče. Dokud jsou písmena
    oddělená mezerami, `fold()` v app.js z nich udělá „r e p r e s i v n í“
    a hledání ani kartičky slovo nenajdou. Dvě mezery mezi slovy zůstávají,
    takže „R E N E S A N Č N Í H O  H U M A N I S M U“ se nespojí v jedno.
    """
    n = 0
    for b in blocks:
        if b["kind"] != "p":
            continue
        for part in b["parts"]:
            t = part.get("t")
            if not t or not SPACED_RE.search(t):
                continue
            new = SPACED_RE.sub(_unspace, t)
            if new != t:
                part["t"] = new
                n += 1
    return n


def drop_empty_headings(body: list[dict]) -> tuple[list[dict], int]:
    """Nadpis bez textu by udělal prázdnou sekci s prázdnou položkou v obsahu."""
    out, n = [], 0
    for b in body:
        if b["kind"] == "p" and b["style"].startswith("Heading") and not ptext(b):
            n += 1
            continue
        out.append(b)
    return out, n


def demote_long_headings(body: list[dict]) -> int:
    """Věta vyznačená jako nadpis → normální odstavec (viz LONG_HEADING)."""
    n = 0
    for b in body:
        if b["kind"] != "p" or b["style"] not in ("Heading2", "Heading3", "Heading4"):
            continue
        if len(ptext(b)) > LONG_HEADING:
            b["style"] = "Normal"
            n += 1
    return n


def promote_caps(body: list[dict]) -> int:
    """
    Samostatný odstavec VERZÁLKAMI je v tomto dokumentu nadpis sekce.

    Vlastní varianta `docx2html_spec.promote_caps()`, protože ta **zahazuje
    jednoslovné nadpisy** — a v tomhle dokumentu jsou to zrovna ty nejdůležitější:
    `PIKTOGRAMY`, `MAKATON`, `BLISS`, `VOKS`. To jsou přesně systémy, které
    jmenuje okruh 6 zadání A21, a bez nich nemá otázka 17 jediný nadpis.

    Změna je bezpečná, ne odhad: jednoslovných verzálkových odstavců je v celém
    dokumentu **osm a všech osm je nadpis** (PSYCHOPEDIE, PŘÍČINY, RELAXACE,
    REHABILITACE, PIKTOGRAMY, MAKATON, BLISS, VOKS). Hranice délky proto klesá
    z osmi znaků na čtyři; ostatní pojistky zůstávají.
    """
    n = 0
    for b in body:
        if b["kind"] != "p" or b["style"] != "Normal" or b.get("num"):
            continue
        raw = ptext(b).strip()
        t = raw.rstrip(":")                       # „KOMUNIKAČNÍ KLÍČ:“
        if not (4 <= len(t) <= 95) or not S.is_caps(t):
            continue
        letters = sum(c.isalpha() or c.isspace() for c in t)
        if letters / len(t) < 0.75:                # „E, I, P, N, T, K, V, D.“
            continue
        if t.endswith((",", ";", "-", "–", "—", ".")):
            continue
        # Text se zapisuje **beze změny** včetně dvojtečky. Zkracovat ho na `t`
        # by vypadalo o kousek lépe, ale check_fidelity.py porovnává znak po znaku
        # a hlásil by odstavec jako ztracený — cena za kosmetiku je příliš vysoká.
        b["parts"] = [{"t": raw, "b": True, "i": False}]
        b["style"] = "Heading2"
        n += 1
    return n


def is_bold(b: dict) -> bool:
    """Odstavec je tučný, je-li tučný veškerý jeho neprázdný text."""
    parts = [p for p in b["parts"] if p.get("t", "").strip()]
    return bool(parts) and all(p.get("b") for p in parts)


# Utržený konec věty vyznačený tučně není nadpis. Stejný filtr jako
# v docx2html_psy.promote_headings(), jen doplněný o dvojtečkové uvození.
NOT_HEADING_RE = re.compile(r"^\d{1,2}[\.\)]\s")


def promote_bold(body: list[dict]) -> int:
    """
    Tučný samostatný odstavec je v tomto dokumentu podnadpis.

    Běží **po** promote_caps(), takže verzálkové nadpisy už jsou H2 a tučné
    se zařadí o úroveň níž — zdroj ty dvě úrovně opravdu rozlišuje
    (`PODPŮRNÉ OPATŘENÍ` → `1. stupeň`). Nemá-li otázka žádné H2, zůstávají
    tučné nadpisy na H2; stránka bez jediného H2 nemá obsah v levém sloupci.
    """
    has_h2 = any(b["kind"] == "p" and b["style"] == "Heading2" for b in body)
    level = "Heading3" if has_h2 else "Heading2"
    n = 0
    for b in body:
        if b["kind"] != "p" or b["style"] != "Normal" or b.get("num"):
            continue
        t = ptext(b).strip()
        if not t or len(t) > 90 or not is_bold(b):
            continue
        if NOT_HEADING_RE.match(t) and len(t) < 20:
            continue
        if t.endswith((",", ";", "-", "–", "—")):
            continue
        # věta, ne nadpis
        if t.count(".") > 1 or (t.endswith(".") and len(t.split()) > 6):
            continue
        b["style"] = level
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


# Ruční opravy a doplňky z tools/_doplnky_psychopedie.json. Drží se mimo HTML,
# aby je opětovné spuštění konvertoru nesmazalo.
FIXES: dict[str, list] = {}
BOXES: dict[str, str] = {}
NOTES: dict[str, str] = {}
TERMS: dict[str, dict] = {}
WRITTEN: dict[str, dict] = {}


def adjust_terms(n: int, keys: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[str]]:
    """
    Ruční zásahy do automaticky posbíraných klíčových pojmů.

    Z klíčových pojmů se dělají kartičky a glosář, takže na jejich kvalitě
    záleží víc než na zbytku stránky. Neexistující klíč v drop/rename se hlásí
    jako problém, aby soubor tiše nezestárl.

    Proti pedagogice je tu navíc `"auto": false`. Tento zdroj totiž skoro
    nepoužívá vzorec „pojem — definice“ v odrážce, ze kterého heuristika
    v docx2html_spec.py žije, a tak místo pojmů vytahuje uvozovací věty
    („Uživatel má možnost“, „SPPG diagnostika se dělí dle“). U otázek, kde
    je celý výtěžek k zahození, je čistší heuristiku vypnout a pojmy napsat,
    než je jeden po druhém vypisovat do `drop`.
    """
    cfg = TERMS.get(str(n))
    if not cfg:
        return keys, []
    if not cfg.get("auto", True):
        keys = []

    # Zdroj je plný nezlomitelných mezer, takže pojem posbíraný heuristikou
    # může být „Dle místa v\xa0životě člověka“. Do JSON se nezlomitelná mezera
    # rozumně napsat nedá, tak se při párování mezery normalizují — stejnou
    # logikou, jakou používá apply_fixes().
    def norm(s: str) -> str:
        return re.sub(r"[\s\xa0]+", " ", s).strip()

    drop = {norm(t) for t in cfg.get("drop", [])}
    ren = {norm(k): v for k, v in cfg.get("rename", {}).items()}
    have = {norm(t) for t, _ in keys}
    problems = ["otázka %d: pojem %r k odstranění neexistuje" % (n, t)
                for t in sorted(drop) if t not in have]
    problems += ["otázka %d: pojem %r k přejmenování neexistuje" % (n, t)
                 for t in sorted(ren) if t not in have]
    out = [(ren.get(norm(t), norm(t)), d) for t, d in keys if norm(t) not in drop]
    out += [(t, d) for t, d in cfg.get("add", [])]
    return out, problems


def apply_fixes(n: int, page: str) -> tuple[str, list[str]]:
    """
    Aplikuje opravy na hotovou stránku. Vrací (stránka, seznam problémů).

    Hledá se tolerantně k mezerám: zdrojový dokument je plný nezlomitelných
    mezer. Nenajde-li se nebo není-li text jednoznačný, skript to ohlásí
    a skončí chybou — tichá vynechaná oprava je horší než žádná.
    """
    problems = []
    for find, repl in FIXES.get(str(n), []):
        pat = re.compile(r"[\s\xa0]+".join(re.escape(p) for p in find.split()))
        hits = pat.findall(page)
        if not hits:
            problems.append("otázka %d: text pro opravu nenalezen — %r" % (n, find[:60]))
            continue
        if len(hits) > 1:
            problems.append("otázka %d: text pro opravu není jednoznačný (%d×) — %r"
                            % (n, len(hits), find[:60]))
            continue
        found = hits[0]
        tail = repl[len(find):] if repl.startswith(find) else None
        page = page.replace(found, (found + tail) if tail is not None else repl, 1)
    return page, problems


def qhead(n: int, short: str, full: str, ncards: int, expand: bool = True) -> list[str]:
    """Hlavička otázky — společná pro převedené i dopsané stránky."""
    out = [
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
    if ncards:
        out.append('      <button class="chip" data-act="cards">Kartičky '
                   '<span class="chip-n">%d</span></button>' % ncards)
    if expand:
        out.append('      <button class="chip" data-act="expand">Rozbalit vše</button>')
    out += [
        '      <button class="chip" data-act="print">Tisk / PDF</button>',
        "    </div>",
        "  </div>",
        "</header>",
    ]
    return out


def pager(prev, nxt) -> list[str]:
    out = ['    <nav class="pager" aria-label="Další otázky">']
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
    out.append("    </nav>")
    return out


def key_section(keys: list[tuple[str, str]]) -> list[str]:
    if not keys:
        return []
    out = ["", '    <section class="sec sec-key">',
           '      <h2 id="klicove-pojmy"><span class="hemo" aria-hidden="true">🔑</span>'
           'Klíčové pojmy</h2>', "      <ul>"]
    for term, d in keys:
        out.append("        <li><strong>%s</strong> — %s</li>" % (esc(term), esc(d)))
    out += ["      </ul>", "    </section>"]
    return out


def render_question(n, short, full, body, numfmt, prev, nxt):
    D._ids = {}
    D._ol_seen = {}
    ctx = Ctx(numfmt, {}, {})
    ctx.images = {}                       # žádný obrázek ze zdroje se nepublikuje

    keys, term_problems = adjust_terms(n, S.collect_key_terms(body))
    intro, secs = split_sections(body)

    out = topnav([("Státnice", "../index.html"), (LABEL, "index.html"),
                  ("Otázka %02d" % n, None)])
    out += qhead(n, short, full, len(keys))
    out += [
        "",
        '<div class="wrap layout">',
        '  <aside class="side">',
        '    <nav class="toc" aria-label="Obsah otázky"></nav>',
        "  </aside>",
        '  <main id="obsah" class="content">',
    ]

    note = NOTES.get(str(n))
    if note:
        out += ["", _html(note)]

    out += key_section(keys)

    box = BOXES.get(str(n))
    if box:
        out += ["", _html(box)]

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

    out += [""] + pager(prev, nxt) + ["  </main>", "</div>", "", footer()]
    return "\n".join(out), keys, len(secs), term_problems


def render_written(n, short, full, prev, nxt):
    """
    Stránka otázky, která ve zdroji vypracovaná není.

    Obsah je v `written` v tools/_doplnky_psychopedie.json: `body` je hotové
    HTML sekcí, `terms` jsou klíčové pojmy. Zdrojem pravdy zůstává JSON, aby
    opětovné spuštění konvertoru dopsaný text nesmazalo.
    """
    cfg = WRITTEN.get(str(n))
    if not cfg:
        return None, [], 0, ["otázka %d: chybí `written` v _doplnky_psychopedie.json" % n]

    keys = [(t, d) for t, d in cfg.get("terms", [])]
    body = _html(cfg.get("body", ""))
    nsecs = body.count('<section class="sec')

    out = topnav([("Státnice", "../index.html"), (LABEL, "index.html"),
                  ("Otázka %02d" % n, None)])
    out += qhead(n, short, full, len(keys), expand=bool(cfg.get("expand", True)))
    out += [
        "",
        '<div class="wrap layout">',
        '  <aside class="side">',
        '    <nav class="toc" aria-label="Obsah otázky"></nav>',
        "  </aside>",
        '  <main id="obsah" class="content">',
        "",
        _html(cfg.get("note", "")),
    ]
    out += key_section(keys)
    out += ["", body]
    out += [""] + pager(prev, nxt) + ["  </main>", "</div>", "", footer()]
    return "\n".join(x for x in out if x is not None), keys, nsecs, []


# ---------------------------------------------------------------- main

def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    if args:
        src = args[0]
    else:
        found = sorted(glob.glob(SRC_GLOB))
        if not found:
            print("Zdrojový dokument %s jsem nenašel." % SRC_GLOB)
            return 2
        src = found[0]
    outdir = args[1] if len(args) > 1 else SUBJECT
    os.makedirs(outdir, exist_ok=True)

    existing = glob.glob(os.path.join(outdir, "otazka-*.html"))
    if existing and not force:
        print("V %s/ už je %d stránek otázek — bez --force nepřepisuji." % (outdir, len(existing)))
        return 2

    here = os.path.dirname(os.path.abspath(__file__))
    dop = os.path.join(here, "_doplnky_psychopedie.json")
    if os.path.exists(dop):
        data = json.load(open(dop, encoding="utf-8"))
        FIXES.update(data.get("fixes", {}))
        BOXES.update(data.get("boxes", {}))
        NOTES.update(data.get("notes", {}))
        TERMS.update(data.get("terms", {}))
        WRITTEN.update(data.get("written", {}))
        print("ruční doplňky: %d oprav v %d otázkách, %d boxů, %d poznámek, "
              "zásahy do pojmů u %d otázek, dopsané otázky: %s"
              % (sum(len(v) for v in FIXES.values()), len(FIXES), len(BOXES),
                 len(NOTES), len(TERMS), ", ".join(sorted(WRITTEN)) or "žádná"))

    blocks, numfmt = parse_document(src)
    normalize_styles(blocks)
    print("zdroj: %s · bloků v dokumentu: %d" % (os.path.basename(src), len(blocks)))

    unspaced = unspace_caps(blocks)
    print("prostrkaných verzálek sraženo: %d" % unspaced)

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
        print("Opravte QSTART v tools/docx2html_psychopedie.py; "
              "generovat naslepo nemá smysl.")
        return 1
    print("mapa hranic: všech %d nadpisů otázek na svém místě" % len(QSTART))

    # --- struktura po otázkách --------------------------------------------
    order = sorted(((n, i) for n, (i, _w) in QSTART.items()), key=lambda kv: kv[1])
    bodies = {}
    dropped = longs = caps = bolds = 0
    star_blocks: list[int] = []
    for k, (n, start) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(blocks)
        span = TITLE_SPAN.get(n, 1)
        star_blocks += [i for i in range(start + span, end) if is_stars(blocks[i])]
        body = [b for b in blocks[start + span:end] if not is_stars(b)]
        caps += promote_caps(body)
        bolds += promote_bold(body)
        body, d = drop_empty_headings(body)
        dropped += d
        longs += demote_long_headings(body)
        bodies[n] = (start, end, body)
    print("verzálkových nadpisů přeznačeno na sekce: %d · tučných na podnadpisy: %d"
          % (caps, bolds))
    print("prázdných nadpisů zahozeno: %d · dlouhých nadpisů na odstavec: %d · "
          "oddělovačů hvězdiček: %d" % (dropped, longs, len(star_blocks)))
    print("obrázků vynecháno: %d (viz SKIP_IMAGES — žádný ze zdroje se nepublikuje)"
          % len(SKIP_IMAGES))

    def href(n):
        return "otazka-%02d-%s.html" % (n, TITLES[n][1])

    nums = sorted(QSTART)
    meta, bmap, total_keys = [], {}, 0
    problems: list[str] = []
    thin_toc = []
    for k, n in enumerate(nums):
        start, end, body = bodies[n]
        short = TITLES[n][0]
        # perex = celé znění okruhu ze zdroje, u otázek 9 a 17 ze dvou bloků
        full = flat(" ".join(ptext(blocks[start + i])
                            for i in range(TITLE_SPAN.get(n, 1))))
        full = re.sub(r"^\d{1,2}\.\s*", "", full)
        prev = (nums[k - 1], href(nums[k - 1]), TITLES[nums[k - 1]][0]) if k else None
        nxt = (nums[k + 1], href(nums[k + 1]), TITLES[nums[k + 1]][0]) if k + 1 < len(nums) else None

        if n in MISSING:
            inner, keys, nsecs, probs = render_written(n, short, full, prev, nxt)
            if inner is None:
                problems.extend(probs)
                continue
        else:
            inner, keys, nsecs, probs = render_question(
                n, short, full, body, numfmt, prev, nxt)
        problems.extend(probs)
        page = shell(
            title="%d. %s · %s · Státnice" % (n, short, LABEL),
            desc="Otázka %d ke státní závěrečné zkoušce z psychopedie: %s" % (n, short),
            body=inner.split("\n"),
            subject=SUBJECT,
            kind="otazka",
        )
        if n not in MISSING:
            page, probs = apply_fixes(n, page)
            problems.extend(probs)
        # initToc() v app.js staví obsah z `h2, h3` s id a při méně než dvou
        # nadpisech ho celý smaže — proto se počítají oba, ne jen sekce.
        nheads = len(re.findall(r"<h[23] id=", page))
        if nheads < 2:
            thin_toc.append(n)
        open(os.path.join(outdir, href(n)), "w", encoding="utf-8").write(page)
        bmap[href(n)] = [start, end]
        total_keys += len(keys)
        meta.append({"n": n, "short": short, "full": full, "href": href(n),
                     "cards": len(keys), "secs": nsecs,
                     "words": sum(len(ptext(b).split()) for b in body),
                     "written": n in MISSING})

    json.dump({"toc": {str(m["n"]): m["full"] for m in meta},
               "bounds": {str(n): QSTART[n][0] for n in QSTART},
               # řádky hvězdiček oddělující otázky — čistá typografie, do stránek
               # nepatří; check_fidelity.py --map si `drop` přečte, aby je nehlásil
               "drop": sorted(star_blocks), "map": bmap, "missing": MISSING,
               "a21": {str(k): {"otazky": v[0], "text": v[1]} for k, v in A21.items()},
               "bridge": {str(k): list(v) for k, v in BRIDGE.items()},
               "skipped_images": SKIP_IMAGES, "questions": meta},
              open(os.path.join(here, "_meta_psychopedie.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("zapsáno %d otázek do %s/ · klíčových pojmů %d (z toho dopsaných otázek %d)"
          % (len(meta), outdir, total_keys, len([m for m in meta if m["written"]])))
    # Rozcestníková stránka je krátká záměrně — nemá pojmy ani sekce a hlásit
    # to jako problém by znamenalo, že si na varování zvykneme a přestaneme je číst.
    thin = [m["n"] for m in meta if m["cards"] < 4 and m["n"] not in BRIDGE]
    if thin:
        print("  ! málo klíčových pojmů u otázek: %s" % thin)
    thin_toc = [n for n in thin_toc if n not in BRIDGE]
    if thin_toc:
        print("  ! méně než dvě sekce (chudý obsah v levém sloupci): %s" % thin_toc)
    if problems:
        print("  ! RUČNÍ DOPLŇKY SE NEPODAŘILO APLIKOVAT:")
        for p in problems:
            print("    %s" % p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
