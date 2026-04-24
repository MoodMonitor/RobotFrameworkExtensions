# AI Report

## 1. Diagnoza problemu
Problem miał dwa źródła:

1. `robot.api.logger` i `robot.output.librarylogger` domyślnie nie logują z obcych wątków do artefaktów RF, bo publiczne logowanie jest ograniczone do `MainThread` i kilku wątków systemowych.
2. Wykonywanie keywordów RF z `threading.Thread` korzysta z globalnych obiektów wykonania i logowania, które nie są zaprojektowane do równoległego zapisu do aktywnego `output.xml`.

Skutki były widoczne w dwóch scenariuszach:

1. Proste wiadomości z wątków znikały z `output.xml` i `log.html`.
2. Keywordy uruchamiane w wątkach trafiały do raportu bez sensownego grupowania, a ich zapis był podatny na błędne osadzenie względem bieżącego kontekstu testu.

## 2. Założenia i ograniczenia
Założenia:

1. Nie wolno modyfikować plików w katalogu `robot/`.
2. Rozwiązanie ma korzystać wyłącznie z API i mechanizmów wewnętrznych dostępnych w lokalnym kodzie RF.
3. Kod wykonywany wewnątrz wątku nie może być zmieniany.
4. Aktywacja rozwiązania może nastąpić z zewnątrz, na poziomie testu lub biblioteki sterującej.

Ograniczenia:

1. Zrzut grupy wątku do aktywnego `output.xml` następuje przy `Thread.join()` oraz awaryjnie przy końcu testu/suite, więc najlepsze rezultaty są wtedy, gdy wątki są poprawnie `join`owane w tym samym logicznym kontekście testu.
2. Rozwiązanie nie zmienia semantyki wyjątków Pythona między wątkami; zamiast propagować je do `join()`, zapisuje je czytelnie w grupie wątku.
3. Nie dodawałem wsparcia dla wszystkich możliwych egzotycznych ścieżek wykonania RF, np. setup/teardown na keywordach uruchamianych wewnątrz wątku jako osobne przypadki serializacji.

## 3. Uzasadnienie projektu
Wybrane podejście:

1. Tymczasowe, odwracalne podpięcie pod `threading.Thread.start/join`.
2. Tymczasowe przekierowanie wybranych punktów logowania RF (`librarylogger.write`, `LOGGER.log_message`, `LOGGER.message`, `LOGGER.log_output`).
3. Utworzenie osobnego bufora wyniku per wątek jako syntetycznej grupy RF `Thread <name>`.
4. Serializacja gotowego poddrzewa wyniku wątku do aktywnego `OutputFile` dopiero w kontrolowanym momencie, zamiast pozwalać wielu wątkom pisać równolegle do jednego strumienia XML.

Powód wyboru:

1. To podejście daje izolację per wątek i nie wymaga zmian w kodzie wykonywanym w środku wątku.
2. Zachowuje natywne obiekty `result.*` Robot Framework, więc nie spłaszcza `FOR` / `IF` / `TRY`.
3. Pozwala całkowicie wycofać ingerencję po zakończeniu wykonania suite.

Zaakceptowany kompromis:

1. Grupa wątku jest emitowana jako blok po zakończeniu wątku, a nie strumieniowo linia po linii. Dzięki temu nie ma przeplatania i pozostają oryginalne timestampy wiadomości.

## 4. Przebieg weryfikacji
Uruchomione testy:

1. `.\.venv\Scripts\python.exe -m unittest tests.test_thread_capture`

Wynik końcowy:

1. `Ran 2 tests in 2.928s`
2. `OK`

Zakres testów:

1. Reprodukcja problemu bazowego bez poprawki.
2. Grupowanie logów prostych wiadomości per wątek.
3. Zachowanie struktury `FOR` / `IF` / `TRY` przy keywordach uruchamianych w wątkach.
4. Czytelna widoczność błędu kończącego wątek.
5. Obecność danych zarówno w `output.xml`, jak i `log.html`.

## 5. Lista iteracji i poprawek
Iteracja 1:

1. Pierwsza wersja przepisywała `output.xml` przy `Output.close()`.
2. Problem: obiekt wyniku dostępny na tym etapie był już zbyt odchudzony i nowy `output.xml` tracił ciała testów.
3. Poprawka: zrezygnowałem z pełnego przepisywania pliku i przeszedłem na bezpośredni, kontrolowany zapis poddrzew wątków do aktywnego `OutputFile`.

Iteracja 2:

1. Po uruchomieniu keywordów w wątkach brakowało części struktury, bo wątkowy obiekt output nie implementował zgodnej sygnatury `trace(..., write_if_flat=False)`.
2. Poprawka: dodałem zgodną metodę `trace()` oraz przekierowanie ścieżek logowania używanych przez RF podczas wykonywania keywordów.

Iteracja 3:

1. Test strukturalny łączył zachowanie `TRY/EXCEPT` z osobnym scenariuszem błędu wątku.
2. To mieszało walidację struktury z walidacją błędu.
3. Poprawka: rozdzieliłem test zachowania struktur od testu awarii wątku.

## 6. Ocena końcowego rezultatu
`output.xml`:

1. Struktura jest poprawna dla sprawdzonych scenariuszy.
2. Wątki są widoczne jako osobne grupy `Thread <name>`.
3. Wiadomości mają zachowane oryginalne atrybuty czasu.
4. Zagnieżdżone konstrukcje `FOR`, `IF`, `TRY`, `branch`, `iter` są obecne w wyniku i nie są spłaszczane.

`log.html`:

1. Jest czytelny.
2. Grupy wątków są łatwe do znalezienia.
3. Błędy kończące wątek są widoczne zarówno w samej grupie wątku, jak i w sekcji błędów.

Ocena praktyczna:

1. Grupowanie per wątek jest sensowne do analizy.
2. Rozdzielenie od `MainThread` jest dużo lepsze niż w stanie bazowym.
3. Artefakty nadają się do praktycznej diagnostyki problemów wielowątkowych.

## 7. Znane ryzyka lub braki
1. Najlepsza jakość osadzenia w strukturze testu jest wtedy, gdy wątki są `join`owane w przewidywalnym miejscu tego samego kontekstu wykonania.
2. Rozwiązanie nie próbuje wymuszać faila całego testu na podstawie błędu wątku; pokazuje błąd jasno w grupie wątku, ale nie zmienia automatycznie statusu testu.
3. Nie rozbudowywałem osobnej obsługi wszystkich możliwych przypadków setup/teardown keywordów wykonywanych wewnątrz wątku.

## Samoocena 0-2
1. poprawność techniczna: 2
2. zgodność z wymaganiami: 2
3. bezpieczeństwo wątkowe: 1
4. jakość struktury logów: 2
5. czytelność rozwiązania: 2
6. łatwość utrzymania: 1
