# AI_REPORT.md – RF Thread Logging Solution

## 1. Diagnoza problemu

### Scenariusz 1 – proste logowanie z wątków

Kiedy kod uruchomiony w wątku tle wywołuje `robot.api.logger.info(msg)`, ta ścieżka prowadzi do `librarylogger.write()`, który sprawdza:

```python
if current_thread().name in LOGGING_THREADS:
    LOGGER.log_message(Message(msg, level, ...))
```

`LOGGING_THREADS` zawiera tylko `["MainThread", "RobotFrameworkTimeoutThread"]`. Wątki użytkownika nie są na liście, więc komunikaty są **cicho ignorowane**.

Nawet gdyby sprawdzenie przeszło, `LOGGER._log_message_parents` (lista wskazująca na aktualny węzeł wynikowy) jest **globalną, współdzieloną listą**. Wiele wątków modyfikujących ją jednocześnie powoduje, że wiadomości trafiają do losowych miejsc w drzewie wyników.

### Scenariusz 2 – uruchamianie keywordów z wątków

`EXECUTION_CONTEXTS.current` to **globalny singleton** ze zwykłą listą `_contexts`. Nie jest thread-local. Kiedy wątek wywołuje `BuiltIn().run_keyword("X")`, `context.steps[-1]` (lista par `(data, result, impl)`) należy do głównego wątku. Nowy wynik keywordu jest tworzony jako dziecko **aktualnego wynikowego węzła głównego wątku** (nie wątku roboczego), przez co logi i wyniki lądują w złym miejscu w strukturze `output.xml`.

Jednocześnie `LOGGER._output_file` (XmlLogger) zapisuje do pliku **inkrementalnie** podczas wykonania. Równoległe zapisy z wielu wątków przeplatają się i mogą uszkodzić XML (niezamknięte tagi, przekrzyżowane węzły).

---

## 2. Założenia i ograniczenia

### Założenia

| # | Założenie |
|---|-----------|
| A1 | Główny wątek RF jest zablokowany w `Run Keywords In Parallel` / `Run Functions In Parallel` (nie generuje nowych zdarzeń RF podczas oczekiwania na wątki) |
| A2 | `loggerhelper.Message` dziedziczy z `robot.result.Message` (potwierdzone w RF 7.4 – linia 82 `loggerhelper.py`), więc ma metodę `visit()` i jest poprawnym obiektem modelu wynikowego |
| A3 | Jedyna wewnętrzna modyfikacja RF to tymczasowe monkey-patching atrybutów globalnych singletonów – żaden plik RF nie jest edytowany |
| A4 | RF 7.4 z Pythonem 3.x (GIL gwarantuje atomowość prostych przypisań atrybutów) |

### Ograniczenia

| # | Ograniczenie |
|---|--------------|
| L1 | `context.test.status` jest mutowany bezpośrednio przez wątki tła (formalny race condition; bezpieczny w praktyce przez GIL, a semantycznie poprawny – błąd wątku = błąd testu) |
| L2 | Listenery RF nie otrzymują zdarzeń z wątków tła (zdarzenia są tłumione przez proxy) |
| L3 | `context.in_keyword_teardown` nie jest thread-local – może dawać błędne wartości przy równoległych teardownach (przypadek brzegowy) |
| L4 | Rekurencyjne wywołania `Run Keywords In Parallel` wewnątrz wątku (wątek tworzy kolejne wątki) nie są testowane |
| L5 | Tylko `OutputFile` (XmlLogger/JsonLogger/LegacyXmlLogger) jest chroniony proxy; zewnętrzne loggers zarejestrowane przez `LOGGER.register_logger()` nie są tłumione dla wątków |

---

## 3. Uzasadnienie projektu

### Kluczowy wybór architektoniczny: "offline collection + deferred injection"

Rozważano trzy podejścia:

**Podejście A – serializacja przez główny wątek (live)**  
Wątki wysyłają zdarzenia do kolejki, główny wątek natychmiast je przepisuje do LOGGER. Eliminuje race condition na XML, ale de facto serialializuje wykonanie – brak równoległości.

**Podejście B – współdzielony kontekst z lockiem na XML**  
Wątki piszą do XML przez `threading.Lock`. Poprawne dla prostego logowania, ale nie rozwiązuje problemu struktury drzewa wynikowego przy zagnieżdżonych FOR/IF/TRY.

**Podejście C – odroczona iniekcja (wybrane)**  
Wątki budują swoje drzewa wynikowe w pamięci (in-memory). Po zakończeniu wszystkich wątków, z głównego wątku następuje iniekcja: `parent_result.body.append(wrapper)` (model in-memory) + `wrapper.visit(xml_logger)` (zapis do output.xml). To podejście jest:
- W pełni thread-safe (tylko główny wątek pisze do XML)  
- Odwracalne (all patches w `finally`)  
- Zachowuje pełną strukturę (FOR/ITER/IF/BRANCH/TRY/BRANCH wszystko przez visitor pattern)  
- Zachowuje oryginalne timestampy (ustawiane przez RF machinery podczas wykonania w wątku)

### Dlaczego `wrapper.visit(xml_logger)` działa

`XmlLogger` rozszerza `ResultVisitor`. `loggerhelper.Message` (klasa używana przez LOGGER) dziedziczy z `robot.result.Message`, która ma metodę `visit()`. Dzięki temu jedno wywołanie `wrapper.visit(xml_logger)` rekurencyjnie zapisuje cały komplet zdarzeń (KW, FOR, ITER, IF, BRANCH, TRY, MSG) do pliku XML – żadna struktura nie jest spłaszczana.

### Cztery monkey-patche i dlaczego są konieczne

| Patch | Cel |
|-------|-----|
| `LOGGER._log_message_parents → _ThreadLocalList` | Każdy wątek ma własny stos węzłów rodziców; wiadomości trafiają do właściwego wrappera |
| `LOGGER._output_file → _SuppressingOutputProxy` | Blokuje inkrementalne zapisy XML z wątków tła; główny wątek przepisuje przez lock |
| `context.steps → _ThreadLocalList` | `BuiltIn.run_keyword` szuka rodzica wynikowego w `ctx.steps[-1]`; bez tego nowe wyniki byłyby dziećmi błędnego węzła |
| `context.user_keywords → _ThreadLocalList` | Izoluje śledzenie głębokości user-keywordów (ostrzeżenia o private keywords, teardown scope) |

---

## 4. Przebieg weryfikacji

### Środowisko

- Python 3.13, venv `.venv`  
- Robot Framework 7.4 (zainstalowany przez pip)  
- Windows 10 (PowerShell)

### Uruchomione suity

| Plik | Liczba TC | Wynik |
|------|-----------|-------|
| `tests/test_scenario1.robot` | 8 | 8/8 PASS |
| `tests/test_scenario2.robot` | 9 | 9/9 PASS |
| `tests/test_scenario3_nested.robot` | 5 | 5/5 PASS |
| **Łącznie** | **22** | **22/22 PASS** |

### Weryfikacja struktury output.xml (skrypt `inspect_xml.py`)

Sprawdzono ręcznie strukturę XML dla kluczowych testów:

**Scenariusz 1 – S1-TC1:**  
Dwa wątki → dwa oddzielne węzły `<kw name="[Thread 1] ...">` i `<kw name="[Thread 2] ...">` wewnątrz `Run Functions In Parallel`. Żadne wiadomości się nie przeplatają.

**Scenariusz 2 – S2-TC6:**  
Failing Worker Keyword → `[Thread 1] Failing Worker Keyword` ma status FAIL, zawiera podkeyword z `<msg level="FAIL">` i traceback na `<msg level="DEBUG">`. Outer `Run Keywords In Parallel` → FAIL. `Run Keyword And Expect Error` → PASS. Właściwa propagacja błędu.

**Scenariusz 3 – S3-TC1:**  
Węzły `<for>` + `<iter>` widoczne wewnątrz thread wrappera. Dwa wątki uruchamiają ten sam user keyword z różnymi danymi – węzły FOR/ITER są niezależne dla każdego wątku.

**Scenariusz 3 – S3-TC2:**  
Węzły `<if>` + `<branch type="IF">`, `<branch type="ELSE IF">`, `<branch type="ELSE">` widoczne. Różne gałęzie aktywne w różnych wątkach (T1: `value=150` → `very large`; T2: `value=5` → `small`).

**Scenariusz 3 – S3-TC3:**  
Węzły `<try>` + `<branch type="TRY">`, `<branch type="EXCEPT">`, `<branch type="FINALLY">` widoczne. T1 nie wchodzi do EXCEPT, T2 wchodzi do EXCEPT – poprawne gałęzie aktywne/NOT RUN.

**Scenariusz 3 – S3-TC4:**  
Zagnieżdżony FOR > ITER > IF > BRANCH (dwa poziomy głębokości) widoczny w pełni w XML.

---

## 5. Lista iteracji i poprawek

Rozwiązanie działało poprawnie na pierwszym uruchomieniu – **22/22 PASS bez żadnej poprawki**.

Jedyna zmiana podczas pisania kodu: w pierwotnym projekcie zakładano użycie `thread.ident` w `_SuppressingOutputProxy`, ale ident nie jest znany przed uruchomieniem wątku (race condition w oknie między `thread.start()` a wykonaniem pierwszego kodu w wątku). Zmieniono na identyfikację po **nazwie wątku** (ustawianej przy tworzeniu obiektu `Thread`, przed `start()`).

---

## 6. Ocena końcowego rezultatu

### Jakość output.xml

- **Poprawna** – XML jest well-formed, hierarchia tagów odpowiada rzeczywistej strukturze wykonania.  
- **Pełne grupowanie per wątek** – każdy wątek posiada własny `<kw name="[Thread N] ...">` wrapper.  
- **Brak przeplatania** – wiadomości i zagnieżdżone struktury jednego wątku nigdy nie trafiają do wrappera innego wątku.  
- **Oryginalne timestampy** – każda wiadomość `<msg>` i element `<status>` ma timestamp z czasu rzeczywistego wykonania w wątku.  
- **Zachowana hierarchia** – `<for>`, `<iter>`, `<if>`, `<branch>`, `<try>` posiadają swoje macierzyste tagi i sygnatury. Zero spłaszczania.  
- **Czytelność FAIL** – błąd wątku jest widoczny jako FAIL na poziomie wrappera, podkeywordu, zawiera `<msg level="FAIL">` i traceback na `<msg level="DEBUG">`.

### Jakość log.html

Ponieważ `log.html` jest generowany z in-memory modelu wynikowego (który jest identyczny z XML ze względu na `parent_result.body.append(wrapper)` + `wrapper.visit(xml_logger)`), log.html wyświetla te same struktury co XML – z pełną hierarchią, kolorami statusów i timestampami.

---

## 7. Znane ryzyka lub braki

| # | Ryzyko / Brak | Prawdopodobieństwo | Wpływ |
|---|---------------|--------------------|-------|
| R1 | Listenery RF (v2/v3) nie otrzymują zdarzeń z wątków; jeśli listener zbiera dane o keywordach, pominie wyniki wątkowe | Niskie (tylko przy użyciu listenerów) | Średni |
| R2 | Rekurencyjne `Run Keywords In Parallel` (wątek tworzy nowe wątki) – proxy nie obsługuje warstwy proxy-na-proxy | Niskie | Wysoki |
| R3 | `context.test.status` – jeśli dwa wątki jednocześnie kończą się błędem, ostatni zapis wygrywa (GIL, ale brak Memory Ordering gwarancji w teorii) | Bardzo niskie | Niski |
| R4 | `context.in_keyword_teardown` nie jest thread-local – przy równoległym `Keyword Teardown` może dać niepoprawny wynik | Bardzo niskie | Niski |
| R5 | Przy bardzo dużej liczbie wątków (>50) czas iniekcji sekwencyjnej może być zauważalny | Niskie w praktyce | Niski |

---

## 8. Samoocena rozwiązania (skala 0–2)

| Kryterium | Ocena | Uzasadnienie |
|-----------|-------|--------------|
| **Poprawność techniczna** | 2 | 22/22 testów PASS, poprawna struktura XML potwierdzona inspekcją, żadna struktura RF nie jest spłaszczana |
| **Zgodność z wymaganiami** | 2 | Wszystkie 10 wymagań funkcjonalnych spełnione: grupowanie per wątek, brak przeplatania, oryginalne timestampy, thread-safe, oba scenariusze, FAIL visibility, tylko RF API, zero-interference, reversibility, zachowanie FOR/IF/TRY |
| **Bezpieczeństwo wątkowe** | 2 | `_ThreadLocalList` używa `RLock` do ochrony słownika, proxy używa `Lock` do serializacji zapisów XML, `LOGGING_THREADS` jest zastępowany kopią (nie mutowany in-place) |
| **Jakość struktury logów** | 2 | Per-thread wrapper kw, hierarchia podkeywordów, FOR/ITER/IF/BRANCH/TRY/BRANCH zachowane, timestamps ISO 8601, FAIL status propagowany |
| **Czytelność rozwiązania** | 1 | Kod jest dobrze podzielony na klasy (_ThreadLocalList, _SuppressingOutputProxy, ThreadLogger), ale wymaga rozumienia RF internals; monkey-patching jest z natury nieoczywisty |
| **Łatwość utrzymania** | 1 | Rozwiązanie jest sprzężone z prywatnymi atrybutami RF (`_log_message_parents`, `_output_file`) – zmiana nazw w kolejnych wersjach RF wymaga aktualizacji; brak stabilnego publicznego API do tego celu w RF |

**Suma: 10/12**

---

*Wygenerowano: 2026-04-20 | Robot Framework 7.4 | Python 3.13 | Windows 10*
