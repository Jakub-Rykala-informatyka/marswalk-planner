# Marswalk Planner: wersja do powiedzenia na głos

## Czym się zajmowaliśmy

Na hackathonie zbudowaliśmy Marswalk Planner, narzędzie do planowania i prowadzenia pieszego wyjścia astronautów na Marsie. Wybraliśmy zbocze Mount Sharp w kraterze Gale, gdzie łazik Curiosity badał formacje skrzynkowe. Narzędzie łączy dane z kilku misji NASA w jedną mapę, wyznacza trasę dla człowieka w skafandrze i pokazuje ją zarówno na ekranie w habitacie, jak i na szybie hełmu.

## Problem

Dane o Marsie już istnieją, ale są przygotowane pod widok regionu albo całej planety, a nie pod kilkukilometrowy spacer. Każdy rodzaj danych leży w innym miejscu, więc nikt nie odpowiada wprost na pytanie, którędy iść. Do tego człowiek to nie łazik: męczy się na stromym zboczu, ma ograniczony zapas tlenu, dostaje dawkę promieniowania, a przy burzy słonecznej musi szybko znaleźć schronienie.

## Rozwiązanie

Łączymy dane o terenie, minerałach, podłożu, promieniowaniu i pogodzie w warstwy dla jednego małego obszaru i liczymy z nich trasę dla człowieka. Planer omija strome zbocza, piasek i głazy, prowadzi przez ciekawe cele naukowe i pilnuje, żeby z każdego miejsca dało się bezpiecznie wrócić. Dodaliśmy też mapę schronień, czyli miejsc, gdzie teren zasłania niebo i dawka promieniowania jest mniejsza. Astronaucie towarzyszy łazik z ramieniem robotycznym i zestawem narzędzi, który pobiera próbki tam, gdzie człowiek nie powinien wchodzić, i służy jako ruchome schronienie.

## Jak to działa

Korzystamy z modelu terenu i zdjęć z sondy Mars Reconnaissance Orbiter, z danych termicznych z sondy Mars Odyssey oraz z pomiarów promieniowania i pogody zrobionych przez łazik Curiosity. Z zasobów od organizatorów bierzemy podkłady z Mars Trek, mapy geologiczne USGS i proponowaną trasę Curiosity jako punkt odniesienia. Python zamienia te dane w mapę kosztów, a algorytm A*, ten sam pomysł co w nawigacji robotów, wyznacza trasę. Wynik widać w aplikacji w przeglądarce, a w Isaac Sim nagrywamy przelot po trasie z perspektywy astronauty.

## Dla kogo skierowane

Najbardziej skorzystają planiści wyjść w centrum misji i w habitacie, bo dziś muszą składać te dane ręcznie. Astronauci dostają prosty widok na hełmie z tym, co ważne w danej chwili, a naukowcy widzą, ile kosztuje dojście do wybranych celów. Ten sam pomysł działa też przy wyjściach na Księżycu, w ziemskich misjach analogowych i w edukacji.

## Demo

Najpierw w habitacie włączamy kolejne warstwy, wybieramy cele naukowe i pokazujemy, że prosta linia prowadzi przez klif, a nasza trasa go omija. Potem ogłaszamy alert burzy słonecznej, przełączamy się na widok z hełmu i planer prowadzi do najbliższego schronienia. Na koniec odtwarzamy przelot w Isaac Sim obok prawdziwych zdjęć Curiosity, w którym łazik sięga ramieniem po próbkę ze stromego zbocza, a astronauta idzie już do następnego celu.
