# Planer misji

Planer misji układa całe wyjście naukowe (EVA): dokąd iść, w jakiej kolejności, kto wykonuje pracę przy każdym celu i czy wystarczy tlenu. Działa jako węzeł ROS 2 (`ros/mission_planner.py`), a wynik widać w zakładce **Mission** w dashboardzie, na mapie 3D i w HUD.

---

## W skrócie (na slajd)

- **Wejście:** cel naukowy i lista celów z zadaniami, narzędziami i czasem pracy.
- **Planer decyduje**, kto pracuje przy każdym celu: astronauta, ramię łazika albo łazik z wiertłem.
- **Układa kolejność** z najkrótszym marszem i liczy każdy odcinek algorytmem A* na mapie kosztów.
- **Pilnuje tlenu:** 8 h skafandra minus 30 min rezerwy. Gdy nie starcza, odrzuca cele o najniższym priorytecie.
- **Wynik:** czas wyjścia, dystans, zapas tlenu, dawka promieniowania i harmonogram minuta po minucie.

---

## Co planer dostaje

**Plik misji** (`data/mission_*.json`):
- cel naukowy i tło, np. Boxwork EVA 1: jak powstały grzbiety boxwork na Mount Sharp,
- punkt startu, czyli parking łazika osobowego,
- cele: położenie, zadania (np. próbka młotkiem), potrzebne narzędzia, czas pracy na miejscu i priorytet.

**Dane na żywo z ROS 2:**
- mapa kosztów dla pieszego (`/costmap/walk`) i dla łazika (`/costmap/rover`),
- warstwa dawki promieniowania (`/nasa/dose_rate`),
- plan łazika z zakładki Rover planner (`/rover/config`): który łazik i jakie wyposażenie.

Gdy któraś z tych danych się zmieni, planer od razu przelicza misję.

---

## Jak planer liczy misję

### 1. Kto pracuje przy celu

| Sytuacja przy celu | Wykonawca | Co się dzieje |
| --- | --- | --- |
| teren dozwolony dla pieszego, nachylenie do 15° | **astronauta** | astronauta podchodzi i pracuje na miejscu |
| teren zakazany albo nachylenie ponad 15° | **ramię łazika** | astronauta staje w najbliższym bezpiecznym punkcie, a ramię łazika sięga po próbkę |
| zadanie wymaga wiertła rdzeniowego | **+ łazik** | wiertło zostaje na łaziku, więc łazik musi móc tam dojechać |

Przy każdym celu planer dopisuje ostrzeżenia, na przykład:
- „needs a robotic arm on the rover”: cel wymaga ramienia, a łazik go nie ma,
- „missing on the rover: …”: brakuje narzędzi w planie łazika,
- „the crew rover cannot drive to this target”: łazik nie dojedzie do celu z wiertłem.

### 2. Kolejność celów

Planer sprawdza **wszystkie kolejności** celów i wybiera tę z najkrótszym marszem od parkingu, przez cele, z powrotem do parkingu. Przy kilku celach to kilkadziesiąt kombinacji, więc liczy się to od razu.

Każdy odcinek to trasa A* na mapie kosztów dla pieszego. Ta sama mapa omija strome zbocza, głazowiska i miejsca o dużej dawce (zobacz slajd z mapą kosztów).

### 3. Tlen

- Skafander ma zapas tlenu na 8 godzin, z czego 30 minut to rezerwa, której plan nie może zużyć.
- Czas wyjścia to czas marszu (0,8 m/s) plus czas pracy przy celach.
- Jeśli plan się nie mieści, planer odrzuca cel o najniższym priorytecie i liczy jeszcze raz. Odrzucone cele są pokazane osobno.
- Jeśli wybrano małego robota pomocniczego z zapasowymi butlami, zapas tlenu rośnie.

### 4. Dawka promieniowania

Planer sumuje dawkę na każdym kroku marszu i w czasie pracy przy celu. Moc dawki pochodzi z modelu: pomiar RAD z Curiosity (0,64 mSv/dobę) razy widoczna część nieba w danym miejscu.

---

## Co widać w zakładce Mission

- **Wybór misji** z listy plików `data/mission_*.json`, bez restartu.
- **Cztery liczby:** czas wyjścia, dystans marszu, zapas tlenu i spodziewana dawka.
- **Cele w kolejności marszu**, każdy z wykonawcą (Astronaut / Rover arm), zadaniami, nachyleniem, narzędziami i ostrzeżeniami.
- **Harmonogram:** każdy odcinek z dystansem, czasem marszu, czasem pracy i godziną dotarcia.
- **Start mission walk:** wysyła trasę misji do symulacji.
- **Show on 3D map:** pokazuje ponumerowane cele i trasę na mapie 3D.

Przykład z krótkiej misji testowej (2 cele obok łazika): 35 min wyjścia, 0,2 km marszu, 15,1 µSv dawki. Drugi cel leży na zboczu 23°, więc planer oddał go ramieniu łazika.

---

## Misja w symulacji

Po kliknięciu „Start mission walk” symulacja w Isaac Sim przechodzi plan krok po kroku:
- przy celu astronauty astronauta stoi przez czas pracy,
- przy celu dla ramienia astronauta czeka w bezpiecznym punkcie, aż łazik podjedzie bliżej niż 7 m, a potem ramię wykonuje sekwencję pobrania próbki: wysięg, zejście do gruntu, nad skrzynkę na próbki, złożenie,
- na koniec astronauta wraca na parking łazika.

Postęp idzie na `/mission/progress` i jest widoczny w zakładce Mission, w logu misji i w HUD w okularach.

---

## Założenia i ograniczenia

- Próg 15° dla pieszego, 8 h tlenu i 30 min rezerwy to nasze założenia, ustawiane parametrami węzła.
- Dawka to model z RAD, a nie pomiar w każdym miejscu.
- Prędkość marszu jest stała (0,8 m/s). Nie zależy jeszcze od nachylenia.
- Sprawdzanie wszystkich kolejności działa dobrze do około 8 celów. Przy większej liczbie trzeba będzie prostszej heurystyki.
- Cele misji Boxwork EVA 1 są ustawione na oko na grzbietach przypominających boxwork, a nie na potwierdzonych miejscach.
