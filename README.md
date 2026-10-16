## Public Llama scoring (October 2026)

The active model is `llama3-numeric-1.0.0`, using the existing local Ollama `llama3:latest` (pinned digest in `msm/llama.py`). Each headline receives -1 (negative), +1 (positive), 0 (mixed), or null (unclear/out of scope). These are direction codes, not calibrated intensity or probability. Null is excluded, zero is included. Numeric output is validated against the model labels, with one corrective retry. Headlines are data, never instructions.

The public US MARKET score includes broad US stories and individual US firms. Existing routing is retained for Nasdaq/S&P segments; additional companies are not automatically claimed as index constituents. Event deduplication, equal publisher weights, six-hour time decay, 24-hour window and minimum coverage remain unchanged. Original rules history is preserved, with a model boundary in the chart and momentum.

GitHub Actions cannot reach a Mac's localhost. Local inference runs with `python3 -B -m msm.rate_local`; then publish only `state/llama_scores.json` to `main`. A cache update triggers the existing collect/deploy workflow, which also recomputes on its 15-minute schedule. The cache stores derived scores, explanations and provenance, not raw headlines or article bodies. It also restores previously observed feed items that have rotated out. Missing Llama ratings never fall back to rules. The web shows pending titles and warns if local inference has not refreshed for an hour. An asleep/offline Mac cannot produce new ratings.

`python3 -B -m msm.rate_local --seed /private/path/results.json` can backfill previously observed real RSS samples. It validates dates/domains and never downloads a model. `python3 -B -m msm.run` builds the public data from the cache. For recurring updates, keep the local Mac, Ollama and the configured publishing task available. No paid inference API is used.

The historical documentation below describes the previous rules model and initial setup; the active behavior is described above and on the public dashboard.

# MARKET SENTIMENT MONITOR 1.0

Funkční experimentální MVP: Python 3.9+ (workflow 3.12) bez externích závislostí, RSS/volitelný API sběr, odhad dopadu anglických titulků na americké akcie, historie, JSON a statický art déco dashboard. Přiložená data pocházejí ze skutečného sběru, nikoli z demonstrace. Syntetické titulky jsou pouze v testech.

Veřejný dashboard: https://pavelkohout-dotcom.github.io/sentiment/

Repozitář: https://github.com/pavelkohout-dotcom/sentiment

## Spuštění

V tomto adresáři:

```sh
python3 -m unittest discover -s tests -v
python3 -m msm.run
python3 -m http.server 8765 --bind 127.0.0.1 --directory docs
```

Otevřete http://127.0.0.1:8765. Dashboard potřebuje HTTP, pouhé otevření `docs/index.html` přes `file://` obvykle zablokuje načítání JSON. Pro přepočet již uložených dat bez sítě: `python3 -m msm.run --offline` (výslovně označený offline běh). Neprovozujte dva místní zapisující procesy současně.

## Co je a není hotovo

- RSS/Atom: MarketWatch Top Stories a Guardian Stock Markets. Oba endpointy ověřeny skutečným HTTP 200 dne 13. 10. 2026. CNBC při ověření HTTP 403; v konfiguraci vypnutý. Žádné obcházení ochrany, paywallu ani získávání článků z alternativních kopií.
- Alpha Vantage NEWS_SENTIMENT: implementovaný volitelný adaptér, whitelist profesionálních vydavatelů. Testovaný pomocí mocků, nikoli skutečného klíče. Skóruje se týmž modelem jako RSS; providerovo sentiment skóre se nemíchá do MSI.
- NASDAQ-100 / S&P 500: tematické filtry přímých zmínek indexů, US makra a omezeného seznamu velkých společností. **Nejde o kompletní, historicky správný seznam členů indexů, indexové váhy ani indexově specifický fundamentální model.** Některé firmy jsou v obou indexech; nynější watchlist je tematické směrování, nikoli důkaz členství. Před systematickým použitím je potřeba doplnit licencovaný point-in-time seznam a označování entit.
- Pravidlový model z titulků, **nikoli LLM ani validovaný prediktor výnosů**. Umí explicitní pohyb akcií, výsledky/guidance, inflaci, výnosy, sazby; zbytek vynechá. Ukazuje konkrétní pravidla. Neumí spolehlivě ironii, složitou negaci, všechny vztahy mezi větami nebo příčinu tržního pohybu.
- Typ komentář se označí pouze při explicitním signálu v titulku. Jinak `unknown`; neoznačujeme domněnku za zprávu.
- Žádné článkové texty, souhrny, obrázky ani API klíče ve veřejném exportu. Titulky jsou standardně `null`. Archiv obsahuje odkazy, čas, zdroj a naše odvozené hodnoty. Přepínač `publish_titles` použijte jen s odpovídajícím oprávněním vydavatele.
- GitHub Pages je nasazený a ověřený: první úspěšný běh [38469312814](https://github.com/pavelkohout-dotcom/sentiment/actions/runs/38469312814), skutečný sběr 13. 10. 2026 ve 23:16 Praha, dashboard i JSON HTTP 200. Rozvrh je nastavený; pravidelnost budoucích běhů není garantovaná.

## Nasazení na GitHub Pages

1. Zvolte nový samostatný repozitář (doporučený název `market-sentiment-monitor`) s výchozí větví `main`; nahrajte celý obsah tohoto adresáře, včetně `.github`, `state` a `docs/data`. Neumisťujte jej do podadresáře jiného dashboardu bez úpravy cest workflow.
2. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
3. Settings → Actions → General: povolte běhy Actions a zápis workflow do repozitáře. Ochrana větve `main` musí dovolit datové commity účtu `github-actions[bot]`; jinak vyhraďte datovou větev a upravte workflow. Zpřístupnění historie přes commit je záměrné; je bez původních titulků a bez tajemství.
4. Actions → **Collect and publish MSM** → Run workflow. Nejprve proběhnou testy, sběr, datový commit, poté publikace `docs` pomocí oficiálních Pages actions.
5. Ověřte zelený běh, URL v kroku Deploy, dostupnost `/data/latest.json` a správný čas posledního běhu. Potom ověřte i další automatický běh a nárůst `history.json`.
6. Automatický rozvrh: minuty **07, 22, 37, 52 každou hodinu, UTC**, nepřetržitě i o víkendech. Jde o požadovaný interval, ne SLA. GitHub může běhy zpozdit/vynechat a v neaktivním veřejném repozitáři rozvrh po 60 dnech deaktivovat. Běhy lze znovu povolit v Actions. Viz [GitHub schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Workflow serializuje zapisující běhy; nepřerušuje běžící aktualizaci. Při souběžném lidském commitu může push bezpečně selhat namísto přepsání historie — spusťte workflow znovu. Po částečném výpadku publikuje stav `degraded` a pak označí běh jako neúspěšný, aby nezůstal problém skrytý. Výchozí `GITHUB_TOKEN` stačí; osobní GitHub token se do repozitáře nedává. Nasazení přes artifact funguje i přesto, že botův commit nespouští další workflow.

## API klíč a datová oprávnění

Základní RSS verze žádný klíč nepotřebuje. U Alpha Vantage:

1. Získejte klíč a tarif s NEWS_SENTIMENT na [Alpha Vantage](https://www.alphavantage.co/support/#api-key); dostupnost a kvótu ověřte pro svůj účet podle [dokumentace](https://www.alphavantage.co/documentation/#news-sentiment).
2. V GitHub Settings → Secrets and variables → Actions → New repository secret nastavte **ALPHAVANTAGE_API_KEY**. Lokálně jej předejte proměnnou prostředí; nikdy jej nevkládejte do HTML/JS, `config.json`, příkazů uložených v historii ani do Git.
3. V `config.json` přepněte zdroj `alphavantage.enabled` na `true`. Výchozí interval je 120 minut: maximálně 12 plánovaných požadavků za 24 hodin, pokud nepřijdou opakované pokusy nebo ruční zásahy. Přizpůsobte jej své kvótě; bez ověřeného tarifu jej nesnižujte. Síťové opakování může spotřebovat další požadavky.
4. Zkontrolujte oprávnění pro zamýšlený účel a veřejné odvozené výstupy. [Podmínky Alpha Vantage](https://www.alphavantage.co/terms_of_service/) rozlišují soukromé osobní a komerční použití. Klíč sám není automaticky licence k redistribuci. Zdroj je proto výchozí vypnutý.

Veřejně dostupný RSS endpoint rovněž není automatickou licencí k libovolné redistribuci. RSS je použit jako vydavatelem vystavený distribuční kanál; texty se neukládají. Odkazy na aktuální podmínky jsou v konfiguraci. Samotné vynechání titulků není právní zárukou všech způsobů použití; při profesionálním/prodejním provozu ověřte práva na analýzu a zveřejnění odvozených dat u poskytovatele. Vypněte zdroj, jehož podmínky vašemu účelu nevyhovují. Projekt nenabízí ani nepředstírá licence Reuters, Bloomberg, FT nebo Barron's.

## Metodika v1

1. URL normalizace odstraní tracking a fragmenty; perzistentní identita je SHA-256 normalizované URL. V rámci stejné verze modelu je první pozorování neměnné. Při změně modelu se znovu dostupný titulek přepočítá; starý odvozený záznam se přesune do `model_revisions` a `docs/data/revisions.json`. Historické snapshoty zůstanou beze změny. Články nepozorované novým modelem se do nového MSI nezahrnou. Nejde o archiv editací ani o archiv celých článků.
2. Čas publikace musí být validní, s časovým pásmem, nejvýše čas sběru. Neznámé datum se nedoplňuje aktuálním časem. Pouze povolené domény. Články bez relevantních entit se vyřadí.
3. Skóre pravidel je v rozsahu −1 až +1, nejisté výroky mají poloviční velikost. Nenalezení pravidla dává `null`, nikoli 0. Síla důkazu `confidence` není statistická pravděpodobnost správnosti.
4. V aktivním okně 24 h se slučují blízké titulky: Jaccard ≥ 0,72 nad hashovanými významovými tokeny, alespoň 4 společné tokeny, odstup maximálně 18 h, žádný opačný směr skóre. Reprezentant je první hodnocený článek. To odstraňuje identické a blízké syndikace, **nikoli všechny různě formulované zprávy o stejné události**. Tematické přepsání může projít jako více událostí; podobné události se mohou mylně sloučit.
5. Váha = `2^(-stáří_h / 6) × confidence × typ`, typ = 0,6 pro komentář, jinak 1. V každém zdroji vážený průměr; mezi zdroji prostý průměr. MSI = `50 + 50 × průměr`. Duplicitní převzetí dalšími médii nezvýší počet událostí ani důkaz nezávislosti zdrojů.
6. `ok` vyžaduje ≥5 hodnocených událostí ze ≥2 zdrojů; jinak `low_coverage` nebo `no_data`. Dílčí skóre při slabém pokrytí zůstává viditelné s upozorněním.
7. Momentum = současné MSI minus platný bod nejbližší času před 60 min v toleranci 45–90 min. Žádná interpolace ani falešná nula při chybějící historii.
8. Panika ≤20 / euforie ≥80 pouze při dostatečném vzorku. Pevné experimentální prahy, ne empiricky kalibrované percentily.

## Export a historie

- `docs/data/latest.json`: poslední běh, tři segmenty, stav zdrojů, relevantní aktivní odkazy.
- `docs/data/history.json`: všechny skutečné snapshoty od prvního spuštění; čas UTC, verze modelu a stav sběru.
- `docs/data/articles.json`: celý archiv odvozených záznamů, bez automatického promazávání.
- `state/store.json`: perzistentní identita URL, hash titulku/tokenů, analýza, poslední pokusy a úspěchy zdrojů. Hash není šifrování; neukládejte zde soukromý obsah.

Zápisy jednotlivých JSON souborů jsou atomické. Při poškozeném JSON se běh zastaví místo resetu historie. Dlouhodobě poroste velikost repozitáře a JSON; MVP je určené pro malé feedy, nikoli neomezený počet zdrojů. Před dosažením limitů GitHub/Pages archiv rozdělte podle měsíců a uchovejte zálohy; současný kód data automaticky nemaže. Obnovení ze staršího commitu musí zachovat všechny tři datové exporty i stav ze stejného běhu.

## Ověření

`VALIDATION.md` a `test-results.txt` obsahují skutečně provedené kontroly. Testy ověřují software a známé finanční jazykové příklady; **nedokazují predikční kvalitu, investiční výnos ani univerzální správnost sentimentu**. Pro takové tvrzení je potřeba nezávislý ručně označený vzorek, měření shody a časově oddělené vyhodnocení.

### Ruční aktualizace z Macu

Tlačítko **Aktualizovat přes Llamu** komunikuje pouze s pomocníkem na
`http://127.0.0.1:8766`. Pomocník se spouští z kořene repozitáře:

```sh
python3 -B -m msm.local_control --directory /absolute/private/runtime-directory
```

V místním nastavení na stejné adrese jednorázově připojte fine-grained GitHub token:
jen repozitář `pavelkohout-dotcom/sentiment`, `Contents: Read and write`.
Token se ukládá do zvoleného soukromého adresáře s právy 0600 (adresář 0700),
nikdy do repozitáře ani veřejného webu. Zvolte adresář mimo checkout.
Po vypršení tokenu jej v nastavení nahraďte. Při odinstalaci zastavte pomocníka,
smažte soukromý adresář a token zrušte v nastavení GitHubu.

Mac musí být vzhůru, online a mít spuštěnou Ollamu s předepsaným modelem.
Pomocník nemění ani nestahuje modely. Každý požadavek použije čistý aktuální main,
spustí `msm.rate_local`, publikuje výhradně `state/llama_scores.json` a čeká až
5 minut na nasazení. Platné částečné výsledky se publikují i při chybách jednotlivých
hodnocení; při selhání publikace zůstanou místně pro další pokus. Při konfliktu
se soubor načte znovu a sloučí podle hashů a času hodnocení, jen pro kompatibilní
model/digest/prompt/options. `state/store.json` a `docs/data/*` nadále spravuje Actions.

Pomocník naslouchá jen na loopbacku; kontroluje Host, Origin a jednorázově při
spuštění generovaný session nonce. Konfigurace přihlašování je dostupná pouze
z místní stránky. Veřejný web se k Macu připojuje až po kliknutí. Prohlížeč může
vyžádat povolení místní sítě; pokud spojení z veřejného webu nepodporuje, lze stejnou
aktualizaci spustit v místním nastavení. Na jiném počítači bez pomocníka tlačítko
zobrazí vysvětlení. Pomocník sám nezavádí další pravidelný plán.
