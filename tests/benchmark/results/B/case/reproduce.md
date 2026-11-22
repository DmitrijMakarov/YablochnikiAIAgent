# Воспроизведение кейса «Ритм»

Все действия из корня `/Users/dima/strateg-benchmark-runs/B`. Использован Python 3.13.5, SQLite 3.49.1, только стандартная библиотека; новые пакеты не устанавливались. Исполняемый файл наблюдался как `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`. Версии и фактические длительности повторного запуска: `calculations/reproduction_check.json`. Модель, токены, денежная стоимость — неизвестны: измеритель не предоставлен. Время фаз — наблюдаемое значение CLI в run.tsv, оно не равно полному времени от пользовательского сообщения.

## Повторить расчёты

```sh
python3 --version
python3 case/calculations/reproduce.py
python3 -m tools.case verify case --research-only
python3 -m tools.case verify case
```

`reproduce.py` сначала сверяет SHA-256 входов с закреплённым `input_versions.json`; при изменении останавливается. Затем по порядку запускает `analysis.py`, `experiment.py`, `reminder_strata.py`, `platform_check.py`, `economics.py`, `independent_check.py`. Все производные файлы остаются внутри case/calculations/. Сравнивает SHA-256 15 результатов с предыдущими; сохраняет returncode/длительности/версии в reproduction_check.json. Выполненный повтор дал совпадение всех 15 файлов. Время в отчёте меняется при повторе; содержательные таблицы детерминированы. Псевдослучайного моделирования нет.

Не запускать init/begin/finish для простого пересчёта законченного кейса: это команды состояния. Не запускать write_claims.py/write_audit.py после закрытия фаз для изменения содержания; они сохранены как код первоначальной сборки реестра и аудита. Для новой версии решения нужен новый кейс-ревизия по workflow, текущий кейс ждёт выбора руководителя.

## Последовательность фактически выполненного рабочего процесса

```sh
python3 -m tools.case init case
python3 -m tools.case begin case scope --environment Codex
# дополнен рабочий brief.md; SOURCE_BRIEF и inputs не изменялись
python3 -m tools.case finish case
python3 -m tools.case begin case research --environment Codex
python3 -m tools.case ingest case S-001@1
python3 -m tools.case ingest case S-002@1
python3 -m tools.case ingest case S-003@1
# S-003@1: ValueError: extraction limit exceeded, split the input
python3 -m tools.case ingest case S-004@1
python3 -m tools.case ingest case S-005@1
python3 -m tools.case ingest case S-006@1
python3 -m tools.case ingest case S-007@1
python3 -m tools.case resume case --environment Codex
# локальные расчёты и реестр; точные отметки в run.tsv
python3 -m tools.case verify case --research-only
python3 -m tools.case finish case
python3 -m tools.case begin case strategy --environment Codex
# стратегия, дополнительные проверки и аудит
python3 -m tools.case verify case
# первый полный verify: missing or unknown claim markers
python3 -m tools.case resume case --environment Codex
# исправлен поясняющий шаблон ссылки, затем повторный verify успешен
python3 -m tools.case verify case
python3 -m tools.case finish case
```

Это перечень команд и зависимостей, а не предлагаемый скрипт перезаписи. После ошибки S-003 остальные источники были обработаны в исходном пакете, затем выполнен resume и диагностика; run.tsv хранит исходный порядок и все статусы. Внешних запросов было ноль; ingest публичных источников использовал локальные снимки без `--live`.

## Ограничение штатного импорта и обход вычислениями

CSV events.csv содержит 85080 строк данных, штатный extractor ограничен 20000 записями. Ошибка записана sources.tsv/run.tsv, tools/sources.py и tools/verify.py читались только для диагностики. Поставленные инструменты, манифест и входы не менялись; повторного бесполезного ingest не было. S-003@1 остаётся unavailable именно для штатной выписки; итоговый verify честно сообщает 6 доступных/1 недоступный источник.

Локальные расчёты читают весь оригинальный events.csv по разрешённому пути. analysis.py сохраняет пять `events_rows_*.jsonl` с исходным `line:N` и source S-003@1, по 19000 записей максимум. independent_check.py сверяет все 85080 строк выписок с CSV и исходным SHA-256; это дополнительная проверка, не формальный результат штатного ingest. Заголовок CSV — line:1; данные событий line:2–85081, регистраций line:2–3021, coverage line:2–147. В JSONL источников CLI locator относится к исходной строке. Для численных выводов claims.tsv содержит полные диапазоны и конкретный расчёт/срез.

## Расположение расчётов и правил

| Файл | Что воспроизводит |
|---|---|
| analysis.py → quality_data.json | Дубликаты, пропуски, даты, исключения, хеши; исходная единица — аккаунт |
| weekly.csv | 10 когорт × 10 метрик; total=immature+unknown_platform+incomplete+n, k/n, Wilson 95%, границы для всей календарно зрелой когорты |
| periods.csv, sensitivity.csv | Ранние/поздние блоки и определения; разницы в п.п. и нормальные 95% интервалы; пустая доля при n=0 |
| segments.csv, decomposition.csv | Канал/platform/goal/channel×platform, unknown, k/n/веса; разложение от ранней базы и стандартизация на средние веса |
| activation.csv, activation_users.csv | D0–3 создание/выполнение/union/reminder и пересечения legacy; полное D0–3 наблюдение |
| activation_associations.csv, reminder_strata.csv | Связь ранних событий с поздним возвратом, дополнительные ограничения по core и цели/каналу; не эффект вмешательства |
| platform_check.csv | Адресная проверка Android/iOS на тех же полных целевых D7/D30-днях; отдельная наблюдаемость D0–3 |
| experiment.py → experiment_scenarios.csv | Мощность против нуля, прохождение практического порога, каждого guardrail и зависимость-свободные совместные границы; все базы/эффекты сценарные |
| economics.py → economics.csv | N×ΔR×маржа и стоимость, пороги окупаемости; не выручка из данных |
| independent_check.py → independent_check.json | Независимый SQL по сырым CSV: 6 сравнений k/n, уникальные ID, построчная сверка всех дополнительных выписок |
| input_versions.json, code_and_brief_versions.json | Закреплённые версии входов, supplied tools, исходного брифа и workflow по SHA-256 |

Паспорта и предвыбранные вопросы — research.md, полное правило эксперимента/допущения — strategy.md. Маркеры утверждений раскрыты в claims.tsv; содержательные вердикты — audit.tsv, пределы проверки — quality.md. Расчёты по синтетике не подтверждают причинное преимущество решения. Для rare-event guardrails нормальное приближение требует нового score/exact-планирования после измерения баз; выборка не обоснована для полного правила успеха.

## Зафиксированные версии входов

| ID | Файл в inputs/ | SHA-256 оригинала |
|---|---|---|
| S-004@1 | coverage.csv | `f9bc1c0170769edbbd1507bed0443effdfc2d574f0b9d32dc518f1b40f2a12d2` |
| S-003@1 | events.csv | `e2652a4f757eab524258ff9a37e3bb2e308a6a1c072e8a1617e93f1b93a4918c` |
| S-005@1 | google-tasks.jsonl | `c22bca37134fbf19c3e049977e7a3ce71b8d2210c2c3a5606c1d7a4c8bf3f5d3` |
| S-006@1 | microsoft-to-do.jsonl | `ecbf649791a348f77d9dec22a2e1c3e78618ed15b3c20b076b0b584126c0c383` |
| S-001@1 | product.md | `5fdf8ec7946107cc1ffe25e2b4f93b97f9f44a07affa8fed2b97f1a5d7215360` |
| S-002@1 | signups.csv | `0cb3e607f604a8196198c3033b570df340ec33cb06aa62a0c24e4669118f2ce4` |
| S-007@1 | todoist.jsonl | `ecb62a559433eddde30d052be67692d9948c39f285eebf06518467967dd9896d` |

SHA-256 оригиналов отличается от SHA-256 извлечений в sources.tsv; это разные объекты. Локальные снимки отражают только перечисленные в inputs.json фрагменты от 10 ноября 2026, а не актуальную полную справку. SOURCE_BRIEF.md и case/inputs.json также захешированы в calculations/code_and_brief_versions.json.

## Известные ошибки и состояние

1. Лимит извлечения S-003@1 — сохранён, локальный вычислительный путь проверен отдельно.
2. Первый полный verify отклонён из-за буквального поясняющего шаблона ссылки с многоточием, принятого за ID. Выполнен resume, шаблон заменён на текстовый пример C-010; повторный verify прошёл. Никакой содержательный источник не заменялся. Ошибка явно дописана в run.tsv; более ранняя запись shell ok фиксировала создание аудита, а не успешный verify.
3. Ошибок расчёта при полном повторе не получено; 15 из 15 SHA-256 совпали.

Запуск продукта и исследования с участниками не выполнялся; Git-коммит не создавался. Финальное состояние фиксируется CLI в state.json/run.tsv и должно быть awaiting_decision. Фактический выбор пользователя отсутствует; фазу decision не открывали.
