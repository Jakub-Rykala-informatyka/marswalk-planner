# Modele CAD dla Gosi

Lista wszystkich modeli 3D, które trafią do symulacji (Isaac Sim) i do zakładki „Rover planner” w dashboardzie. Dziś zamiast nich stoją proste bryły, więc każdy model od razu poprawia wygląd demo i filmu.

**Termin:** najważniejsze modele (priorytet 1) w sobotę do 24:00, reszta w niedzielę do 8:00. O 8:00 Kuba wstawia je do sceny, a o 10:00 kończymy nowe funkcje.

---

## Jak oddać pliki

- **Format:** każdy model w dwóch plikach: **STEP** (do Isaac Sim, Kuba przekonwertuje go na USD) i **GLB** (do dashboardu w przeglądarce). Jeśli eksport do GLB sprawia kłopot, wystarczy sam STEP.
- **Jednostki:** metry. Model łazika ma mieć wymiary jak w tabelach niżej, a nie np. milimetry przeskalowane później.
- **Osie:** Z w górę, X do przodu pojazdu, Y w lewo.
- **Punkt zerowy:**
  - łazik: środek podwozia, na wysokości gruntu (koła stoją na płaszczyźnie z = 0),
  - osprzęt: środek podstawy, czyli miejsce, którym element dotyka łazika.
- **Nazwy plików:** takie jak identyfikator w kolumnie „Plik”, np. `crew_pressurised.step` i `crew_pressurised.glb`. Te same nazwy są w katalogu łazików (`app/rover_catalog.json`), więc dashboard podmieni bryły automatycznie.
- **Gdzie wrzucić:** do repozytorium, folder `media/cad/` (albo na wspólny dysk, Kuba przeniesie).
- **Rozmiar:** łazik do około 50 tys. trójkątów, element osprzętu do około 5 tys. Laptop z RTX 3050 musi to udźwignąć razem z terenem.
- **Wygląd:** proste kolory materiałów wystarczą, tekstury nie są potrzebne. Bez logo NASA i znaków misji.

---

## Priorytet 1: łazik osobowy z kabiną

To najważniejszy model: łazik, który wozi dwie osoby i jest schronieniem przed burzą słoneczną. Wzorem może być koncepcja NASA Space Exploration Vehicle (ciśnieniowa kabina na podwoziu z sześcioma kołami).

| Plik | Długość | Szerokość | Wysokość podwozia | Koła | Promień koła |
| --- | --- | --- | --- | --- | --- |
| `crew_pressurised` | 6,0 m | 3,0 m | 1,0 m (sama rama) | 6 (3 pary) | 0,55 m |

**Co ma mieć:**
- ciśnieniową kabinę dla dwóch osób w przedniej części, z dużym oknem z przodu,
- śluzę albo właz z tyłu kabiny (astronauci wychodzą na powierzchnię),
- płaski pokład z tyłu na skrzynie z narzędziami,
- **koła jako osobne części**, każde z osią obrotu wzdłuż Y i punktem zerowym w środku koła (żeby mogły się kręcić w symulacji),
- **znaczniki miejsc montażu**, czyli puste obiekty albo małe kostki nazwane tak:
  - `mount_arm_1`, `mount_arm_2`: dwa miejsca na ramiona z przodu,
  - `mount_bay_1` … `mount_bay_6`: sześć miejsc na skrzynie na tylnym pokładzie,
  - `mount_mast_1`, `mount_mast_2`: dwa miejsca na maszt (kamera, antena, lidar),
  - `mount_deck_1`, `mount_deck_2`: dwa miejsca na dachu kabiny (panel słoneczny, radar).

Dzięki znacznikom dashboard i symulacja postawią osprzęt dokładnie tam, gdzie zaprojektujesz.

---

## Priorytet 1: końcówka ramienia do pobierania próbek

Na małym robocie w symulacji jest ramię Unitree Z1, które **nie ma chwytaka**, więc dziś „pobranie próbki” to tylko ruch ramienia. Przyda się końcówka mocowana na koniec ramienia:

| Plik | Co to | Wymiary orientacyjne |
| --- | --- | --- |
| `z1_sample_scoop` | łopatka albo chwytak szczękowy na próbki skał i piasku | około 15 × 8 × 8 cm |

Mocowanie: płaski kołnierz o średnicy około 6 cm, punkt zerowy na środku kołnierza, łopatka skierowana wzdłuż osi X.

---

## Priorytet 1: najczęściej używany osprzęt

Te elementy występują w misji „Boxwork EVA 1”, więc będą widoczne w filmie.

| Plik | Co to | Wymiary orientacyjne | Uwagi |
| --- | --- | --- | --- |
| `sample_box` | skrzynka z 12 szczelnymi pojemnikami na próbki | 40 × 30 × 25 cm | widać pojemniki w środku albo numerowane gniazda |
| `geo_tools` | skrzynka z narzędziami geologicznymi: młotek, łopatka, szczypce, grabie | 40 × 25 × 20 cm | narzędzia mogą wystawać z uchwytów |
| `core_drill` | wiertło rdzeniowe na wieży | podstawa 25 × 25 cm, wysokość 90 cm | wiertło skierowane w dół |
| `o2_tank` | zapasowa butla tlenu dla skafandra | średnica 22 cm, długość 55 cm | leży poziomo, z obejmami |

---

## Priorytet 2: łazik otwarty i reszta osprzętu

Te modele uzupełniają planer łazika. Jeśli zabraknie czasu, zostają proste bryły.

| Plik | Co to | Wymiary orientacyjne | Miejsce montażu |
| --- | --- | --- | --- |
| `crew_open` | łazik otwarty dla dwóch astronautów w skafandrach, bez kabiny | 3,6 × 2,2 m, rama 0,5 m, 4 koła o promieniu 0,45 m | znaczniki: 1 × arm, 4 × bay, 1 × mast, 2 × deck |
| `arm_heavy` | ciężkie ramię robotyczne do skrzyń i próbek na zboczach | zasięg około 2 m | arm |
| `spectrometer` | ręczny spektrometr w uchwycie | 25 × 10 × 10 cm | deck |
| `gpr` | radar do badania podłoża | 60 × 35 × 8 cm | deck (pod łazikiem albo na dachu) |
| `solar_panel` | rozkładany panel słoneczny | 1,0 × 0,7 m po rozłożeniu | deck |
| `pan_cam` | kamera panoramiczna na maszcie | 25 × 10 × 10 cm | mast |
| `lidar` | lidar na maszcie | średnica 10 cm, wysokość 8 cm | mast |
| `comm_relay` | przekaźnik radiowy z anteną talerzową | talerz średnicy 60 cm | mast |
| `suit_battery` | zapasowa bateria do skafandra | 25 × 15 × 10 cm | bay |
| `repair_kit` | zestaw naprawczy skafandra i apteczka | 35 × 25 × 15 cm | bay |
| `winch` | wyciągarka z liną | bęben średnicy 20 cm, długość 30 cm | deck, z przodu |

**Nie trzeba modelować:**
- ramienia Unitree Z1 i małego robota Clearpath Jackal, bo są gotowe w bibliotece Isaac Sim,
- lekkiego ramienia `arm_light`: w symulacji jego rolę gra Z1.

---

## Lista do odhaczenia

- [ ] `crew_pressurised`: łazik osobowy z kabiną, koła osobno, znaczniki montażu
- [ ] `z1_sample_scoop`: końcówka ramienia do próbek
- [ ] `sample_box`
- [ ] `geo_tools`
- [ ] `core_drill`
- [ ] `o2_tank`
- [ ] `crew_open`
- [ ] `arm_heavy`
- [ ] pozostały osprzęt z tabeli priorytetu 2
- [ ] zrzuty ekranu modeli z CAD do slajdów (dla Dominiki i Wanessy)

---

## Do zapamiętania

- Wymiary w tabelach to **wartości koncepcyjne** z naszego katalogu, a nie dane NASA. Jeśli projekt wymaga innych proporcji, zmień je i daj znać Kubie, to poprawi katalog.
- Zrzuty modeli z Inventora albo CATII przydadzą się na slajd 6 („Safety and robots”) i do filmu.
- Pytania o mocowania i osie: Kuba.

---

## Aktualizacja: modele Gosi w podglądzie

Modele GLB z archiwum Gosi są w `app/cad/`. Podgląd w zakładce „Rover planner” ładuje je zamiast prostych brył:
- **Kadłub łazika osobowego i otwartego:** pełny model zastępuje podwozie, koła i kabinę. Koła i podwozie z osobnych plików (`*_chassis`, `*_wheel`) są w archiwum, ale do podglądu nie są potrzebne.
- **Osprzęt:** każdy element stoi podstawą na swoim miejscu montażu.
- **Jednostki:** modele są w centymetrach, dashboard przelicza je na metry (× 0,01).

Pliki `.ipt` (Inventor) i `OldVersions` nie idą do repozytorium. Katalog Gosi `cad/rover_catalog.json` ma inny format niż `app/rover_catalog.json` i nie jest jeszcze używany: do decyzji, który katalog zostaje.


---

## Aktualizacja: złożone łaziki

Gotowe pliki `crew_pressurised` i `crew_open` z archiwum nie pasowały do części: kabina była szersza od podwozia i schodziła w koła, koła miały inną szerokość niż `*_wheel`, a znaczniki montażu nazywały się „Bryła2…” zamiast `mount_*`. Łaziki są teraz składane z części skryptem `cad/assemble_rovers.py`:

- podwozie `*_chassis` plus koła `*_wheel` (6 albo 4), 5 cm od boku podwozia, oś koła na wysokości promienia,
- znaczniki przemianowane na `mount_arm_1`, `mount_bay_1` … według tabel wyżej,
- wynik: `cad/crew_pressurised.step` i `cad/crew_open.step` (jedna część z wieloma bryłami, jak eksport z Inventora) oraz `app/cad/crew_*.glb` dla dashboardu (oś Y w górę, metry).

Części źródłowe są w `cad/parts/`. Jeśli poprawisz podwozie albo koło, podmień plik w `cad/parts/` i uruchom skrypt jeszcze raz.
