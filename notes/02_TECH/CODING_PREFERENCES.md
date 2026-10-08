# Coding Preferences and Constraints

## General
- Preserve existing functionality.
- Prefer scoped fixes.
- Avoid architecture-breaking changes unless explicitly requested.
- Do not introduce unnecessary dependencies.
- Do not invent APIs or project behavior.
- Keep changes easy to review.

## React / UI
- For existing projects, do not migrate frameworks just for style improvements.
- UI-only changes should remain UI-only when requested.
- Preserve existing backend/API/logic.
- Long text must remain readable and responsive.
- Prefer restrained, purposeful animation.
- Avoid hover-scale cards.
- Plain CSS/SCSS and Poppins/theme variables have been preferred in some projects.
- Current work may use Tailwind, so respect the project's existing styling system rather than forcing a new one.
- Do not use `useLayoutEffect` in the React dashboard context where Aditya explicitly ruled it out.
- Aditya dislikes using `Promise.all` as a blanket pattern for one React dashboard.

## Code Review
When Aditya asks for a code review:
- First understand the current architecture.
- Identify the exact issue.
- Avoid unrelated refactors.
- Give confidence about what is safe to change.
