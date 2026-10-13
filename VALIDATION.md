# Ověření MVP — 13. 10. 2026

- 39 automatických testů prošlo na Pythonu 3.12.14; úplný výstup: `test-results.txt`. Testovací titulky jsou syntetické a nikdy nejsou exportované jako zprávy.
- Kontrola JavaScript syntaxe pomocí Node: úspěch.
- Místní dashboard přes HTTP: 200. V prohlížeči ověřeno načtení skutečných dat, přepnutí Nasdaq-100, filtr pouze hodnocených zpráv a prázdný stav komentářů.
- Skutečný sběr MarketWatch a Guardian: oba úspěšné; žádný článek nebyl stažen mimo RSS. CNBC samostatný probe: HTTP 403; zůstává vypnuté.
- Alpha Vantage: ověřeno parsování, kvóta, chybějící klíč a whitelist v testech s mocky. Živý API test bez klíče neproveden.
- Testy pokrývají canonical URL, nebezpečné odkazy, RSS/Atom, odmítnutí XML entit, relevance, polaritu, inflaci, negaci, nejisté výroky, neznámý sentiment, slučování syndikací, oddělení protichůdných/časově vzdálených zpráv, nezdvojování vah, váhy zdrojů, slabé pokrytí, expirované zprávy, momentum, extrémy, oddělení verzí modelu, historii při opakování/výpadku, utajení klíčů v chybách, chybnou položku, poškozený stav, zachování archivu, interval API a revize modelu.
- Testy neprokazují kvalitu na nezávislém korpusu ani investiční výkonnost.

## Skutečný poslední lokální sběr

```json
{
  "generated_at": "2026-10-13T17:47:11Z",
  "collection_status": "ok",
  "new_articles": 0,
  "total_archived": 6,
  "metrics": {
    "all": {
      "value": 8.24,
      "status": "low_coverage",
      "events": 4,
      "scored_events": 2,
      "articles": 4,
      "sources": 1,
      "momentum": null,
      "momentum_baseline": null,
      "extreme": "unavailable"
    },
    "nasdaq100": {
      "value": 15.0,
      "status": "low_coverage",
      "events": 3,
      "scored_events": 1,
      "articles": 3,
      "sources": 1,
      "momentum": null,
      "momentum_baseline": null,
      "extreme": "unavailable"
    },
    "sp500": {
      "value": 8.24,
      "status": "low_coverage",
      "events": 4,
      "scored_events": 2,
      "articles": 4,
      "sources": 1,
      "momentum": null,
      "momentum_baseline": null,
      "extreme": "unavailable"
    }
  }
}
```

## Ověřené nasazení

GitHub Actions [běh 38469312814](https://github.com/pavelkohout-dotcom/sentiment/actions/runs/38469312814): completed / success. Dashboard https://pavelkohout-dotcom.github.io/sentiment/ i latest.json vrátily HTTP 200. Skutečný sběr `2026-10-13T21:16:25Z` (23:16 Praha): oba zdroje `ok`, archiv 8 záznamů; 6 aktivních relevantních titulků, 3 hodnocené události ze 2 zdrojů, MSI 45,37 a `low_coverage`. Momentum a extrémy zůstávají správně nedostupné.

Vizuální kontrola veřejné stránky provedena. Mobilní šířka 390 px: obsah nepřetéká vodorovně. Automatický rozvrh 07/22/37/52 UTC je nasazen, pozdější rozvrhový běh nebyl v této kontrole vyčkáván.
