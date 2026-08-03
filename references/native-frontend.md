# Выжимка: frontend, поведение и accessibility

Используй вместе с design system, browser matrix и тестовыми правилами проекта.

## F01. Наблюдаемое поведение вместо внутренностей

**Источники:** `TESTING-LIBRARY-GP`; `SWE-GOOGLE-2020`, ch11–14.

- Проверяй UI через доступные пользователю роли, имена, текст и действия, а не
  через private state, внутренние методы или структуру компонента.
- Тест должен переживать безопасный refactor, если поведение и контракт не
  изменились.
- Test id допустим как последний проектно разрешённый seam, но не подменяет
  семантичную разметку.

## F02. Состояния пользовательского потока

**Основание:** behavioral testing из `TESTING-LIBRARY-GP` и test analysis из
`ISTQB-CTFL-4.0.1` §1.4.

Для затронутого сценария проверь применимые состояния:

- initial/empty/loading;
- success и повторное действие;
- validation/domain/network/permission error;
- retry/cancel/navigation/back;
- disabled/pending и защита от двойного submit;
- восстановление после refresh, если оно входит в контракт.

Не добавляй искусственные состояния без REQ/AC или существующего UX-паттерна.

## F03. Визуальное и адаптивное evidence

**Основание:** `SWEBOK-4.0a`, Testing KA; project-first правило.

- Сверь компоненты, spacing, typography, tokens и responsive breakpoints с
  design system и соседним экраном.
- Для визуального change получи screenshot/visual test на репрезентативных
  viewport и ключевых состояниях.
- Screenshot подтверждает rendering, но не клавиатуру, семантику, network flow
  или сохранённое состояние.
- Отделяй pre-existing visual drift от регрессии change.

## F04. Accessibility по применимым критериям

**Источник:** `WCAG-2.2`, principles and success criteria.

- Выбери применимые success criteria по компоненту и заявленному уровню; не
  прогоняй случайный список без scope.
- Проверь semantics/name-role-value, keyboard path, focus order/visibility,
  labels/errors/status announcements, contrast и target size там, где применимо.
- Сочетай automation с keyboard/manual/assistive-tech checks по риску: WCAG
  рассчитан на автоматическую и человеческую оценку.
- В evidence указывай criterion ID, состояние UI и способ проверки.

## F05. Граница conformance claim

**Источник:** `WCAG-2.2`, §5 Conformance.

- Проверка одного компонента или сценария не подтверждает соответствие всей
  страницы, сайта или уровня WCAG.
- Заявляй только `checked applicable criteria` с перечнем и gaps, если полный
  conformance scope не был поставлен и пройден.
- Учитывай все представления страницы в заявленном scope, включая responsive
  варианты и зависимый контент.

