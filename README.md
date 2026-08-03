# Státnice — studijní web

Statický web se studijními materiály ke státní závěrečné zkoušce ze speciální pedagogiky.
Bez frameworku, bez build kroku, bez serveru — jen HTML, jedno CSS a jeden JS.

Obsahuje dva předměty:

| Předmět | Otázek | Kartiček | Navíc |
|---|---|---|---|
| **Etopedie** | 20 | 191 | glosář 105 pojmů, klíčové zákony, právní audit |
| **Psychologie** | 19 (18 vypracovaných) | 56 | přehled 43 citovaných děl, kontrola aktuálnosti |

Hledání i kartičky fungují napříč oběma předměty.

## Spuštění

Nejjednodušší je otevřít `index.html` dvojklikem — web funguje i přes `file://`
(nepoužívá `fetch()`, takže se nic nerozbije).

S lokálním serverem (hezčí adresy, jinak stejné):

```bash
python3 -m http.server 8000
# → http://localhost:8000
```

## Struktura

```
index.html            rozcestník předmětů
assets/
  style.css           celý design systém (tmavý i světlý režim, boxy, tisk)
  app.js              hledání, kartičky, postup, obsah stránky, filtr glosáře
  data.js             GENEROVANÝ index pro hledání a kartičky
etopedie/
  index.html          přehled 20 otázek + ukazatel postupu
  otazka-01-….html    jednotlivé otázky
  glosar.html         abecední rejstřík s filtrem
  zakony.html         klíčové zákony (opravené, stav 08/2026)
  pravni-aktualnost.html   co bylo opraveno proti zdroji a proč
  aktualizace-2026.html    aktualizační dodatek ze zdroje (MKN-11, novely)
  karticky.html       výběr balíčků kartiček
  jak-pracovat.html   úvod ze zdrojového dokumentu
psychologie/
  index.html          přehled 19 otázek + ukazatel postupu
  otazka-01-….html    jednotlivé otázky
  otazka-17-….html    stub — otázka ve zdroji není vypracovaná
  literatura.html     43 citovaných děl s dohledanými údaji
  aktualnost.html     co se od 2021/2022 změnilo
  img/                obrázky ze zdrojového dokumentu
source/               archivovaný originál .docx
tools/                pomocné skripty (viz níže)
```

## Úprava obsahu

**Zdrojem pravdy je HTML v adresáři `etopedie/`.** Upravujte přímo tyto soubory —
jsou odsazené a čitelné, žádný build se nekoná.

Po každé úpravě obsahu přegenerujte index pro hledání a kartičky:

```bash
python3 tools/reindex.py
```

Skript čte **hotové HTML**, ne `.docx`, takže vaše ruční úpravy zůstanou zachovány.

### Konvence, na kterých závisí funkce webu

| Co | Kde se to používá |
|---|---|
| `<body data-subject="…" data-kind="…" data-up="…">` | `data-up` je cesta ke korenu (`../` nebo prázdno) — bez ní nefungují odkazy z hledání |
| `<h2 id="…">`, `<h3 id="…">` | z nadpisů s `id` se skládá obsah stránky v levém sloupci |
| `<section class="sec sec-key">` | sekce „🔑 Klíčové pojmy“ — z jejích `<li>` se dělají kartičky |
| `<li>Pojem — definice</li>` | oddělovač je pomlčka „—“ (em dash); před ní pojem, za ní definice |
| `<aside class="box sum\|key\|law\|tip\|warn\|link\|src">` | barevné boxy 📌 🔑 ⚖️ 💡 ⚠️ 🔗 📚 |
| `<p class="defn">= …</p>` | definice uvozená „=“ (zápis z psychologických poznámek) |
| `<figure class="fig">` | obrázek s popiskem |
| `<details class="upd">` | poznámka „Aktualizace 2026“; do kartiček ani nadpisů se nepočítá |
| `<span class="fix">` | oranžové zvýraznění opraveného údaje |
| `<td data-label="…">` | název sloupce, který se na mobilu zobrazí u hodnoty |

## Přidání dalšího předmětu

1. Vytvořte adresář, např. `psychopedie/`, a v něm `index.html` a stránky otázek.
   Nejsnáz zkopírováním souboru z `etopedie/` a přepsáním obsahu.
2. V `assets/style.css` přidejte barvu akcentu:
   ```css
   body[data-subject='psychopedie'] { --subject: var(--c-law); }
   ```
3. V `index.html` v korenu nahraďte dlaždici „Připravujeme“ odkazem na nový předmět.
4. Spusťte `python3 tools/reindex.py` — hledání i kartičky předmět rovnou pojmou.

### Import z Wordu

Konvertory jsou dva, protože oba zdrojové dokumenty měly úplně jinou strukturu:

| Skript | Pro dokument, který… |
|---|---|
| `tools/docx2html.py` | používá styly Heading 1/2/3 a tabulky 1×1 jako barevné boxy s emoji (etopedie) |
| `tools/docx2html_psy.py` | nadpisové styly nepoužívá, podnadpisy jsou tučné odstavce, hranice otázek se poznají z obsahu (psychologie) |

```bash
python3 tools/docx2html.py source/nazev.docx psychopedie
python3 tools/docx2html_psy.py 'SZO NAZEV.docx' psychopedie
```

> Oba skripty **odmítnou přepsat** existující stránky. Pokud to opravdu chcete
> (a smíříte se se ztrátou ručních úprav), přidejte `--force`.

Nový dokument bude nejspíš strukturovaný ještě jinak — než začnete, vyplatí se
zjistit, co v něm vlastně je: kolik nadpisových stylů se používá, jak jsou
oddělené otázky a čím jsou vyznačené podnadpisy.

## Kontroly

```bash
python3 tools/check_links.py      # vnitřní odkazy a kotvy vedou někam
python3 tools/reindex.py          # přegenerování assets/data.js

# ze .docx se neztratil žádný text — pro každý předmět zvlášť
python3 tools/check_fidelity.py
python3 tools/check_fidelity.py --map tools/_meta_psychologie.json \
        'SZO PSYCHOLOGIE.docx' psychologie
```

> **Pozor:** zdrojový `.docx` není součástí repozitáře (viz `.gitignore`).
> Z čistého klonu proto nejdou spustit `docx2html.py` ani `check_fidelity.py` —
> potřebují dokument v `source/`. `reindex.py` a `check_links.py` fungují vždy,
> protože pracují jen s HTML.

`check_fidelity.py` porovnává každý odstavec a každou buňku tabulky ze `.docx`
s vygenerovanými stránkami. Vědomé právní opravy jsou vypsané v
`tools/_corrections.txt`, aby je kontrola nehlásila jako ztracený obsah.

## Klávesové zkratky

| Klávesa | Akce |
|---|---|
| `/` nebo `Ctrl`/`⌘` + `K` | hledání |
| `K` | kartičky z otevřené otázky |
| `mezerník` | odkrytí definice na kartičce |
| `←` / `→` | neumím / umím |
| `Esc` | zavřít |

Postup učení a volba světlého/tmavého režimu se ukládají do `localStorage`
prohlížeče — jsou tedy vázané na zařízení, nikam se neposílají.

## Publikování na GitHub Pages

1. Nahrajte repozitář na GitHub.
2. **Settings → Pages → Build and deployment**: *Deploy from a branch*,
   branch `main`, folder `/ (root)`.
3. Web bude na `https://<uživatel>.github.io/<repozitář>/`.

Soubor `.nojekyll` v korenu už je připravený — brání tomu, aby GitHub obsah
zpracovával Jekyllem. Všechny odkazy jsou relativní, takže funguje i v podadresáři.

## Aktuálnost obsahu

Oba materiály byly zkontrolovány proti stavu k **srpnu 2026**. Opravy a doplnění
jsou vyznačené přímo v textu (oranžově `<span class="fix">`, s rozbalovací
poznámkou „Aktualizace 2026“) a zdokumentované na samostatných stránkách.

**Etopedie** — `etopedie/pravni-aktualnost.html`. Zdroj měl vlastní dodatek
k dubnu 2026, ale i tak se našly dvě chybná čísla předpisů (Úmluva o právech
dítěte, poradenské služby) a chybějící deinstitucionalizační novely 363/2021
a 242/2024 Sb. Celkem 11 zjištění.

**Psychologie** — `psychologie/aktualnost.html`. Dokument je z roku 2021/2022
a žádná datovatelná tvrzení neobsahuje (necituje MKN, DSM, RVP ani žádný
předpis), takže nebylo co opravovat. Doplněny jsou čtyři oblasti, kde se od té
doby stav změnil: MKN-11, DSM-5-TR, revize RVP ZV a novely vyhlášek.

Legislativa se mění rychle a několik změn má odloženou účinnost na 2027 a 2028.
Před zkouškou se vyplatí rychlá kontrola na
[e-sbirka.gov.cz](https://e-sbirka.gov.cz), [msmt.gov.cz](https://msmt.gov.cz),
[edu.gov.cz](https://edu.gov.cz) a [zakonyprolidi.cz](https://www.zakonyprolidi.cz).
