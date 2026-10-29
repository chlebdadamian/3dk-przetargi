---
name: przetargi
description: Pobierz nowe przetargi z BZP, oceń dopasowanie do biura 3DK Projekt i przygotuj zestawienie z cenami rynkowymi. Użyj, gdy użytkownik pisze /przetargi, „sprawdź przetargi”, „zestawienie przetargów”.
---

# Przegląd przetargów dla 3DK Projekt

Profil biura i założenia są w `CLAUDE.md` (sekcja „Profil biura”). Odpowiadaj po polsku.

## 1. Pobierz dane

```
python -m przetargi fetch
```

Jeśli baza jest pusta albo nie ma cen (komunikat w `similar`), uruchom `fetch --days 30 --history`
w tle (trwa kilka minut). Przy 403 z WAF: odczekaj ~10 min i spróbuj raz – nie zmieniaj nagłówków.

## 2. Raport kandydatów

```
python -m przetargi report
```

Przeczytaj plik `data/raporty/kandydaci-DATA.md`. Zawiera tylko nieocenione, otwarte przetargi
powyżej progu punktów, z opisem, okresem realizacji, kryteriami, warunkami udziału, wadium
i cenami podobnych zleceń. Przy niejasnościach `python -m przetargi show <nr>`.

## 3. Oceń każdy przetarg

Werdykt `tak` / `moze` / `nie`, kierując się:

- **Zakres** – czy to projekt architektoniczny, który biuro zrobi samo lub z branżystami? Drogi,
  sieci, instalacje-only, „zaprojektuj i wybuduj”, inwestor zastępczy → `nie`.
- **Skala** – mały/średni budynek, wnętrza, elewacja, adaptacja, koncepcja → dobrze. Szpital,
  duży kompleks, wielka hala → raczej `nie` lub `moze`.
- **Warunki udziału (najważniejsze)** – biuro nie ma portfolio publicznego (jedno zlecenie:
  łazienka dla policji). Brak warunku doświadczenia albo warunek spełnialny projektami domów
  prywatnych → plus. Wymóg projektów „budynku użyteczności publicznej” o określonej skali → zwykle
  `nie`, chyba że da się użyć zasobów podwykonawcy/partnera (art. 118 Pzp) – wtedy `moze` z adnotacją.
  Kryterium „doświadczenie projektanta” liczy osoby, nie firmę – sprawdź, czy liczą też projekty prywatne.
- **Termin** – ile dni zostało na ofertę; okres realizacji vs. zakres.
- **Pieniądze i konkurencja** – mediana cen podobnych zleceń i liczba ofert. Dużo ofert = presja cenowa.
- **Lokalizacja** – Kraków/Sądecczyzna najlepiej; dalej tylko przy dobrym dopasowaniu.
- **Kryteria** – doświadczenie projektanta jako kryterium może pomóc lub zaszkodzić.

Zapisz każdą ocenę (uzasadnienie 1–2 zdania, konkretnie):

```
python -m przetargi review <nr> tak "Adaptacja remizy na świetlicę, Chełmiec, 6 mies., warunek 1 projekt budynku – spełniamy"
```

## 4. Zestawienie

Zapisz `data/raporty/zestawienie-DATA.md` i pokaż w odpowiedzi skrót:

1. **Warte oferty** (`tak`) – tytuł, zamawiający, termin ofert, link, szacowana cena rynkowa
   (mediana podobnych + zakres) i proponowany przedział ceny oferty, kluczowe warunki, ryzyka.
2. **Do rozważenia** (`moze`) – co trzeba sprawdzić w SWZ.
3. **Odrzucone** – jedna linijka na przetarg z powodem.

Ceny w BZP to kwoty ofert (zwykle brutto). Nie wymyślaj liczb – jeśli brak podobnych zleceń, napisz to.
Jeśli wiele odrzuceń ma wspólną przyczynę, zaproponuj zmianę w `config.toml` (wykluczenia / punkty).
