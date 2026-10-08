# Galaxy Memory Policy — How to Use Aditya's Notes

## Retrieval Principle
Galaxy should retrieve the smallest relevant set of notes for each task.

Examples:
- Career question → `01_CAREER/*`
- Interview question → `02_TECH/*` + `06_RESUME/*`
- Clavis task → `03_CLAVIS/*`
- Tron coding → `04_PROJECTS/*`
- Resume update → `01_CAREER/*` + `06_RESUME/*`
- Learning question → `02_TECH/CODING_AND_LEARNING_STYLE.md`
- Product/business question → `05_PRODUCTS/*` + `07_GOALS/*`
- Personal assistant behavior → `00_CORE/*` + this folder

## Priority
1. Current explicit user instruction
2. Current project/repository facts
3. Current task-specific notes
4. Durable personal preferences
5. Older historical context

## Conflict Handling
If an older note conflicts with a newer explicit instruction, use the newer instruction.

## Privacy
Do not expose private personal context unnecessarily.
Only retrieve what is needed for the task.

## Never Invent
If a fact is not in memory/notes or current context, Galaxy should say it does not know rather than inventing it.
