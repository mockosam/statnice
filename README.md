# Státnice — studijní web

Statický web se studijními materiály ke státní závěrečné zkoušce ze speciální pedagogiky.
Bez frameworku, bez build kroku, bez serveru — jen HTML, jedno CSS a jeden JS.

Obsahuje čtyři předměty:

| Předmět | Otázek | Kartiček z otázek | Balíček předmětu | Glosář | Navíc |
|---|---|---|---|---|---|
| **Poradenství** (SP – poradenství, intervence a diagnostika) | 20 | 175 | 175 | 173 pojmů | klíčové zákony, právní audit se 14 zjištěními |
| **Pedagogika** | 20 | 216 | 216 | 215 pojmů | klíčové zákony, právní audit se 16 zjištěními, mapování na 17 okruhů zadání |
| **Etopedie** | 20 | 86 | 151 | 105 pojmů | klíčové zákony, právní audit, aktualizační dodatek |
| **Psychologie** | 19 | 67 | 67 | 50 pojmů | přehled 43 citovaných děl, kontrola aktuálnosti |

„Balíček předmětu“ spojuje kartičky z otázek s glosářem, ale **stejný pojem bere
jen jednou** — proto se nerovná součtu. U psychologie, poradenství a pedagogiky
jsou obě čísla prakticky shodná, protože jejich glosář je z těch definic sestavený.
Balíček přes všechny předměty má po odečtení duplicit **591 kartiček**.

Počty se na stránkách dopočítávají za běhu z `assets/data.js` (atribut
`data-count-for`), takže zestarat nemohou; čísla v HTML jsou jen záloha pro případ
vypnutého JavaScriptu a v této tabulce je potřeba je opravit ručně.

Hledání prochází všechny předměty; kartičky a glosář se drží předmětu, na kterém jste.

Glosáře mají různý původ: etopedie ho má **ze zdrojového dokumentu** (samostatná
kapitola se 105 hesly), psychologie, poradenství ani pedagogika ho ve zdroji
nemají — jejich rejstřík je **sestavený z definic v textu otázek** skriptem
`tools/make_glosar.py`.

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
  otazka-17-….html    ve zdroji není vypracovaná — dopsáno z literatury
  glosar.html         GENEROVANÝ rejstřík (make_glosar.py)
  karticky.html       výběr balíčků kartiček
  literatura.html     43 citovaných děl s dohledanými údaji
  aktualnost.html     co se od 2021/2022 změnilo
  img/                obrázky ze zdrojového dokumentu
poradenstvi/
  index.html          přehled 20 otázek + ukazatel postupu
  otazka-01-….html    jednotlivé otázky
  glosar.html         GENEROVANÝ rejstřík (make_glosar.py)
  karticky.html       výběr balíčků kartiček
  zakony.html         klíčové zákony ve znění k 08/2026 + tabulka zrušených předpisů
  pravni-aktualnost.html   14 zjištění + porovnání se zadáním A21
  img/                tři audiogramy ze zdroje (jediné publikovatelné obrázky)
pedagogika/
  index.html          přehled 20 otázek + ukazatel postupu
  otazka-01-….html    jednotlivé otázky
  glosar.html         GENEROVANÝ rejstřík (make_glosar.py)
  karticky.html       výběr balíčků kartiček
  zakony.html         klíčové zákony ve znění k 08/2026 + tabulka zrušených předpisů
  pravni-aktualnost.html   16 zjištění + mapa 20 stránek na 17 okruhů zadání
  (bez img/ — ze 14 obrázků ve zdroji není publikovatelný ani jeden, viz níže)
source/               archivovaný originál .docx
tools/                pomocné skripty (viz níže)
```

## Úprava obsahu

**Zdrojem pravdy je HTML v adresáři `etopedie/`.** Upravujte přímo tyto soubory —
jsou odsazené a čitelné, žádný build se nekoná.

Po každé úpravě obsahu přegenerujte index pro hledání a kartičky:

```bash
python3 tools/reindex.py
python3 tools/make_glosar.py --all   # jen když jste měnili klíčové pojmy
python3 tools/reindex.py             # znovu — glosáře taky přispívají kartičkami
```

Oba skripty čtou **hotové HTML**, ne `.docx`, takže vaše ruční úpravy zůstanou
zachovány. Výjimka: `psychologie/glosar.html` a `poradenstvi/glosar.html` jsou
generované — ruční úpravy v nich `make_glosar.py` přepíše. Chcete-li heslo vyřadit
nebo přejmenovat, upravte definici v příslušné otázce, případně filtr `SKIP_RE`
ve skriptu.

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
3. V `index.html` v korenu nahraďte dlaždici „Připravujeme“ odkazem na nový předmět
   a opravte čísla v hlavičce (počet předmětů, otázek, pojmů).
4. Má-li mít předmět generovaný glosář, přidejte ho do `SUBJECTS` v `tools/make_glosar.py`.
5. Spusťte `python3 tools/reindex.py` — hledání i kartičky předmět rovnou pojmou.

### Import z Wordu

Konvertory jsou čtyři, protože každý zdrojový dokument byl strukturovaný jinak.
Vykreslování (inline formátování, seznamy, tabulky, šablona stránky) mají společné —
pozdější skripty ho importují z `docx2html.py`, takže všechny předměty
vypadají stejně.

| Skript | Pro dokument, který… |
|---|---|
| `tools/docx2html.py` | používá styly Heading 1/2/3 a tabulky 1×1 jako barevné boxy s emoji (etopedie) |
| `tools/docx2html_psy.py` | nadpisové styly nepoužívá, podnadpisy jsou tučné odstavce, hranice otázek se poznají z obsahu (psychologie) |
| `tools/docx2html_spec.py` | nadpisové styly používá, ale `Nadpis1` slouží zároveň jako nadpis otázky i sekce; hranice otázek jsou proto v ověřované mapě `QSTART` (poradenství) |
| `tools/docx2html_ped.py` | totéž jako `_spec`, ale obsah je pole (perex se bere z nadpisu), jedna tabulka má titulkový řádek přes celou šířku a **žádný obrázek se nepublikuje** (pedagogika) |

```bash
python3 tools/docx2html.py source/nazev.docx psychopedie
python3 tools/docx2html_psy.py 'SZO NAZEV.docx' psychopedie
python3 tools/docx2html_spec.py 'SZO SPECIÁLNÍ PEDAGOGIKA.DOCX' poradenstvi
python3 tools/docx2html_ped.py 'SZZ- Padagogika (komplet).DOCX' pedagogika
```

> Všechny čtyři skripty **odmítnou přepsat** existující stránky. Pokud to opravdu
> chcete (a smíříte se se ztrátou ručních úprav), přidejte `--force`.

Nový dokument bude nejspíš strukturovaný ještě jinak — než začnete, vyplatí se
zjistit, co v něm vlastně je: kolik nadpisových stylů se používá, jak jsou
oddělené otázky a čím jsou vyznačené podnadpisy.

#### Jak konvertory poradenství a pedagogiky drží ruční opravy

`docx2html_spec.py` a `docx2html_ped.py` se dají spustit znovu bez ztráty
právních oprav — ty nejsou v HTML, ale v `tools/_doplnky_poradenstvi.json`,
resp. `tools/_doplnky_pedagogika.json`:

* `fixes` — dvojice *hledaný text → čím se nahradí*, aplikované na hotovou stránku.
  Hledá se tolerantně k mezerám (zdroj je plný nezlomitelných). Pokud se text
  nenajde nebo není jednoznačný, skript to **ohlásí a skončí chybou** — nikdy
  opravu tiše nevynechá.
* `boxes` — HTML vložené za sekci „🔑 Klíčové pojmy“ (boxy k MKN-11, k revizím RVP…).
* `notes` (jen pedagogika) — HTML vložené **před** klíčové pojmy; vysvětluje,
  který obrázek ze zdroje se nepublikuje a proč.
* `terms` (jen pedagogika) — `drop`, `rename` a `add` pro automaticky posbírané
  klíčové pojmy. Z nich se dělají kartičky a glosář, takže se vyplatí opravit
  případy, kdy heuristika urve začátek věty nebo zmenší příjmení. Neexistující
  klíč v `drop`/`rename` skript ohlásí, aby soubor tiše nezestárl.

Značka `<span class="fix">` a rozbalovací `<details class="upd">` se vždy věší
**až za koncovou značku odstavce nebo seznamu** — uvnitř nich by rozdělily text
a `check_fidelity.py` by ho hlásil jako ztracený.

Mapa `QSTART` v konvertoru se při každém spuštění **ověřuje proti textu nadpisů**.
Když se dokument změní, skript spadne s výpisem, co nesouhlasí, místo aby
vygeneroval rozsypané stránky.

## Kontroly

```bash
python3 tools/check_links.py      # vnitřní odkazy a kotvy vedou někam
python3 tools/reindex.py          # přegenerování assets/data.js

# ze .docx se neztratil žádný text — pro každý předmět zvlášť
python3 tools/check_fidelity.py
python3 tools/check_fidelity.py --map tools/_meta_psychologie.json \
        'SZO PSYCHOLOGIE.docx' psychologie
python3 tools/check_fidelity.py --map tools/_meta_poradenstvi.json \
        'SZO SPECIÁLNÍ PEDAGOGIKA.DOCX' poradenstvi
python3 tools/check_fidelity.py --map tools/_meta_pedagogika.json \
        'SZZ- Padagogika (komplet).DOCX' pedagogika
```

> **Pozor:** zdrojové dokumenty nejsou součástí repozitáře (viz `.gitignore`).
> Z čistého klonu proto nejdou spustit konvertory ani `check_fidelity.py` —
> potřebují dokument v `source/`. `reindex.py` a `check_links.py` fungují vždy,
> protože pracují jen s HTML.

`check_fidelity.py` porovnává každý odstavec a každou buňku tabulky ze `.docx`
s vygenerovanými stránkami. Vědomé odchylky jsou vypsané v
`tools/_corrections.txt`, aby je kontrola nehlásila jako ztracený obsah — a naopak
si stěžuje na řádky, kterým už ve zdroji nic neodpovídá. Řádek začínající
`predmet/soubor.html` patří jen tomu předmětu, samotné `soubor.html` se hledá
v adresáři právě kontrolovaného předmětu.

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

Všechny čtyři materiály byly zkontrolovány proti stavu k **srpnu 2026**. Opravy
a doplnění jsou vyznačené přímo v textu (oranžově `<span class="fix">`,
s rozbalovací poznámkou „Aktualizace 2026“) a zdokumentované na samostatných
stránkách.

**Pedagogika** — `pedagogika/pravni-aktualnost.html`. Nejstarší zdroj na webu
(2016/2017) a jediný bez vlastního dodatku. Teorie výchovy, didaktika ani
filozofie výchovy nezastaraly; problémy se soustřeďují do otázky 7, kde je
**devět ze šestnácti zjištění** — Akreditační komise zaniklá v roce 2016, model
maturity nahrazený v roce 2021, výčet pedagogických pracovníků z předpisů před
rokem 2004, ISCED-97 a ORP jako orgán státní správy ve školství. Dokument navíc
**neobsahuje ani jednu zmínku o GDPR**, přestože stojí na sociometrii
a pedagogické diagnostice. Součástí je i mapa 20 stránek na 17 okruhů zadání A21
a upozornění na téma, které ve zdroji chybí celé (Berne, bariéry v komunikaci).

**Poradenství** — `poradenstvi/pravni-aktualnost.html`. Zdroj je z května 2022,
vlastní dodatek nemá a cituje **šest zrušených předpisů nebo pojmů** jako platné —
vyhl. 73/2005 Sb., zák. 101/2000 Sb., zákon o rodině, vyhl. 182/1991 Sb.,
„chráněné dílny“ a „osoby se změněnou pracovní schopností“.
Celkem **14 zjištění**, k tomu porovnání se zadáním A21 (17 okruhů × 20 otázek)
a upozornění na téma, které ve zdroji chybí celé (sociální exkluze, žáci s OMJ).

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
[edu.gov.cz](https://edu.gov.cz) a [uzis.cz](https://www.uzis.cz) (MKN-11).
`zakonyprolidi.cz` funguje v prohlížeči, ale blokuje automatizované dotazy.

## Obrázky ze zdrojů

Ze 21 obrázků ve zdroji poradenství jsou na webu **tři** — audiogramy převodní,
percepční a smíšené poruchy. Ostatní se nepublikují a je to záměr, ne chyba
konverze: byly to snímky obrazovky s uživatelským jménem a osobní lištou
záložek, sken **vyplněného záznamového listu WISC-III** s výsledky konkrétního
dítěte, snímek s **jmenným seznamem lékařů a jejich e-maily** a jedna předloha
s výslovným zákazem dalšího šíření. U každé vynechávky je na příslušné stránce
box, který vysvětluje, co tam bylo a proč tam není — seznam s důvody drží
`SKIP_IMAGES` v `tools/docx2html_spec.py`.

Ze 14 obrázků ve zdroji pedagogiky **nepoužíváme ani jeden** a adresář
`pedagogika/img/` proto vůbec nevzniká. Dva z nich jsou snímek celé obrazovky
s PowerPointem, na kterém je v titulkové liště **jméno autorky** a její hlavní
panel; jeden je logo fakulty a jeden vektorové **EMF**, které prohlížeč
nevykreslí. Zbytek jsou šedé skeny knižních stránek, kterými prosvítá text
z rubu — ty jsou **překreslené nativně**: tabulky jako `<table>`, Maňákova
klasifikace metod jako vnořený seznam a tři komunikační struktury organizačních
forem jako inline SVG, které dědí barvu textu, takže funguje ve světlém i tmavém
režimu a v tisku. Zdrojem překreslených verzí je `tools/_doplnky_pedagogika.json`,
důvody vynechání drží `SKIP_IMAGES` v `tools/docx2html_ped.py`.
