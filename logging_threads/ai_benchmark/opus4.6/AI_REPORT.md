# Raport techniczny: Thread-Safe Logging dla Robot Framework

## 1. Diagnoza problemu

Robot Framework 7.4 jest zaprojektowany jako w pełni jednowątkowy silnik wykonawczy. Logowanie z wątków (`threading.Thread`) nie działa z dwóch powodów:

**Przyczyna 1: Filtr wątków w `librarylogger.py`**
Funkcja `librarylogger.write()` (linia 44) sprawdza `current_thread().name in LOGGING_THREADS`, gdzie `LOGGING_THREADS = ["MainThread", "RobotFrameworkTimeoutThread"]`. Wiadomości z dowolnych innych wątków są **cicho odrzucane**.

**Przyczyna 2: Brak izolacji wątkowej stanu globalnego**
- `LOGGER._log_message_parents` — zwykła lista Pythona służąca jako stos do przypisywania wiadomości do keywordów
- `EXECUTION_CONTEXTS._contexts` — globalny stos kontekstów wykonania
- `_ExecutionContext.steps` — stos wywołań keywordów

Żaden z tych elementów nie używa `threading.local()`. Współbieżne operacje push/pop prowadzą do korupcji danych, przypisania wiadomości do niewłaściwych keywordów lub crash'y.

**Scenariusze problemu:**
1. `robot.api.logger.info("msg")` z wątku → wiadomość odrzucona (nigdy nie trafia do output.xml)
2. `BuiltIn().run_keyword("Log", "msg")` z wątku → korupcja stosu `_log_message_parents`, wiadomość trafia do niewłaściwego keywordu lub crash

## 2. Założenia i ograniczenia

### Założenia
- Rozwiązanie działa wyłącznie z API Robot Framework i standardową biblioteką Pythona (brak pip)
- Wątki są uruchamiane przez dedykowaną bibliotekę RF (`thread_executor.py`)
- Kod wewnątrz wątków nie wymaga modyfikacji (zero-interference)
- Monkey-patche działają wyłącznie na czas trwania wątków i są w pełni odwracalne
- Namespace (rozwiązywanie keywordów) jest współdzielony jako read-mostly

### Ograniczenia
1. **Zmienne RF nie są thread-safe** — zapis do zmiennych z wielu wątków jednocześnie może powodować wyścigi
2. **`set_test_variable` / `set_test_message`** — operacje na poziomie testu z wątków mogą być niezdefiniowane
3. **Timeout RF** — wątki nie wspierają mechanizmu timeout Robot Framework
4. **Asyncio** — każdy wątek dostaje własny `Asynchronous` — nie ma współdzielenia pętli zdarzeń
5. **Library listeners** — nie są powiadamiane o zdarzeniach z wątków (tylko XML output jest uzupełniany)
6. **User keywords z embedded arguments** — mogą mieć problemy z namespace scope tracking przy współbieżności
7. **Wyniki z wątków są mergowane po zakończeniu wszystkich wątków** — brak streamingu w trakcie wykonania

## 3. Uzasadnienie projektu

### Podejście: Thread-Local Capture + Post-Merge Replay

**Dlaczego nie modyfikacja plików RF:**
Wymaganie #11 wyraźnie zabrania edycji plików robotframework.

**Dlaczego monkey-patching zamiast subprocessów:**
- Subprocesy nie mają dostępu do namespace RF (keyword resolution)
- Multiprocessing wymaga serializacji, co wyklucza złożone obiekty RF
- Monkey-patching pozwala na pełne wykorzystanie istniejącej infrastruktury RF

**Dlaczego izolacja per-thread zamiast lock'ów na globalnym stanie:**
- Lock'i na `LOGGER._log_message_parents` nie wystarczą — stos musi być logicznie per-wątek
- Lock'i spowalniałyby MainThread
- Izolacja jest prostsza do weryfikacji i debugowania

**Dlaczego visitor pattern do replay zamiast bezpośredniego XML:**
- `XmlLogger` implementuje pełny `ResultVisitor` — replay `root.visit(xml_logger)` generuje poprawne, zagnieżdżone XML
- Gwarantuje, że FOR/IF/TRY mają natywne tagi XML bez ręcznej serializacji
- Jedno wywołanie `visit()` obsługuje dowolnie złożone drzewo wyników

### Kompromisy
- **Wyniki z wątków pojawiają się po zakończeniu wszystkich wątków** — nie ma streamingu. Akceptowalne, bo output.xml jest pisany inkrementalnie i wstawianie wyników w trakcie wymagałoby synchronizacji XML writera.
- **Namespace jest współdzielony bez lock'ów** — keyword resolution jest read-mostly, ale dynamiczne importy z wątków mogą być niebezpieczne. W praktyce to rzadki scenariusz.
- **Thread context współdzieli `test` z MainThread** — pozwala na `BuiltIn._context.test` w wątkach, ale operacje modyfikujące test (tagsetter etc.) mogą być niezdefiniowane.

## 4. Przebieg weryfikacji

### Scenariusze testowe (12 testów)

| Test | Cel | Wynik |
|------|-----|-------|
| Simple Logging From Threads | `robot.api.logger` z 2 wątków | PASS |
| Keyword Execution From Threads | `BuiltIn.log()`, `BuiltIn.evaluate()`, `BuiltIn.sleep()` | PASS |
| Nested Structures In Threads | Python loops/conditionals z `BuiltIn` calls | PASS |
| Complex Nested Structures | Zagnieżdżone pętle + warunki + obsługa błędów | PASS |
| Thread Error Handling | Wątek rzuca RuntimeError → czytelny błąd | PASS |
| Partial Failure With Logs | Logi przed błędem są zachowane | PASS |
| Multiple Concurrent Threads | 4 równoległe wątki z `Run In Threads With Args` | PASS |
| Patch Cleanup Verification | Normalne logowanie po wątkach działa | PASS |
| RF FOR Loop In Thread | User keyword z `FOR` → natywne `<for>` w XML | PASS |
| RF IF ELSE In Thread | User keyword z `IF/ELSE` → natywne `<if>/<branch>` | PASS |
| RF TRY EXCEPT In Thread | User keyword z `TRY/EXCEPT/FINALLY` → natywne `<try>/<branch>` | PASS |
| RF Nested Structures In Thread | FOR + IF + TRY zagnieżdżone → pełna struktura w XML | PASS |

### Weryfikacja output.xml
- 19 `<kw name="Thread: ...">` elementów z poprawnym `owner="ThreadExecutor"`
- FOR loops: `<for flavor="IN RANGE">` z `<iter>` i zagnieżdżonymi `<kw>`
- IF/ELSE: `<if>` z `<branch type="IF">` i `<branch type="ELSE">`
- TRY/EXCEPT: `<try>` z `<branch type="TRY">`, `<branch type="EXCEPT">`, `<branch type="FINALLY">`
- Timestampy: zachowane oryginalne czasy wygenerowania (np. opóźnione wiadomości mają ~50ms odstępy)
- TRACE: callable messages (lambdy) poprawnie zresolvowane do tekstów ("Arguments: [...]", "Return: None")
- Błędy: wątki z błędami mają `status="FAIL"` z pełnym traceback w `<msg level="ERROR">`

### Weryfikacja log.html
- Wyniki z wątków widoczne jako zagnieżdżone keywordy `"Thread: xxx"` pod `"Run In Threads"`
- FOR/IF/TRY widoczne z natywnym renderowaniem (rozwijalne sekcje)
- Wiadomości z różnych wątków nie są pomieszane
- Timestampy czytelne i w porządku chronologicznym per wątek

## 5. Lista iteracji i poprawek

| # | Problem | Poprawka |
|---|---------|---------|
| 1 | Klasa `ThreadExecutor` nierozpoznana przez RF | Zmiana nazwy na `thread_executor` (konwencja RF: nazwa klasy = nazwa modułu) |
| 2 | `AttributeError: 'NoneType' object has no attribute 'is_loop_required'` | Dodanie `Asynchronous()` do kontekstu wątku — RF sprawdza wynik keyword'a pod kątem coroutine |
| 3 | TRACE messages wyświetlane jako `<function lambda at 0x...>` | Dodanie `msg.resolve_delayed_message()` w `ThreadOutput.message()` — resolvuje lazy callables |
| 4 | `BuiltIn.run_keyword()` z wątku nie wie, gdzie utworzyć child keyword | Dodanie initial step push w `_thread_worker` (`context.steps.append((fake_data, root, None))`) |

## 6. Ocena końcowego rezultatu

### output.xml
- **Struktura:** Poprawna. Thread keywords są zagnieżdżone pod parent keyword `Run In Threads`.
- **Tagi XML:** FOR/IF/TRY mają natywne tagi (`<for>`, `<if>`, `<try>`, `<branch>`, `<iter>`).
- **Messages:** Poprawnie przypisane do parent keyword'ów, nie wylewają się poza kontener wątku.
- **Timestampy:** Oryginalne (czas wygenerowania, nie czas merge'a).
- **Status:** `PASS`/`FAIL` poprawnie propagowane.
- **Walidacja schema:** Spójna z schemaversion="5".

### log.html
- **Czytelność:** Wyniki z wątków widoczne jako rozwijalne drzewo pod `Run In Threads`.
- **Grupowanie:** Każdy wątek ma osobny kontener `Thread: <name>`.
- **Brak przeplotu:** Wiadomości z różnych wątków nie mieszają się ze sobą ani z MainThread.
- **Nawigacja:** Klikalne tagi, filtrowanie po poziomie logów działa.

### Ocena ogólna
Rezultat nadaje się do praktycznej analizy. Struktura jest spójna, czytelna i zachowuje pełną informację o wykonaniu w wątkach.

## 7. Znane ryzyka i braki

1. **Namespace race conditions** — dynamiczne importy bibliotek (`Import Library`) z wątków mogą kolidować z MainThread. Workaround: importy wykonywać przed uruchomieniem wątków.

2. **Variable store** — współbieżne zapisy do zmiennych RF (`Set Variable`, `Set Suite Variable`) z wielu wątków nie są thread-safe. Workaround: używać zmiennych lokalnych Pythona w wątkach.

3. **User keyword scope** — `namespace.start_user_keyword()` / `end_user_keyword()` modyfikuje współdzielony `_user_kw_scope`. Przy wielu wątkach wywołujących user keywords jednocześnie, scope może się pomylić. W praktyce dotyczy to głównie zagnieżdżonych user keywords z private keywords.

4. **Signal handling** — `STOP_SIGNAL_MONITOR.start_running_keyword()` nie jest thread-safe. Ctrl+C podczas wykonywania wątków może nie poprawnie przerwać wszystkich wątków.

5. **Timeouts** — RF timeouts nie działają w wątkach. Jeśli wątek się zawiesi, jedynym zabezpieczeniem jest `daemon=True` na wątku.

6. **Library listeners** — listenery nie otrzymują zdarzeń z wątków. Jeśli listener modyfikuje wyniki (np. Allure), wyniki z wątków nie będą obsłużone.

7. **Jednoczesne uruchomienie wielu `Run In Threads`** — nie jest wspierane (zagnieżdżone monkey-patche mogą się zepsuć). Workaround: seryjne wywołania `Run In Threads`.

## 8. Samoocena

| Kryterium | Ocena (0-2) | Komentarz |
|-----------|-------------|-----------|
| Poprawność techniczna | 2 | 12/12 testów, poprawny XML, lazy message resolution |
| Zgodność z wymaganiami | 2 | Wszystkie 11 wymagań funkcjonalnych spełnione |
| Bezpieczeństwo wątkowe | 1 | Izolacja per-thread poprawna, ale namespace sharing to znane ryzyko |
| Jakość struktury logów | 2 | Natywne tagi FOR/IF/TRY, per-thread grouping, oryginalne timestampy |
| Czytelność rozwiązania | 2 | Modularny kod (ThreadOutput, PatchManager, thread_executor), jasne API |
| Łatwość utrzymania | 1 | Monkey-patching wymaga aktualizacji przy zmianach wewnętrznych RF |

**Suma: 10/12**

Główne ryzyka utrzymaniowe to zależność od wewnętrznego API RF (monkey-patching `LOGGER`, `EXECUTION_CONTEXTS`, `librarylogger.write`) oraz współdzielenie namespace bez pełnej synchronizacji. Przy upgradeach RF należy zweryfikować, czy monkey-patche nadal działają z nową wersją.
