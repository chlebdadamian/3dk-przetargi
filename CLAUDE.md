# 3dk-przetargi

Monitor przetargów publicznych (BZP / e-Zamówienia) dla biura architektonicznego 3DK Projekt.
Python 3.11+, tylko biblioteka standardowa. Dane w `data/` (SQLite + raporty, poza gitem).

## Komendy

```
python -m przetargi fetch [--days N] [--history]   # pobierz ogłoszenia; --history = rok wyników (ceny)
python -m przetargi rescore                        # przelicz punkty po zmianie config.toml
python -m przetargi list [--all] [--verdict tak]   # otwarte, pasujące przetargi
python -m przetargi show <nr>                      # opis, okres, kryteria, warunki, wadium
python -m przetargi similar <nr>                   # ceny podobnych rozstrzygniętych przetargów
python -m przetargi prices <słowa> [--province PL12]
python -m przetargi report [--all]                 # data/raporty/kandydaci-DATA.md do oceny
python -m przetargi review <nr> tak|moze|nie "uzasadnienie"
python -m przetargi partners [--province PL12]       # kto wygrywa przetargi projektowe (partnerzy)
python -m przetargi outcomes                       # wyniki ocenionych przetargów
python -m przetargi daily [--dry-run]              # automat: źródła + Jev + Telegram/WhatsApp
python -m przetargi notify ["tekst"]               # test powiadomień
```

`<nr>` może być fragmentem numeru, np. `00506260`.

## Źródła (`fetch --source …`)

| źródło | moduł | uwagi |
|---|---|---|
| `bzp` – e-Zamówienia (BZP) | `bzp.py` | zamówienia ≥ 130 tys. zł + ogłoszenia o wyniku (ceny); WAF – patrz niżej |
| `bk` – Baza Konkurencyjności | `bk.py` | zamówienia z projektów UE; lista + szczegóły kandydatów |
| `bip` – BIP-y gmin na bip.malopolska.pl | `bip.py` | zapytania < 130 tys. zł; lista jednostek w `config.toml` `[fetch.bip_units]`; termin w PDF, więc „aktualne” = 21 dni od publikacji |
| `pz` – platformazakupowa.pl | `pz.py` | robots.txt: Crawl-delay 900 → 15 min między zapytaniami; tylko wyszukiwarka po frazach; brak lokalizacji – bliskość z nazwy zamawiającego |
| `sarp` – konkursy SARP | `sarp.py` | wszystkie nowe idą do oceny (bez terminów w danych, „aktualne” = 60 dni) |

`fetch` bez `--source` pobiera wszystko; przez platformazakupowa trwa to ~45 min.

## Karta doświadczenia i załączniki

- `portfolio.toml` (poza gitem, wzór: `portfolio.example.toml`) – projekty biura; `eligibility.py` porównuje
  z nimi warunki udziału („Doświadczenie wg karty” w raporcie, dane dla Jev). „SPEŁNIA” tylko przy mierzalnym
  kryterium (kubatura, wartość, powierzchnia, obiekt publiczny, zabytek); rodzaj usługi zawsze sprawdzić w treści.
- `docs.py` – tekst z PDF/DOCX (zależność: `pypdf`, `pip install -r requirements.txt`), termin składania ofert
  i warunki z załączników BIP; termin zgłoszeń w konkursach SARP.

## API BZP

- `https://ezamowienia.gov.pl/mo-board/api/v1/notice` – publiczne, bez klucza.
- `PageNumber` jest ignorowany; przy 500 wynikach dzielimy okno dat (patrz `bzp.fetch`).
- Za API stoi WAF: blokuje domyślny UA urllib i podszywanie się pod przeglądarkę.
  Używamy `przetargi-monitor/0.1` i przerwy 1 s między zapytaniami. Po serii 403 IP bywa
  blokowane na kilka–kilkanaście minut – wtedy odczekać, nie zmieniać nagłówków.

## Profil biura (do oceny przetargów)

3DK Projekt – Daniel Kałuziński, architekt. Biura: Kraków (ul. Podedworze 9) i okolice Nowego Sącza.
Mały zespół, 8+ lat, 30+ zrealizowanych projektów.

Mocne strony: projekty architektoniczne budynków (dotąd głównie domy jednorodzinne premium),
projekty na trudnym terenie (skarpy, zbocza), elewacje i termomodernizacje, wnętrza, wizualizacje 3D,
koncepcje, nadzór autorski. Teren: Kraków, Sądecczyzna, Małopolska, Beskidy.

Potwierdzone z biurem (2026-10-29):
- branże konstrukcja / instalacje – biuro ma podwykonawców, więc dokumentacja wielobranżowa jest możliwa;
  duże obiekty (szpitale, hale, kompleksy) nadal to ryzyko skali;
- doświadczenie w zamówieniach publicznych – praktycznie brak: jedno zlecenie (projekt łazienki dla policji).
  Warunki udziału typu „N projektów budynku użyteczności publicznej o pow. > X m²” zwykle wykluczają.
  Najlepsze są przetargi bez warunku doświadczenia albo z warunkiem spełnialnym projektami prywatnymi
  (np. „projekt budynku o kubaturze/powierzchni…” bez wymogu „użyteczności publicznej”),
  ewentualnie wspólnie z podwykonawcą/partnerem lub na jego zasobach (art. 118 Pzp);
- Daniel ma uprawnienia do projektowania w specjalności architektonicznej **bez ograniczeń**;
- wnętrza: domy prywatne + projekt wnętrz części wspólnych bloku mieszkalnego. Brak wnętrz przestrzeni
  edukacyjnych, wystawienniczych, muzealnych, kulturalnych, turystycznych (pensjonat, hotel, restauracja);
- brak projektów obiektów zabytkowych (ewidencja / rejestr zabytków) – warunki „projekt przy zabytku” wykluczają;
- największe dotychczasowe zlecenie: ok. 80–90 tys. zł – warunki „usługa o wartości min. X zł” powyżej tej
  kwoty wykluczają (chyba że na zasobach partnera, art. 118 Pzp);
- kosztorysy zleca podwykonawcy (podobnie branże) – problem, gdy SWZ zastrzega osobiste wykonanie danej branży;
- realny zakres wartości: do ok. 300–500 tys. zł brutto.
