# Lango Core: актуальная карта проекта

## 1) Модули и их роль

- `integrations` — доменные интеграции с внешними API:
  - `Tracker`, `ApiAuthType`, `ApiAuthID` (включая шифрование credentials и auth-injection в запросы).
  - `PartnerAccount` и идентификаторы аккаунтов.
  - Утилиты авторизации/маскирования чувствительных данных (`integrations/utils.py`).
- `service_builder` — ядро оркестрации выполнения:
  - Конструкторы API-вызовов: `ServiceEndpoint`, `ServiceMethod`.
  - Исполняемые блоки: `Scenario` + `ScenarioStep`.
  - Оркестрация: `Workflow` + `WorkflowStep`.
  - Абстракция бизнес-действий: `BusinessAction` + `BusinessActionVariant`.
  - Runtime-движок: `ScenarioRunner`, `WorkflowRunner` (`service_builder/utils.py`).
- `scheduler` — планировщик запуска workflow:
  - `Frequency` (cron-выражение), `ScheduledWorkflow` (workflow + расписание + default args).
  - Sync в системный crontab (`scheduler/crontab.py`), запуск через management command (`scheduler/management/commands/run_workflow.py`).
  - Админ-виджеты для typed аргументов scheduled workflow.
- `metadata` — справочники и правила конфигурации:
  - Наборы параметров/совместимости/глобальных переменных (`TargetParameter`, `CompatibilityMatrix`, `GlobalVariable`).
  - Конфиги по трекерам/паблишерам (`TrackerConfig`, `PublisherConfig`).

## 2) Связи между модулями

- `service_builder` -> `integrations`:
  - `ServiceEndpoint.tracker` указывает на `integrations.Tracker`.
  - Runtime (`ScenarioRunner`/`WorkflowRunner`) резолвит `ApiAuthID` и использует `integrations.utils.apply_auth_to_request`.
- `scheduler` -> `service_builder`:
  - `ScheduledWorkflow.workflow` ссылается на `service_builder.Workflow`.
  - Команда `run_workflow` запускает `WorkflowRunner`.
- `metadata` -> `integrations`:
  - `TrackerConfig.tracker` и `PublisherConfig.partner_account` привязаны к сущностям integrations.
  - `GlobalVariable` используется как системный словарь ключей для нормализации.
- Общая точка входа — Django Admin (маршруты и app wiring через `lango_core/urls.py`).

## 3) Runtime-потоки (коротко)

### 3.1 Integrations runtime

1. В рантайме шаг API получает `auth` из контекста.
2. `apply_auth_to_request` инжектит auth в header/query/path-template.
3. Выполняется HTTP-запрос, чувствительные значения маскируются в логах.

### 3.2 Service Builder runtime

1. `WorkflowRunner` стартует с `initial_context`, резолвит model/auth аргументы.
2. По `WorkflowStep`:
   - либо прямой запуск `Scenario`,
   - либо `BusinessAction` -> выбор `BusinessActionVariant` (по tracker) -> `Scenario`.
3. Внутри `ScenarioRunner`:
   - шаблонизация `{{ var }}` и безопасный доступ к nested paths,
   - API-вызовы/Action steps,
   - pagination, error handlers, context extraction, success conditions.
4. Контекст и логи накапливаются и возвращаются наружу.

### 3.3 Scheduler runtime

1. `Frequency` генерирует cron-expression.
2. `sync_crontab` пишет активные `ScheduledWorkflow` в системный crontab.
3. cron запускает `manage.py run_workflow --scheduled-workflow=<id>`.
4. Команда:
   - применяет distributed lock (Redis) против дублей,
   - резолвит default arguments,
   - запускает `WorkflowRunner`,
   - пишет structured logs в `logs/cron_workflow/<date>/`.

### 3.4 Metadata runtime

- В основном read-heavy конфигурационный слой для админки и правил.
- `GlobalVariableListView` отдает список глобальных переменных для UI/API.
- Прямого исполнения workflow в `metadata` нет; модуль поставляет справочники и ограничения.

## 4) Изменения по типизации Scheduled Workflow arguments

Ниже зафиксировано текущее фактическое состояние typed-аргументов scheduled workflow:

- В `scheduler` admin виджете аргументы workflow загружаются динамически из `workflow.arguments` и нормализуются до структуры с `name` + `type`.
- На UI уровне добавлен typed input parsing:
  - `integer` -> `int`,
  - `float/number` -> `float`,
  - `boolean` -> `bool`,
  - `json` -> `JSON`,
  - `report_dates` -> `{preset}` или `{start, end}`.
- Для `type=model` подгружаются model choices через API и сохраняется PK выбранного объекта.
- На backend в `scheduler.utils.resolve_default_arguments` закреплена типизация перед запуском:
  - `report_dates` preset разворачивается в реальные даты,
  - строки приводятся к integer/float/boolean/json в зависимости от declared type.

Итог: `ScheduledWorkflow.default_arguments` перестал быть «плоским строковым JSON» и стал типизированным входным контекстом для рантайма.

## 5) Влияние на WorkflowRunner / Scenario / BusinessAction

- `WorkflowRunner`:
  - получает уже типизированный `initial_context` из scheduler command;
  - дополнительно резолвит `type=model` из `workflow.arguments` (pk -> model instance), что делает работу с `ApiAuthID`/другими model args устойчивой;
  - фильтрует stale mapping keys по фактическим аргументам target-сущности (Scenario/BusinessAction/Variant).
- `Scenario`:
  - контракт аргументов теперь фактически поддерживает смешанный формат (legacy string + typed dict),
  - runner корректно работает с object/list значениями при шаблонизации (не принудительно в строку при exact template match).
- `BusinessAction`:
  - аргументы также обрабатываются как typed-aware список (через общий extraction/filtering в `WorkflowRunner`);
  - variant mapping опирается на реальные arg names целевого `Scenario`, лишние ключи отсекаются и логируются как stale.

Практический эффект: меньше runtime-ошибок из-за неверных типов и устаревших mapping-ключей, предсказуемее передача аргументов от scheduler -> workflow -> business action -> scenario.

## 6) Инженерные принципы разработки

Свод правил по качеству, темпу работы и полиморфным контрактам вынесен в отдельный файл: [`engineering_principles.md`](engineering_principles.md).
