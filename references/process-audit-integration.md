# Независимый аудит Delivery-процесса

Аудит запускается после каждого terminal или interrupted delivery cycle и
оценивает процесс, а не повторяет product verification.

## Evidence pack

Передай Process Auditor только неизменяемые источники текущего cycle:

- requirements/delivery handoff и exact revision;
- `manifest.json`, `engineering-context.json`, `agent-ledger.json`;
- developer/test/conformance reports и их subject hashes;
- diff/check/read-back evidence;
- Work Metrics reconciliation при наличии полного покрытия;
- terminal outcome и пользовательский/guard stop marker.

Отсутствующий источник остаётся coverage gap. Не ставь нулевые tokens, время,
findings или rework из отсутствия данных.

## Независимость

Process reviewer не должен быть BE/FE/test автором исходного cycle и не получает
его самооценку как готовый вывод. В Codex используй отдельного read-only Claude
reviewer; в другом harness — свежего reviewer, не участвовавшего в работе.

Аудитор не правит продукт, delivery case или скиллы. Он возвращает ровно один
verdict Process Auditor и evidence refs. `KEEP` обязателен к сохранению наравне с
дефектом.

## Остановки

`user_stopped` сохраняет snapshot до остановки, причину либо `unknown` и
`resume_authority=user_only`. Позднее сообщение/действие не считается
автоматическим resume. Recovery после отдельного решения пользователя создаёт
новый связанный episode/cycle.

`verification-budget-exhausted`, guard stop, limit/tool/provider failure и
обычный product defect классифицируются отдельно. Стоимость или три review сами
по себе не доказывают процессный дефект: нужен причинный finding с evidence.

## Результат

- `KEEP` — delivery process соразмерен риску;
- `EXECUTION_DEFECT` — исправлять конкретный результат;
- `PROCESS_DEFECT` — shadow proposal для Delivery/Vigers/другого target skill;
- `EXTERNAL_FAILURE` — не менять процесс без доказанного дефекта fallback/retry;
- `EVIDENCE_GAP` — вывод пока невозможен;
- manual stop assessment — validated/unconfirmed без auto-resume.

Ни один verdict не разрешает self-merge, deploy, status transition или изменение
скилла.
