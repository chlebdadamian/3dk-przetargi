# Plan rozwoju

Stan na 2026-10-30. Zrobione: źródła BZP, Baza Konkurencyjności, BIP-y (135 jednostek), platformazakupowa.pl,
konkursy SARP; filtr punktowy, Jev, raport i oceny w Claude Code (`/przetargi`), automat `daily` + Telegram.

## Zrobione 2026-10-30

1. **Karta doświadczenia biura** – projekty Daniela (obiekt, rok, kubatura, powierzchnia, wartość, inwestor,
   referencja); automatyczne sprawdzanie warunków udziału i dane dla Jev.
2. **Czytanie PDF-ów z BIP-ów** – termin, warunki i zakres zapytań ofertowych gmin (dziś „aktualne” = 21 dni).
3. **Przypomnienia o terminach** – Telegram 3 dni i 1 dzień przed terminem dla ocen `tak` / `moze`.

Dodatkowo: `partners` – zwycięzcy przetargów projektowych w regionie (pkt 6), `outcomes` +
powiadomienie Telegram o wyniku ocenionego przetargu (pkt 8).

Do zrobienia przez biuro: uzupełnić `portfolio.toml` (lata, kubatury, wartości zleceń, inwestorzy, referencje).

## Na później

4. **Szkic oferty** – dla `tak`: wypełniony formularz ofertowy, wykaz usług i osób, lista dokumentów do złożenia
   (dane z karty doświadczenia). Odłożone na prośbę biura (2026-10-30).
5. **Wycena** – ceny podobnych rozstrzygnięć z BZP + kalkulacja wg zasad wyceny prac projektowych SARP →
   proponowany przedział ceny oferty.
6. ~~**Lista partnerów do konsorcjów**~~ (zrobione: `partners`) – firmy wygrywające przetargi projektowe w regionie (z ogłoszeń o wyniku);
   ich doświadczenie (art. 118 Pzp) otwiera przetargi z progami typu „usługa ≥ 200 tys. zł”.
7. **Plany zamówień gmin** – BIP „Plan zamówień publicznych” i platformazakupowa `/pn/{gmina}/proceedings/plan`:
   co gminy zamierzają zamówić w danym kwartale.
8. ~~**Wyniki pominiętych przetargów**~~ (zrobione: `outcomes`, Telegram) – kto wygrał i za ile; kalibracja wyceny i obraz konkurencji.
9. **Strategia portfolio publicznego** – pierwsze miesiące: małe zapytania z BIP-ów < 130 tys. zł, żeby zebrać
   referencje od gmin, które otwierają kolejne przetargi.
10. **Konkursy z BZP** – osobny typ ogłoszeń w API BZP (po zakończeniu pobierania historii, żeby nie drażnić WAF).
