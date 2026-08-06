#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx2html_spec.py — jednorázový převod „SZO SPECIÁLNÍ PEDAGOGIKA.DOCX“ do poradenstvi/.

Třetí zdrojový dokument, třetí struktura. Proti etopedii i psychologii:

  * názvy stylů jsou české (Nadpis1…Nadpis5, Odstavecseseznamem, Nzev)
  * nadpisové styly se používají, ale `Nadpis1` je současně nadpis otázky
    i nadpis sekce **uvnitř** otázky (22 ze 42 výskytů) → dělit podle H1 nelze
  * nadpis otázky 20 má styl Normal a číslovaný nadpis otázky 11 leží
    **za** svým obsahem → dvě otázky by se nenašly vůbec
  * část otázek nemá jediný Nadpis2, zato používá ODSTAVCE VERZÁLKAMI

Hranice otázek proto nejsou heuristika, ale ověřená mapa QSTART: u každé otázky
se kontroluje, že na daném bloku skutečně stojí očekávaný nadpis. Když se
dokument změní, skript spadne a řekne to — nevygeneruje tiše rozsypané stránky.

Vykreslování (inline formátování, seznamy, tabulky, šablona stránky) se přebírá
z docx2html.py, aby všechny tři předměty vypadaly stejně.

    python3 tools/docx2html_spec.py 'SZO SPECIÁLNÍ PEDAGOGIKA.DOCX' poradenstvi [--force]
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx2html import (  # noqa: E402
    Ctx,
    deaccent,
    esc,
    parse_document,
    render_flow,
    shell,
    slugify,
    split_sections,
    strip_emoji,
    topnav,
    SEC_TYPES,
)
import docx2html as D  # noqa: E402

SUBJECT = "poradenstvi"
LABEL = "Poradenství"

# české názvy stylů → to, co očekává render_flow z docx2html.py
STYLE_MAP = {
    "Nadpis1": "Heading1", "Nadpis2": "Heading2", "Nadpis3": "Heading3",
    "Nadpis4": "Heading4", "Nadpis5": "Heading4",
    "Odstavecseseznamem": "ListParagraph",
    "Nzev": "Title", "Normlnweb": "Normal", "Bezmezer": "Normal",
}

# Blok, na kterém začíná nadpis otázky, a začátek jeho textu pro kontrolu.
# Ověřeno proti dokumentu; 18× styl Nadpis1, u otázek 3 a 20 styl Normal.
QSTART = {
    1: (34, "PORADENSKÉ SLUŽBY, AKTUÁLNÍ LEGISLATIVA"),
    2: (325, "SPECIÁLNĚ PEDAGOGICKÁ DIAGNOSTIKA LOGOPEDICKÁ"),
    3: (432, "SPECIFICKÉ VÝVOJOVÉ PORUCHY ŘEČI A JAZYKA DLE MKN"),
    4: (853, "KLASIFIKACE MENTÁLNÍ RETARDACE DLE MKN"),
    5: (1099, "SPECIFIKA DIAGNOSTIKY ROZUMOVÝCH SCHOPNOSTÍ"),
    6: (1402, "UČEBNÍ PLÁNY VZDĚLÁVACÍCH PROGRAMŮ"),
    7: (1677, "SOCIÁLNÍ PÉČE O JEDINCE S MENTÁLNÍM POSTIŽENÍM"),
    8: (1908, "SPECIÁLNĚ PEDAGOGICKÁ PODPORA OSOB S TĚLESNÝM POSTIŽENÍM"),
    9: (2453, "SPECIFIKA DIAGNOSTIKY U ŽÁKA S TĚLESNÝM POSTIŽENÍM"),
    10: (2551, "INKLUZE DÍTĚTE, ŽÁKA, STUDENTA S TĚLESNÝM POSTIŽENÍM"),
    11: (2602, "SPECIFICKÉ PORUCHY UČENÍ a jejich souvislost"),
    12: (2821, "12.METODIKA POČÁTEČNÍ VÝUKY ČTENÍ A PSANÍ"),
    13: (2921, "13. REEDUKACE A KOMPENZACE SPU"),
    14: (3075, "14. PORUCHY CHOVÁNÍ A EMOCÍ"),
    15: (3263, "15. PORUCHY CHOVÁNÍ SPOJENÉ S ADHD"),
    16: (3437, "16. VÝVOJ PŘÍSTUPŮ K JEDINCŮM S PORUCHAMI CHOVÁNÍ"),
    17: (3557, "17. SYMPTOMATOLOGIE SLUCHOVÝCH VAD"),
    18: (4432, "18. SPECIÁLNĚ PEDAGOGICKÁ PODPORA OSOB SE ZRAKOVÝM POSTIŽENÍM"),
    19: (4844, "19. NADANÍ ŽÁCI"),
    20: (5258, "20. PERVAZIVNÍ VÝVOJOVÉ PORUCHY DLE MKN"),
}

# Osiřelý číslovaný nadpis otázky 11 — ve zdroji stojí omylem až za jejím
# obsahem, těsně před nadpisem otázky 12. Do stránky nepatří.
DROP_BLOCKS = {2818}

# krátký titulek pro H1 a název souboru (plné znění okruhu jde do perexu)
TITLES = {
    1: ("Poradenské služby a legislativa", "poradenske-sluzby-legislativa"),
    2: ("Logopedická diagnostika", "logopedicka-diagnostika"),
    3: ("Vývojové poruchy řeči a jazyka", "vyvojove-poruchy-reci"),
    4: ("Klasifikace mentální retardace", "klasifikace-mentalni-retardace"),
    5: ("Diagnostika rozumových schopností", "diagnostika-rozumovych-schopnosti"),
    6: ("Učební plány pro žáky s mentálním postižením", "ucebni-plany-mentalni-postizeni"),
    7: ("Sociální péče o osoby s mentálním postižením", "socialni-pece-mentalni-postizeni"),
    8: ("Podpora osob s tělesným postižením", "telesne-postizeni-podpora"),
    9: ("Diagnostika žáka s tělesným postižením", "diagnostika-telesne-postizeni"),
    10: ("Inkluze žáka s tělesným postižením", "inkluze-telesne-postizeni"),
    11: ("Specifické poruchy učení", "specificke-poruchy-uceni"),
    12: ("Metodika počáteční výuky čtení a psaní", "metodika-cteni-psani"),
    13: ("Reedukace a kompenzace SPU", "reedukace-kompenzace-spu"),
    14: ("Poruchy chování a emocí", "poruchy-chovani-emoci"),
    15: ("ADHD a hyperkinetické poruchy", "adhd-hyperkineticke-poruchy"),
    16: ("Vývoj přístupů k poruchám chování", "pristupy-poruchy-chovani"),
    17: ("Symptomatologie sluchových vad", "sluchove-vady"),
    18: ("Podpora osob se zrakovým postižením", "zrakove-postizeni"),
    19: ("Nadaní žáci", "nadani-zaci"),
    20: ("Pervazivní vývojové poruchy", "pervazivni-vyvojove-poruchy"),
}

# ---------------------------------------------------------------- obrázky
#
# Zdroj obsahuje 21 vložených obrázků, ale **publikovatelné jsou jen tři.**
# Ostatní jsou snímky obrazovky autorky nebo naskenované záznamy a na veřejný
# web nepatří — viz IMAGE_NOTES, kde je u každé otázky vysvětleno, co bylo
# vynecháno a proč. Vynechání je vědomé rozhodnutí, ne chyba konverze.
IMAGES = {
    "rId47": ("audiogram-prevodni-porucha.png",
              "Audiogram — převodní porucha sluchu. Vzdušné vedení (plná čára) je zhoršené, "
              "kostní vedení (přerušovaná) zůstává v normě; mezi křivkami je kostně-vzdušný rozdíl.",
              "Audiogram převodní poruchy: kostní vedení kolem 0–10 dB, vzdušné vedení 20–40 dB "
              "napříč frekvencemi 250–8000 Hz."),
    "rId48": ("audiogram-percepcni-porucha.png",
              "Audiogram — percepční porucha sluchu. Obě vedení klesají společně a ztráta "
              "narůstá k vyšším frekvencím; kostně-vzdušný rozdíl chybí.",
              "Audiogram percepční poruchy: obě křivky klesají z 20 dB na 250 Hz až k 80 dB "
              "na 8000 Hz, prakticky se překrývají."),
    "rId49": ("audiogram-smisena-porucha.png",
              "Audiogram — smíšená porucha sluchu. Klesají obě vedení (percepční složka) "
              "a zároveň mezi nimi zůstává rozdíl (převodní složka).",
              "Audiogram smíšené poruchy: kostní vedení klesá z 20 dB na 50 dB, vzdušné "
              "vedení leží o 20–30 dB níž, na 8000 Hz dosahuje 80 dB."),
}

# rId → proč se nepoužívá (jen pro výpis při konverzi)
SKIP_IMAGES = {
    "rId8": "logo fakulty na titulní straně",
    "rId9": "sken vyplněného záznamového listu WISC-III s výsledky konkrétního dítěte",
    "rId10": "sken vyplněného záznamového listu WISC-III",
    "rId21": "spojnice diagramu (0 kB)", "rId22": "spojnice diagramu",
    "rId23": "spojnice diagramu", "rId24": "spojnice diagramu",
    "rId25": "spojnice diagramu", "rId26": "spojnice diagramu",
    "rId27": "spojnice diagramu",
    "rId42": "snímek plochy Windows s uživatelským jménem a cestami k souborům",
    "rId43": "snímek prohlížeče s osobní lištou záložek; předloha navíc zapovídá šíření",
    "rId50": "snímek prohlížeče s jmenným seznamem lékařů a jejich e-mailovými adresami",
}

# Boxy, které konvertor vloží na začátek otázky místo vynechaného obrázku.
IMAGE_NOTES = {
    5: ('    <aside class="box warn">\n'
        '      <h4><span class="bemo" aria-hidden="true">⚠️</span>Vynechaný obrázek</h4>\n'
        '      <p>Na tomto místě měl zdrojový dokument <strong>sken vyplněného záznamového '
        'listu WISC-III</strong> s hrubými i váženými skóry konkrétního dítěte (IQ 63). '
        'Do studijního materiálu na veřejném webu nepatří: jsou to <strong>výsledky '
        'vyšetření skutečné osoby</strong> a zároveň <strong>testový materiál</strong>, '
        'jehož šíření znehodnocuje samotný test.</p>\n'
        '      <p>Co si z něj odnést, je struktura profilu: verbální a performační subtesty '
        'se vyhodnocují zvlášť, sledují se <strong>vážené skóry</strong> jednotlivých subtestů '
        '(průměr 10) a z nich se skládá <strong>VIQ, PIQ a CIQ</strong> plus indexové skóry '
        '(ISP, IPU, IKO, IRZ). Diagnosticky nese informaci především '
        '<strong>rozptyl mezi subtesty</strong>, ne jen výsledné číslo.</p>\n'
        '    </aside>'),
    8: ('    <aside class="box warn">\n'
        '      <h4><span class="bemo" aria-hidden="true">⚠️</span>Vynechaný obrázek '
        '— a zastaralé názvy škol</h4>\n'
        '      <p>Zdroj sem vložil <strong>snímek plochy Windows</strong> s naskenovanou '
        'stránkou učebnice. Snímek obsahoval uživatelské jméno a cesty k souborům, proto se '
        'nepublikuje.</p>\n'
        '      <p>Podstatnější je, že seznam škol na skenu je <strong>z doby před rokem '
        '2005</strong> — uvádí „zvláštní školy“ a „pomocné školy“, tedy typy, které školský '
        'zákon č. 561/2004 Sb. zrušil. Dnes se žáci s tělesným postižením vzdělávají '
        've školách hlavního proudu s podpůrnými opatřeními podle § 16, případně ve třídách '
        'a školách zřízených podle <strong>§ 16 odst. 9</strong>. Viz '
        '<a href="pravni-aktualnost.html">právní aktuálnost</a>.</p>\n'
        '    </aside>'),
    12: ('    <aside class="box warn">\n'
         '      <h4><span class="bemo" aria-hidden="true">⚠️</span>Vynechaný obrázek</h4>\n'
         '      <p>Srovnávací tabulka analyticko-syntetické a genetické metody byla ve zdroji '
         'vložena jako <strong>snímek prohlížeče</strong> — včetně osobní lišty záložek '
         'autorky. Předloha navíc výslovně zapovídá další šíření. Snímek se proto '
         'nepublikuje; obsah srovnání je níž v textu otázky.</p>\n'
         '    </aside>'),
    17: ('    <aside class="box warn">\n'
         '      <h4><span class="bemo" aria-hidden="true">⚠️</span>Vynechaný obrázek</h4>\n'
         '      <p>U pasáže o screeningu sluchu byl ve zdroji <strong>snímek prohlížeče</strong> '
         's dokumentem ČSORLCHHK, který obsahoval <strong>jmenný seznam krajských koordinátorů '
         'včetně jejich e-mailových adres</strong>. Osobní kontaktní údaje se na veřejný web '
         'nepřenášejí, snímek je proto vynechán. Tři audiogramy níž na stránce ze zdroje '
         'převzaty jsou — neobsahují žádné osobní údaje.</p>\n'
         '    </aside>'),
}


# ---------------------------------------------------------------- pomůcky

def ptext(b: dict) -> str:
    if b["kind"] == "table":
        return ""
    return "".join(p.get("t", "") for p in b["parts"]).strip()


def flat(s: str) -> str:
    """Text pro srovnání s mapou hranic — zdroj používá nezlomitelné mezery."""
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def is_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.75


def normalize_styles(blocks: list[dict]) -> None:
    for b in blocks:
        if b["kind"] == "p":
            b["style"] = STYLE_MAP.get(b["style"], b["style"])
        else:
            for row in b["rows"]:
                for cell in row:
                    normalize_styles(cell)


def demote_inner_h1(body: list[dict]) -> int:
    """`Nadpis1` uvnitř otázky není další stránka, ale sekce → H2."""
    n = 0
    for b in body:
        if b["kind"] == "p" and b["style"] == "Heading1":
            b["style"] = "Heading2"
            n += 1
    return n


def promote_caps(body: list[dict]) -> int:
    """
    Samostatný odstavec VERZÁLKAMI je v tomto dokumentu nadpis sekce.

    Bez toho by otázky 17 a 20 neměly jediný H2, tedy ani obsah v levém sloupci
    (otázka 17 má 11 000 slov — stránka bez navigace by byla nepoužitelná).
    Podmínky drží heuristiku u zdi: musí to být aspoň dvě slova, převážně
    písmena a nesmí to být položka seznamu ani utržený konec věty.
    """
    n = 0
    for b in body:
        if b["kind"] != "p" or b["style"] != "Normal" or b.get("num"):
            continue
        t = ptext(b)
        if not (8 <= len(t) <= 95) or not is_caps(t):
            continue
        if len(t.split()) < 2:
            continue
        letters = sum(c.isalpha() or c.isspace() for c in t)
        if letters / len(t) < 0.75:          # „E, I, P, N, T, K, V, D.“
            continue
        if t.endswith((",", ";", "-", "–")):
            continue
        b["style"] = "Heading2"
        n += 1
    return n


# ---------------------------------------------------------------- klíčové pojmy

# začátky, které nedávají použitelný pojem (věta, výčet, obecná rubrika)
STEM_RE = re.compile(
    r"^(provádí|poskytuje|zajišťuje|spolupracuj|vede |zpracov|podílí|sleduje|"
    r"eviduje|metodicky|koordinuje|realizuje|dbá|usiluje|pomáhá|umožňuje|"
    r"označujeme|rozlišujeme|rozdělujeme|patří|jsou to|dělíme|vychází|"
    r"zahrnuje|zahrnujeme|má podobu|podle|jedná se|při |pro |kromě |dále |"
    r"možnosti|zásady|přehled|klasifikace|"
    r"legislativa|literatura|právní předpisy|cíle |cílem|"
    r"nutno|nutné|oblíben|založen|zaměřen|určen|mezi |vývoj inteligence|"
    r"u dítěte|u žáka|u osob|doporučuj|nejčastější)",
    re.I)

# Poslední slovo pojmu, po kterém věta pokračuje — pak to není pojem, ale
# utržený začátek souvětí („U dítěte s OVŘ je vhodné — doporučit rodičům…“).
TAIL_RE = re.compile(
    r"\b(je|jsou|bývá|bývají|patří|zahrnuje|obsahuje|vhodné|nutné|možné|"
    r"důležité|třeba|následující|toto|tyto|jiné)$", re.I)

# „Vývoj inteligence probíhá cca do 10 — 12 let“ — pomlčka tu odděluje rozsah
# čísel, ne pojem od definice.
RANGE_RE = re.compile(r"^\d+\s*(let|rok|roků|roky|%|dB|měsíc)", re.I)

# Rubriky, které samy o sobě nic neučí. Držíme seznam krátký: „Reedukace“ nebo
# „Intervence“ s poctivou definicí jsou naopak přesně ty kartičky, které chceme.
STOP_TERMS = {
    "primarni", "sekundarni", "terciarni", "uvod", "zaver", "dalsi", "ostatni",
    "jine", "poznamka", "priklad", "priklady", "shrnuti", "pozor",
}

SEP_RE = re.compile(r"^(.{4,60}?)\s+[–—]\s+(.{28,})$")

# Definiční signál — bez něj by se za definici vydávala kterákoli první věta
# pod nadpisem. Odstavec začínající malým písmenem větu nadpisu dokončuje,
# takže u něj signál nepotřebujeme.
DEFN_CUE = re.compile(
    r"\b(je |jsou |znamená|označuj|spočívá|představuj|charakterizuj|rozumí se|"
    r"chápe se|definuje|soubor|skupina|proces|metoda|metody|schopnost|"
    r"porucha|poruchy|stav |činnost|systém|snížení|narušení)", re.I)


def _ok_term(term: str) -> bool:
    if not (4 <= len(term) <= 60) or len(term.split()) > 6:
        return False
    if not term[0].isupper():
        return False
    if STEM_RE.match(term) or TAIL_RE.search(term.rstrip(" .:")):
        return False
    if deaccent(term).lower().strip(" .:") in STOP_TERMS:
        return False
    return bool(re.search(r"[A-Za-zÁ-Žá-ž]{3}", term))


def _ok_def(d: str) -> bool:
    if len(d) < 28 or d.endswith((":", ",", ";")):
        return False
    return not RANGE_RE.match(d)


ACRONYMS: set[str] = set()

# česká slova, která se verzálkami psaná tváří jako zkratka
NOT_ACRONYM = {
    "SE", "NA", "PRO", "DLE", "JE", "JSOU", "VE", "ZA", "OD", "DO", "PŘI",
    "PO", "BEZ", "NEBO", "ALE", "TAK", "JAK", "KDY", "KDE", "CO", "TO",
    "DÍL", "VÍCE", "MÁ", "MÁME", "JEN", "AŽ", "ČI", "TÉŽ", "TÉTO", "TÍM",
}
VOWELS = "AEIOUYÁÉÍÓÚŮÝĚ"


def _looks_acronym(tok: str) -> bool:
    if tok in NOT_ACRONYM:
        return False
    # BUDOU, BĚŽNÁ, CHOVÁNÍ, PÉČE — česká slova mají samohlásek víc než zkratky
    return len(tok) < 4 or sum(c in VOWELS for c in tok) <= 1


def detect_acronyms(blocks: list[dict], min_hits: int = 2) -> set[str]:
    """
    Zkratky vyčteme z dokumentu, ne z ručního seznamu: co se píše verzálkami
    i uvnitř normálně psané věty, je zkratka (SPC, RVP, ZŠS, MKN, IVP…).
    Krátká česká slova jako „PRO“, „DLE“ nebo „PÉČE“ se takto samy vyloučí,
    protože v běžném textu verzálkami nestojí.
    """
    hits: dict[str, int] = {}
    for b in blocks:
        if b["kind"] != "p":
            continue
        t = ptext(b)
        if not t or is_caps(t):              # nadpis verzálkami nic nedokazuje
            continue
        for tok in re.findall(r"\b[A-ZÁ-Ž][A-ZÁ-Ž0-9]{1,6}\b", t):
            hits[tok] = hits.get(tok, 0) + 1
    return {k for k, v in hits.items() if v >= min_hits and _looks_acronym(k)}


def _fold_caps(term: str) -> str:
    """
    VERZÁLKY na běžný zápis, ale zkratky nechá být — jinak ze „DIAGNOSTICKÉ
    METODY SPC“ vznikne „Diagnostické metody spc“ a z „RVP ZŠS“ „rvp zšs“.
    """
    out = []
    for i, w in enumerate(term.split()):
        core = w.strip("().,;:„“\"'")
        if core in ACRONYMS or re.search(r"\d", core):
            out.append(w)                    # SPC, RVP, ZŠS, MP, IVP, F84.1…
        elif i == 0:
            out.append(w[:1].upper() + w[1:].lower())
        else:
            out.append(w.lower())
    return " ".join(out)


def collect_key_terms(body: list[dict], limit: int = 14) -> list[tuple[str, str]]:
    """
    Dvojice pojem/definice pro sekci „🔑 Klíčové pojmy“, z níž se dělají
    kartičky a glosář. Zdroj vlastní sekci klíčových pojmů nemá, ale používá
    dva čitelné vzory: odrážku „Pojem — definice“ a nadpis, za nímž následuje
    jeho definice.
    """
    pairs: list[tuple[str, str]] = []

    # 1) odrážky „Pojem — definice“
    for b in body:
        if b["kind"] != "p" or b["style"] != "ListParagraph":
            continue
        m = SEP_RE.match(ptext(b))
        if not m:
            continue
        term, d = m.group(1).strip(" .:"), m.group(2).strip()
        if _ok_term(term) and _ok_def(d):
            pairs.append((term, d))

    # 2) nadpis + definice pod ním
    for i, b in enumerate(body):
        if b["kind"] != "p" or b["style"] not in ("Heading2", "Heading3", "Heading4"):
            continue
        term = ptext(b).strip(" .:")
        if not _ok_term(term):
            continue
        for j in range(i + 1, min(i + 3, len(body))):
            nb = body[j]
            if nb["kind"] != "p" or nb["style"].startswith("Heading"):
                break
            d = ptext(nb)
            if not d:
                continue
            if d.startswith("="):
                d = d.lstrip("= ").strip()
            elif not d[0].islower() and not DEFN_CUE.search(d[:90]):
                break
            if _ok_def(d):
                pairs.append((term, d))
            break

    # jeden pojem jednou; verzálky zmírníme, ať glosář nekřičí
    seen, out = set(), []
    for term, d in pairs:
        k = deaccent(term).lower()
        if k in seen:
            continue
        seen.add(k)
        if is_caps(term) and len(term) > 4:
            term = _fold_caps(term)
        out.append((term, d))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- render

def img_html(rid: str, up: str = "") -> str:
    if rid not in IMAGES:
        return ""
    fname, caption, alt = IMAGES[rid]
    return (
        '\n      <figure class="fig">'
        '\n        <img src="%simg/%s" alt="%s" loading="lazy">'
        '\n        <figcaption>%s</figcaption>'
        '\n      </figure>' % (up, fname, esc(alt), esc(caption))
    )


def footer() -> str:
    return "\n".join([
        '<footer class="foot">',
        '  <div class="wrap">',
        '    <p>%s · otázky ke státní závěrečné zkoušce · '
        'právní stav <a href="pravni-aktualnost.html">ověřen k 08/2026</a></p>' % LABEL,
        "  </div>",
        "</footer>",
    ])


# Ruční opravy a doplňky ze tools/_doplnky_poradenstvi.json. Drží se mimo HTML,
# aby je opětovné spuštění konvertoru nesmazalo (stejný důvod jako u psychologie).
FIXES: dict[str, list] = {}
BOXES: dict[str, str] = {}


def apply_fixes(n: int, page: str) -> tuple[str, list[str]]:
    """
    Aplikuje opravy na hotovou stránku. Vrací (stránka, seznam problémů).

    Hledá se tolerantně k mezerám: zdrojový dokument je plný nezlomitelných
    mezer, takže „Žáci s LMP“ zkopírované z výstupu nemusí být totéž, co je
    ve stránce. Jakýkoli úsek mezer v hledaném textu proto odpovídá jakémukoli
    úseku mezer ve stránce.
    """
    problems = []
    for find, repl in FIXES.get(str(n), []):
        pat = re.compile(r"[\s ]+".join(re.escape(p) for p in find.split()))
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
    ctx = Ctx(numfmt, {}, {})
    ctx.images = {rid: img_html(rid) for rid in IMAGES}

    keys = collect_key_terms(body)
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
        '    <p class="lead">%s</p>' % esc(full),
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

    note = IMAGE_NOTES.get(n)
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
    return "\n".join(out), keys


# ---------------------------------------------------------------- main

def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    force = "--force" in sys.argv
    src = args[0] if args else "SZO SPECIÁLNÍ PEDAGOGIKA.DOCX"
    outdir = args[1] if len(args) > 1 else SUBJECT
    os.makedirs(outdir, exist_ok=True)

    existing = glob.glob(os.path.join(outdir, "otazka-*.html"))
    if existing and not force:
        print("V %s/ už je %d stránek otázek — bez --force nepřepisuji." % (outdir, len(existing)))
        return 2

    here = os.path.dirname(os.path.abspath(__file__))
    dop = os.path.join(here, "_doplnky_poradenstvi.json")
    if os.path.exists(dop):
        data = json.load(open(dop, encoding="utf-8"))
        FIXES.update(data.get("fixes", {}))
        BOXES.update(data.get("boxes", {}))
        print("ruční doplňky: %d oprav v %d otázkách, %d boxů"
              % (sum(len(v) for v in FIXES.values()), len(FIXES), len(BOXES)))

    blocks, numfmt = parse_document(src)
    normalize_styles(blocks)
    print("bloků v dokumentu: %d" % len(blocks))

    ACRONYMS.update(detect_acronyms(blocks))
    print("zkratek rozpoznaných v textu: %d (%s…)"
          % (len(ACRONYMS), ", ".join(sorted(ACRONYMS)[:12])))

    # --- kontrola mapy hranic ---------------------------------------------
    bad = []
    for n, (idx, want) in sorted(QSTART.items()):
        got = flat(ptext(blocks[idx])) if idx < len(blocks) else "<za koncem dokumentu>"
        if not got.startswith(want):
            bad.append("  otázka %2d: blok %d má %r, čekáno %r" % (n, idx, got[:70], want))
    if bad:
        print("MAPA HRANIC NESOUHLASÍ SE ZDROJEM — dokument se změnil:")
        print("\n".join(bad))
        print("Opravte QSTART v tools/docx2html_spec.py; generovat naslepo nemá smysl.")
        return 1
    print("mapa hranic: všech %d nadpisů otázek na svém místě" % len(QSTART))

    # --- struktura po otázkách --------------------------------------------
    order = sorted(((n, i) for n, (i, _w) in QSTART.items()), key=lambda kv: kv[1])
    bodies, demoted, promoted = {}, 0, 0
    for k, (n, start) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(blocks)
        body = [b for i, b in enumerate(blocks[start + 1:end], start=start + 1)
                if i not in DROP_BLOCKS]
        demoted += demote_inner_h1(body)
        promoted += promote_caps(body)
        bodies[n] = (start, end, body)
    print("nadpisů Nadpis1 uvnitř otázek přeznačeno na sekce: %d" % demoted)
    print("odstavců verzálkami povýšeno na sekce: %d" % promoted)

    # --- obrázky -----------------------------------------------------------
    imgdir = os.path.join(outdir, "img")
    os.makedirs(imgdir, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        rels = z.read("word/_rels/document.xml.rels").decode("utf-8")
        for rid, (fname, _c, _a) in IMAGES.items():
            m = re.search(r'Id="%s"[^>]*Target="([^"]+)"' % rid, rels)
            if not m:
                print("  ! obrázek %s v dokumentu není" % rid)
                continue
            data = z.read("word/" + m.group(1).lstrip("/"))
            open(os.path.join(imgdir, fname), "wb").write(data)
            print("  obrázek: img/%s (%d kB)" % (fname, len(data) // 1024))
    print("  vynecháno %d obrázků (snímky obrazovky, skeny záznamů, spojnice diagramů)"
          % len(SKIP_IMAGES))

    # --- perex z obsahu dokumentu -----------------------------------------
    toc = {}
    for b in blocks[:34]:
        m = re.match(r"^(\d{1,2})\s*\.\s*(.{20,})$", ptext(b))
        if m and int(m.group(1)) in QSTART:
            toc[int(m.group(1))] = re.sub(r"\s+", " ", m.group(2)).strip()
    missing_toc = [n for n in QSTART if n not in toc]
    if missing_toc:
        print("  ! bez záznamu v obsahu dokumentu: %s" % missing_toc)

    def href(n):
        return "otazka-%02d-%s.html" % (n, TITLES[n][1])

    nums = sorted(QSTART)
    meta, bmap, total_keys = [], {}, 0
    fix_problems: list[str] = []
    for k, n in enumerate(nums):
        start, end, body = bodies[n]
        short = TITLES[n][0]
        full = toc.get(n, short)
        prev = (nums[k - 1], href(nums[k - 1]), TITLES[nums[k - 1]][0]) if k else None
        nxt = (nums[k + 1], href(nums[k + 1]), TITLES[nums[k + 1]][0]) if k + 1 < len(nums) else None
        inner, keys = render_question(n, short, full, body, numfmt, prev, nxt)
        page = shell(
            title="%d. %s · %s · Státnice" % (n, short, LABEL),
            desc="Otázka %d ke státní závěrečné zkoušce ze speciální pedagogiky "
                 "— poradenství: %s" % (n, short),
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
                     "cards": len(keys), "words": sum(len(ptext(b).split()) for b in body)})

    json.dump({"toc": toc, "bounds": {str(n): QSTART[n][0] for n in QSTART},
               "drop": sorted(DROP_BLOCKS), "map": bmap, "missing": [],
               "skipped_images": SKIP_IMAGES, "questions": meta},
              open("tools/_meta_poradenstvi.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("zapsáno %d otázek do %s/ · klíčových pojmů %d" % (len(meta), outdir, total_keys))
    thin = [m["n"] for m in meta if m["cards"] < 4]
    if thin:
        print("  ! málo klíčových pojmů u otázek: %s" % thin)
    if fix_problems:
        print("  ! RUČNÍ OPRAVY SE NEPODAŘILO APLIKOVAT:")
        for p in fix_problems:
            print("    %s" % p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
