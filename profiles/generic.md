---
delivery_engineering_profile: 1
profile_id: generic
capabilities: test
---

# Generic delivery profile

## Область

Безопасный fallback для test-design и read-only verification. Реализация
выключена, пока ближайший профиль и явный запрос не разрешат dev lane.

## Источники истины

1. Явный запрос и утверждённые REQ/AC.
2. Ближайшие project instructions и архитектурный канон.
3. Актуальный код, тесты, CI и среда.
4. Общий engineering baseline только как линза.

## Capabilities

- `test`: enabled;
- `backend`: disabled;
- `frontend`: disabled.

## Codebase conformance

Исследуй ближайшие инструкции, tool configs и несколько аналогичных участков.
Без устойчивого evidence не изобретай универсальный стиль и фиксируй gap.

## Engineering gates

Используй команды ближайшего репозитория. Без project commands не выдумывай
универсальный build/lint/test; зафиксируй coverage gap.

## Тестирование и приёмка

Tester работает в свежем контексте и разделяет defect, spec gap, environment
blocker, baseline failure и coverage gap. Готовность подтверждается evidence.

## Внешний жизненный цикл

Запись product code, commit/MR, merge, deploy и внешние статусы не разрешены.

