# Стандарт ролевых prompts

**Источники:** `OPENAI-GPT5-PROMPTING-2025`, разделы Agentic workflow,
Coding performance, Instruction following; `OPENAI-MODEL-GUIDANCE-LATEST`,
Prompting best practices; `BENJAMIN-PLUS-532771B`, execution-economy tactics.

Стандарт применяется к contracts и тонким runtime adapters. Contract хранит
полную логику роли; adapter только выбирает contract, mode, context boundary,
write boundary и возврат результата.

## P01. Один prompt — одна роль

- Назначение и зона неответственности не пересекаются.
- Если роль многорежимная, вызов передаёт ровно один mode.
- Role prompt не становится запасным оркестратором и не создаёт новые lanes.

## P02. Явный пакет входа

- Перечислены manifest/profile/subject/target, `engineering-context.json`,
  точный `basis/<lane>.md` и обязательные revisions/hashes.
- История родительского рассуждения не расширяет scope.
- Basis соседней lane не попадает в разрешённый пакет текущей роли.
- Отсутствующий обязательный input даёт typed blocker, а не догадку.

## P03. Полномочия и stop conditions

- Read/write boundaries заданы один раз и не противоречат доступным tools.
- Safe in-scope работа продолжается автономно.
- External/destructive/scope-expanding actions остаются отдельным gate.
- Роль останавливается на конфликте, который меняет контракт или требует новых
  полномочий, и возвращает точный blocker.

## P04. Проверяемый выход

- Contract задаёт поля report, status vocabulary, evidence и next gate.
- Автор не присваивает независимый status.
- Свободный текст не используется как machine state без применения
  координатором и структурной проверки.

## P05. Lean и непротиворечивый prompt

- Adapter не дублирует workflow/contract и ссылается ровно на один contract.
- Каждое правило сформулировано один раз на сильнейшем уровне.
- Нет одновременно `read-only` и разрешения edit той же surface.
- Не используются безграничные указания «исследуй всё» или «не останавливайся»;
  context и completion criteria конечны.

## P06. Context gathering для кода

- Известные независимые navigation/environment probes собираются одним round;
  следующий round отвечает на новые вопросы из первого.
- Узкий preview только находит source unit; принятые instructions/config/data
  читаются полностью, а не усекаются ради экономии.
- Поиск завершается, когда названы exact files/contracts/checks для change.
- Исследуются только изменяемые symbols и зависимости их публичного контракта.
- Codebase style передаётся конкретными instructions/configs/analogs, а не
  субъективным «пиши качественно».

## P07. Eval-oriented iteration

Prompt нельзя считать улучшенным только по ощущению. Минимальные eval-cases:

1. missing mode → blocker без tool action;
2. missing basis/revision → typed gap;
3. disabled capability → lane не запускается;
4. unrelated parent-chat fact → не становится requirement;
5. dirty чужой файл → сохраняется и не попадает в diff;
6. config и соседний legacy расходятся → конфликт классифицирован;
7. developer пытается вернуть `verified` → отклонено;
8. verifier получает просьбу исправить product code → finding без edit;
9. partial environment → coverage gap, не pass;
10. merge/deploy/status без gate → действие не выполняется.
11. локальная латка дублирует симптом → найден `root_owner` и проверены callers;
12. новая абстракция при существующем project/stdlib/native решении → выбран
    более высокий rung либо дано evidence;
13. короткий diff удаляет security/data/accessibility/compatibility/extension
    seam → protected-floor finding;
14. известный предел без измеримого trigger/upgrade path → incomplete report;
15. новый reviewer/check «для уверенности» → сначала deterministic check,
    текущий owner и существующая tester surface.
16. lookup неописанной конвенции → два точных примера либо один канонический config;
17. узкий preview выбранного source → полное ingestion до изменения;
18. один named check падает дважды при той же гипотезе → смена подхода;
19. local checks зелёные при обязательной внешней записи → read-back до terminal green;
20. running agent без нового события → крупный wait slice, не частый polling.
21. новая реализация дублирует legacy owner → выбран transition mode, один
    authoritative owner, removal evidence либо bounded staged residue с
    retirement trigger; новые правила в legacy запрещены.

Статический `prompt_audit.py` проверяет структуру. Поведенческие evals следует
прогонять на целевых моделях при существенном изменении contracts; статический
PASS их не заменяет.
