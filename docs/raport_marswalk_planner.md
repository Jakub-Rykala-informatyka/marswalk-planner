# Marswalk Planner: raport z NASA Space Apps Challenge 2026

Stalowa Wola, 14–15 listopada 2026. Zadanie: *Interplanetary Survival Guide: Martian Map* (treść w `task.md`).

---

## Czym się zajmowaliśmy

Zbudowaliśmy **Marswalk Planner**: narzędzie do planowania i prowadzenia pieszego wyjścia astronautów (EVA) na powierzchni Marsa.

**Miejsce: Gale, zbocze Mount Sharp, rejon formacji skrzynkowych (boxwork).** Wybraliśmy je z trzech powodów:
- tę okolicę w 2025 roku badał łazik Curiosity, więc jest dużo danych z orbity i z powierzchni,
- Curiosity ma przyrząd RAD, jedyny, który mierzył promieniowanie **na powierzchni** Marsa,
- jego trasa jest dowodem, że ten teren da się przejechać, więc mamy punkt odniesienia dla naszej trasy.

**Co powstało w ramach hackathonu:**
- **Potok danych** w Pythonie. Pobiera i przycina dane NASA dla wycinka o boku kilku kilometrów i zamienia je w warstwy mapy.
- **Planer trasy.** Mapa kosztów z ruchem człowieka w skafandrze plus algorytm A* przez punkty naukowe.
- **Ekran w habitacie.** Aplikacja w przeglądarce z warstwami 2D, widokiem 3D i budżetem misji.
- **Tryb HUD.** Uproszczony widok na szybę hełmu, używany w trakcie wyjścia.
- **Łazik wsparcia.** Model łazika z ramieniem robotycznym i zestawem narzędzi do wyjścia, włączony do planu trasy.
- **Przelot w Isaac Sim.** Trasa oglądana z perspektywy astronauty, nagrana jako wideo.

**Podział pracy w zespole:**
- Jakub (Head of Software): potok danych terenu i scena w Isaac Sim, pomoc przy ROS 2. Ma do tego dwa przygotowania:
  - z pracy inżynierskiej, w której Nav2 prowadzi robota Unitree Go2 w Isaac Sim: mapy kosztów, planowanie ruchu i scenę w Isaac Sim,
  - ze Smooth Mappera z HackYeah 2026: przejście od surowych danych do działającej mapy w przeglądarce w czasie hackathonu.
- Rafał: ROS 2, czyli węzły czujników skafandra, planer trasy i dane na żywo dla aplikacji. Pracował razem z Jakubem.
- Gosia: aplikacja w przeglądarce, czyli ekran habitatu i tryb HUD.
- Dominika i Wanessa: film prezentacyjny (30 sekund), prezentacja (7 slajdów) i zgłoszenie projektu.

---

## Problem

**Dane o Marsie są, ale nie w skali spaceru.** Mars Trek i mapy geologiczne USGS pokazują region albo całą planetę. Pojedyncze wyjście to kilka kilometrów i kilka godzin. Na takim obszarze liczy się każdy klif, pole piasku i głaz.

**Każda warstwa leży w innym miejscu.** Rzeźba terenu jest w HiRISE, minerały w CRISM, rodzaj podłoża w THEMIS, a promieniowanie i pogoda w danych łazika. Planista musi sam złożyć te dane w głowie. Nikt nie podaje ich razem jako odpowiedzi na pytanie: *którędy iść?*

**Narzędzia dla łazików nie pasują do ludzi.** Łazik:
- jedzie powoli,
- nie męczy się,
- nie zużywa tlenu,
- nie dostaje dawki promieniowania, która ogranicza karierę astronauty.

Człowiek w skafandrze ma inne limity:
- **nachylenie:** w ciężkim skafandrze, z gorszym wyczuciem gruntu, strome zbocze męczy i grozi upadkiem,
- **zapasy:** tlen i energia skafandra wyznaczają, jak daleko wolno odejść,
- **promieniowanie:** dawka zależy od czasu na zewnątrz i od tego, jak bardzo teren zasłania niebo,
- **pogoda kosmiczna:** przy burzy słonecznej (SEP) załoga ma minuty na dojście do schronienia.

**Bezpieczeństwo jest na pierwszym miejscu, ale nauka też.** Wyjście ma sens tylko wtedy, gdy dojdzie do ciekawych celów. Trzeba więc równoważyć ryzyko i wartość naukową, a nie tylko szukać najbezpieczniejszej drogi.

---

## Rozwiązanie

**Jedna mapa, która odpowiada na pytanie „którędy i kiedy iść”.** Łączymy dane z kilku misji NASA w warstwy dla małego obszaru, a z warstw liczymy trasę dla człowieka, nie dla łazika.

### Trzy pomysły w centrum rozwiązania

**1. Mapa kosztów dla człowieka w skafandrze.**
Każda komórka terenu dostaje koszt przejścia. Koszt uwzględnia:
- nachylenie,
- szorstkość terenu,
- głazy,
- luźny piasek,
- dawkę promieniowania.

Prędkość marszu liczymy zmodyfikowaną funkcją Toblera (wzorem na tempo pieszej wędrówki). Uwzględnia ona grawitację Marsa (0,38 g) i masę skafandra ze sprzętem. Powyżej progu nachylenia komórka jest zakazana.

**2. Mapa schronień przed promieniowaniem.**
Dawka od promieniowania kosmicznego zależy od tego, ile nieba widać nad głową. Na płaskim terenie połowę nieba zasłania już sama planeta. Pod klifem albo w wąskim kanionie zasłonięte jest więcej. Z modelu terenu liczymy, jaka część nieba jest widoczna w każdym punkcie, i mnożymy to przez dawkę zmierzoną przez RAD. Wychodzi mapa miejsc, w których dawka jest wyraźnie mniejsza. **Takiej warstwy nie ma w Mars Trek.**

**3. Bezpieczny powrót w każdej chwili.**
Planer pilnuje dwóch ograniczeń. Z każdego punktu trasy da się wrócić do łazika ciśnieniowego z zapasem tlenu (zasada znana z misji Apollo). Do schronienia da się dojść w czasie krótszym niż czas ostrzeżenia przed burzą słoneczną.

### Jak wygląda praca z narzędziem

- **Przed wyjściem**, w habitacie: zespół wybiera cele naukowe, a planer proponuje trasę, czas, dawkę i zużycie zapasów.
- **W trakcie wyjścia**, na HUD-zie: kierunek do celu, zapas na powrót, najbliższe schronienie i alerty.
- **Para astronautów.** Planer pozwala rozdzielić cele między dwie osoby, żeby zrobić więcej nauki w tym samym czasie.

### Łazik z ramieniem i zestawem narzędzi

Łazik jest trzecim członkiem zespołu, a nie tylko pojazdem. Ma w planie cztery role:

- **Sięga tam, gdzie człowiek nie powinien wchodzić.** Gdy cel leży na zboczu albo w polu głazów oznaczonym jako zakaz, łazik podjeżdża do krawędzi i pobiera próbkę ramieniem.
- **Skraca czas na zewnątrz.** Ramię wierci, pakuje i odkłada próbki, a astronauta idzie do następnego celu. Krótszy postój to mniejsza dawka i mniejsze zużycie tlenu.
- **Niesie narzędzia i zapasy.** Astronauta idzie lżejszy, więc model ruchu liczy mu większą prędkość.
- **Jest ruchomym schronieniem i punktem powrotu.** Do niego liczymy bezpieczny powrót i drogę ucieczki przy burzy słonecznej.

Planer przypisuje każdemu celowi wykonawcę: **człowiek**, **ramię łazika** albo **razem**. Sprawdza też, czy na łaziku są narzędzia potrzebne przy tym celu.

---

## Jak to działa

### Dane

| Rodzaj danych | Źródło (misja / przyrząd) | Rozdzielczość | Co z nich liczymy |
| --- | --- | --- | --- |
| Wysokościowe | MRO HiRISE, numeryczny model terenu (DTM) | ok. 1 m | nachylenie, szorstkość, widoczność nieba, profil trasy |
| Wysokościowe (tło) | MRO CTX, MGS MOLA | ok. 6 m / 463 m | kontekst wokół wycinka |
| Optyczne | MRO HiRISE, ortofotomapa | ok. 25 cm | podkład mapy, wykrywanie głazów |
| Termiczne | Mars Odyssey THEMIS, inercja termiczna | ok. 100 m | luźny piasek (niska inercja) lub lita skała (wysoka) |
| Widmowe | MRO CRISM, parametry mineralne | ok. 18 m | cele naukowe: minerały uwodnione, siarczany |
| Geologiczne | mapy geologiczne USGS | jednostki geologiczne | kontekst celów naukowych |
| Radiacyjne | Curiosity RAD | pomiar punktowy na powierzchni | bazowa dawka (ok. 0,64 mSv na sol) |
| Pogoda kosmiczna | NASA DONKI (baza zdarzeń pogody kosmicznej) | zdarzenia | scenariusze burzy słonecznej |
| Atmosferyczne | Curiosity REMS | pomiar punktowy | temperatura, ciśnienie, UV w ciągu sola |
| Z powierzchni | zdjęcia Mastcam i Navcam z Curiosity | zdjęcia | podgląd „czego się spodziewać” w punktach trasy |
| Trasa referencyjna | ślad przejazdu Curiosity | GeoJSON | porównanie i potwierdzenie przejezdności |

**Rozdzielczość jest różna i to mówimy wprost.** THEMIS i CRISM są dużo grubsze niż HiRISE, więc traktujemy je jako tło dla wycinka, a nie jako dane dokładne co do metra.

### Zasoby od organizatorów (`nasa_data.md`)

- **Mars Trek (JPL):** portal NASA z danymi z miejsc lądowań. Bierzemy z niego podkłady i warstwy dla Gale. Udostępnia też kafelki mapy (WMTS), które frontend wczytuje bezpośrednio.
- **Mapy geologiczne USGS–NASA:** standardowe mapy geologiczne Marsa. Dają warstwę jednostek geologicznych.
- **Proponowana trasa Curiosity na Mount Sharp:** animacja i mapa z opisanymi rejonami naukowymi. Przenosimy te rejony jako punkty naukowe i porównujemy trasę łazika z trasą pieszą.
- **NASA Worldview:** pokazuje tylko Ziemię, więc nie daje danych o Marsie. Wzorujemy się na jego interfejsie: suwaku czasu i przełączaniu warstw.
- **Galeria zdjęć Perseverance:** dotyczy krateru Jezero, a my jesteśmy w Gale. Do podglądu z powierzchni używamy więc analogicznej galerii Curiosity. Galeria Perseverance jest gotowa, gdyby narzędzie generowało mapę dla Jezero.

Dane RAD, REMS, THEMIS i CRISM nie są w tych zasobach. Pobieramy je z archiwum PDS (Planetary Data System).

### Potok danych

1. **Wycinek.** Przycinamy DTM i ortofoto HiRISE do obszaru wyjścia, kilka kilometrów na kilka.
2. **Warstwy z terenu.** Z DTM liczymy:
   - nachylenie,
   - szorstkość (odchylenie wysokości w małym oknie),
   - widoczność nieba (kąty horyzontu w kilkudziesięciu kierunkach).
3. **Głazy.** Model wizji komputerowej wykrywa głazy na ortofoto HiRISE i tworzy z nich warstwę przeszkód.
4. **Dopasowanie warstw.** THEMIS, CRISM i mapę geologiczną przeliczamy na siatkę DTM.
5. **Mapa kosztów.** Łączymy warstwy w jeden koszt przejścia, z wagami i progami zakazu.
6. **Trasa.** A* przez punkty naukowe w zadanej lub optymalnej kolejności. Sprawdzamy ograniczenia powrotu i schronienia.
7. **Eksport.** Trasa i warstwy trafiają do GeoJSON i rastrów dla frontendu oraz do siatki dla Isaac Sim.

### Model ruchu w skafandrze

- **Prędkość:** funkcja Toblera, przeskalowana dla 0,38 g i masy skafandra.
- **Progi nachylenia:** do ok. 15° marsz swobodny, powyżej ok. 25° zakaz. To założenia do skalibrowania, wpisane w konfiguracji.
- **Zapasy:** czas marszu i postojów przy celach przeliczamy na zużycie tlenu i energii.
- **Dawka:** dawka z RAD razy widoczność nieba w danym miejscu razy czas spędzony w tym miejscu.

### Łazik wsparcia i zestaw narzędzi

**Zestaw narzędzi na łaziku.** Lista jest naszym założeniem. Wzorujemy się na narzędziach geologicznych z misji Apollo i na przyrządach łazików Curiosity i Perseverance.

| Grupa | Co jest na łaziku | Do czego służy |
| --- | --- | --- |
| Pobieranie próbek | młotek geologiczny, łopatka, szczypce, grabie do okruchów, wiertło rdzeniowe na ramieniu | próbki skał i gruntu z celów naukowych |
| Przechowywanie próbek | szczelne pojemniki i worki z numerami, stojak na próbki | zapis, skąd pochodzi każda próbka |
| Pomiary na miejscu | ręczny spektrometr, kamera do zbliżeń, georadar pod łazikiem | szybka ocena, czy cel jest wart próbki, i budowa podłoża |
| Bezpieczeństwo | zapasowy tlen i energia do skafandra, zestaw naprawczy skafandra, apteczka, dozymetr | powrót z zapasem i reakcja na awarię |
| Łączność i nawigacja | przekaźnik radiowy do habitatu, znaczniki trasy, oświetlenie | łączność w zagłębieniach terenu i powrót po zmroku |

**Jak planer z tego korzysta:**
- każdy cel naukowy ma listę wymaganych narzędzi i przypisanego wykonawcę,
- przed wyjściem planer sprawdza, czy ładunek łazika pokrywa wszystkie cele,
- łazik dostaje własną trasę po terenie, który jest dla niego przejezdny, i miejsca postoju przy celach,
- zapasowy tlen na łaziku wydłuża dozwoloną odległość astronauty od habitatu.

**W symulacji:** ramię to gotowy model z zasobów Isaac Sim zamontowany na łaziku. Przy punkcie próbkowania odtwarza przygotowany ruch przegubów. Nie symulujemy chwytania ani planowania ruchu ramienia.

### Oprogramowanie

- **Python:** GDAL i rasterio (rastry), NumPy i SciPy (obliczenia), scikit-image i OpenCV (wizja), własna implementacja A*.
- **Serwer:** aiohttp, który podaje warstwy i liczy trasy na żądanie.
- **Frontend:** mapa 2D z warstwami (Leaflet lub czysty JS), widok 3D terenu w Three.js (alternatywnie CesiumJS), profil wysokości i panel budżetu.
- **Symulacja:** NVIDIA Isaac Sim 5.1. DTM zamieniony na siatkę z teksturą HiRISE, gotowe modele łazika i ramienia, kamera prowadzona po trasie i nagrywanie wideo.
- **Opcjonalnie ROS 2 Humble i Nav2:** łazik w symulacji jedzie za astronautami po wyznaczonej trasie. Logika mapy kosztów jest ta sama co w Nav2.
- **Środowisko:** Ubuntu 24.04, Docker, laptop z RTX 3050 6 GB. Dlatego scena w Isaac Sim to przycięty wycinek, a nie cały krater.

---

## Dla kogo skierowane

**Główni odbiorcy:**
- **Planiści wyjść (EVA) w centrum misji i w habitacie.** Dostają jedną mapę zamiast kilku portali i trasę z policzonym ryzykiem. Korzystają najbardziej, bo dziś składają te dane ręcznie.
- **Astronauci w trakcie wyjścia.** Dostają tryb HUD z tym, co ważne teraz: dokąd iść, ile zostało zapasu i gdzie się schować.
- **Zespoły naukowe.** Wybierają cele na mapie minerałów i geologii i od razu widzą, ile kosztuje dojście do nich.

**Dalsi odbiorcy:**
- **Planiści misji Artemis na Księżycu.** Ten sam potok działa na danych LRO, a problem pieszego wyjścia w skafandrze jest ten sam.
- **Ziemskie misje analogowe** (stacje symulujące Marsa na pustyniach). Ten sam planer działa na ziemskim modelu terenu.
- **Zespoły robotyczne.** Mapa kosztów i trasa nadają się do prowadzenia łazika towarzyszącego załodze.
- **Edukacja.** Interaktywna mapa pokazuje, jak wygląda prawdziwe planowanie misji na Marsie.

---

## Demo

**Pokaz na żywo, około 3 minut, w trzech aktach.**

### Akt 1: planowanie w habitacie (ok. 1 min)

- Otwieramy ekran habitatu nad rejonem boxwork na Mount Sharp.
- Włączamy warstwy po kolei: ortofoto, nachylenie, piasek z THEMIS, minerały z CRISM, mapa schronień. Każde włączenie od razu pokazuje coś nowego o terenie.
- Klikamy trzy cele naukowe: grzbiet formacji skrzynkowych, odsłonięcie siarczanów i punkt widokowy.
- Jeden cel leży na zboczu zakazanym dla człowieka. Planer przypisuje go ramieniu łazika i pokazuje, których narzędzi z łazika wymaga każdy cel.
- **Porównanie:** prosta linia między celami przechodzi przez stromy klif i pole piasku. Trasa z planera omija je, a panel pokazuje czas, dystans, dawkę i zużycie tlenu.

### Akt 2: burza słoneczna (ok. 1 min)

- Uruchamiamy scenariusz alertu SEP oparty na prawdziwym zdarzeniu z bazy DONKI.
- Przełączamy się w tryb HUD: pojawia się kierunek do najbliższego schronienia pod klifem i czas dojścia.
- Planer przelicza resztę wyjścia: jeden cel odpada, bo nie mieści się w zapasie na powrót.

### Akt 3: widok z perspektywy astronauty (ok. 1 min)

- Odtwarzamy przelot w Isaac Sim po wyznaczonej trasie, z łazikiem jadącym obok.
- Przy celu na zboczu łazik staje na krawędzi, a ramię sięga po próbkę. Astronauta w tym czasie idzie dalej.
- Obok pokazujemy prawdziwe zdjęcia Curiosity z tego samego rejonu, żeby było widać, że scena oddaje teren.
- Na koniec trasa Curiosity i trasa naszego zespołu na jednej mapie: **człowiek z łazikiem wsparcia dochodzi do celów, które Curiosity ominął.**

**Plan awaryjny:** całe demo jest też nagrane jako wideo, na wypadek problemów z siecią albo z laptopem.
