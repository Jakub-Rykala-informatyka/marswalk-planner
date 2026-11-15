# Marswalk Planner: biznesplan

Wersja z 15 listopada 2026, po NASA Space Apps Challenge w Stalowej Woli. Opis produktu i danych jest w `raport_marswalk_planner.md`. Ten dokument odpowiada na pytanie, jak z projektu hackathonowego zrobić produkt, za który ktoś zapłaci.

**Ważne:** kwoty, ceny i harmonogram poniżej to nasze założenia do sprawdzenia, a nie wyniki badań rynku. Zaznaczamy je w tekście jako *założenie*.

---

## 1. Streszczenie

**Co robimy:** narzędzie, które z danych o terenie liczy trasę dla człowieka idącego pieszo w trudnych warunkach. Łączy kilka warstw danych (rzeźbę terenu, szorstkość, promieniowanie) w jedną mapę kosztów i wyznacza najtańszą, bezpieczną trasę. Pokazuje ją na ekranie planisty i na wyświetlaczu w okularach (HUD).

**Pierwsze zastosowanie:** piesze wyjścia astronautów (EVA) na Marsie i Księżycu. Na hackathonie zbudowaliśmy działający prototyp na prawdziwych danych NASA z krateru Gale.

**Dlaczego to ma sens biznesowy:** ten sam silnik działa na ziemskich modelach terenu. Rynek kosmiczny daje prestiż, granty i pierwszych partnerów. Rynek ziemski (misje analogowe, geologia terenowa, ratownictwo górskie) daje szybsze i liczniejsze wdrożenia.

**Czego szukamy teraz:** inkubacji (np. ESA BIC Poland), grantu na rozwój i jednego partnera pilotażowego na misji analogowej.

---

## 2. Problem

**W kosmosie:**
- Dane o Marsie i Księżycu są, ale w portalach pokazujących region albo całą planetę (Mars Trek, mapy USGS). Pojedyncze wyjście to kilka kilometrów, a liczy się każdy klif i pole głazów.
- Każda warstwa leży w innym źródle: HiRISE, CRISM, THEMIS, RAD. Planista składa je ręcznie.
- Narzędzia nawigacyjne powstały dla łazików. Człowiek w skafandrze ma inne limity: nachylenie, zapas tlenu, dawkę promieniowania, czas dojścia do schronienia.

**Na Ziemi ten sam problem ma inna skala i inni ludzie:**
- uczestnicy misji analogowych ćwiczą wyjścia w skafandrach na pustyniach i w habitatach,
- geolodzy terenowi planują przejścia po trudnym terenie z ciężkim sprzętem,
- ratownicy górscy szukają najszybszej bezpiecznej drogi do poszkodowanego.

Wszyscy dziś łączą mapę topograficzną, zdjęcia i własne doświadczenie. Nie mają narzędzia, które policzy trasę z ich limitami.

---

## 3. Rozwiązanie i stan prototypu

### Co już działa (po hackathonie)

| Element | Stan |
| --- | --- |
| Potok danych NASA (HiRISE DTM 1 m, ortofoto 25 cm) | działa dla wycinka 2 × 2 km w Gale |
| Warstwy: nachylenie, szorstkość, widoczność nieba, model dawki z RAD | działają |
| Mapa kosztów dla pieszego i dla łazika (węzły ROS 2) | działa, parametry zmieniane na żywo |
| Planer A* i planer całej misji (kolejność celów, zapas tlenu) | działa |
| Dashboard w przeglądarce (mapa 2D/3D, budżet misji, kamery) | działa |
| HUD w okularach XREAL One | prototyp |
| Symulacja w NVIDIA Isaac Sim (teren, astronauta, łazik z ramieniem) | działa |
| Planer konfiguracji łazika z modelami CAD | działa w przeglądarce |

### Czego jeszcze nie ma

- danych termicznych (THEMIS) i mineralnych (CRISM) w mapie kosztów,
- kalibracji modelu ruchu w skafandrze na prawdziwych pomiarach,
- pracy offline na tablecie lub w okularach bez laptopa,
- importu dowolnego modelu terenu jednym kliknięciem (dziś wymaga skryptów).

### Wyróżniki

1. **Trasa liczona dla człowieka, nie dla robota.** Model kosztów uwzględnia nachylenie, szorstkość i dawkę, a progi da się ustawić pod konkretny skafander albo sprzęt.
2. **Mapa schronień przed promieniowaniem** z widoczności nieba. Takiej warstwy nie ma w Mars Trek.
3. **Jeden kod od planowania do HUD.** Ta sama mapa kosztów działa w symulacji, w ROS 2 i w okularach.
4. **Otwarte standardy:** ROS 2, GeoJSON, rastry. Łatwo wpiąć narzędzie w istniejące systemy.

---

## 4. Klienci i rynek

### Segmenty, od najbliższego wdrożenia

| Segment | Kto | Czego potrzebuje | Kiedy realnie |
| --- | --- | --- | --- |
| Misje analogowe | stacje analogowe w Polsce i za granicą (np. LunAres w Pile, MDRS w Utah), programy szkoleniowe | planowanie wyjść w skafandrach, trening z HUD | 6–12 miesięcy |
| Badania i edukacja | uczelnie, centra nauki, programy edukacyjne o kosmosie | interaktywna mapa i symulacja wyjścia | 6–12 miesięcy |
| Agencje i firmy kosmiczne | POLSA, ESA, firmy pracujące przy programie Artemis | narzędzie do studiów misji księżycowych i marsjańskich | 1–3 lata |
| Praca w terenie na Ziemi | geolodzy, firmy poszukiwawcze, ratownictwo górskie | trasa z limitami ludzi i sprzętu, offline | 1–2 lata, po wersji terenowej |

### Wielkość rynku

Nie mamy jeszcze własnych danych o wielkości rynku. Do zrobienia w pierwszych 3 miesiącach:
- policzyć aktywne stacje i misje analogowe oraz ich budżety szkoleniowe,
- sprawdzić programy ESA i POLSA, w których narzędzia planowania misji są finansowane,
- przeprowadzić 15–20 rozmów z potencjalnymi użytkownikami z każdego segmentu.

---

## 5. Model przychodów

*Założenie*, do sprawdzenia w rozmowach z klientami:

| Źródło | Dla kogo | Forma |
| --- | --- | --- |
| Granty i kontrakty badawcze | ESA, POLSA, programy UE | finansowanie rozwoju, studia wykonalności |
| Wdrożenie pilotażowe | stacje analogowe, uczelnie | jednorazowa opłata za przygotowanie terenu, modelu ruchu i szkolenie |
| Licencja roczna | instytucje i firmy | dostęp do planera, aktualizacje, wsparcie |
| Usługi | agencje, firmy kosmiczne | przygotowanie warstw dla nowych miejsc lądowania, integracja z ich systemami |

**Wersja open-core:** podstawowy potok danych i planer zostają otwarte (repozytorium publiczne). Płatne są: wersja terenowa offline, HUD, gotowe zestawy danych dla wybranych miejsc i wsparcie. Otwarty kod buduje zaufanie w środowisku naukowym i ułatwia granty.

---

## 6. Konkurencja

| Rozwiązanie | Co robi dobrze | Czego mu brakuje względem nas |
| --- | --- | --- |
| NASA JPL Mars Trek / Moon Trek | dużo warstw, darmowe, oficjalne | skala regionu, brak trasy dla człowieka i mapy kosztów |
| JMARS (ASU) | analiza danych orbitalnych dla naukowców | narzędzie badawcze, nie planer wyjść, brak HUD |
| QGIS / ArcGIS (analiza kosztu dojścia) | potężna analiza GIS | wymaga eksperta GIS, brak modelu ruchu w skafandrze, brak HUD |
| Nav2 (ROS 2) | nawigacja robotów | stworzone dla robotów, nie dla ludzi |
| Aplikacje turystyczne (np. CalTopo, Gaia GPS) | mapy i trasy dla turystów | brak własnych limitów ruchu, promieniowania, zapasów |

**Nasza pozycja:** łączymy analizę GIS, model ruchu człowieka i interfejs w trakcie wyjścia w jednym narzędziu, które nie wymaga eksperta GIS.

---

## 7. Wejście na rynek

1. **Pokaz po hackathonie.** Film, slajdy i publiczne repozytorium jako wizytówka.
2. **Pilotaż na misji analogowej.** Jedna stacja, jedno wyjście z prawdziwymi ludźmi w skafandrach. Mierzymy różnicę między trasą z planera a trasą faktycznie przebytą.
3. **Publikacja wyników.** Konferencja albo artykuł o modelu ruchu w skafandrze i mapie schronień. To otwiera drzwi do agencji.
4. **Inkubator i grant.** Zgłoszenie do ESA BIC Poland i programów POLSA z wynikami pilotażu.
5. **Wersja ziemska.** Po pilotażu: tryb offline na tablecie i rozmowy z ratownictwem górskim oraz geologami.

---

## 8. Plan rozwoju

| Okres | Cel | Wynik |
| --- | --- | --- |
| 0–3 miesiące | uporządkować kod, dodać THEMIS i CRISM, import dowolnego terenu | wersja 0.2, 15–20 rozmów z klientami |
| 3–6 miesięcy | pilotaż na misji analogowej, kalibracja modelu ruchu | raport z pilotażu, pierwszy list intencyjny |
| 6–12 miesięcy | tryb offline, HUD bez laptopa, zgłoszenie do inkubatora | wersja 1.0, grant albo inkubacja |
| 12–24 miesiące | Księżyc (dane LRO), wersja ziemska, pierwsze licencje | 2–3 płacących klientów (*założenie*) |

---

## 9. Zespół

| Osoba | Rola | Wkład w produkt |
| --- | --- | --- |
| Kuba (Jakub) | Head of Software | symulacja Isaac Sim, dane terenu, dashboard, most ROS 2 |
| Rafał | HUD i ROS 2 | okulary XREAL, mapa kosztów, planer, czujniki skafandra |
| Gosia | projektowanie mechaniczne (CAD) | łaziki, ramiona, narzędzia |
| Dominika | komunikacja | film, prezentacja, zgłoszenia |
| Wanessa | komunikacja | film, prezentacja, zgłoszenia |

**Kogo brakuje:** osoby od rozwoju biznesu i kontaktu z agencjami oraz doradcy z doświadczeniem w EVA albo w misjach analogowych.

---

## 10. Koszty pierwszego roku

*Założenie*, rząd wielkości do planowania grantu:

| Pozycja | Szacunek |
| --- | --- |
| Praca zespołu (2 osoby na pełen etat, 3 na część etatu) | największa pozycja, zależy od grantu |
| Sprzęt: stacja z kartą RTX do Isaac Sim, okulary AR, tablet terenowy | 20–40 tys. zł |
| Pilotaż na misji analogowej (dojazd, pobyt, przygotowanie) | 15–30 tys. zł |
| Chmura i przechowywanie danych | kilka tys. zł rocznie |
| Konferencje i publikacja | 10–20 tys. zł |

Dane NASA są darmowe i publiczne, więc nie płacimy za dane źródłowe.

---

## 11. Ryzyka

| Ryzyko | Co robimy |
| --- | --- |
| Mały rynek kosmiczny, długie decyzje agencji | wersja ziemska i misje analogowe jako szybsze źródło przychodu |
| Model ruchu w skafandrze nie jest skalibrowany | pilotaż z pomiarami, progi jako parametry, uczciwe opisy założeń |
| Dawka to model, nie pomiar w każdym miejscu | mówimy to wprost; dodamy powtórkę danych RAD z PDS |
| Duże firmy GIS dodadzą podobną funkcję | skupiamy się na człowieku w terenie i HUD, czyli niszy, której nie obsługują |
| Zespół pracuje dziś po godzinach | inkubator i grant na 1–2 etaty |
| Zależność od sprzętu NVIDIA do symulacji | planer i dashboard działają bez Isaac Sim; symulacja to dodatek |

---

## 12. Wskaźniki sukcesu

- liczba rozmów z użytkownikami i listów intencyjnych,
- różnica czasu i dawki między trasą z planera a prostą linią lub trasą planowaną ręcznie,
- zgodność czasu przejścia z planu z czasem zmierzonym w pilotażu,
- liczba miejsc (wycinków terenu) gotowych w systemie,
- pierwsze płatne wdrożenie.

---

## 13. Najbliższe kroki

1. Wysłać zgłoszenie Space Apps i opublikować film oraz repozytorium.
2. Napisać do 2–3 stacji analogowych z propozycją pilotażu.
3. Przygotować krótką prezentację dla ESA BIC Poland i POLSA.
4. Ustalić w zespole, kto prowadzi rozmowy biznesowe.
