# Marswalk Planner: plan działania zespołu

Stan na sobotę 14.11.2026, godz. 15:05. Godziny niedzielne są ustawione pod oddanie około 13:00. **Wpiszcie tu prawdziwy termin oddania i przesuńcie niedzielę pod niego.**

---

## Co oddajemy

| Rzecz | Kto odpowiada | Wersja minimalna |
| --- | --- | --- |
| Aplikacja: ekran habitatu i tryb HUD | Gosia | mapa z 3 warstwami, trasa, panel budżetu |
| Symulacja w Isaac Sim | Kuba | przelot kamerą po trasie na terenie z DTM |
| Dane na żywo (ROS 2) | Rafał, pomaga Kuba | udawane czujniki skafandra widoczne w HUD-zie |
| Film 30 sekund | Dominika i Wanessa | nagranie ekranu aplikacji z lektorem |
| Prezentacja 7 slajdów | Dominika i Wanessa | 7 slajdów według układu niżej |
| Zgłoszenie na stronie Space Apps | Dominika i Wanessa | opis projektu, link do repozytorium, lista danych NASA |

---

## Kolejność ważności

Gdy brakuje czasu, tniemy od dołu.

1. **Musi być:** mapa z co najmniej trzema warstwami danych NASA, trasa omijająca przeszkody, budżet tlenu i dawki, film i slajdy.
2. **Powinno być:** HUD w okularach XREAL One z danymi na żywo, przelot w Isaac Sim, mapa schronień.
3. **Jeśli zostanie czas:** łazik z ruchem ramienia, scenariusz burzy słonecznej, wykrywanie głazów, broker MQTT.

**Wykrywanie głazów i modele CAD nie mają dziś właściciela.** Bierzemy gotowe modele (łazik i ramię z zasobów Isaac Sim, modele 3D NASA). Głazy pomijamy albo zastępujemy warstwą szorstkości z DTM.

---

## Ustalenia na start (15:00–16:00, wszyscy)

To jest najważniejsza godzina. Dzięki tym ustaleniom każdy pracuje dalej bez czekania na innych.

- **Jedno repozytorium** z folderami: `data/`, `planner/`, `ros/`, `sim/`, `app/`, `media/`.
- **Jeden wycinek terenu.** Kuba wybiera DTM HiRISE nad rejonem boxwork i podaje jego granice.
- **Jeden układ współrzędnych:** metry w układzie lokalnym, początek w południowo-zachodnim rogu wycinka, x na wschód, y na północ.
- **Format warstw:** obrazy PNG o tym samym rozmiarze co DTM plus `data/meta.json` (granice, rozdzielczość, lista warstw).
- **Format trasy:** `data/route.geojson` z punktami trasy i celami naukowymi. Każdy cel ma: nazwę, wykonawcę (człowiek, ramię łazika, razem) i wymagane narzędzia.
- **Format danych na żywo:** jedna wiadomość JSON przez WebSocket, kilka razy na sekundę:

```json
{
  "t": 123.4,
  "astronaut": {"x": 512.0, "y": 830.5, "heading_deg": 74},
  "rover": {"x": 498.2, "y": 815.0, "state": "sampling"},
  "suit": {"o2_pct": 81, "battery_pct": 77, "dose_uSv": 12.4},
  "next_target": {"name": "Boxwork 1", "dist_m": 140, "bearing_deg": 62},
  "return": {"dist_m": 620, "o2_margin_pct": 35},
  "alert": {"sep": false, "shelter": {"x": 530, "y": 790, "eta_s": 95}}
}
```

- **Zasada udawanych danych:** w pierwszym bloku Rafał wystawia tę wiadomość z danymi zmyślonymi, a Kuba daje przykładowe warstwy i trasę. Gosia buduje aplikację na nich, a prawdziwe dane podmieniamy później bez zmian w aplikacji.

---

## Harmonogram

### Sobota

| Godziny | Kuba | Rafał | Gosia | Dominika i Wanessa |
| --- | --- | --- | --- | --- |
| 15:00–16:00 | ustalenia, wybór DTM | ustalenia, repozytorium | ustalenia, szkielet aplikacji | ustalenia, historia do pokazania |
| 16:00–19:00 | DTM przycięty, warstwy: nachylenie, szorstkość, widoczność nieba | serwer WebSocket z udawaną wiadomością, potem węzły ROS 2 czujników skafandra | mapa z podkładem, przełączanie warstw na przykładowych plikach | scenariusz filmu, szkic 7 slajdów, tekst opisu projektu |
| 19:00–22:00 | teren w Isaac Sim (siatka z teksturą), kamera astronauty | A* na mapie kosztów, zapis trasy do GeoJSON | trasa i cele na mapie, panel budżetu, szkielet HUD-u | grafiki, slajdy 1–4, lista danych NASA do zgłoszenia |
| **22:00** | **Punkt kontrolny 1** | | | |
| 22:00–24:00 | most Isaac Sim ↔ ROS 2: pozycja astronauty i łazika | prawdziwa pozycja zamiast udawanej, licznik dawki i tlenu | HUD podłączony do danych na żywo, test w okularach | pierwsze nagrania ekranu, lektor na próbę |

**Punkt kontrolny 1 (22:00):** aplikacja pokazuje prawdziwe warstwy i trasę z planera, a HUD dostaje wiadomości z serwera. Jeśli czegoś brakuje, to właśnie to robimy do północy, a rzeczy z listy „jeśli zostanie czas” odpadają.

**Noc:** śpimy. Zmęczony zespół psuje demo w niedzielę rano.

### Niedziela

| Godziny | Kuba | Rafał | Gosia | Dominika i Wanessa |
| --- | --- | --- | --- | --- |
| 8:00–10:00 | łazik w scenie, ruch ramienia, nagranie przelotu | scenariusz burzy słonecznej, droga do schronienia | poprawki wyglądu, tryb alertu w HUD-zie | nagranie osoby w okularach, slajdy 5–7 |
| **10:00** | **Punkt kontrolny 2: koniec nowych funkcji** | | | |
| 10:00–11:30 | pomoc przy nagraniach, zapasowe wideo symulacji | próba całego demo, poprawki błędów | próba całego demo, poprawki błędów | montaż filmu, ostatnia wersja slajdów |
| 11:30–12:30 | porządek w repozytorium, README | porządek w repozytorium | zrzuty ekranu do zgłoszenia | wypełnienie zgłoszenia |
| 12:30–13:00 | wspólne sprawdzenie zgłoszenia i wysłanie | | | |

**Punkt kontrolny 2 (10:00):** po tej godzinie nikt nie zaczyna nowych funkcji. Naprawiamy tylko to, co widać w filmie i w demo.

---

## Zadania według osób

### Kuba: symulacja i dane terenu

1. Pobrać DTM i ortofoto HiRISE, przyciąć do wycinka około 2 × 2 km.
2. Policzyć warstwy: nachylenie, szorstkość, widoczność nieba. Zapisać jako PNG z `meta.json`.
3. Zamienić DTM na siatkę z teksturą i wczytać do Isaac Sim.
4. Kamera prowadzona po `route.geojson` na wysokości oczu astronauty.
5. Most do ROS 2: pozycja astronauty i łazika.
6. Łazik i ramię z gotowych zasobów, jeden odtwarzany ruch ramienia.
7. Nagranie przelotu do pliku wideo, najpóźniej w niedzielę o 10:00.

**Pierwsze dwa punkty są najpilniejsze, bo czeka na nie Rafał (planer) i Gosia (warstwy).**

### Rafał: ROS 2 i planer

1. Serwer WebSocket z udawaną wiadomością, gotowy w pierwszej godzinie.
2. Węzły ROS 2 udające czujniki skafandra: tlen, bateria, dawka.
3. Mapa kosztów z warstw Kuby i A* przez cele naukowe. Wynik w `route.geojson`.
4. Licznik dawki: dawka bazowa razy widoczność nieba w aktualnej pozycji.
5. Zapas na powrót: odległość do łazika i zapas tlenu.
6. Scenariusz burzy słonecznej: alert i najbliższe schronienie.

### Gosia: aplikacja

1. Ekran habitatu: mapa, przełączniki warstw, legenda.
2. Trasa i cele naukowe z `route.geojson`, z wykonawcą i narzędziami przy każdym celu.
3. Panel budżetu: czas, dystans, tlen, dawka.
4. Tryb HUD: osobna strona na pełny ekran, **jasne elementy na czarnym tle** (czarne jest w okularach przezroczyste), duże napisy, mało elementów.
5. HUD pokazuje: kierunek i odległość do celu, tlen, zapas na powrót, najbliższe schronienie, alert.
6. Test w okularach XREAL One już w sobotę wieczorem, nie w niedzielę.

### Dominika i Wanessa: film, slajdy, zgłoszenie

1. Ustalić jedną historię: astronautka wychodzi po próbki formacji skrzynkowych, w połowie przychodzi alert burzy słonecznej.
2. Slajdy i film według układów poniżej.
3. Tekst opisu projektu na podstawie `raport_marswalk_planner.md`.
4. Lista użytych danych i narzędzi NASA oraz informacja o użyciu AI, jeśli zasady tego wymagają.
5. Zbierać materiał na bieżąco: zrzuty ekranu po każdym punkcie kontrolnym, nagranie osoby w okularach.

---

## Układ 7 slajdów

1. **Tytuł:** nazwa, jedno zdanie, zespół.
2. **Problem:** dane o Marsie są w skali planety, a spacer ma kilka kilometrów.
3. **Rozwiązanie:** jedna mapa z warstwami i trasa dla człowieka w skafandrze.
4. **Dane NASA:** tabela warstw i misji, z których pochodzą.
5. **Bezpieczeństwo:** mapa schronień, zapas na powrót, alert burzy słonecznej.
6. **Demo:** ekran habitatu, HUD w okularach, kadr z Isaac Sim, łazik z ramieniem.
7. **Dla kogo i co dalej:** planiści wyjść, astronauci, Księżyc, misje analogowe.

## Układ filmu 30 sekund

| Sekundy | Obraz | Lektor |
| --- | --- | --- |
| 0–5 | Mars z orbity, zbliżenie na Mount Sharp | problem w jednym zdaniu |
| 5–13 | ekran habitatu: warstwy włączane po kolei, pojawia się trasa | co robi mapa |
| 13–20 | osoba w okularach, widok HUD-u, alert burzy i strzałka do schronienia | bezpieczeństwo |
| 20–27 | przelot w Isaac Sim, łazik sięga ramieniem po próbkę | łazik wsparcia |
| 27–30 | nazwa projektu i zespół | jedno zdanie na koniec |

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

## Do sprawdzenia u organizatorów

- dokładny termin i forma oddania,
- czy film i slajdy są wymagane oba, czy do wyboru,
- czy trzeba opisać użycie narzędzi AI,
- czy repozytorium ma być publiczne.
