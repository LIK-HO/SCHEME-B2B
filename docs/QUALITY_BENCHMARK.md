# Quality benchmark: SCHEME-B2B

Дата ревизии: 2026-09-19

Этот документ не утверждает, что SCHEME-B2B должен копировать внутренние системы перечисленных компаний. Список используется как **benchmark library**: из зрелых публично описанных продуктов и инженерных практик извлекаются конкретные свойства, которые можно проверить тестами, контрактами и эксплуатационными правилами.

## 1. Поле сравнения

### CRM, workflow и операционная автоматизация

Salesforce, Microsoft Dynamics 365, HubSpot, Zoho CRM, Bitrix24, Kommo (amoCRM), Creatio, Pipedrive, ServiceNow, Freshworks, SAP Customer Experience, Oracle NetSuite, Monday.com, Jira Service Management.

Из них берём: явные состояния процесса, правила переходов, роли, историю изменений, дедупликацию, автоматизацию с контролем ошибок, понятный operator-first UX.

### Российская идентификация и контрагентская разведка

ФНС ЕГРЮЛ/ЕГРИП, ФНС Реестр МСП, Росстат Статистический регистр, Росстат ОК ТЭИ, Контур.Фокус, СПАРК-Интерфакс, Saby/СБИС, Rusprofile, List-Org, Checko.

Из них берём: идентичность юридического лица, историю и актуальность, признаки риска, связанные сущности, разные классы источников, автоматическое обновление, API/массовые проверки, provenance.

### MDM, entity resolution и data quality

SAP Master Data Governance, Informatica MDM, IBM Master Data Management, Oracle Enterprise Data Management, Reltio, Stibo Systems, Semarchy xDM, TIBCO EBX, Profisee, Ataccama, Collibra, Dun & Bradstreet.

Из них берём: master identity, deterministic/threshold matching, duplicate prevention, validation rules, data stewardship, completeness/quality metrics, lineage, auditability.

### B2B enrichment и data health

ZoomInfo, Apollo, D&B, Salesforce Data Cloud / CRM data quality patterns.

Из них берём: data health, enrichment, freshness, suppression of bad/duplicate records, explicit confidence/provenance вместо «AI уверен».

### Data ingestion и orchestration

Airbyte, Fivetran, Dagster, Apache Airflow, Prefect, Temporal, Confluent/Kafka, dbt, AWS Glue, Azure Data Factory, Google Cloud Dataflow.

Из них берём: adapter/connector boundary, checkpoints, bounded retries, idempotent jobs, replay/recovery, source contracts, observability, failure isolation.

### Reliability, API и delivery engineering

Google SRE, AWS Builders Library, Microsoft Azure Well-Architected, Stripe API, OpenTelemetry.

Из них берём: SLI/SLO thinking, error budgets как operating mechanism, timeout/retry/backoff/jitter, idempotency keys, health/readiness, structured events, metrics/logs/traces semantics.

### Observability и security

Prometheus, Grafana, Datadog, Sentry, Splunk, Elastic, PagerDuty, Okta, Auth0, GitHub/GitLab CI/CD.

Из них берём: operational visibility, least privilege, secret isolation, audit trail, controlled releases, explicit failure states, rollback/recovery readiness.

## 2. Сводная матрица зрелости

| Домен | Эталонное свойство | Требование SCHEME-B2B | Как доказывается |
|---|---|---|---|
| Identity | Один устойчивый идентификатор | Нормализованный ИНН + ОГРН/ОГРНИП | unit/integration tests |
| Uniqueness | Global duplicate prevention | P0 по 01/02/03 | dedup tests |
| Requisites | Formal validation | P1 checksum + type consistency | validation tests |
| Source truth | Provenance | Источник + FNS source + run id | contract + run log |
| Freshness | Current enough to support decision | snapshot ДатаВыг + freshness gate | FNS tests |
| Workflow | Explicit state machine | Ожидает/Принят/Отклонён + outbox state | contract docs/tests |
| Idempotency | Safe replay | event id + ambiguous create reconciliation | service/outbox tests |
| Concurrency | Single active worker role | durable SQLite leases | lease tests |
| Fault isolation | One source/channel failure does not corrupt others | source isolation + independent outbox channels | service tests |
| Retry | Transient-only retry, backoff, jitter | Airtable + bounded external retries | client tests |
| Recovery | Crash-safe restart | durable lease expiry + retryable outbox | lease/outbox tests |
| Readiness | Fail closed before unsafe work | /ready checks source and FNS state | API tests |
| Observability | Every run has outcome and evidence | RunLog + structured summary | integration tests |
| Security | Secret separation | env/Secrets, HTTPS, no secret logging | review + CI |
| Release | Automated quality gate | lint, format, compile, tests, coverage, package build, Docker | GitHub Actions |
| Maintainability | Stable internal contracts | adapters + domain services | architecture review |
| Operator UX | Small number of meaningful controls | profile, source, queue, result | UX review |

## 3. Что сознательно не копируем

- микросервисы ради «enterprise» вида;
- десятки автоматизаций, которые повторяют core-бизнес-правила;
- AI-оценку как замену официальной проверке;
- скрытые синхронизации без idempotency;
- бесконечные retry;
- неограниченную схему/поля, которые оператору не нужны;
- scraping нестабильных внутренних интерфейсов как основу core;
- раннее усложнение инфраструктуры до появления соответствующей нагрузки.

## 4. Критерий реальной зрелости

Компонент считается зрелым не потому, что в нём есть «сложная» технология, а только если выполнены одновременно:

1. бизнес-инвариант сформулирован однозначно;
2. отказ и пограничный случай определены;
3. состояние можно восстановить после сбоя;
4. повторная операция безопасна или явно запрещена;
5. источник данных и актуальность доказуемы;
6. ошибка видима оператору/системе и не маскируется успехом;
7. поведение покрыто автоматическим тестом;
8. изменение проходит release gate.

## 5. Текущий вывод по SCHEME-B2B

Ядро уже имеет правильное направление: монолит, adapter boundaries, P0/P1, FNS freshness, outbox, health/readiness, CI gates. Следующая граница зрелости — не добавление «ещё функций», а усиление доказуемости: concurrency, contract tests, source readiness, recovery, measurable SLO/SLI и controlled release.

## Основные публичные ориентиры

- Google SRE: service level objectives, monitoring and error-budget practices.
- AWS Builders Library: safe retries and idempotent APIs.
- Microsoft Azure Well-Architected: transient fault handling, idempotency, health monitoring.
- Salesforce / HubSpot / Bitrix24: duplicate management, workflow history and auditability.
- SAP MDG / Informatica / Stibo: master-data quality, governance, matching and lineage.
- Kontur.Focus / СПАРК / Saby / Rusprofile: Russian counterparty identity, monitoring and enrichment.


## 6. Фиксированный предел сложности

Benchmark library не является списком технологий к внедрению. Это библиотека проверяемых свойств. Для первого рабочего контура зафиксирован конечный инженерный массив из девяти слоёв: Discovery, Normalize, Identity/Dedup, Verification/Freshness, Qualification, Core/Projection, Run/Recovery, Notification, Operator UI.

Цель каждого слоя — одна измеримая обязанность. Дублирование бизнес-правил между core, Airtable и автоматизациями не допускается.

### Функциональный критерий готовности

Система не считается готовой только потому, что в ней есть CI, API, база или dashboard. Первый рабочий контур готов только когда оператор получает пригодный результат: компания + подтверждаемая идентичность + Москва/сфера + потребность или её источник-сигнал + контактный канал + источник данных, а повторный поиск не возвращает уже обработанную сущность.

### Остановка расширения

После выполнения обязательного массива проект не должен продолжать расти ради «зрелого вида». Изменения переводятся в maintenance: исправления, актуальность источников, тесты, безопасность, восстановление и улучшение операторского времени. Новая функция требует доказанной задачи, метрики/теста и анализа нового отказа.
