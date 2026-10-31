#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx2html_zapisky.py — podrobné stránky k okruhům zadání ze studentských zápisků 2025.

Šestý konvertor a první, který nebere jeden dokument, ale **sadu**: jeden .docx
na každý okruh oficiálního zadání — 17 okruhů etopedie, 17 psychopedie. Zápisky
jsou z roku 2025 a jsou to skoro výhradně nové texty: s otázkami, které na webu
už jsou, se překrývají jen v jednotkách procent. Proto se k nim nepřilévají,
ale vznikají samostatné stránky „Podrobně: okruh N“, provázané se stručnými
otázkami oběma směry.

Proti předchozím pěti dokumentům se řeší tohle:

  * **Text v hypertextových odkazech.** `docx2html.parse_para()` čte jen běhy,
    které jsou přímými potomky odstavce, takže text uvnitř `<w:hyperlink>`
    zahodí — a zrovna tady jsou v odkazech názvy metodických pokynů i zákonů.
    Tenhle konvertor proto parsuje odstavce sám (`parse_document_full`).
  * **Zbytky z ChatGPT.** Část textu je vložená z ChatGPT i s „pilulkami“
    zdrojů — odkazy s `utm_source=chatgpt.com` a textem typu „Projekty OSU+1“
    nalepeným za větou. Ty se zahazují (pravidlo, ne ruční seznam) a každé
    zahození se zapíše do _meta_zapisky_<předmět>.json. Vložená konverzace
    v psychopedii, okruhu 10 („Řekl/a jsi:“, „ChatGPT řekl:“) je vyřazená
    po blocích v `drop`, i s důvodem.
  * **Emoji v nadpisech** (🔷, 🟠, ✅, 🧠…) se z nadpisů odstraňují; v textu
    zůstávají jen šipky a podobné znaky, které nesou význam.
  * **Nadpisové styly jsou nejednotné** — někde `Nadpis2/3/4`, jinde `Heading`,
    někde je Nadpis 1 použitý na větu uprostřed textu a čtyři dokumenty nemají
    nadpisové styly vůbec. Úrovně se berou podle *jména* stylu ve styles.xml,
    ne podle jeho id, a pro jednotlivé okruhy se dají přemapovat (`levels`),
    doplnit (`promote`) nebo potlačit (`demote`).
  * **Obrázky se nepublikují.** Jsou to snímky tabulek z učebnic a z dokumentů
    MŠMT a MPSV; jejich obsah je přepsaný jako HTML tabulky v `images`.
    Obrázek bez záznamu v `images` je chyba, ne tichá vynechávka.

Ruční opravy, klíčové pojmy, přepsané obrázky a vyřazené bloky jsou mimo HTML
v tools/_doplnky_<předmět>_podrobne.json, takže opětovné spuštění nic neztratí.

    python3 tools/docx2html_zapisky.py etopedie [--force]
    python3 tools/docx2html_zapisky.py psychopedie [--force]
    python3 tools/docx2html_zapisky.py --all [--force]
    python3 tools/docx2html_zapisky.py etopedie --dump /tmp/vypis   # text s čísly bloků

Zdroje se čekají v source/zapisky-2025/<předmět>/ (adresář je v .gitignore):
etopedie = obsah složky „Eto“, psychopedie = obsah složky „Psychopedie “
(s mezerou na konci názvu).
"""

from __future__ import annotations

import difflib
import glob
import html
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docx2html import (  # noqa: E402
    NS,
    SEC_TYPES,
    W,
    Ctx,
    esc,
    render_flow,
    shell,
    split_sections,
    strip_emoji,
    topnav,
)
import docx2html as D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.join("source", "zapisky-2025")
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PRNS = "http://schemas.openxmlformats.org/package/2006/relationships"

# ------------------------------------------------------------------ předměty

SUBJECTS = {
    "etopedie": {
        "label": "Etopedie",
        "file_re": r"^(\d{1,2})\.\s*otazka",
        "zadani": "ETOPEDIE.docx",
    },
    "psychopedie": {
        "label": "Psychopedie",
        "file_re": r"^Otazka c\.\s*(\d{1,2})\b",
        "zadani": "PSYCHOPEDIE.docx",
    },
}

# krátký titulek pro H1 a název souboru; plné znění okruhu ze zadání jde do perexu
TITLES = {
    "etopedie": {
        1: ("Historie etopedie, strategie a systémový přístup", "historie-strategie"),
        2: ("Sociální normy, morální vývoj a trestní odpovědnost", "normy-moralni-vyvoj"),
        3: ("Diagnostika, etiologie a prevence poruch chování", "diagnostika-etiologie"),
        4: ("Edukace žáků s PCH, sociální dovednosti a emoční inteligence", "edukace-socialni-dovednosti"),
        5: ("Školská zařízení NVP a ústavní výchova", "zarizeni-nvp-ustavni-vychova"),
        6: ("Cíle zařízení NVP, diagnostika a terapie", "cile-nvp-diagnostika"),
        7: ("Kurikulární dokumenty a standardy v NVP", "kurikulum-standardy"),
        8: ("Osobnost pedagoga, odborníci a terapeutické směry", "pedagog-odbornici-terapie"),
        9: ("Rodina dítěte ohroženého PCH a náhradní rodinná péče", "rodina-ohrozeni-nrp"),
        10: ("Rodina dítěte s PCH, postpéče a sanace rodiny", "rodina-postpece-sanace"),
        11: ("Sociálně-právní ochrana dětí a práva dítěte", "spod-prava-ditete"),
        12: ("Agrese a šikana", "agrese-sikana"),
        13: ("ADHD, hyperkinetická porucha a opoziční chování", "adhd-opozicni-chovani"),
        14: ("Lež, záškoláctví a krádeže", "lez-zaskolactvi-kradeze"),
        15: ("Emoční poruchy, deprese a suicidální chování", "emocni-poruchy"),
        16: ("Prevence v socializaci, třída, odměny a tresty", "prevence-odmeny-tresty"),
        17: ("Závislostní chování a prevence", "zavislostni-chovani"),
    },
    "psychopedie": {
        1: ("AAK u dětí a dospělých, pomůcky s hlasovým výstupem", "aak-deti-dospeli"),
        2: ("Alternativní vzdělávací programy a sociální čtení", "alternativni-programy"),
        3: ("Psychopedie jako obor, historie a klasifikace", "obor-historie-klasifikace"),
        4: ("Vzdělávání dětí s PAS a program TEACCH", "pas-vzdelavani-teacch"),
        5: ("Organizace a vládní dokumenty", "organizace-dokumenty"),
        6: ("Piktogramy, Bliss, Makaton, Lormova abeceda a VOKS", "aak-systemy-voks"),
        7: ("Volný čas, profesní orientace a práce s dospělými", "volny-cas-dospeli"),
        8: ("Výchova dítěte s mentálním postižením a raná péče", "vychova-rana-pece"),
        9: ("Vzdělávací systém, RVP a podpůrná opatření", "vzdelavaci-system"),
        10: ("Spolurozhodování, advokacie a sebeobhajování", "sebeobhajovani-advokacie"),
        11: ("Zaměstnávání lidí s mentálním postižením", "zamestnavani"),
        12: ("Trénink pracovních dovedností a tranzitní program", "tranzitni-program"),
        13: ("Pervazivní vývojové poruchy a PAS", "pervazivni-poruchy-pas"),
        14: ("Diagnostika v psychopedii", "diagnostika"),
        15: ("Partnerství, sexualita, rodičovství a stáří", "partnerstvi-stari"),
        16: ("Poradenství pro marginalizované osoby", "poradenstvi-marginalizovani"),
        17: ("Proces učení, metody čtení a psaní, IVP", "proces-uceni-cteni-psani"),
    },
}

# Okruh zadání → stručné otázky webu, které ho pokrývají. U psychopedie je mapa
# převzatá z A21 v docx2html_psychopedie.py (zdroj z roku 2018 má okruhy
# přeskládané), u etopedie z mapy 20 stránek na 17 okruhů zadání.
STRUCNE_ETOPEDIE = {
    1: [1, 3], 2: [2], 3: [4, 5], 4: [6], 5: [7], 6: [8], 7: [9], 8: [10],
    9: [11], 10: [12], 11: [13], 12: [15], 13: [14], 14: [16], 15: [17],
    16: [18, 19], 17: [20],
}


def strucne_map(subject: str) -> dict[int, list[int]]:
    if subject == "psychopedie":
        import docx2html_psychopedie as P
        return {k: list(v[0]) for k, v in P.A21.items()}
    return dict(STRUCNE_ETOPEDIE)


def href_of(subject: str, n: int) -> str:
    return "podrobne-okruh-%02d-%s.html" % (n, TITLES[subject][n][1])


# ------------------------------------------------------------------ parsování
#
# docx2html.parse_document() vynechává text v <w:hyperlink> (a v dalších
# obalech běhů — <w:ins>, <w:smartTag>, <w:sdt> uvnitř odstavce). Tady je
# kopie se stejným výstupem, jen s rekurzí do obalů. U částí z odkazu je
# navíc klíč "href" s cílem odkazu, aby šly rozeznat citační pilulky ChatGPT.

RUN_WRAPPERS = {"hyperlink", "ins", "smartTag", "customXml", "sdt", "sdtContent",
                "fldSimple", "bdo", "dir", "moveTo"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


A_BLIP = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"


def run_parts_full(run) -> list[dict]:
    """
    `docx2html.run_parts()` se dvěma rozdíly: `<w:tab/>` je mezera, ne nic
    (v zadání etopedie jsou tabulátorem oddělená slova — „Diagnostika⇥poruch“),
    a pevný spojovník je spojovník.
    """
    rpr = run.find("w:rPr", NS)

    def on(tag):
        if rpr is None:
            return False
        el = rpr.find("w:" + tag, NS)
        return el is not None and el.get(W + "val") not in ("0", "false", "none")

    bold, ital = on("b"), on("i")
    out, buf = [], []
    for node in run.iter():
        if node.tag == A_BLIP:
            rid = node.get("{%s}embed" % RNS)
            if rid:
                out.append({"img": rid})
            continue
        tag = _local(node.tag)
        if tag == "t":
            buf.append(node.text or "")
        elif tag == "tab":
            buf.append(" ")
        elif tag == "noBreakHyphen":
            buf.append("-")
        elif tag in ("br", "cr"):
            out.append({"t": "".join(buf), "b": bold, "i": ital})
            out.append({"br": True})
            buf = []
    if buf:
        out.append({"t": "".join(buf), "b": bold, "i": ital})
    return out


def parse_para_full(p, rels: dict[str, str]) -> dict:
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
    parts: list[dict] = []

    def walk(el, href=None):
        for child in el:
            tag = _local(child.tag)
            if tag == "r":
                got = run_parts_full(child)
                if href:
                    for g in got:
                        if "t" in g:
                            g["href"] = href
                parts.extend(got)
            elif tag in RUN_WRAPPERS:
                h = href
                if tag == "hyperlink":
                    rid = child.get("{%s}id" % RNS)
                    h = rels.get(rid) or ("#" + (child.get(W + "anchor") or ""))
                walk(child, h)

    walk(p)
    return {"kind": "p", "style": style, "num": num, "lvl": lvl, "parts": parts}


def parse_table_full(tbl, rels) -> dict:
    rows = []
    for tr in tbl.findall("w:tr", NS):
        row = []
        for tc in tr.findall("w:tc", NS):
            cell = []
            for el in tc:
                if _local(el.tag) == "p":
                    cell.append(parse_para_full(el, rels))
                elif _local(el.tag) == "tbl":           # vnořená tabulka → odstavce
                    for p in el.iter(W + "p"):
                        cell.append(parse_para_full(p, rels))
            row.append(cell)
        rows.append(row)
    return {"kind": "table", "rows": rows}


def parse_document_full(path: str) -> tuple[list[dict], dict, dict[str, str]]:
    """Vrací (bloky, formáty číslování, id stylu → jméno stylu)."""
    with zipfile.ZipFile(path) as z:
        doc = ET.fromstring(z.read("word/document.xml"))
        try:
            numbering = ET.fromstring(z.read("word/numbering.xml"))
        except KeyError:
            numbering = None
        try:
            styles = ET.fromstring(z.read("word/styles.xml"))
        except KeyError:
            styles = None
        relx = ET.fromstring(z.read("word/_rels/document.xml.rels"))
    rels = {r.get("Id"): r.get("Target") for r in relx.findall("{%s}Relationship" % PRNS)}

    names: dict[str, str] = {}
    if styles is not None:
        for s in styles.findall(W + "style"):
            n = s.find(W + "name")
            names[s.get(W + "styleId")] = n.get(W + "val") if n is not None else s.get(W + "styleId")

    numfmt: dict[str, dict[int, str]] = {}
    if numbering is not None:
        absfmt = {}
        for an in numbering.findall("w:abstractNum", NS):
            lv = {}
            for lvl_el in an.findall("w:lvl", NS):
                f = lvl_el.find("w:numFmt", NS)
                lv[int(lvl_el.get(W + "ilvl") or 0)] = f.get(W + "val") if f is not None else "bullet"
            absfmt[an.get(W + "abstractNumId")] = lv
        for n in numbering.findall("w:num", NS):
            a = n.find("w:abstractNumId", NS)
            numfmt[n.get(W + "numId")] = absfmt.get(a.get(W + "val"), {})

    blocks: list[dict] = []

    def walk(el):
        for child in el:
            tag = _local(child.tag)
            if tag == "p":
                blocks.append(parse_para_full(child, rels))
            elif tag == "tbl":
                blocks.append(parse_table_full(child, rels))
            elif tag == "sdt":
                inner = child.find("w:sdtContent", NS)
                walk(inner if inner is not None else child)

    walk(doc.find("w:body", NS))
    return blocks, numfmt, names


def ptext(b: dict) -> str:
    if b["kind"] == "table":
        return ""
    return "".join(p.get("t", "\n") for p in b["parts"] if "img" not in p).strip()


def flat(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def normalize_styles(blocks: list[dict], names: dict[str, str]) -> None:
    """
    Styl podle jména, ne podle id: `Nadpis3` i `Heading3` se jmenují „heading 3“.

    Nadpisy si pamatují svou původní úroveň v `hlevel`; na úroveň HTML se
    přemapují až v `apply_levels()`, protože každý zápisek používá jinou sadu.
    """
    for b in blocks:
        if b["kind"] == "table":
            for row in b["rows"]:
                for cell in row:
                    normalize_styles(cell, names)
            continue
        name = names.get(b["style"], b["style"] or "").lower()
        m = re.match(r"heading (\d)", name)
        if m:
            b["hlevel"] = int(m.group(1))
            b["style"] = "Heading"
        elif name == "title":
            b["hlevel"] = 1
            b["style"] = "Heading"
        elif name == "list paragraph":
            b["style"] = "ListParagraph"
        else:
            b["style"] = "Normal"


# ------------------------------------------------------------------ úklid

# Citační „pilulky“ ChatGPT: odkaz s utm_source=chatgpt.com, jehož text je
# jen název webu („Projekty OSU“, „Podnikatel.cz+3krajta.slv.cz+3“).
CHATGPT_URL = re.compile(r"utm_source=chatgpt\.com")
PILL_SUFFIX = re.compile(r"\+\d{1,2}(?=$|[^\d])")

# Prefix prohlížeče PDF v Chromu a sledovací parametry v adresách.
CHROME_PDF = re.compile(r"chrome-extension://[a-z]{32}/")
UTM = re.compile(r"[?&]utm_source=chatgpt\.com(?=$|[&#\s)\]])")

# Emoji a obrázkové symboly, kterými zápisky zdobí nadpisy (🔷 🟠 ✅ 🧠 ▪ ➤ …).
# Šipky → a ← zůstávají v textu, nesou význam; z nadpisů se odstraní jen na
# začátku a na konci.
EMOJI_ANY = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u25A0-\u25FF\u2190-\u21FF"
    "\uFE0F\u200D\u20E3]+")
HEAD_TRIM = re.compile(
    "^[\\s\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u25A0-\u25FF\u2190-\u21FF"
    "\uFE0F\u200D\u20E3\u2022\u00B7*\u2013\u2014-]+"
    "|[\\s\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u25A0-\u25FF\uFE0F\u200D]+$")


def clean_url(u: str) -> str:
    u = CHROME_PDF.sub("", u or "")
    u = UTM.sub("", u)
    u = re.sub(r"^(https?):/(?!/)", r"\1://", u)      # „https:/cmhrc.org“ po odříznutí prefixu
    if u.endswith("?"):
        u = u[:-1]
    return u


def clean_text(t: str) -> str:
    """Úklid textu, který se týká i zdrojového znění (adresy z prohlížeče)."""
    t = CHROME_PDF.sub("", t)
    t = UTM.sub("", t)
    return t


def is_pill(part: dict) -> bool:
    return bool(part.get("href")) and bool(CHATGPT_URL.search(part["href"]))


def clean_heading_text(t: str) -> str:
    t = HEAD_TRIM.sub("", t)
    t = EMOJI_ANY.sub(" ", t) if EMOJI_ANY.search(t) else t
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def merge_runs(parts: list[dict]) -> list[dict]:
    """
    Sousední běhy se stejným formátováním spojí v jeden. Word dělí text na běhy
    i uprostřed slova („chrome-“ + „extension“ + „://“…), takže bez spojení by
    úklid adres nenašel celý prefix — a HTML by bylo plné <strong>…</strong><strong> </strong>.
    """
    out: list[dict] = []
    for p in parts:
        prev = out[-1] if out else None
        if (prev is not None and "t" in p and "t" in prev
                and (prev.get("b"), prev.get("i"), prev.get("href")) == (p.get("b"), p.get("i"), p.get("href"))):
            prev["t"] += p["t"]
            continue
        out.append(dict(p))
    return out


def clean_block(b: dict, log: list, where: str) -> None:
    """Zahodí citační pilulky a uklidí adresy. Do logu zapíše, co zmizelo — jen odstraněný kus."""
    if b["kind"] == "table":
        for r, row in enumerate(b["rows"]):
            for c, cell in enumerate(row):
                for p in cell:
                    clean_block(p, log, "%s[%d,%d]" % (where, r, c))
        return
    keep = []
    for part in merge_runs(b["parts"]):
        if is_pill(part):
            if part.get("t", "").strip():
                log.append({"kde": where, "co": "citační odkaz ChatGPT", "text": part["t"].strip()})
            continue
        if "t" in part:
            removed = CHROME_PDF.findall(part["t"]) + UTM.findall(part["t"])
            if removed:
                log.append({"kde": where, "co": "adresa z prohlížeče / utm", "text": " ".join(removed)})
                part["t"] = clean_text(part["t"])
        if part.get("href"):
            part["href"] = clean_url(part["href"])
        keep.append(part)
    b["parts"] = keep


# ------------------------------------------------------------------ zdroje

def find_sources(subject: str, src_dir: str) -> dict[int, str]:
    cfg = SUBJECTS[subject]
    found: dict[int, list[str]] = {}
    for path in sorted(glob.glob(os.path.join(src_dir, "*.docx"))):
        name = unicodedata.normalize("NFC", os.path.basename(path))
        m = re.match(cfg["file_re"], name, re.I)
        if m:
            found.setdefault(int(m.group(1)), []).append(path)
    problems = []
    for n in range(1, 18):
        if n not in found:
            problems.append("okruh %d: zápisek nenalezen" % n)
        elif len(found[n]) > 1:
            problems.append("okruh %d: víc kandidátů %s" % (n, found[n]))
    extra = sorted(set(found) - set(range(1, 18)))
    if extra:
        problems.append("zápisky mimo okruhy 1–17: %s" % extra)
    if problems:
        raise SystemExit("ZDROJE V %s NESEDÍ:\n  %s" % (src_dir, "\n  ".join(problems)))
    return {n: v[0] for n, v in found.items()}


def read_zadani(subject: str, src_dir: str) -> dict[int, str]:
    """Plné znění 17 okruhů z oficiálního zadání (číslovaný seznam)."""
    path = os.path.join(src_dir, SUBJECTS[subject]["zadani"])
    blocks, _numfmt, names = parse_document_full(path)
    normalize_styles(blocks, names)
    items = [flat(ptext(b)) for b in blocks
             if b["kind"] == "p" and (b["num"] or b["style"] == "ListParagraph") and ptext(b)]
    if len(items) != 17:
        raise SystemExit("Zadání %s má %d okruhů, čekáno 17." % (path, len(items)))
    return {i + 1: t for i, t in enumerate(items)}


def load_doplnky(subject: str) -> dict:
    path = os.path.join(HERE, "_doplnky_%s_podrobne.json" % subject)
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8"))


def _html(v) -> str:
    """Doplňky se dají psát jako string i jako pole řádků (čitelnější diff)."""
    return "\n".join(v) if isinstance(v, list) else (v or "")


# ------------------------------------------------------------------ výpis

def dump(subject: str, src_dir: str, out_dir: str) -> int:
    """
    Text zápisků s čísly bloků — pomůcka pro psaní _doplnky_*_podrobne.json
    (`drop`, `promote`, `demote` a `images` se odkazují na čísla bloků).
    """
    os.makedirs(out_dir, exist_ok=True)
    for n, path in sorted(find_sources(subject, src_dir).items()):
        blocks, _numfmt, names = parse_document_full(path)
        normalize_styles(blocks, names)
        lines = ["# %s — okruh %d — %s" % (subject, n, os.path.basename(path))]
        for i, b in enumerate(blocks):
            if b["kind"] == "table":
                lines.append("%4d TABULKA %d×%d" % (i, len(b["rows"]), max(len(r) for r in b["rows"])))
                for row in b["rows"]:
                    lines.append("     | " + " | ".join(
                        flat(" ".join(ptext(p) for p in cell)) for cell in row))
                continue
            imgs = [p["img"] for p in b["parts"] if p.get("img")]
            t = flat(ptext(b))
            if not t and not imgs:
                continue
            tag = "H%d" % b["hlevel"] if b["style"] == "Heading" else (
                "L%d" % b["lvl"] if (b["num"] or b["style"] == "ListParagraph") else "  ")
            parts = [p for p in b["parts"] if p.get("t", "").strip()]
            bold = "B" if parts and all(p.get("b") for p in parts) else " "
            links = ["%s→%s" % (p["t"], p["href"][:60]) for p in b["parts"] if p.get("href") and p.get("t")]
            extra = (" [OBRÁZEK %s]" % ",".join(imgs)) if imgs else ""
            extra += (" [ODKAZY %s]" % " | ".join(links)) if links else ""
            lines.append("%4d %-3s%s %s%s" % (i, tag, bold, t, extra))
        fn = os.path.join(out_dir, "%s-%02d.txt" % (subject, n))
        open(fn, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("výpis zápisků %s → %s/" % (subject, out_dir))
    return 0


# ------------------------------------------------------------------ main

def main() -> int:
    argv = sys.argv[1:]
    dump_dir = None
    if "--dump" in argv:
        k = argv.index("--dump")
        dump_dir = argv[k + 1]
        del argv[k:k + 2]
    subjects = [a for a in argv if not a.startswith("-")]
    if "--all" in argv:
        subjects = list(SUBJECTS)
    if not subjects or any(s not in SUBJECTS for s in subjects):
        print("Použití: docx2html_zapisky.py etopedie|psychopedie|--all [--force] [--dump DIR]")
        return 2
    rc = 0
    for subject in subjects:
        src_dir = os.path.join(SRC_ROOT, subject)
        if dump_dir:
            rc |= dump(subject, src_dir, dump_dir)
            continue
        rc |= build(subject, src_dir, force="--force" in argv)
    return rc


# ------------------------------------------------------------------ příprava okruhu

# Původní úroveň nadpisu ve Wordu → úroveň v HTML. Nadpis 1 je v zápiscích
# buď titulek dokumentu, nebo věta uprostřed textu, nikdy nadřazená kapitola —
# proto padá na stejnou úroveň jako Nadpis 2. Okruh si může mapu přepsat
# (`levels`), 0 znamená „není nadpis, jen tučný odstavec“.
LEVELS = {1: 2, 2: 2, 3: 3, 4: 4, 5: 4, 6: 4}

# Nadpis delší než tohle je věta, ne nadpis (stejná hranice jako u pedagogiky
# a psychopedie).
LONG_HEADING = 150


def _bold_para(b: dict) -> None:
    """Z nadpisu udělá obyčejný tučný odstavec (text zůstane beze změny)."""
    b["style"] = "Normal"
    b.pop("hlevel", None)
    for p in b["parts"]:
        if "t" in p:
            p["b"] = True


def _set_heading(b: dict, level: int, log: list, where: str) -> None:
    raw = ptext(b)
    txt = clean_heading_text(flat(raw))
    if txt != flat(raw):
        log.append({"kde": where, "co": "emoji v nadpisu", "text": flat(raw)})
    b["parts"] = [{"t": txt, "b": False, "i": False}]
    b["style"] = "Heading%d" % level
    b["num"] = None


def mark_pills(blocks: list[dict]) -> int:
    """
    Označí citační pilulky ChatGPT jako odkazy s utm_source, aby je clean_block()
    zahodil. Kromě odkazů se sledovacím parametrem jsou pilulkou i odkazy,
    jejichž text má příponu „+N“, a — v dokumentu, kde pilulky jsou — odkaz,
    který stojí na samém konci odstavce a jeho text je jen název webu
    („IS MU Brno“, „Podnikatel.cz“). Odkaz na zákon uprostřed věty nebo holá
    adresa pilulkou nejsou.
    """
    paras = []
    for b in blocks:
        if b["kind"] == "table":
            for row in b["rows"]:
                for cell in row:
                    paras.extend(cell)
        else:
            paras.append(b)
    has = any(is_pill(p) for b in paras for p in b["parts"])
    n = 0
    for b in paras:
        texts = [k for k, p in enumerate(b["parts"]) if p.get("t", "").strip()]
        for k, p in enumerate(b["parts"]):
            if not p.get("href") or is_pill(p) or not p.get("t"):
                continue
            t = p["t"].strip()
            last = bool(texts) and k == texts[-1] and len(texts) > 1
            sitename = (sum(c.isalpha() for c in t) >= 2 and not t.lower().startswith(("http", "www."))
                        and len(t) <= 60)
            if PILL_SUFFIX.search(t) or (has and last and sitename):
                p["href"] += ("&" if "?" in p["href"] else "?") + "utm_source=chatgpt.com"
                n += 1
    return n


QTITLE_RE = re.compile(r"^(\d{1,2}\.\s*otázka|otázka\s*(č\.\s*)?\d{1,2})\.?$", re.I)


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9a-záčďéěíňóřšťúůýž]", "", flat(s).lower())


def title_blocks(blocks: list[dict], okruh: str) -> list[int]:
    """
    Úvodní bloky, které jen opakují hlavičku: „5. otázka“ a znění okruhu ze
    zadání — to už je na stránce v perexu. Bere se jen jedno opakování znění
    (i rozdělené do víc odstavců); tučný podnadpis, který za ním z části znění
    okruhu cituje, zůstává, protože v zápiscích uvozuje první část textu.
    """
    want = _alnum(okruh)
    out, covered = [], 0
    for i, b in enumerate(blocks[:10]):
        if b["kind"] != "p":
            break
        t = _alnum(ptext(b))
        if not t:
            continue
        if QTITLE_RE.match(flat(ptext(b))):
            out.append(i)
            continue
        if covered < 0.9 * len(want) and len(t) >= 15 and (
                t in want or difflib.SequenceMatcher(None, t, want).ratio() >= 0.9):
            out.append(i)
            covered += len(t)
            continue
        break
    return out


def prepare(subject: str, n: int, path: str, dop: dict, okruh: str = "") -> dict:
    """
    Načte a uklidí jeden zápisek. Výsledek používá konvertor i check_fidelity.py,
    takže kontrola srovnává stránku přesně s tím, co se mělo vykreslit.
    """
    blocks, numfmt, names = parse_document_full(path)
    normalize_styles(blocks, names)
    log: list[dict] = []
    key = str(n)

    # titulek dokumentu a opakované znění okruhu (je v hlavičce stránky)
    dropped: dict[int, str] = {}
    if okruh:
        for i in title_blocks(blocks, okruh):
            dropped[i] = "titulek zápisku a znění okruhu — totéž je v hlavičce stránky"
    # vyřazené bloky z doplňků (vložená konverzace s ChatGPT apod.)
    for d in dop.get("drop", {}).get(key, []):
        a, b = d["bloky"]
        for i in range(a, b + 1):
            dropped[i] = d["proc"]

    # nadpis rozlomený do dvou odstavců („…základní východiska a vývoj“ + „v rámci
    # speciální pedagogiky“) se spojí do prvního z nich
    for a, b in dop.get("spojit", {}).get(key, []):
        if blocks[a]["kind"] != "p" or blocks[b]["kind"] != "p":
            raise SystemExit("okruh %d: spojit %d+%d — oba bloky musí být odstavce" % (n, a, b))
        blocks[a]["parts"] = blocks[a]["parts"] + [{"t": " "}] + blocks[b]["parts"]
        dropped[b] = "druhá polovina rozlomeného nadpisu — spojeno s blokem %d" % a

    # Úklid jen u bloků, které na stránku jdou — vyřazený blok může obsahovat
    # i to, kvůli čemu se vyřazuje (místní cestu k souboru), a do logu nepatří.
    mark_pills([b for i, b in enumerate(blocks) if i not in dropped])
    for i, b in enumerate(blocks):
        if i not in dropped:
            clean_block(b, log, "blok %d" % i)

    levels = dict(LEVELS)
    levels.update({int(k): v for k, v in dop.get("levels", {}).get(key, {}).items()})
    promote = {int(i): int(lvl) for lvl, idx in dop.get("promote", {}).get(key, {}).items() for i in idx}
    demote = set(dop.get("demote", {}).get(key, []))
    problems = []
    for i in list(promote) + list(demote):
        if i >= len(blocks) or blocks[i]["kind"] != "p" or not ptext(blocks[i]):
            problems.append("okruh %d: blok %d v promote/demote není neprázdný odstavec" % (n, i))

    body: list[dict] = []
    for i, b in enumerate(blocks):
        if i in dropped:
            continue
        b["idx"] = i
        if b["kind"] == "p":
            if i in promote:
                _set_heading(b, promote[i], log, "blok %d" % i)
            elif b["style"] == "Heading":
                if not ptext(b):
                    continue                      # prázdný nadpis
                lvl = levels.get(b["hlevel"], 4)
                if i in demote or lvl == 0 or len(flat(ptext(b))) > LONG_HEADING:
                    _bold_para(b)
                else:
                    _set_heading(b, lvl, log, "blok %d" % i)
        body.append(b)

    return {"blocks": blocks, "body": body, "numfmt": numfmt, "log": log,
            "dropped": dropped, "problems": problems}


def units_of(body: list[dict]) -> list[tuple[int, str]]:
    """Textové jednotky (odstavce, buňky) pro check_fidelity.py: (blok, text)."""
    out = []
    for b in body:
        if b["kind"] == "table":
            for row in b["rows"]:
                for cell in row:
                    for p in cell:
                        t = ptext(p)
                        if t:
                            out.append((b["idx"], t))
        else:
            t = ptext(b)
            if t:
                out.append((b["idx"], t))
    return out


# ------------------------------------------------------------------ vykreslení

LINK_RE = re.compile("\uE000([^\uE001]*)\uE001([^\uE002]*)\uE002")


def encode_links(body: list[dict]) -> None:
    """
    Odkazy ve zdroji (zákony na e-Sbírce, metodické pokyny MŠMT) zůstávají
    odkazy. inline() z docx2html.py o odkazech neví, takže se cíl schová do
    textu mezi znaky ze soukromé oblasti Unicode — esc() je nechá být — a po
    vykreslení se z nich složí <a>. Číslo poznámky pod čarou z vloženého
    zákona („43)“) odkazem není, to je jen šum.
    """
    def fix(parts):
        for p in parts:
            h = p.get("href")
            if not h or not p.get("t") or h.startswith("#"):
                continue
            if not re.search(r"[A-Za-zÁ-ž]{2}", p["t"]):
                continue
            p["t"] = "\uE000%s\uE001%s\uE002" % (h.replace('"', "%22"), p["t"])

    for b in body:
        if b["kind"] == "table":
            for row in b["rows"]:
                for cell in row:
                    for p in cell:
                        fix(p["parts"])
        else:
            fix(b["parts"])


def decode_links(page: str) -> str:
    return LINK_RE.sub(lambda m: '<a href="%s" rel="noopener">%s</a>' % (m.group(1), m.group(2)), page)


def split_images(body: list[dict]) -> list[dict]:
    """Obrázek uprostřed odstavce → samostatný blok, aby <figure> nebyla v <p>."""
    out = []
    for b in body:
        if b["kind"] != "p" or not any(p.get("img") for p in b["parts"]):
            out.append(b)
            continue
        cur = dict(b, parts=[])
        for p in b["parts"]:
            if p.get("img"):
                if any(q.get("t", "").strip() for q in cur["parts"]):
                    out.append(cur)
                out.append(dict(b, parts=[p], num=None, style="Normal"))
                cur = dict(b, parts=[])
            else:
                cur["parts"].append(p)
        if any(q.get("t", "").strip() for q in cur["parts"]):
            out.append(cur)
    return out


def question_titles(subject: str) -> dict[int, tuple[str, str]]:
    """Číslo stručné otázky → (soubor, titulek z <h1>)."""
    out = {}
    for path in sorted(glob.glob(os.path.join(subject, "otazka-*.html"))):
        m = re.match(r"otazka-(\d+)-", os.path.basename(path))
        h1 = re.search(r"<h1>(.*?)</h1>", open(path, encoding="utf-8").read(), re.S)
        if m and h1:
            out[int(m.group(1))] = (os.path.basename(path), html.unescape(re.sub(r"<[^>]+>", "", h1.group(1))))
    return out


def words_label(words: int) -> str:
    """„asi 5 400 slov“ — zaokrouhleno na stovky, s pevnou mezerou v tisících."""
    r = int(round(words, -2)) or words
    s = "{:,}".format(r).replace(",", "\u00a0")
    return "asi %s slov" % s


def footer(label: str) -> str:
    return "\n".join([
        '<footer class="foot">',
        '  <div class="wrap">',
        '    <p>%s · podrobné zápisky 2025 k okruhům zadání · právní údaje '
        '<a href="pravni-aktualnost.html#zapisky-2025">ověřeny k 10/2026</a></p>' % label,
        "  </div>",
        "</footer>",
    ])


def key_section(keys: list[list[str]]) -> list[str]:
    if not keys:
        return []
    out = ["", '    <section class="sec sec-key">',
           '      <h2 id="klicove-pojmy"><span class="hemo" aria-hidden="true">🔑</span>'
           'Klíčové pojmy</h2>', "      <ul>"]
    for term, d in keys:
        out.append("        <li><strong>%s</strong> — %s</li>" % (esc(term), esc(d)))
    out += ["      </ul>", "    </section>"]
    return out


def _ws_pattern(text: str) -> re.Pattern:
    """Hledání tolerantní k mezerám — zdroj je plný nezlomitelných mezer a zalomení."""
    return re.compile(r"[\s\xa0]+".join(re.escape(p) for p in text.split()))


# Prvky, za jejichž konec se věší poznámka „Aktualizace 2026“: celý seznam
# (ne jeho položka), celá tabulka nebo box, jinak odstavec či nadpis.
_TAG_RE = re.compile(r"<(/?)(ul|ol|li|p|h2|h3|h4|table|figure|aside|details|dl|div)\b([^>]*)>")
_OUTER = ("ul", "ol", "figure", "aside", "dl")


def _note_anchor(page: str, at: int) -> tuple[int, str]:
    """
    Kam za nalezený text pověsit poznámku: vrací pozici hned za koncovou značkou
    prvku, který text obsahuje. Uvnitř seznamu je to konec nejvnějšího seznamu,
    uvnitř tabulky obal .table-wrap, uvnitř boxu konec boxu; jinak konec odstavce.
    """
    main = page.find('<main id="obsah"')
    stack: list[tuple[str, str]] = []
    for m in _TAG_RE.finditer(page, main, at):
        close, tag, attrs = m.group(1), m.group(2), m.group(3)
        if not close:
            stack.append((tag, attrs))
        else:
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == tag:
                    del stack[k:]
                    break
    target = None
    for tag, attrs in stack:                       # od nejvnějšího
        if tag in _OUTER or (tag == "div" and "table-wrap" in attrs):
            target = tag
            break
    if target is None:
        for tag, _attrs in reversed(stack):
            if tag in ("p", "h2", "h3", "h4"):
                target = tag
                break
    if target is None:
        return -1, ""
    depth = 0
    for m in _TAG_RE.finditer(page, at):
        if m.group(2) != target:
            continue
        if not m.group(1):
            depth += 1
        elif depth == 0:
            return m.end(), target
        else:
            depth -= 1
    return -1, target


def upd_note(body: str, odkaz: str | None = None, summary: str = "Aktualizace 2026") -> str:
    out = ['<details class="upd">', "  <summary>%s</summary>" % summary, '  <div class="upd-body">']
    out += ["    " + line for line in body.split("\n") if line.strip()]
    if odkaz:
        out.append('    <p><a href="pravni-aktualnost.html#%s">Podrobně v právní aktuálnosti →</a></p>' % odkaz)
    out += ["  </div>", "</details>"]
    return "\n".join(out)


def apply_fixes(n: int, page: str, fixes: list) -> tuple[str, list[str]]:
    """
    Opravy z doplňků, na hotové stránce, každá právě jednou.

    Dvojí zápis:
      * [hledaný text, náhrada(, důvod)] — jako u ostatních konvertorů; začíná-li
        náhrada hledaným textem, připojí se jen její zbytek.
      * {"najdi": …, "nahrad": …, "pozn": …, "proc": …, "odkaz": …} — `najdi`
        se (volitelně) nahradí `nahrad` a za konec odstavce, seznamu, tabulky
        nebo boxu, který text obsahuje, se pověsí rozbalovací poznámka
        „Aktualizace 2026“ s textem `pozn`. Poznámka tak nikdy nerozdělí
        odstavec — jinak by ho check_fidelity.py hlásil jako ztracený.
    Nenalezený nebo nejednoznačný text je chyba, ne tichá vynechávka.
    """
    problems = []
    for fx in fixes:
        if isinstance(fx, dict):
            find = fx["najdi"]
        else:
            find, repl = fx[0], _html(fx[1])
        pat = _ws_pattern(find)
        hits = list(pat.finditer(page))
        if not hits:
            problems.append("okruh %d: text pro opravu nenalezen — %r" % (n, find[:70]))
            continue
        if len(hits) > 1:
            problems.append("okruh %d: text pro opravu není jednoznačný (%d×) — %r"
                            % (n, len(hits), find[:70]))
            continue
        m = hits[0]
        if not isinstance(fx, dict):
            tail = repl[len(find):] if repl.startswith(find) else None
            page = page[:m.start()] + ((m.group(0) + tail) if tail is not None else repl) + page[m.end():]
            continue
        inline = fx.get("nahrad", m.group(0))
        page = page[:m.start()] + inline + page[m.end():]
        if fx.get("pozn"):
            at, target = _note_anchor(page, m.start())
            if at < 0:
                problems.append("okruh %d: nevím, kam pověsit poznámku k %r" % (n, find[:60]))
                continue
            note = upd_note(_html(fx["pozn"]), fx.get("odkaz"), fx.get("souhrn", "Aktualizace 2026"))
            page = page[:at] + "\n" + note + page[at:]
    return page, problems


def render_page(subject: str, n: int, okruh: str, prep: dict, dop: dict,
                prev, nxt, strucne: list[tuple[int, str, str]], words: int) -> tuple[str, list, list[str]]:
    label = SUBJECTS[subject]["label"]
    short = TITLES[subject][n][0]
    key = str(n)
    D._ids = {}
    D._ol_seen.clear()
    ctx = Ctx(prep["numfmt"], {}, {})
    problems: list[str] = []

    # obrázky: každý musí mít v doplňcích přepis, nebo výslovné vyřazení
    imgs = dop.get("images", {}).get(key, {})
    ctx.images = {rid: _html(v.get("html", "")) for rid, v in imgs.items()}
    used = {p["img"] for b in prep["body"] if b["kind"] == "p" for p in b["parts"] if p.get("img")}
    known = {p["img"] for b in prep["blocks"] if b["kind"] == "p" for p in b["parts"] if p.get("img")}
    for rid in sorted(used - set(imgs)):
        problems.append("okruh %d: obrázek %s nemá v doplňcích přepis ani důvod vyřazení" % (n, rid))
    for rid in sorted(set(imgs) - known):
        problems.append("okruh %d: přepis obrázku %s, který ve zdroji není" % (n, rid))

    body = split_images(prep["body"])
    encode_links(body)
    keys = dop.get("terms", {}).get(key, [])
    intro, secs = split_sections(body)

    out = topnav([("Státnice", "../index.html"), (label, "index.html"),
                  ("Okruh %02d · podrobně" % n, None)])
    out += [
        "",
        '<header class="qhead">',
        '  <div class="wrap">',
        '    <p class="eyebrow"><span class="qnum">%02d</span> %s · podrobné zápisky 2025 · '
        'okruh %d zadání</p>' % (n, label, n),
        "    <h1>%s</h1>" % esc(short),
        '    <p class="lead"><em>%s</em></p>' % esc(okruh),
        '    <div class="qtools">',
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
        '    <nav class="toc" aria-label="Obsah stránky"></nav>',
        "  </aside>",
        '  <main id="obsah" class="content">',
        "",
        '    <aside class="box link">',
        '      <h4><span class="bemo" aria-hidden="true">🔗</span>Podrobné zápisky k okruhu %d</h4>' % n,
    ]
    if strucne:
        links = ", ".join('<a href="%s">otázka %d — %s</a>' % (h, q, esc(t)) for q, h, t in strucne)
        out.append("      <p>Studentské zápisky z roku 2025 k okruhu %d zadání, převzaté bez krácení "
                   "(%s). Stručná verze téhož tématu: %s.</p>" % (n, words_label(words), links))
    else:
        out.append("      <p>Studentské zápisky z roku 2025 k okruhu %d zadání, převzaté bez krácení "
                   "(%s).</p>" % (n, words_label(words)))
    out += [
        '      <p>Opravené a doplněné právní údaje jsou <span class="fix">vyznačené oranžově</span> '
        's rozbalovací poznámkou „Aktualizace 2026“, přehled je v '
        '<a href="pravni-aktualnost.html#zapisky-2025">právní aktuálnosti</a>. Obrázky ze zápisků '
        'jsou přepsané do textu, zbytky z ChatGPT odstraněné. Literatura: '
        '<a href="literatura.html">seznam zdrojů k zápiskům</a>.</p>',
        "    </aside>",
    ]
    note = dop.get("notes", {}).get(key)
    if note:
        out += ["", _html(note)]
    out += key_section(keys)

    if intro:
        rendered = render_flow(intro, "      ", ctx)
        if rendered:
            out += ["", '    <section class="sec sec-read">'] + rendered + ["    </section>"]
    for h, sbody in secs:
        emo, htext = strip_emoji(h)
        out += ["", '    <section class="sec sec-%s">' % SEC_TYPES.get(emo, "read")]
        out.append('      <h2 id="%s">%s</h2>' % (D.ctx_id(ctx, htext), esc(htext)))
        out.extend(render_flow(sbody, "      ", ctx))
        out.append("    </section>")

    out += ["", '    <nav class="pager" aria-label="Další okruhy">']
    if prev:
        out.append('      <a class="pager-l" href="%s"><span>← Předchozí okruh</span>'
                   '<strong>%02d %s</strong></a>' % (prev[1], prev[0], esc(prev[2])))
    else:
        out.append('      <a class="pager-l" href="index.html#podrobne"><span>←</span>'
                   '<strong>Přehled okruhů</strong></a>')
    if nxt:
        out.append('      <a class="pager-r" href="%s"><span>Další okruh →</span>'
                   '<strong>%02d %s</strong></a>' % (nxt[1], nxt[0], esc(nxt[2])))
    else:
        out.append('      <a class="pager-r" href="literatura.html"><span>Dál →</span>'
                   '<strong>Literatura k zápiskům</strong></a>')
    out += ["    </nav>", "  </main>", "</div>", "", footer(label)]

    page = shell(
        title="Okruh %d: %s · %s podrobně · Státnice" % (n, short, label),
        desc="Podrobné zápisky k okruhu %d zadání státní závěrečné zkoušky z %s: %s"
             % (n, "etopedie" if subject == "etopedie" else "psychopedie", short),
        body="\n".join(out).split("\n"),
        subject=subject,
        kind="podrobne",
    )
    page = decode_links(page)
    if "\uE000" in page or "\uE001" in page:
        problems.append("okruh %d: rozbitý odkaz (značka zůstala ve stránce)" % n)
    page, probs = apply_fixes(n, page, dop.get("fixes", {}).get(key, []))
    problems += probs
    return page, keys, problems


# ------------------------------------------------------------------ odkazy do stávajících stránek

MARK_A, MARK_B = "<!-- podrobne:start -->", "<!-- podrobne:end -->"


def load_meta(subject: str) -> dict:
    path = os.path.join(HERE, "_meta_zapisky_%s.json" % subject)
    if not os.path.exists(path):
        return {}
    return json.load(open(path, encoding="utf-8"))


def crosslink_html(subject: str, q: int, meta: dict | None = None, ind: str = "    ") -> str:
    """
    Box „Podrobně ze zápisků 2025“ pro stručnou otázku q — nebo "", pokud
    k ní podrobná stránka není. Volá ho tento konvertor i docx2html_psychopedie.py,
    aby se odkaz neztratil, když se psychopedie přegeneruje.
    """
    meta = meta if meta is not None else load_meta(subject)
    rows = [(int(k), v) for k, v in sorted(meta.get("okruhy", {}).items(), key=lambda kv: int(kv[0]))
            if q in v.get("strucne", [])]
    if not rows:
        return ""
    links = ", ".join('<a href="%s">okruh %d — %s</a> (%s)' % (v["href"], k, esc(v["titulek"]),
                                                               words_label(v["slov"]))
                      for k, v in rows)
    return "\n".join([
        ind + MARK_A,
        ind + '<aside class="box link">',
        ind + '  <h4><span class="bemo" aria-hidden="true">🔗</span>Podrobně ze zápisků 2025</h4>',
        ind + "  <p>K tématu této otázky jsou na webu i podrobné studentské zápisky podle "
              "oficiálního zadání: %s.</p>" % links,
        ind + "</aside>",
        ind + MARK_B,
    ])


def _replace_marked(text: str, block: str, anchor_re: str, where: str) -> str:
    """Nahradí blok mezi značkami, nebo ho vloží za první shodu anchor_re."""
    pat = re.compile(r"[ \t]*" + re.escape(MARK_A) + r".*?" + re.escape(MARK_B) + r"\n?", re.S)
    if pat.search(text):
        return pat.sub(lambda m: (block + "\n") if block else "", text, count=1)
    if not block:
        return text
    m = re.search(anchor_re, text)
    if not m:
        raise SystemExit("%s: nenašel jsem místo pro vložení odkazů (%s)" % (where, anchor_re))
    return text[:m.end()] + "\n" + block + "\n" + text[m.end():]


def index_section(subject: str, meta: dict) -> str:
    rows = []
    for k, v in sorted(meta["okruhy"].items(), key=lambda kv: int(kv[0])):
        st = v.get("strucne", [])
        sub = ("→ stručně: otázk%s %s · " % ("a" if len(st) == 1 else "y", ", ".join(map(str, st)))
               if st else "") + words_label(v["slov"])
        rows += [
            '      <a class="qrow" href="%s">' % v["href"],
            '        <span class="qrow-num">%02d</span>' % int(k),
            '        <span class="qrow-t"><span class="qrow-title">%s</span>' % esc(v["titulek"]),
            '          <span class="qrow-sub">%s</span></span>' % sub,
            '        <span class="qrow-state">okruh %d</span>' % int(k),
            "      </a>",
        ]
    total = sum(v["slov"] for v in meta["okruhy"].values())
    return "\n".join([
        "  " + MARK_A,
        '  <section id="podrobne" style="padding-top:44px;padding-bottom:20px">',
        '    <h2 class="sec-label">Podrobně podle zadání — zápisky 2025</h2>',
        '    <p style="max-width:62ch;color:var(--text-dim);font-size:15px;margin:-6px 0 18px">'
        "Studentské zápisky z roku 2025, jeden dokument na každý ze 17 okruhů oficiálního zadání — "
        "dohromady %s, tedy mnohem víc než stručné otázky výš. Právní údaje jsou "
        '<a href="pravni-aktualnost.html#zapisky-2025">ověřené k 10/2026</a>, zdroje jsou v '
        '<a href="literatura.html">literatuře k zápiskům</a>.</p>' % words_label(total),
        '    <div class="qlist">',
    ] + rows + [
        "    </div>",
        "  </section>",
        "  " + MARK_B,
    ])


def _src_label(url: str) -> str:
    m = re.search(r"e-sbirka\.gov\.cz/(sb|sm)/(\d{4})/(\d+)", url)
    if m:
        return "%s/%s Sb.%s" % (m.group(3), m.group(2), " m. s." if m.group(1) == "sm" else "")
    if "icd.who.int" in url:
        return "MKN-11 (WHO)"
    if "edu.gov.cz" in url:
        return "edu.gov.cz"
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0]


def audit_section(subject: str, dop: dict, meta: dict) -> str:
    """
    Oddíl „Podrobné zápisky 2025“ na stránce pravni-aktualnost.html. Tabulka se
    skládá z oprav v doplňcích, které mají `bylo`/`plati`/`zdroj` — stránka
    tak nemůže zestárnout proti tomu, co je skutečně opravené v zápiscích.
    """
    rows, n_all, n_inline = [], 0, 0
    for k in sorted(dop.get("fixes", {}), key=int):
        for fx in dop["fixes"][k]:
            if not isinstance(fx, dict):
                continue
            n_all += 1
            n_inline += "nahrad" in fx
            if not fx.get("bylo"):
                continue
            href = meta["okruhy"][k]["href"]
            src = " · ".join('<a href="%s" rel="noopener">%s</a>' % (html.escape(u, quote=True), esc(_src_label(u)))
                             for u in fx.get("zdroj", []))
            rows += ["          <tr>",
                     '            <td data-label="Okruh"><a href="%s">%s</a></td>' % (href, k),
                     '            <td data-label="V zápiscích">%s</td>' % esc(fx["bylo"]),
                     '            <td data-label="Platný stav (10/2026)">%s</td>' % esc(fx["plati"]),
                     '            <td data-label="Ověřeno">%s</td>' % src,
                     "          </tr>"]
    pills = sum(1 for v in meta["okruhy"].values() for e in v["uklid"] if e["co"].startswith("citační"))
    dropped = sum(1 for v in meta["okruhy"].values() for i, why in v["vyrazeno"] if "titulek" not in why)
    label = SUBJECTS[subject]["label"].lower()
    return "\n".join([
        "    " + MARK_A,
        '    <section class="sec sec-law">',
        '      <h2 id="zapisky-2025">Podrobné zápisky 2025 — co bylo opraveno</h2>',
        "      <p>Studentské zápisky z roku 2025 k 17 okruhům zadání (<a href=\"index.html#podrobne\">podrobné stránky</a>) "
        "prošly stejnou kontrolou jako stručné otázky: každý odkaz na zákon, vyhlášku, metodický pokyn a klasifikaci "
        "byl porovnán s platným zněním na <a href=\"https://e-sbirka.gov.cz\" rel=\"noopener\">e-Sbírce</a> "
        "(stav k 31. 10. 2026), u metodik MŠMT na edu.gov.cz a u klasifikací v MKN-11 WHO.</p>",
        "      <p>V textu je <strong>%d poznámek „Aktualizace 2026“</strong>, z toho %d opravuje přímo údaj v textu "
        "(<span class=\"fix\">oranžově</span>); původní znění je vždy citované v poznámce. Tabulka uvádí ty, které se "
        "týkají předpisů a institucí; poznámky ke klasifikacím, terminologii a faktům jsou přímo u textu. Navíc bylo "
        "odstraněno %d citačních odkazů ChatGPT a %d bloků vložených konverzací nebo osobních údajů.</p>" % (
            n_all, n_inline, pills, dropped),
        '      <div class="table-wrap">',
        "        <table>",
        "          <thead><tr><th>Okruh</th><th>V zápiscích</th><th>Platný stav (10/2026)</th><th>Ověřeno</th></tr></thead>",
        "          <tbody>",
    ] + rows + [
        "          </tbody>",
        "        </table>",
        "      </div>",
        '      <aside class="box tip">',
        '        <h4><span class="bemo" aria-hidden="true">💡</span>Jak s tím pracovat</h4>',
        "        <p>Zápisky z %s jsou podrobné, ale psané z různých zdrojů a místy s pomocí umělé inteligence. "
        "U zákonů vždy platí číslo a název z tabulky výš; když si nejste jistá, řekněte „ve znění pozdějších předpisů“.</p>" % label,
        "      </aside>",
        "    </section>",
        "    " + MARK_B,
    ])


def update_existing(subject: str, meta: dict, dop: dict | None = None) -> list[str]:
    """Odkazy z přehledu předmětu a ze stručných otázek na podrobné stránky."""
    changed = []
    if dop is not None:
        path = os.path.join(subject, "pravni-aktualnost.html")
        text = open(path, encoding="utf-8").read()
        new = _replace_marked(text, audit_section(subject, dop, meta), r"\n(?=\s*<nav class=\"pager\")", path)
        if new != text:
            open(path, "w", encoding="utf-8").write(new)
            changed.append(path)
    idx = os.path.join(subject, "index.html")
    text = open(idx, encoding="utf-8").read()
    new = _replace_marked(text, index_section(subject, meta), r"\n(?=</main>)", idx)
    if new != text:
        open(idx, "w", encoding="utf-8").write(new)
        changed.append(idx)
    for q, (fname, _t) in sorted(question_titles(subject).items()):
        path = os.path.join(subject, fname)
        text = open(path, encoding="utf-8").read()
        new = _replace_marked(text, crosslink_html(subject, q, meta),
                              r'<main id="obsah" class="content">', path)
        if new != text:
            open(path, "w", encoding="utf-8").write(new)
            changed.append(path)
    return changed


# ------------------------------------------------------------------ literatura
#
# Seznam zdrojů, který k zápiskům patří (Eto: „Zdroje- etopedie .docx“,
# Psychopedie: „ZDROJE SZZ PSYCHOPEDIE.docx“). Položky se převádějí tak, jak
# jsou, jen se z adres odstraní prefix prohlížeče PDF a sledovací parametry.
# Opravy (dohledané adresy, poznámky, štítky) jsou v `literatura` v doplňcích.

ZDROJE = {"etopedie": "Zdroje- etopedie .docx", "psychopedie": "ZDROJE SZZ PSYCHOPEDIE.docx"}
CAPS_NAME = re.compile(r"\b([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{3,}(?:-[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{2,})?),")
URL_RE = re.compile(r"(https?://[^\s<>\"]+?)(?=[.,;)\]]?(?:\s|$|<))")


def href_attr(url_html: str) -> str:
    """Adresa z textu → hodnota atributu href: bez prefixu prohlížeče, s procentovým kódováním."""
    u = clean_url(html.unescape(url_html))
    return html.escape(urllib.parse.quote(urllib.parse.unquote(u), safe=":/?&=#%~+,;@!$'()*"), quote=True)


def read_zdroje(subject: str, src_dir: str) -> list[dict]:
    path = os.path.join(src_dir, ZDROJE[subject])
    blocks, _numfmt, names = parse_document_full(path)
    normalize_styles(blocks, names)
    out = []
    for i, b in enumerate(blocks):
        if b["kind"] != "p":
            continue
        t = flat(ptext(b))
        if not t or t.upper() in ("ETOPEDIE", "PSYCHOPEDIE"):
            continue
        out.append({"idx": i, "block": b, "text": t})
    return out


def _surname_forms(s: str) -> list[str]:
    """Pár pádových tvarů příjmení — stačí na zmínky typu „podle Kaleji“."""
    if s.endswith("ová"):
        return [s, s[:-1] + "é", s[:-1] + "ou"]
    if s.endswith("a"):
        return [s, s[:-1] + "y", s[:-1] + "e", s[:-1] + "ou", s[:-1] + "i", s[:-1] + "u"]
    return [s, s + "a", s + "ovi", s + "em", s + "e", s + "ův", s + "ova", s + "ovy"]


CAPS_GIVEN_FIRST = re.compile(r"\ba [A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+ ([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{3,})\b")
# konec autorské části: tečka za křestním jménem nebo za rokem, ne za iniciálou
AUTHORS_END = re.compile(r"(?<=[a-záčďéěíňóřšťúůýž0-9])\.\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ0-9])")


def authors_segment(block: dict) -> str:
    """Autorská část položky: před první kurzívou (název), jinak do první tečky za jménem."""
    head = []
    for p in block["parts"]:
        if p.get("i") and p.get("t", "").strip():
            return "".join(head)
        head.append(p.get("t", ""))
    text = flat("".join(head))
    m = AUTHORS_END.search(text)
    return text[:m.start()] if m else text


def _cite_label(entry: str, authors: str, override: str | None) -> tuple[str, list[str]]:
    """„Kaleja, 2013“ + seznam příjmení (pro hledání zmínek v okruzích)."""
    names = CAPS_NAME.findall(authors + ",") + CAPS_GIVEN_FIRST.findall(authors)
    names = [n[0] + n[1:].lower() for n in names]
    if override:
        return override, names
    body = re.sub(r"\[cit\.[^\]]*\]|https?://\S+|ISBN[\s\d-]+", "", entry)
    year = re.search(r"\b(19|20)\d{2}\b", body)
    y = year.group(0) if year else "b. d."
    if not names:
        return "%s, %s" % (entry.split(".")[0], y), names
    if len(names) == 1:
        who = names[0]
    elif len(names) <= 3:
        who = ", ".join(names[:-1]) + " a " + names[-1]
    else:
        who = names[0] + " a kol."
    return "%s, %s" % (who, y), names


def literatura_page(subject: str, src_dir: str, dop: dict, meta: dict) -> tuple[str, int, list[str]]:
    label = SUBJECTS[subject]["label"]
    cfg = dop.get("literatura", {})
    entries = read_zdroje(subject, src_dir)
    problems = []
    texts = {}
    for k, v in meta["okruhy"].items():
        path = os.path.join(subject, v["href"])
        page = open(path, encoding="utf-8").read()
        texts[int(k)] = html.unescape(re.sub(r"<[^>]+>", " ", page))

    items, seen = [], {}
    for e in entries:
        o = cfg.get(str(e["idx"]), {})
        lab, names = _cite_label(e["text"], authors_segment(e["block"]), o.get("stitek"))
        n = seen.get(lab, 0)
        seen[lab] = n + 1
        items.append((e, o, lab, names))
    # stejný štítek dvakrát (Kaleja, 2013) → 2013a, 2013b
    dup = {lab for lab, c in seen.items() if c > 1}
    order: dict[str, int] = {}
    out_items = []
    for e, o, lab, names in items:
        if lab in dup:
            order[lab] = order.get(lab, 0) + 1
            lab = lab + "abcdefgh"[order[lab] - 1]
        # text položky: kurzíva z Wordu, adresy bez prefixu prohlížeče a utm
        parts = []
        for p in merge_runs(e["block"]["parts"]):
            t = p.get("t")
            if not t:
                continue
            s = esc(t)
            if p.get("i"):
                s = "<em>%s</em>" % s
            parts.append(s)
        body = re.sub(r"</em><em>", "", "".join(parts)).strip()
        body = clean_text(re.sub(r"\s+", " ", body))
        if o.get("text"):
            body = o["text"]
        body = URL_RE.sub(lambda m: '<a href="%s" rel="noopener">%s</a>' % (href_attr(m.group(1)), m.group(1)), body)
        if o.get("url"):
            body += ' <span class="fix">Dostupné z: <a href="%s" rel="noopener">%s</a></span>' % (
                o["url"], esc(o.get("url_text", o["url"])))
        notes = []
        if o.get("pozn"):
            notes.append(o["pozn"])
        hits = []
        if names:
            pat = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(f) for nm in names for f in _surname_forms(nm)))
            hits = [k for k in sorted(texts) if pat.search(texts[k])]
        for kw in o.get("hledat", []):
            hits = sorted(set(hits) | {k for k in texts if kw in texts[k]})
        if hits:
            links = ", ".join('<a href="%s">%d</a>' % (meta["okruhy"][str(k)]["href"], k) for k in hits)
            notes.insert(0, "Jméno autora nebo název se objevuje v okruzích %s" % links)
        dd = body + "".join('<br><span class="src-pages">%s</span>' % x for x in notes)
        gid = "d-" + D.slugify(lab, 48)
        out_items.append((lab, gid, dd))
    for k in cfg:
        if not any(str(e["idx"]) == k for e in entries):
            problems.append("literatura: oprava pro blok %s, který v seznamu není" % k)

    rows = []
    for lab, gid, dd in out_items:
        rows += ['        <div class="gitem" id="%s">' % gid,
                 "          <dt>%s</dt>" % esc(lab),
                 "          <dd>%s</dd>" % dd,
                 "        </div>"]
    note = _html(dop.get("literatura_uvod", ""))
    body = topnav([("Státnice", "../index.html"), (label, "index.html"), ("Literatura k zápiskům", None)])
    body += [
        "",
        '<header class="qhead qhead-plain">',
        '  <div class="wrap">',
        '    <p class="eyebrow">Zdroje · %s · podrobné zápisky 2025</p>' % label,
        "    <h1>Literatura k podrobným zápiskům</h1>",
        '    <p class="lead">%d zdrojů ze seznamu, který ke studentským zápiskům patří. '
        'U každého je odkaz na okruhy, kde se autor nebo název objevuje.</p>' % len(out_items),
        "  </div>",
        "</header>",
        "",
        '<div class="wrap layout">',
        '  <aside class="side"><nav class="toc" aria-label="Obsah stránky"></nav></aside>',
        '  <main id="obsah" class="content">',
        "",
        note,
        "",
        '    <section class="sec sec-read">',
        '      <h2 id="seznam-zdroju">Seznam zdrojů <span class="h-count">%d</span></h2>' % len(out_items),
        '      <dl class="glist">',
    ] + rows + [
        "      </dl>",
        "    </section>",
        "",
        '    <nav class="pager" aria-label="Další stránky">',
        '      <a class="pager-l" href="index.html#podrobne"><span>←</span><strong>Přehled okruhů</strong></a>',
        '      <a class="pager-r" href="%s"><span>Dál →</span><strong>Okruh 1 podrobně</strong></a>'
        % meta["okruhy"]["1"]["href"],
        "    </nav>",
        "  </main>",
        "</div>",
        "",
        footer(label),
    ]
    page = shell(title="Literatura k zápiskům · %s · Státnice" % label,
                 desc="Seznam zdrojů ke studentským zápiskům 2025 z %s, s odkazy na okruhy zadání."
                      % ("etopedie" if subject == "etopedie" else "psychopedie"),
                 body=body, subject=subject, kind="literatura")
    return page, len(out_items), problems


# ------------------------------------------------------------------ build

def build(subject: str, src_dir: str, force: bool) -> int:
    label = SUBJECTS[subject]["label"]
    existing = glob.glob(os.path.join(subject, "podrobne-okruh-*.html"))
    if existing and not force:
        print("V %s/ už je %d podrobných stránek — bez --force nepřepisuji." % (subject, len(existing)))
        return 2
    dop = load_doplnky(subject)
    sources = find_sources(subject, src_dir)
    zadani = read_zadani(subject, src_dir)
    smap = strucne_map(subject)
    qt = question_titles(subject)
    print("%s: %d zápisků, zadání se 17 okruhy, doplňky: %d oprav, %d přepsaných obrázků, "
          "pojmy u %d okruhů" % (
              subject, len(sources), sum(len(v) for v in dop.get("fixes", {}).values()),
              sum(len(v) for v in dop.get("images", {}).values()), len(dop.get("terms", {}))))

    for old in existing:
        os.remove(old)

    meta = {"zdroj": src_dir, "okruhy": {}}
    problems: list[str] = []
    nums = sorted(sources)
    total_keys = 0
    for k, n in enumerate(nums):
        prep = prepare(subject, n, sources[n], dop, zadani[n])
        problems += prep["problems"]
        words = sum(len(t.split()) for _i, t in units_of(prep["body"]))
        prev = (nums[k - 1], href_of(subject, nums[k - 1]), TITLES[subject][nums[k - 1]][0]) if k else None
        nxt = ((nums[k + 1], href_of(subject, nums[k + 1]), TITLES[subject][nums[k + 1]][0])
               if k + 1 < len(nums) else None)
        strucne = [(q, qt[q][0], qt[q][1]) for q in smap.get(n, []) if q in qt]
        page, keys, probs = render_page(subject, n, zadani[n], prep, dop, prev, nxt, strucne, words)
        problems += probs
        open(os.path.join(subject, href_of(subject, n)), "w", encoding="utf-8").write(page)
        total_keys += len(keys)
        nh = len(re.findall(r"<h[23] id=", page))
        meta["okruhy"][str(n)] = {
            "soubor": unicodedata.normalize("NFC", os.path.basename(sources[n])),
            "href": href_of(subject, n),
            "titulek": TITLES[subject][n][0],
            "zadani": zadani[n],
            "strucne": smap.get(n, []),
            "slov": words,
            "bloku": len(prep["blocks"]),
            "nadpisu": nh,
            "pojmu": len(keys),
            "vyrazeno": [[i, why] for i, why in sorted(prep["dropped"].items())],
            "obrazky": {rid: v.get("co", "") for rid, v in dop.get("images", {}).get(str(n), {}).items()},
            "uklid": prep["log"],
        }
        if nh < 2:
            problems.append("okruh %d: méně než dva nadpisy — obsah v levém sloupci bude prázdný" % n)

    json.dump(meta, open(os.path.join(HERE, "_meta_zapisky_%s.json" % subject), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    lit, nlit, probs = literatura_page(subject, src_dir, dop, meta)
    problems += probs
    open(os.path.join(subject, "literatura.html"), "w", encoding="utf-8").write(lit)
    print("  literatura.html: %d zdrojů" % nlit)
    changed = update_existing(subject, meta, dop)
    pills = sum(1 for v in meta["okruhy"].values() for e in v["uklid"] if e["co"].startswith("citační"))
    print("  zapsáno %d stránek, klíčových pojmů %d, citačních odkazů ChatGPT zahozeno %d, "
          "vyřazených bloků %d" % (len(nums), total_keys, pills,
                                   sum(len(v["vyrazeno"]) for v in meta["okruhy"].values())))
    print("  odkazy na podrobné stránky aktualizovány v %d souborech" % len(changed))
    if problems:
        print("  ! PROBLÉMY:")
        for p in problems:
            print("    %s" % p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
