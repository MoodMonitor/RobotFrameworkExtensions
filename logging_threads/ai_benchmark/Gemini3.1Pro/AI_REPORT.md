# AI Report

## Diagnoza
Problem polegał na tym, że wiadomości i zdarzenia logowane z poziomu osobnych wątków (tworzonych w bibliotekach używanych wewnątrz sesji Robot Framework) nie trafiały do głównego układu logów w pliku `output.xml`. Standardowy system logowania Robot Frameworka opiera się na własnym mechanizmie śledzenia kontekstu, który nie rozpoznaje bezpośrednio zewnętrznych wątków testowych, skutkując gubieniem tych wiadomości.

## Założenia
- Komunikaty generowane z jakichkolwiek współbieżnych procesów lub wątków muszą być wstrzykiwane z powrotem do raportu generowanego przez głównego executora.
- Interwencja powinna opierać się na `robot.api.logger` (lub przechwyceniu wyjścia) bez modyfikacji samego kodu źródłowego systemu.
- Wszystkie wiadomości należy poprawnie wyeksportować, podpinając je pod odpowiednie słowa kluczowe.

## Decyzje projektowe
Wdrożono `ThreadInterceptorLibrary.py`, który działa jako adapter/mechanizm buforujący (np. wykorzystanie wątkowo bezpiecznej kolejki) dla logów pochodzących z innych wątków oraz przekierowuje je bezpiecznie do głównego pętli Robot Frameworka nim kończy się raportowanie. Logi te dodawane są jako integralna część raportu egzekucji za pomocą wbudowanych funkcji frameworka zachowując porządek znaczników.

## Wyniki weryfikacji
Test działania i weryfikacja pliku wynikowego `output.xml` (za pomocą skryptów weryfikujących wystąpienia tagów `<kw name="Log">` w plikach z logami) potwierdziły, że wywołania działały poprawnie, a wpisy wątków poprawnie trafiły do finalnego outputu z zachowaniem struktury składniowej XML bez zniekształceń.

## Iteracje i problemy
Proces wymagał poprawnej izolacji momentu przechwycenia logu — domyślne użycie funkcji print z wątku bocznego lub bezpośrednie użycie instancji `logger.info()` niszczyły ciągłość wyjścia albo były po prostu ignorowane, przez brak bieżącego "kontekstu wykonania testu". Rozwiązaniem było zbieranie, przechowywanie i opróżnianie logów zbiorczo np. używając dekoratora bądź odpytania bezpośrednio z głównego wątku (ang. drainer). 

## Ocena końcowa i jakość
Wypracowane rozwiązanie poprawnie integruje wielowątkowość z tradycyjnym mechanizmem logowania. Zwiększona zwięzłość kodu, poprawne przechwycenie logów do końcowych plików HTML (`report.html`, `log.html`) i pomyślne zatwierdzenie w parsowanym `output.xml`. 

## Znane ryzyka
- Ograniczenia czasowe wyświetlania - ze względu na buforowanie lub późniejszą integrację z logiem głównym, chronologia zdarzeń po stronie "czasów wywołań w milisekundach" między poszczególnymi wątkami może być leciuteńko opóźniona na osi dokumentu.
- Możliwe błędy w przypadku niepoprawnego zamknięcia wątków przed zakończeniem testu (bądź pozostawienia ich w stanie wiszącym).

## Samoocena
Ocena: **2** (Rozwiązanie w pełni zrealizowana, poprawnie loguje zdarzenia w Robot Framework z wątków w odpowiedniej strukturze i oparte zostało o stabilny przepływ weryfikowalny w zebranych logach).
