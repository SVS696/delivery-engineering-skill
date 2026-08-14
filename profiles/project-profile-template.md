---
delivery_engineering_profile: 1
profile_id: example
capabilities: backend,frontend,test
---

# Project delivery profile

Скопируй в `<project-root>/.delivery-engineering/profile.md`. Приватный профиль
не входит в общий пакет.

## Область

Репозитории, артефакты и intent, покрываемые профилем.

## Источники истины

Приоритет spec/code/schema/CI/environment и правила freshness/read-back.

## Capabilities

Разрешённые `backend`, `frontend`, `test` и условия явного запуска.

## Codebase conformance

Instructions, architecture/style guides, formatter/linter/type checker configs,
выборка аналогов, naming/API/data/UI/test conventions и правила конфликтов.

## Engineering gates

Project build/lint/test/static/security/visual commands и write boundaries.
Зафиксируй project-native возможности и reuse rules, обязательный protected
floor и доказанные extension seams, которые нельзя удалить ради малого diff.

## Тестирование и приёмка

Test levels/types, environments, data, evidence и independence rules.

## Внешний жизненный цикл

Commit/MR/merge/deploy/status gates и запреты.
