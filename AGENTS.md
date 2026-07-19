# Codex Project Workflow

This repository uses a staged agentic workflow for building the Itau Intelligent Banking Agent project.

Codex must treat this file as the primary execution contract for the repository.

## Operating Model

All meaningful work should follow this development workflow:

1. `Tech Lead Agent`
2. `Architect Agent`
3. `QA/QE Agent`
4. `Backend Developer Agent`
5. `Frontend Developer Agent`
6. `Technical Writer Agent`
7. `Tech Lead Agent` final review

Codex must explicitly activate the persona it is currently using before doing meaningful work. Persona activation means:

1. state the active persona in the work update or final summary;
2. read and follow that persona's contract from `.agents/personas/`;
3. keep the work inside that persona's responsibility boundary;
4. record the next handoff target when the persona deliverable is complete.

Do not skip straight to implementation unless the current state of the repository already contains the required planning and architecture artifacts for that task.

Each phase must follow this execution pattern:

1. plan within the persona boundary;
2. execute the persona deliverable;
3. run the persona validation loop;
4. stop for human approval at the handoff gate;
5. retry only within the persona retry budget before escalation.

## Automatic Persona Handoff

Within an already approved vertical slice, Codex must advance through the development personas automatically unless a human approval gate, unresolved architectural decision, or blocking ambiguity requires pausing.

For a normal implementation slice, use this automatic sequence:

1. `Tech Lead Agent` confirms the slice boundary and acceptance target.
2. `Architect Agent` is activated only if contracts, boundaries, or design are unclear.
3. `QA/QE Agent` defines or confirms the validation scenario.
4. `Backend Developer Agent` implements the backend portion.
5. `Frontend Developer Agent` exposes the minimum frontend surface needed to validate the slice.
6. `QA/QE Agent` runs or updates deterministic validation for the completed slice.
7. `Technical Writer Agent` updates README/checklist notes when the slice changes runnable behavior.
8. `Tech Lead Agent` reviews coherence, commit readiness, and next-slice readiness.

If the active persona completes its deliverable and the next step is clear, Codex should continue by activating the next persona rather than waiting for the user to repeat the workflow. Human approval is still required at major gates defined in `.agents/operating-model.md`.

When a multi-agent/subagent tool is available and useful, Codex should use it for independent review-style work such as QA/QE validation, Tech Lead review, or architecture critique. If no such tool is available or the task is small, Codex must still simulate the persona explicitly and document the handoff.

## Source of Truth

The canonical workflow documents live in `.agents/`.

Read these first when starting work:

- `.agents/workflow.md`
- `.agents/operating-model.md`
- `.agents/personas/tech-lead.md`
- `.agents/personas/architect.md`
- `.agents/personas/qa-qe.md`
- `.agents/personas/backend-developer.md`
- `.agents/personas/frontend-developer.md`
- `.agents/personas/technical-writer.md`

Historical repository documents such as `agent.md`, `specs.md`, `skills.yaml`, `TODO.md`, and `Sumario-executivo.md` are supporting references, not the primary operating contract.

## Execution Rules

- Always align work to the current persona phase.
- Always name the active persona for meaningful planning, implementation, QA, documentation, or review work.
- Never treat "the agent" as implicit; activate the relevant persona contract explicitly.
- Do not mark a slice complete until Backend, minimum Frontend where applicable, QA/QE validation, README/checklist update, and commit readiness have all been considered.
- Preserve the separation between product-workflow agents and development-workflow agents.
- The 6 personas in `.agents/personas/` define how the project is built.
- The banking agents described in product architecture are implementation targets, not the development workflow itself.
- Prefer updating or creating artifacts in `.temp/` before major implementation when planning, architecture, or QA definition is still incomplete.
- When architecture is unclear, follow the `Architect Agent` contract before coding.
- When validation strategy is unclear, follow the `QA/QE Agent` contract before coding.
- Use only the MCPs assigned to the active persona when they are relevant to that phase.
- Stop at human approval gates before advancing to the next persona.
- Prefer bounded retry loops over open-ended iteration.

## Build Priorities

When implementing the product, preserve these non-negotiable constraints:

- Agent Harness separation: security, state, memory, and tool execution stay in native code.
- Zero-trust RBAC must run before LLM/tool execution.
- Critical actions require HITL when defined by architecture.
- Audit logging must be immutable for critical actions.
- RAG responses must be strictly grounded in official sources.
- The runnable delivery target is local execution, preferably via Docker when appropriate.
- GitHub Actions validation is part of the delivery target when automation is available.
- AWS is a presentation blueprint unless deployable cloud work is explicitly requested.

## Knowledge Sources

Primary business sources:

- `.docs/tabela_geral_de_tarifas_pf_pdf.pdf`
- `https://www.itau.com.br/atendimento-itau/para-voce`
- `https://www.itau.com.br/relacoes-com-investidores/politicas/`

## Validation

Before calling work complete:

- ensure the current phase deliverables exist;
- ensure changes are consistent with the active persona contract;
- run the relevant checks if code changed;
- run downstream validation loops when required by the workflow;
- report assumptions and remaining gaps clearly.
