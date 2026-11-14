# Marswalk Planner: plan działania zespołu

Stan na sobotę 14.11.2026, godz. 17:45.

**Termin globalny: niedziela 15.11, godz. 23:59 czasu lokalnego** (przycisk „Submit for Judging”). Ocena lokalna w Stalowej Woli może być wcześniej. Godziny niedzielne w tym planie zakładają pokaz lokalny około 13:00. **Zapytajcie organizatora lokalnego o godzinę i przesuńcie niedzielę pod nią.**

---

## Podział pracy

| Osoba | Zakres |
| --- | --- |
| **Kuba** | symulacja w Isaac Sim, dane terenu, aplikacja (dashboard), most do ROS 2 |
| **Rafał** | HUD w okularach XREAL One, węzły ROS 2 (mapa kosztów, planer, czujniki skafandra), razem z Kubą |
| **Gosia** | CAD łazików: narzędzia i ramiona robotyczne na łaziku, nadwozie łazika osobowego |
| **Dominika i Wanessa** | film 30 sekund, prezentacja 7 slajdów, zgłoszenie na stronie Space Apps |

Kuba ma teraz najwięcej zadań. Jeśli zabraknie czasu, pierwsze do oddania Rafałowi są węzły ROS 2 (mapa kosztów i planer).

---

## MVP: dashboard połączony z robotem

**Stan: działa.** Symulacja publikuje pozycje do ROS 2, serwer przekazuje je przez WebSocket, a dashboard pokazuje je na mapie z warstwami.

| Element | Stan |
| --- | --- |
| Teren Gale z DTM HiRISE w Isaac Sim, z fizyką | gotowe |
| Astronauta idzie po trasie, łazik jedzie za nim | gotowe |
| Tematy ROS 2: `/astronaut/pose`, `/rover/pose`, `/rover/state`, `/clock` | gotowe |
| Serwer telemetrii (ROS 2 → WebSocket) | gotowe |
| Dashboard: mapa, warstwy, trasa, pozycje na żywo | gotowe |
| Warstwy: nachylenie, szorstkość, widoczność nieba | gotowe |
| Trzeci rodzaj danych: dawka promieniowania z RAD × widoczność nieba | gotowe |
| Warstwy NASA jako tematy ROS `/nasa/*` | gotowe |
| Dawka astronauty na żywo (`/astronaut/dose_rate`, `/astronaut/dose`) | gotowe |
| Mapy kosztów `/costmap/walk` i `/costmap/rover` z warstw `/nasa/*`, parametry ROS | gotowe |
| Planer A* na `/costmap/walk`, trasa `/route` z budżetem (długość, czas, dawka) | gotowe |
| Nowy cel kliknięciem w mapę, symulacja zmienia trasę w trakcie przejścia | gotowe |
| Budżet skafandra: tlen, bateria, droga powrotu do łazika, alert „turn back” (`/suit/status`) | gotowe |
| Dashboard 3D w Three.js zamiast mapy 2D | gotowe |
| Lidar na łaziku (`/rover/points`) nałożony na widok 3D | gotowe |
| Kamery kasku i łazika w ROS 2, druga zakładka dashboardu z nakładką HUD | gotowe |

Uruchomienie:

```bash
./scripts/run_dashboard.sh   # dashboard na http://localhost:8080
./scripts/run_sim.sh         # Isaac Sim z publikacją do ROS 2
```

### Co dalej, w kolejności

1. ~~Trzeci rodzaj danych~~: zrobione. Mamy wysokości i zdjęcia z HiRISE oraz promieniowanie z RAD.
2. ~~Mapa kosztów na tematach ROS~~: zrobione. Węzeł `costmap` subskrybuje `/nasa/*` i publikuje `/costmap/walk` i `/costmap/rover`; wagi i limity zmienia się parametrami ROS na żywo.
3. ~~Planer na tematach ROS~~: zrobione. Węzeł `planner` publikuje `/route` i `/route/summary`; cel ustawia się kliknięciem w mapę na dashboardzie.
4. ~~Budżet wyjścia~~: zrobione. Węzeł `suit_monitor` publikuje `/suit/status`. Rafał może brać te same pola do HUD-u w okularach.
5. **HUD.** Osobna strona na czarnym tle, zasilana tym samym WebSocketem co dashboard.
6. **Łazik osobowy i ramię** w symulacji.
7. **Scenariusz burzy słonecznej.**

---

## Dwa łaziki

| Łazik | Rola | W symulacji |
| --- | --- | --- |
| **Łazik osobowy** (ciśnieniowy, ok. 3,5 m) | wozi załogę i zapasy na miejsce, jest schronieniem przed burzą słoneczną i punktem bezpiecznego powrotu | jeszcze nie; jest szkic podwozia 6-kołowego, nadwozie zrobi Gosia w CAD |
| **Robot pomocnik** (Clearpath Jackal, 0,5 m) | jedzie za astronautą, niesie narzędzia, sięga ramieniem w miejsca zakazane dla człowieka | jeździ; ramię i narzędzia dojdą z CAD Gosi |

**Jak łazik osobowy zmienia mapę:**
- są dwie mapy kosztów: dla jazdy (szybko, ale tylko po łagodnym terenie) i dla marszu (wolno, ale w trudniejszy teren),
- trasa jest łączona: dojazd łazikiem do miejsca postoju, ostatni odcinek pieszo,
- planer wybiera miejsce postoju tak, żeby powrót pieszo mieścił się w zapasie tlenu,
- w kabinie dawka i zużycie zapasów skafandra są mniejsze, więc budżet wyjścia liczy osobno jazdę i marsz.

**Od Gosi potrzebne są** modele w formacie STEP albo USD, w metrach: nadwozie łazika osobowego, ramię i skrzynia z narzędziami dla robota pomocnika. Fizyka zostaje prosta (rama i koła), a modele CAD są nakładane jako wygląd.

---

## Kolejność ważności

Gdy brakuje czasu, tniemy od dołu.

1. **Musi być:** mapa z co najmniej trzema rodzajami danych NASA, trasa omijająca przeszkody, budżet tlenu i dawki, film i slajdy.
2. **Powinno być:** mapa kosztów i planer na tematach ROS, HUD w okularach z danymi na żywo, przelot w Isaac Sim, mapa schronień.
3. **Jeśli zostanie czas:** łazik osobowy w symulacji, ruch ramienia, scenariusz burzy słonecznej, wykrywanie głazów.

---

## Wspólne ustalenia

- **Jedno repozytorium:** `data/`, `planner/`, `ros/`, `sim/`, `app/`, `media/`, `docs/`.
- **Jeden wycinek terenu:** 2072 × 2072 m na zboczu Mount Sharp, opisany w `data/meta.json`.
- **Jeden układ współrzędnych:** metry w układzie lokalnym, początek w południowo-zachodnim rogu wycinka, x na wschód, y na północ, z w górę.
- **Warstwy:** `data/layers/*.npy` (liczby, wiersz 0 to południe) i `*.png` (obraz, wiersz 0 to północ).
- **Trasa:** GeoJSON w układzie lokalnym, na razie `data/route_example.geojson`.
- **Tematy ROS 2:** opisane w `ros/README.md`, domena DDS 43.
- **Dane na żywo dla przeglądarki:** jedna wiadomość JSON przez WebSocket `ws://localhost:8080/ws`, pięć razy na sekundę (pole `suit` pojawia się, gdy działa `dose_monitor`):

```json
{
  "live": true,
  "t": 123.4,
  "astronaut": {"x": 1126.0, "y": 810.0, "z": 307.7, "heading_deg": -136.0},
  "rover": {"x": 1129.0, "y": 813.0, "z": 307.5, "heading_deg": -131.0, "state": "following"},
  "rover_distance_m": 4.7,
  "suit": {"dose_rate_uSv_h": 26.4, "dose_uSv": 0.52}
}
```

Pozostałe pola budżetu (tlen, zapas na powrót, alert) dojdą do tej wiadomości, gdy powstaną węzły, które je liczą. HUD Rafała może już teraz czytać pozycje z tego samego adresu.

---

## Harmonogram

### Sobota

| Godziny | Kuba | Rafał | Gosia | Dominika i Wanessa |
| --- | --- | --- | --- | --- |
| do 20:00 | warstwa dawki, mapa kosztów na tematach ROS | szkielet HUD-u na WebSocket, test w okularach | nadwozie łazika osobowego | scenariusz filmu, slajdy 1–4, tekst opisu po angielsku |
| 20:00–22:00 | planer na tematach, trasa z `/route` w symulacji i na dashboardzie | HUD: kierunek do celu, odległość do łazika | ramię i narzędzia dla robota pomocnika | grafiki, lista danych NASA do zgłoszenia |
| **22:00** | **Punkt kontrolny 1** | | | |
| 22:00–24:00 | budżet wyjścia na dashboardzie | czujniki skafandra jako węzły ROS 2 | eksport modeli do STEP | pierwsze nagrania ekranu |

**Punkt kontrolny 1 (22:00):** trzy rodzaje danych na mapie, trasa z planera na dashboardzie, HUD pokazuje pozycje na żywo. Jeśli czegoś brakuje, to właśnie to robimy do północy, a rzeczy z listy „jeśli zostanie czas” odpadają.

**Noc:** śpimy. Zmęczony zespół psuje demo w niedzielę rano.

### Niedziela

| Godziny | Kuba | Rafał | Gosia | Dominika i Wanessa |
| --- | --- | --- | --- | --- |
| 8:00–10:00 | modele Gosi w scenie, nagranie przelotu | scenariusz burzy słonecznej, alert w HUD-zie | poprawki modeli | nagranie osoby w okularach, slajdy 5–7 |
| **10:00** | **Punkt kontrolny 2: koniec nowych funkcji** | | | |
| 10:00–11:30 | próba całego demo, zapasowe wideo | próba całego demo | zrzuty modeli do slajdów | montaż filmu, ostatnia wersja slajdów |
| 11:30–12:30 | porządek w repozytorium, README, repozytorium publiczne | porządek w repozytorium | pomoc przy slajdach | wypełnienie zgłoszenia |
| 12:30–13:00 | wspólne sprawdzenie zgłoszenia i wysłanie | | | |

**Punkt kontrolny 2 (10:00):** po tej godzinie nikt nie zaczyna nowych funkcji. Naprawiamy tylko to, co widać w filmie i w demo.

---

## Układ 7 slajdów

Slajdy muszą być po angielsku. Limit to 7 slajdów razem z tytułowym.

1. **Tytuł:** nazwa projektu, jedno zdanie, nazwa zespołu, imiona członków, nazwa wybranego zadania (wszystko to jest wymagane).
2. **Problem:** dane o Marsie są w skali planety, a spacer ma kilka kilometrów.
3. **Rozwiązanie:** jedna mapa z warstwami i trasa dla człowieka w skafandrze.
4. **Dane NASA:** tabela warstw i misji, z których pochodzą.
5. **Bezpieczeństwo:** mapa schronień, zapas na powrót, alert burzy słonecznej.
6. **Demo:** ekran habitatu, HUD w okularach, kadr z Isaac Sim, łazik z ramieniem.
7. **Dla kogo i co dalej:** planiści wyjść, astronauci, Księżyc, misje analogowe.

## Układ filmu 30 sekund

Układ idzie za wzorem z przewodnika Space Apps. Film może być po polsku, ale **musi mieć angielskie napisy**. Limit to 30 sekund i ani sekundy więcej.

| Sekundy | Co mówi przewodnik | Obraz | Lektor |
| --- | --- | --- | --- |
| 0–2 | przedstaw się | zespół albo plansza z nazwą zespołu | kto mówi i nazwa zespołu |
| 2–5 | zadanie i inspiracja | Mars z orbity, zbliżenie na Mount Sharp | które zadanie i dlaczego |
| 5–10 | nazwa projektu i hasło | plansza „Marswalk Planner” | nazwa i jedno zdanie |
| 10–20 | jak to działa, dane NASA | ekran habitatu z warstwami i trasą, potem HUD w okularach z alertem burzy | co robi mapa i z jakich danych NASA |
| 20–30 | spojrzenie w przyszłość | przelot w Isaac Sim, łazik sięga ramieniem po próbkę | co to daje załodze na Marsie i na Księżycu |

---

## Ryzyka

| Ryzyko | Co robimy |
| --- | --- |
| Pobieranie DTM trwa długo albo plik jest za duży | zacząć pobieranie o 15:00, w razie problemu wziąć DEM z Mars Trek o gorszej rozdzielczości |
| Isaac Sim nie wyrabia na RTX 3050 | mniejszy wycinek, rzadsza siatka, nagranie klatka po klatce zamiast na żywo |
| Okulary nie działają z laptopem | sprawdzić dziś; zapasowo HUD pokazany na ekranie i nagrany przez okulary telefonem |
| Most Isaac Sim ↔ ROS 2 sprawia kłopoty | pozycja astronauty odtwarzana z `route.geojson` przez węzeł Rafała, bez symulatora |
| Aplikacja czeka na dane | udawane dane od pierwszej godziny, ten sam format co prawdziwe |
| Demo na żywo zawodzi | wszystko nagrane jako wideo do niedzieli 10:00 |

---

## Zasady zgłoszenia

Źródło: przewodnik „Project Submission Guide” na stronie Space Apps (wersja z 13.11.2026).

**Termin i forma**
- Zgłoszenie zamyka się w niedzielę 15.11 o 23:59 czasu lokalnego. Liczy się kliknięcie „Submit for Judging”.
- Można zapisywać i zgłaszać wiele razy. Sędziowie widzą ostatnią zapisaną wersję.
- **Wszystko w formularzu i w podlinkowanych materiałach musi być po angielsku.** Wyjątek: film może być w innym języku, jeśli ma angielskie napisy.

**Demo**
- W formularzu jest jedno pole na demo: **film do 30 sekund albo prezentacja do 7 slajdów**. Wystarczy jedno z dwóch.
- Przekroczenie limitu wyklucza projekt z oceny globalnej.
- Film i slajdy trzeba wgrać na zewnętrzny serwis (YouTube, Dysk Google, GitHub) i podać link publiczny.

**Linki**
- Każdy link musi działać **bez logowania, hasła i próśb o dostęp**. Przed zgłoszeniem sprawdzić w oknie prywatnym przeglądarki.
- Z tego wynika, że **repozytorium na GitHubie musi być publiczne najpóźniej w chwili zgłoszenia**.
- Na samą stronę projektu można wgrać tylko obrazy (JPG, PNG, GIF do 10 MB).

**Pola formularza do wypełnienia**
- nazwa projektu,
- krótkie podsumowanie,
- link do demo,
- link do gotowego projektu,
- szczegółowy opis (co robi, jak działa, korzyści, narzędzia i języki),
- użycie AI,
- dane NASA (co najmniej jedno źródło NASA, żeby walczyć o nagrodę globalną),
- dane agencji partnerskich i pozostałe źródła (kod, teksty, obrazy, także otwarte).

**Użycie AI**
- AI jest dozwolone jako narzędzie. Według zasad **nie powinno wymyślać pomysłu na rozwiązanie**.
- Trzeba wskazać, gdzie i jak było użyte.
- Obrazy i filmy z AI muszą mieć widoczny znak wodny.
- Dźwięk, kod i dane z AI trzeba oznaczyć w opisie i w metadanych.
- Materiały z AI nie mogą zawierać logo NASA, flag ani znaków misji.

**Inne**
- W filmie i materiałach nie może być osób poniżej 18 lat.
- Wszyscy członkowie zespołu muszą być potwierdzonymi uczestnikami tego samego wydarzenia lokalnego.
- Kryteria oceny: wpływ, kreatywność, poprawność, związek z zadaniem, prezentacja.

## Do sprawdzenia u organizatora lokalnego

- godzina i forma oceny lokalnej w Stalowej Woli (pokaz na żywo czy tylko zgłoszenie).
