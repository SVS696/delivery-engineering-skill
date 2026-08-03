---
name: delivery-engineering
description: "Оркестрирует опциональных backend-, frontend- и test-агентов для реализации утверждённых требований, test-design и независимой проверки готовой реализации. Применяй к запросам «реализуй постановку», «сделай BE/FE», «подготовь тесты», «проверь готовую реализацию», когда известны scope и критерии приёмки. Не применяй для подготовки постановки, чистого code review, merge или deploy без отдельного разрешения."
allowed-tools: Read Glob Grep Write Edit Bash AskUserQuestion Task TaskCreate TaskList TaskUpdate TodoRead TodoWrite
---

# Delivery Engineering

Оркестрируй изменение и проверку ПО после определения требований. Подготовка
смысла остаётся в requirements-процессе; изменение кода имеет отдельные
полномочия, контексты, состояние и критерии завершения.

## Неподвижные правила

1. **Project-first.** Явный запрос, ближайшие инструкции, архитектурный канон,
   автоматические правила и устойчивый стиль соседнего кода выше общей
   литературы.
2. **Явные полномочия.** Профиль объявляет доступные lanes, пользователь —
   разрешённое действие. Наличие роли не разрешает правку кода.
3. **Scope по требованиям.** Каждая lane получает REQ/AC либо эквивалент,
   target repository, baseline и границы файлов.
4. **Conformance к живой кодовой базе.** До правок изучи инструкции, конфиги,
   ближайшие аналоги и тесты. Не копируй очевидный дефект или небезопасный
   паттерн; конфликт источников зафиксируй.
5. **Разработка не равна проверке.** BE/FE self-check — evidence реализации;
   итоговый verification выполняет новый test-agent.
6. **Состояние переживает контекст.** `manifest.json`, lane cards и reports —
   handoff; история чата и самооценка агента не являются состоянием поставки.
7. **Merge/deploy отдельно.** Локальный diff, commit/MR, merge, deploy/restart
   и post-deploy verification — разные гейты.

## Когда применять

- Реализовать утверждённый backend- или frontend-scope.
- Подготовить тестовую модель до реализации.
- Написать тесты в явно назначенной test-only области.
- Независимо проверить уже готовую реализацию по REQ/AC.
- Продолжить частично выполненную поставку в новых контекстах.

Для анализа и постановки используй профильный requirements-процесс. Для
архитектурного решения без реализации — architecture/spec pipeline. Для чистого
review diff, merge или deploy — отдельный проектный процесс.

## Фаза 0. Выбери профиль

```text
python3 {baseDir}/scripts/delivery_pipeline.py detect --cwd "<cwd>"
python3 {baseDir}/scripts/delivery_pipeline.py show-profile auto --cwd "<cwd>"
```

Загрузи ближайший `<project-root>/.delivery-engineering/profile.md` либо
generic. Профиль дополняет, но не заменяет ближайшие `AGENTS.md`/`CLAUDE.md`.

## Intent и lanes

| Intent | Обязательные lanes | Результат |
|---|---|---|
| `implement` | Фактически затронутые BE/FE + test | Код и независимый verification |
| `accept` | test | Проверка готовой реализации без разработки |
| `test-design` | test | Test model без claims о реализации |

```text
python3 {baseDir}/scripts/delivery_case.py init --case-root "<path>" \
  --case-id "<id>" --intent implement|accept|test-design \
  --profile-id "<profile>" --lane test [--lane backend] [--lane frontend]
```

Не создавай отсутствующую lane «для комплекта».

## Роли

| Роль | Режимы | Контракт |
|---|---|---|
| `delivery-backend` | implementation | `{baseDir}/agents/contracts/backend.md` |
| `delivery-frontend` | implementation | `{baseDir}/agents/contracts/frontend.md` |
| `delivery-tester` | test-design, test-automation, verification, conformance | `{baseDir}/agents/contracts/tester.md` |

- Передавай роли только утверждённый handoff, профиль, case card, target repo и
  назначенный scope.
- BE и FE можно вести параллельно лишь при непересекающихся файлах и стабильном
  публичном контракте.
- `verification` и `conformance` — свежие запуски. Авторский self-report служит
  картой evidence, но не доказательством.
- Tester не исправляет продуктовый код во время независимой проверки.
- Роли не мержат, не деплоят и не меняют внешние статусы без отдельного гейта.

## Маршрутизация инженерной базы

Не загружай всю литературу в один контекст. Сначала выбери маршрут:

```text
python3 {baseDir}/scripts/delivery_context.py route --task "<задача>"
python3 {baseDir}/scripts/delivery_context.py extract --route "<route-id>"
```

Карта и версия источников находятся в
`{baseDir}/references/knowledge-map.md` и
`{baseDir}/references/source-registry.md`. Выжимки — проектные проверочные
линзы, а не новые требования.

## Исполняемый workflow

Полностью прочитай и выполни
`{baseDir}/workflows/delivery-pipeline.md`. Вход и reports заданы в
`{baseDir}/references/delivery-handoff.md`; состояние — в
`{baseDir}/references/case-state.md`.

## Проверка скилла

```text
python3 {baseDir}/scripts/delivery_pipeline.py validate
python3 {baseDir}/scripts/delivery_context.py validate
python3 {baseDir}/scripts/prompt_audit.py validate --skill-root {baseDir}
python3 -m unittest discover -s {baseDir}/scripts -p 'test_*.py'
```

## Критерии успеха

- Выбран один профиль и только разрешённые lanes.
- Scope связан с REQ/AC и конкретными worktree/file boundaries.
- Чужие dirty changes сохранены и не попали в результат.
- Для каждого изменённого контура есть style evidence из проекта.
- BE/FE выполнили project checks и вернули воспроизводимое evidence.
- Tester независимо проверил persisted/live result либо назвал coverage gaps.
- `implemented`, `verified`, `merged` и `deployed` не смешаны.

## Индекс

| Путь | Назначение |
|---|---|
| `{baseDir}/workflows/delivery-pipeline.md` | Полный процесс |
| `{baseDir}/references/delivery-handoff.md` | Входы и role reports |
| `{baseDir}/references/case-state.md` | Состояния и гейты |
| `{baseDir}/references/knowledge-map.md` | Маршруты выжимок |
| `{baseDir}/references/source-registry.md` | Источники, версии и границы |
| `{baseDir}/references/prompt-standard.md` | Стандарт ролевых prompts и eval-cases |
| `{baseDir}/profiles/generic.md` | Безопасный fallback |
| `{baseDir}/profiles/project-profile-template.md` | Шаблон приватного overlay |
