# LeidsaOracle — Lessons Learned

## Lesson 1: Follow CLAUDE.md task management (2026-03-12)
**Trigger**: User had to remind me to write plans to `tasks/todo.md` instead of only using the system plan file.
**Rule**: ALWAYS write the plan to `tasks/todo.md` with checkable items BEFORE starting implementation. The system plan file is supplementary; `tasks/todo.md` is the source of truth per CLAUDE.md.

## Lesson 2: Verify game format before building (2026-03-12)
**Trigger**: Research showed conflicting data — some sources say Loto is 6/38, others 6/40.
**Rule**: When building for a specific domain, confirm exact specs with the user EARLY. Don't build on assumptions. Made the system configurable via GameDefinition registry to handle ambiguity.

## Lesson 3: Match test code to actual interfaces, not assumptions (2026-03-13)
**Trigger**: 11 test failures because subagent-generated tests assumed different constructor signatures and field names than the actual modules.
**Rule**: Before writing tests for existing code, always READ the actual class/function signatures first. Common mistakes:
- Passing `game_def` to `__init__()` when it belongs in `analyze(draws, game_def)`
- Using dict `.get()` on dataclass fields (use `.field_name` instead)
- Assuming field names without checking (e.g. `relative_frequencies` vs `global_pct`)
- Wrong schema fields (`draw_date` vs `date_str`, `list[int]` vs `list[str]`)

## Lesson 4: Verify constructor signatures before wiring route endpoints (2026-03-13)
**Trigger**: `generate.py` route passed `must_include`, `must_exclude`, `min_sum`, `max_sum` to `CombinationConstraints` which only accepts `(game_def, sum_mean, sum_std, config)`.
**Rule**: When writing API routes that instantiate domain objects, always check the actual `__init__` parameters. Don't infer from naming conventions.

## Lesson 5: Subagents need interface context, not just task descriptions (2026-03-13)
**Trigger**: Two subagents generated code that didn't match actual interfaces, causing 11 test failures and 2 route bugs.
**Rule**: When delegating to subagents that need to write code integrating with existing modules, include the actual signatures/dataclass definitions in the prompt — not just "write tests for X". The cost of re-reading source files is always less than the cost of fixing broken integrations.
