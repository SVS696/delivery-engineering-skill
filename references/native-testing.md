# Выжимка: test analysis, design и completion

Выжимка объединяет публичный syllabus ISTQB, карту SWEBOK и публичную структуру
серии ISO 29119. Она не воспроизводит платные нормативные тексты ISO.

## T01. Test basis и test conditions

**Источники:** `ISTQB-CTFL-4.0.1`, §1.4; `ISO-29119-OVERVIEW`.

- Назови test object, test basis, scope, objectives и baseline revision.
- Разложи REQ/AC, risks, interfaces и quality constraints в test conditions.
- Неполный или противоречивый basis — `spec gap`, а не повод придумать expected
  result по реализации.
- Для каждого condition укажи oracle: откуда берётся ожидаемое поведение.

## T02. Выбор техник и уровней

**Источники:** `ISTQB-CTFL-4.0.1`, ch2, ch4, §§5.1.6–5.1.7;
`SWEBOK-4.0a`, Software Testing.

- Выбирай level/type/technique из цели и риска, а не из привычной пирамиды.
- Комбинируй specification-based, structure-based, experience-based и
  collaboration-based техники только там, где они добавляют различимое
  покрытие.
- Обязательно рассмотри positive, boundary, negative, state/decision и
  interaction cases, если модель поведения их содержит.
- Не требуй E2E для того, что надёжнее и дешевле доказывается ниже, но не
  заменяй интеграцию моками, когда риск находится на границе систем.

## T03. Traceability и coverage

**Источник:** `ISTQB-CTFL-4.0.1`, §1.4.4.

Веди связь:

```text
test basis / risk -> condition -> case/check -> result -> defect or evidence
```

- Coverage metric объявляй заранее и привязывай к цели.
- Пройденные тесты без связи с AC не доказывают acceptance coverage.
- Trace помогает impact analysis после изменения; обновляй затронутые связи,
  а не весь corpus механически.
- Непроверенное условие остаётся coverage gap, даже если остальные тесты зелёные.

## T04. Независимость и evidence

**Источники:** `ISTQB-CTFL-4.0.1`, §§1.5, 5.2.4; `SWE-GOOGLE-2020`, ch09.

- Developer tests дают быстрый feedback и знание реализации; независимый tester
  лучше замечает иные предположения. Используй оба уровня по риску.
- Verification запускается в свежем контексте и опирается на test basis, а не
  на убеждение автора.
- Сохраняй environment, build/revision, data, exact action/command, expected,
  actual и artifact link/path.
- После исправления перепроверь defect и разумный regression neighborhood.

## T05. Completion без ложной полноты

**Источник:** `ISTQB-CTFL-4.0.1`, §5.3.

Completion report разделяет:

- выполненный scope и результаты;
- невыполненные проверки и причины;
- open defects/spec gaps/environment blockers;
- residual risks и baseline failures;
- расхождения с планом;
- точный следующий gate.

`partial` не округляется до `pass`. Отсутствующая среда — coverage gap, а не
доказательство отсутствия дефекта.

## T06. Risk-based depth

**Источник:** `ISTQB-CTFL-4.0.1`, §5.2.

- Оцени likelihood и impact без ложной числовой точности.
- Риск влияет на priority, techniques, levels, independence и coverage depth.
- Рассматривай product risks отдельно от project risks.
- После проверки фиксируй residual risk; количество тестов само по себе его не
  измеряет.

## T07. Дефект, spec gap и environment blocker

**Основание:** `ISTQB-CTFL-4.0.1`, defect management и reporting.

- `defect`: наблюдаемое поведение расходится с подтверждённым oracle;
- `spec gap`: oracle отсутствует или противоречив;
- `environment blocker`: проверка не может состояться из-за среды/доступа;
- `coverage gap`: область осознанно или вынужденно не проверена;
- `baseline failure`: сбой воспроизводится без текущего change.

Не чинить expected result под фактическую реализацию без решения владельца.

