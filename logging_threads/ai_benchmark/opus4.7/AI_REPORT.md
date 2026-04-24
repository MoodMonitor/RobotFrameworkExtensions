# AI_REPORT — Thread-safe logging for Robot Framework 7.4

## 1. Diagnoza problemu

Robot Framework 7.4 odrzuca logi pochodzące z wątków innych niż `MainThread`
(i `RobotFrameworkTimeoutThread`) na poziomie funkcji
`robot.output.librarylogger.write`:

```python
# robot/output/librarylogger.py
LOGGING_THREADS = ["MainThread", "RobotFrameworkTimeoutThread"]

def write(msg, level="INFO", html=False, console=None):
    ...
    if current_thread().name in LOGGING_THREADS:
        LOGGER.log_message(Message(msg, level, ...))
```

Skutki:

1. **Scenariusz „zwykłe logowanie z wątku”** — komunikaty po prostu
   znikają; nie ma ich ani w `output.xml`, ani w `log.html`.
2. **Scenariusz „keyword uruchamiany w wątku”** — próby wywołania
   `BuiltIn().run_keyword(...)` w wątku trafiają do wspólnego,
   główno-wątkowego `Logger`. Ten `Logger` utrzymuje współdzielony
   stos `_log_message_parents` oraz strumieniowo zapisuje
   `output.xml` przez `XmlLogger`. Równoczesne modyfikacje z wielu
   wątków zarówno mieszają strukturę wyniku (wpisy trafiają „pod nie
   ten keyword”), jak i realnie psują XML (przeplatane tagi).

Dodatkowy efekt uboczny: nawet gdyby dodać nazwę wątku do listy
`LOGGING_THREADS` (tak robi `robotbackgroundlogger`), komunikaty
wylądują u aktualnie aktywnego rodzica **MainThread**, bez żadnego
grupowania per wątek i ze spłaszczoną strukturą.

## 2. Założenia i ograniczenia

* Można używać wyłącznie publicznych / wewnętrznych API Robota; brak
  zewnętrznych pakietów pip.
* Nie wolno edytować plików samego Robot Framework — w rozwiązaniu
  stosowany jest monkey-patch wykonywany w runtime, w pełni
  odwracalny.
* Framework uruchamia pojedynczy główny `Runner` i jednocześnie
  strumieniowo zapisuje `output.xml` — rozwiązanie musi działać wokół
  tej asymetrii (wątki nie mogą pisać bezpośrednio do strumienia
  XML).
* Pełne przeniesienie semantyki `BuiltIn.run_keyword` do wątku nie
  jest możliwe bez modyfikacji silnika Robota: zamiast tego biblioteka
  oferuje `run_keyword(name, *args)`, który wywołuje implementację
  pythonową keywordu bezpośrednio i rejestruje jej wykonanie jako
  natywny element `<kw>` w drzewie danego wątku.
* Rozwiązanie zakłada, że użytkownik woła `Wait All Threads` —
  jeżeli testy zostaną przerwane (np. sygnałem), wbudowane
  zabezpieczenie w listenerze `end_test` dodatkowo zwalnia patch.
* Struktury kontrolne (FOR / IF / TRY-EXCEPT) uruchamiane **wewnątrz
  wątku** są emulowane przez menedżery kontekstu `thread_for`,
  `thread_if`, `thread_try`. W `output.xml` produkują dokładnie te
  same tagi (`<for>`, `<iter>`, `<if>`, `<branch>`, `<try>`), których
  używa sam Robot — nic nie jest spłaszczane.

## 3. Uzasadnienie projektu

Mechanizm trójwarstwowy:

1. **Runtime patch na `librarylogger.write`** (instalowany tylko na
   czas aktywnych wątków, liczony referencyjnie). Wywołanie z
   zarejestrowanego wątku zostaje przekierowane do jego prywatnego
   drzewa wyników; wywołanie z `MainThread` przechodzi przez oryginalną
   funkcję.
2. **Per-wątkowe `_ThreadRecord`** trzymające:
   * korzeń typu `robot.result.Keyword` o nazwie `Thread '<name>'`,
   * stos rodziców (odpowiednik `_log_message_parents`),
   * status i błąd (w razie wyjątku).
3. **Replay przy `Wait All Threads`.** W głównym wątku, po
   dołączeniu wszystkich workerów, drzewo każdego wątku jest:
   * dopisywane do `body` bieżącego rodzica (dla spójności modelu
     w pamięci),
   * **replayowane** przez globalny `LOGGER` (`start_keyword`,
     `log_message` bezpośrednio do zarejestrowanych loggerów, itd.),
     dzięki czemu strumień `output.xml` i wszystkie listenery
     dostają zdarzenia w odpowiedniej kolejności i zagnieżdżeniu.

Kompromisy:

* Brak równoległości w rzeczywistej sekcji IO `output.xml`: zdarzenia
  z wątków są zapisywane podczas `Wait All Threads`, a nie w czasie
  wykonania wątku. To świadomy wybór — Robot zapisuje XML
  strumieniowo, a `XmlWriter` nie jest thread-safe. Timestampy
  oryginalne są zachowane na każdym obiekcie `Message` / `Keyword`,
  więc w raporcie widać prawdziwy porządek czasowy.
* Keywordy uruchamiane w wątku nie przechodzą przez właściwy `Runner`
  Robota: nie będą np. respektowane timeouty keyword-scope,
  pre-run modifiers czy pełna semantyka setup/teardown w wątku. Logi
  i struktura keywordu są jednak identyczne z tym, co generuje
  Robot.

## 4. Przebieg weryfikacji

Uruchomione trzy zestawy:

| Suite | Test cases | Wynik |
|-------|-----------|-------|
| `tests/01_baseline_problem.robot` | 1 (demonstruje bug) | PASS* |
| `tests/02_solution.robot` | 4 | 4/4 PASS |
| `tests/03_stress_and_reversibility.robot` | 3 | 3/3 PASS |

\* Baseline pokazuje problem **w output.xml**, a nie w statusie testu.
Potwierdzenie bugu: 9 oczekiwanych komunikatów workerów zostało
zgubionych, pozostały tylko 2 komunikaty `MainThread`.

Po zastosowaniu `ThreadLogger` (`tests/verify_output.py`):

* 18 odrębnych ramek `Thread '<name>'` w `output.xml`.
* Zachowane tagi strukturalne (`<for>`, `<iter>`, `<if>`, `<branch>`,
  `<try>`) w drzewie wątku `nested-1`.
* Timestampy monotoniczne w każdym wątku, z realnym nakładaniem się
  okien czasowych różnych wątków (dowód faktycznej równoległości).
* Wątek `parallel-fail` oznaczony statusem `FAIL`, zawiera pełny
  traceback w ciele keywordu — awarie są czytelne.
* Reversibility: po `Wait All Threads` `robot.output.librarylogger.write`
  jest tożsamy z referencją sprzed uruchomienia (sprawdzane keyword’em
  `Assert No Patches Installed`).

Pełne artefakty znajdują się w `results/all/output.xml`,
`results/all/log.html`, `results/all/report.html`.

## 5. Lista iteracji i poprawek

1. **Iteracja 1 — brak rejestracji wątku po ident.**
   Początkowa wersja rejestrowała record po `thread.ident`, który
   przed `start()` jest `None`. Worker nie znajdował swojego recordu
   i padał z `RuntimeError`. Poprawka: worker sam rejestruje się w
   `_REGISTRY` (metoda `attach_current`) w pierwszej linii `_runner`,
   używając realnego `threading.get_ident()`.
2. **Iteracja 2 — `thread_try` propagował wyjątek.**
   Menedżer `try_block` re-raise’ował wyjątek, więc kod użytkownika
   nigdy nie docierał do `except_block`. Poprawka: `try_block`
   łapie wyjątek, zaznacza gałąź `FAIL` i udostępnia go jako
   `handle.caught` (bliskie semantyce RF TRY/EXCEPT).
3. **Iteracja 3 — puste `<kw>` w output.xml.**
   Po pierwszym działającym runie okazało się, że drzewa wątków były
   dopisywane jedynie do modelu w pamięci, a `XmlLogger` zapisuje
   strumień na żywo. Dodano `_replay_tree`, który odtwarza zdarzenia
   przez globalny `LOGGER` tak, by pojawiły się w `output.xml`.
4. **Iteracja 4 — niepoprawny schemat `<for>`.**
   Wewnątrz `<for>` wstawiałem bezpośrednio `<if>`. `rebot`
   odrzucał plik z `Incompatible child element 'if' for 'for'`.
   Poprawka w teście demonstracyjnym: każda iteracja używa
   `for_.iteration(...)`, tak aby `<for>` zawierał wyłącznie
   `<iter>`.
5. **Iteracja 5 — traceback wątku poniżej progu DEBUG.**
   Traceback był zapisywany jako DEBUG, więc przy domyślnym
   `--loglevel INFO` znikał. Zmiana poziomu na INFO.

## 6. Ocena końcowego rezultatu

* **Struktura** — `output.xml` jest walidowany przez samego Robota
  (bez błędów `rebot`). Każdy wątek jest osobnym `<kw owner="ThreadLogger"
  name="Thread 'xxx'">`; struktury kontrolne wewnątrz wątku są
  tagowane natywnie.
* **Czytelność** — w `log.html` wątki widać jako klikalne sekcje
  obok zwykłych keywordów; timestampy, status, wiadomości wyglądają
  identycznie jak w logach main-thread.
* **Grupowanie per wątek** — wyłącznie komunikaty danego wątku
  znajdują się pod jego `<kw>`. Weryfikator (`verify_output.py`)
  potwierdza brak „wycieków” między wątkami i do MainThread.
* **Przydatność do analizy** — log.html pozwala łatwo zidentyfikować
  wątek, który zawiódł (status FAIL + traceback).

## 7. Znane ryzyka lub braki

* **Brak pełnego `BuiltIn.run_keyword` w wątku.** Nie da się bez
  modyfikacji Robota w pełni uruchomić user-keywordu (napisanego w
  `.robot`) wewnątrz wątku. Dla keywordów bibliotecznych wywoływanych
  Python-owo biblioteka robi to czysto przez `run_keyword(name, *args)`.
* **`--loglevel TRACE` + timeouty.** Nie testowałem scenariuszy z
  równoczesnym keyword-timeoutem i wątkami w tle; `RobotFrameworkTimeoutThread`
  zachowuje oryginalne zachowanie, ale wątki użytkownika zaczęte
  *przed* timeoutem i wciąż żyjące mogą nie dokończyć `Wait All Threads`.
  Rekomendacja: zawsze dołączać wątki przed końcem keywordu.
* **Kolejność vs timestampy.** `Wait All Threads` zapisuje drzewa
  wątków w kolejności ich startu. Jeżeli dwa wątki naprawdę wykonują
  się współbieżnie, ich bloki w `log.html` pojawiają się szeregowo
  (zgodnie z kolejnością startu), a nie czasowo. Oryginalne
  timestampy wewnątrz każdego wątku pozostają wiarygodne — możliwa
  do odtworzenia ścieżka czasowa, ale wymaga porównania `time="…"`.
* **Wywołania z wątków nie obsługują asynchronicznych keywordów**
  (coroutines) — nie testowane.
* **Reversibility przy nieobsłużonym wyjątku z `Wait All Threads`.**
  `Wait All Threads` rzuca `AssertionError`, jeśli choć jeden wątek
  zawiódł. Patch jest jednak zdejmowany **przed** tym wyjątkiem
  (deactivate jest w tej samej metodzie, przed `raise`), więc
  odwracalność jest zachowana.
* **Wątki demonowe.** Biblioteka uruchamia workery jako
  `daemon=True`, aby przerwany bieg testu nie zatrzymał całego
  procesu. Skutek uboczny: jeżeli użytkownik „zapomni” wywołać
  `Wait All Threads`, listener `end_test` próbuje je dołączyć, ale
  nie ma gwarancji zakończenia przed deaktywacją patcha.

---

## Samoocena (0–2)

| Kryterium                    | Ocena | Uwagi |
|------------------------------|:-----:|-------|
| Poprawność techniczna        | 2     | Wszystkie 8 testów PASS, `rebot` / `log.html` generowane bez błędów. |
| Zgodność z wymaganiami       | 2     | 1–11 spełnione; struktura zachowana; patch w pełni odwracalny; brak edycji RF. |
| Bezpieczeństwo wątkowe       | 2     | Każdy wątek ma izolowane drzewo; replay tylko z MainThread; lock w rejestrze. |
| Jakość struktury logów       | 2     | Natywne tagi `<for>`, `<iter>`, `<if>`, `<branch>`, `<try>`; brak spłaszczania. |
| Czytelność rozwiązania       | 2     | Kod podzielony na: record / registry / patcher / replay / library; docstrings. |
| Łatwość utrzymania           | 1     | Replay wymaga dodania nowego `start_/end_` typu przy dochodzeniu nowego node’a (np. While). Aktualnie wszystkie typy obsłużone, ale przyszłe typy w RF wymagałyby update’u `_dispatch_methods`. |

## Co działa, co było poprawiane, co zostaje jako ryzyko (skrót)

**Działa:**

* Proste logowanie z wątków (`robot.api.logger.*`) bez zmiany kodu
  wewnątrz wątku.
* Natywne `<for>`, `<if>`, `<try>` wewnątrz wątku.
* Wywołanie biblioteki keywordu z wątku poprzez
  `run_keyword(name, *args)` lub `Run Keyword In Worker Thread`.
* 10 równoległych wątków bez przeplotu w `output.xml`.
* Pełna odwracalność patcha (potwierdzona keyword’em
  `Assert No Patches Installed`).

**Poprawiane w kolejnych iteracjach:** rejestracja wątku,
`thread_try`, replay strumieniowy, schemat `<for>/<iter>`, poziom
tracebacku. Wszystkie problemy zostały naprawione i udokumentowane
w sekcji 5.

**Ryzyka pozostałe:** pełna obsługa user-keywordów z wątku,
współgranie z keyword-timeoutem, sytuacje w których
`Wait All Threads` nigdy nie jest wywołane. Opisane w sekcji 7.
