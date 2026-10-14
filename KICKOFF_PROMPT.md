# Kickoff prompt: paste this as your first message to Claude Code

> Open Claude Code in the root of this repo (the folder containing `CLAUDE.md`), then paste everything between the lines below.

---

Read `CLAUDE.md`, then read every file in `docs/` in numbered order. Then:

1. Summarize back to me in under 15 bullets: what we're building, the stack, and the phases. Flag anything in the specs that looks wrong, outdated, or contradictory (especially package versions and APIs you know have changed).
2. Check my environment: Python version, whether `uv`, `git`, `node`/`npm`, and `docker` are installed. Tell me what's missing and the install command for each.
3. Initialize git if needed and make an initial commit of the scaffold as-is.
4. Start **Phase 0** from `docs/05_roadmap.md`. Work through it, run its acceptance checks, update `docs/PROGRESS.md`, commit, then stop and report.

Rules for the whole project: follow `CLAUDE.md`. Work one phase at a time and stop after each phase for my review unless I say "continue through Phase N". Record any deviation from the specs in `docs/DECISIONS.md`. Never invent numbers for the README.

---

## Useful follow-up prompts

- **Continue:** `Phase N looks good. Start Phase N+1.`
- **Batch phases:** `Continue through Phase 4 without stopping, unless you hit a decision that changes scope or cost.`
- **Review pass:** `Act as a senior analytics engineer reviewing this repo for a hiring panel. List the 10 highest-impact improvements, ranked, then fix the top 3.`
- **README pass (after Phase 8):** `Query the marts and fill every <<FILL ...>> placeholder in README.md with real numbers. Write 3 to 5 findings in plain business language, each tied to a decision.`
- **Interview prep:** `Quiz me on the design decisions in this repo the way an interviewer would. One question at a time.`
