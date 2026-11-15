# Pitch: Marswalk Planner

Tekst do powiedzenia przy prezentacji (polska wersja, 7 slajdów). Każdy slajd to około 25 sekund, całość około 3 minut. Liczby są te same co na slajdach i pochodzą z naszego kodu.

---

## 1. Marswalk Planner

Cześć, jesteśmy zespołem CTRL i wybraliśmy zadanie Martian Map. Zbudowaliśmy Marswalk Planner: mapę i planer trasy dla astronauty, który wychodzi pieszo na powierzchnię Marsa. Pokażemy go na prawdziwym kawałku planety, podnóżu Mount Sharp w kraterze Gale, gdzie łazik Curiosity badał w 2025 roku formacje boxwork.

## 2. Problem

Mapy Marsa, które dziś mamy, pokazują regiony i całą planetę. Wyjście astronauty to kilka kilometrów i kilka godzin, a na takiej trasie jeden klif zmienia wszystko. Dane leżą w osobnych archiwach, a planery tras powstały dla łazików, które się nie męczą, nie oddychają i nie zbierają dawki promieniowania. Chcieliśmy odpowiedzieć na jedno pytanie: którędy człowiek w skafandrze przejdzie bezpiecznie?

## 3. Dane NASA

Zaczęliśmy od danych NASA. Model terenu HiRISE z rozdzielczością jednego metra daje nam nachylenie, szorstkość i to, ile nieba widać nad każdym punktem. Pomiar promieniowania z Curiosity, 0,64 milisiwerta na dobę, zamieniamy w mapę dawki: tam, gdzie teren zasłania niebo, dawka jest mniejsza, więc wychodzi z tego mapa schronień. Każda warstwa pokrywa dokładnie ten sam wycinek dwa na dwa kilometry.

## 4. Mapa kosztów i trasa

Warstwy zamieniamy w koszt przejścia. Najwięcej waży nachylenie: powyżej 25 stopni albo przy nierównościach ponad 2 metry teren jest zakazany, i to 9% naszego wycinka. Na tej mapie algorytm A* szuka najtańszej trasy. Z parkingu łazika do pola boxwork wychodzi 814 metrów zamiast 741 w linii prostej, 17 minut marszu i 7 mikrosiwertów. Ten sam kod działa na żywo w naszych węzłach ROS 2.

## 5. Planer misji

Jedna trasa to jeszcze nie misja. Planer bierze cele naukowe, tutaj cztery cele misji Boxwork EVA 1, i układa je w kolejności z najkrótszym marszem. Przy każdym celu decyduje, kto pracuje: astronauta, ramię łazika, gdy jest za stromo, albo łazik z wiertłem. Pilnuje tlenu z półgodzinną rezerwą. Wynik: 4 kilometry, trzy godziny wyjścia, ponad cztery godziny zapasu tlenu i 80 mikrosiwertów.

## 6. Symulacja

Całość sprawdziliśmy w symulacji. W Isaac Sim astronauta w modelu skafandra Z2 idzie zaplanowaną trasą po prawdziwym terenie HiRISE, a łazik z ramieniem jedzie za nim i pobiera próbki tam, gdzie człowiekowi wejść nie wolno. Dane płyną przez ROS 2 na ekran w habitacie, a prototyp HUD-a w okularach XREAL pokazuje astronaucie kierunek i zapas tlenu.

## 7. Dla kogo i co dalej

Najwięcej zyskają planiści wyjść, którzy dziś składają te dane ręcznie, i astronauci w trakcie spaceru. Ten sam potok zadziała na danych z Księżyca, więc nadaje się dla misji Artemis i dla misji analogowych na Ziemi. Dalej chcemy dodać warstwy piasku i minerałów z THEMIS i CRISM, alert burzy słonecznej z danych DONKI i sprawdzić model marszu na ludziach w skafandrach. Dziękujemy!

---

## Gdyby padły pytania

- **Czy dawka to pomiar?** Nie. To model: pomiar RAD z Curiosity razy część otwartego nieba. Mówimy to na slajdzie.
- **Skąd progi 15° i 25°?** To nasze założenia dla człowieka w skafandrze. W węzłach ROS 2 są parametrami, które można zmienić na żywo.
- **Czy cele boxwork są potwierdzone?** Nie. Ustawiliśmy je na oko na grzbietach przypominających boxwork na zdjęciu HiRISE.
