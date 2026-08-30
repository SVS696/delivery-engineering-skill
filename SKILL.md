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
6. **Состояние переживает контекст.** `engineering-context.json`, отдельные
   `basis/<lane>.md`, `manifest.json`, lane cards и reports — handoff; история
   чата и самооценка агента не являются состоянием поставки.
   `agent-ledger.json` не входит в bounded role-context, но schema-3 case
   связывает независимые verification/conformance PASS с точным completed run,
   subject hash и неизменным output artifact.
7. **Merge/deploy отдельно.** Локальный diff, commit/MR, merge, deploy/restart
   и post-deploy verification — разные гейты.
8. **Нативная простота.** До новой абстракции, зависимости или механизма пройди
   лестницу переиспользования, исправляй корневого владельца причины и не удаляй
   protected floor безопасности, данных, accessibility, совместимости и
   доказанной расширяемости.
9. **Green относится к границе результата.** Локальные checks не доказывают
   внешнюю проекцию, handoff, merge или deploy. Обязательный read-back входит в
   соответствующий green; после достигнутого terminal state лишние проходы запрещены.
10. **Один authoritative implementation path.** Существующее поведение либо
    развивается у текущего owner, либо заменяется целиком, либо временно
    мигрирует по принятому transition contract. Legacy не получает новые
    бизнес-правила и не остаётся без retirement trigger.
11. **Процесс проверяет внешний аудитор.** После terminal, blocked, guard/user
    stop или исчерпания verification budget создай hash-bound episode и запусти
    независимый Process Auditor. Delivery tester проверяет продукт, но не
    соразмерность собственного orchestration. Verdict не возобновляет ручной stop
    и не меняет policy автоматически.
12. **Revmux — opt-in backend conformance reviewer.** Только при явном
    `review_backend: revmux` свежий tester `conformance` действует как driver по
    `{baseDir}/references/revmux-review-backend.md`: вызывает revmux, но не
    добавляет собственный model-review и не запускает цикл. Native conformance
    и revmux для одного gate взаимоисключающие, кроме отдельного сравнительного
    замера. Opt-in fail-closed зависит от binary+skill revmux совместимой
    ревизии `33ede7aaf632cebbde08f2dd53ffa06c4722d81b`; default не меняется до
    ручного решения после 3–5 кейсов.

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

Не создавай отсутствующую lane «для комплекта».

## Роли

| Роль | Режимы | Контракт |
|---|---|---|
| `delivery-backend` | implementation | `{baseDir}/agents/contracts/backend.md` |
| `delivery-frontend` | implementation | `{baseDir}/agents/contracts/frontend.md` |
| `delivery-tester` | test-design, test-automation, verification, conformance | `{baseDir}/agents/contracts/tester.md` |

- Передавай роли только утверждённый handoff, профиль, case card, target repo и
  назначенный scope. Точный пакет получай через
  `delivery_case.py context --case-root "<path>" --lane <lane>`.
- BE и FE можно вести параллельно лишь при непересекающихся файлах и стабильном
  публичном контракте.
- `verification` и `conformance` — свежие запуски. Авторский self-report служит
  картой evidence, но не доказательством.
- При `review_backend: revmux` tester `conformance` остаётся свежим независимым
  run и владельцем output artifact, но является только driver: один назначенный
  revmux round, без собственного review поверх него.
- Перед каждым полным verification выполни `begin-verification`. На одну
  неизменную source revision разрешены initial pass и не более двух correction
  passes; затем собери один полный spec-feedback batch или запроси решение.
- Tester не исправляет продуктовый код во время независимой проверки.
- Роли не мержат, не деплоят и не меняют внешние статусы без отдельного гейта.

## Маршрутизация инженерной базы

Не загружай всю литературу в один контекст и не смешивай корпуса разных ролей.
Выбери один основной маршрут на каждую активную lane; для BE/FE допустим второй,
а для test — до двух дополнительных маршрутов реально проверяемых поверхностей:

```text
python3 {baseDir}/scripts/delivery_context.py route --task "<задача>"
python3 {baseDir}/scripts/delivery_context.py materialize \
  --assign backend=backend-http --assign test=test-design \
  --write "<case-root>"

python3 {baseDir}/scripts/delivery_case.py init --case-root "<case-root>" \
  --case-id "<id>" --intent implement|accept|test-design \
  --profile-id "<profile>" --lane test [--lane backend] [--lane frontend]
```

Повтори `--assign lane=route` не более двух раз для BE/FE и трёх для test,
только для активных lanes. `materialize` создаёт `engineering-context.json` и изолированные
`basis/backend.md`, `basis/frontend.md`, `basis/test.md`. `init` пересобирает их
по текущим skill-native источникам, связывает fingerprint с manifest и
отклоняет несовпадение lane или выжимки.

Карта и версия источников находятся в
`{baseDir}/references/knowledge-map.md` и
`{baseDir}/references/source-registry.md`. Выжимки — проектные проверочные
линзы, а не новые требования.

## Исполняемый workflow

Полностью прочитай и выполни
`{baseDir}/workflows/delivery-pipeline.md`. Вход и reports заданы в
`{baseDir}/references/delivery-handoff.md`; состояние — в
`{baseDir}/references/case-state.md`. Post-run граница — в
`{baseDir}/references/process-audit-integration.md`.

## Проверка скилла

```text
python3 {baseDir}/scripts/delivery_pipeline.py validate
python3 {baseDir}/scripts/delivery_context.py validate
python3 {baseDir}/scripts/prompt_audit.py validate --skill-root {baseDir}
python3 -m unittest discover -s {baseDir}/scripts -p 'test_*.py'
```

## Критерии успеха

- Выбран один профиль и только разрешённые lanes.
- Для каждой lane инженерная база материализована, привязана к manifest и
  автоматически входит в её role-context; basis другой lane исключён.
- Scope связан с REQ/AC и конкретными worktree/file boundaries.
- Vigers-authored scope связан с immutable `delivery-handoff.json`; его revision
  и hashes не восстанавливаются из чата.
- Чужие dirty changes сохранены и не попали в результат.
- Для каждого изменённого контура есть style evidence из проекта.
- Developer report фиксирует `root_owner`, `chosen_rung`, состояние
  `protected_floor` и, только для сознательного компромисса, измеримый
  `revisit_trigger` с `upgrade_path`.
- Для затронутой существующей реализации report фиксирует
  `implementation_transition`, authoritative owner, superseded/temporary paths,
  retirement trigger и removal evidence.
- BE/FE выполнили project checks и вернули воспроизводимое evidence.
- Tester независимо проверил persisted/live result либо назвал coverage gaps.
- `implemented`, `verified`, `merged` и `deployed` не смешаны.
- После каждого terminal/interrupted delivery cycle сохранён независимый process
  verdict: `KEEP` либо доказанная категория дефекта; manual stop остаётся
  `resume_authority=user_only`.

## Индекс

| Путь | Назначение |
|---|---|
| `{baseDir}/workflows/delivery-pipeline.md` | Полный процесс |
| `{baseDir}/references/delivery-handoff.md` | Входы и role reports |
| `{baseDir}/references/case-state.md` | Состояния и гейты |
| `{baseDir}/references/knowledge-map.md` | Маршруты выжимок |
| `{baseDir}/references/source-registry.md` | Источники, версии и границы |
| `{baseDir}/references/prompt-standard.md` | Стандарт ролевых prompts и eval-cases |
| `{baseDir}/references/agent-observability.md` | Additive supervision, artifact bindings и finding yield без новых вызовов |
| `{baseDir}/references/process-audit-integration.md` | Независимый post-run аудит процесса и ручных остановок |
| `{baseDir}/references/revmux-review-backend.md` | Opt-in backend conformance review и adoption metrics |
| `{baseDir}/scripts/revmux_review.py` | Materialization exact diff context, round evidence и adoption metrics revmux |
| `{baseDir}/profiles/generic.md` | Безопасный fallback |
| `{baseDir}/profiles/project-profile-template.md` | Шаблон приватного overlay |
