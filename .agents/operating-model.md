# Operating Model

## Purpose

This file defines the control behavior of the development workflow:

- MCP routing per persona
- retry budgets
- human-in-the-loop approval gates
- validation loops
- post-development QA loops
- commit governance per task
- checklist governance per stage
- README governance per slice

## MCP Routing

### GitHub MCP

Use GitHub MCP for personas that need repository-facing awareness or governance.

Required for:

- `Tech Lead Agent`
  - branch flow
  - PR flow
  - review governance

Optional for:

- `Backend Developer Agent`
  - when repository or branch state matters directly
- `QA/QE Agent`
  - when branch, PR, or repository validation context matters
- `Technical Writer Agent`
  - when final documentation needs repository-aware verification

Not required by default for:

- `Architect Agent`
- `Frontend Developer Agent`

### docs-langchain MCP

Use docs-langchain MCP for personas that need LangChain/LangGraph source-backed guidance.

Required for:

- `Architect Agent`
- `QA/QE Agent`
- `Backend Developer Agent`

Optional for:

- `Technical Writer Agent`

Not required by default for:

- `Tech Lead Agent`
- `Frontend Developer Agent`

## Human Approval Gates

Every major handoff pauses for human approval.

## Persona Activation and Handoff

Persona activation is mandatory for meaningful work.

Before planning, implementing, validating, documenting, or reviewing a slice, Codex must:

1. name the active persona;
2. follow the matching contract in `.agents/personas/`;
3. keep the deliverable inside that persona's responsibility boundary;
4. record the next persona handoff when the deliverable is complete.

Within an already approved vertical slice, persona handoff should be automatic unless a major gate or blocker requires the user.

Default automatic slice sequence:

1. `Tech Lead Agent` confirms slice boundary and acceptance target.
2. `Architect Agent` clarifies contracts only when design is unclear.
3. `QA/QE Agent` defines or confirms validation scenarios.
4. `Backend Developer Agent` implements backend behavior.
5. `Frontend Developer Agent` exposes the minimum validation surface.
6. `QA/QE Agent` executes or updates validation.
7. `Technical Writer Agent` updates README/checklist evidence.
8. `Tech Lead Agent` reviews coherence and commit readiness.

If multi-agent/subagent tooling is available and proportionate, use it for independent QA/QE, architecture critique, or Tech Lead review. If it is unavailable or excessive for the slice, Codex must still explicitly simulate the persona and document the handoff.

## Commit Governance

Commits are part of the workflow, not an afterthought.

### General Rules

1. the active persona works in the isolated branch, never directly in `main`
2. every meaningful task slice should be committed after validation and before the next handoff
3. commits must be coherent enough for review by the `Tech Lead Agent`
4. if a slice fails validation, fix it before committing unless the commit is intentionally a checkpoint requested by the user
5. the final PR is opened only after the branch has completed the required gates
6. vertical slices must be committed in a way that keeps backend, frontend, QA evidence, and documentation understandable together

### Commit Responsibility by Persona

- `Tech Lead Agent`
  - define task boundaries suitable for commits
  - verify that commit granularity matches the WBS
- `Architect Agent`
  - commit architecture artifacts after Gate 2 approval when changed
- `QA/QE Agent`
  - commit test strategy or harness changes after validation
- `Backend Developer Agent`
  - commit each validated backend slice
- `Frontend Developer Agent`
  - commit each validated UI slice
- `Technical Writer Agent`
  - commit final documentation package before final review

### Minimum Commit Trigger

Create or prepare a commit when one of these happens:

- a task reaches its acceptance criteria
- a backend slice passes its planned tests
- a frontend slice passes demo validation
- a documentation milestone becomes reviewable
- a vertical slice becomes understandable end to end

## Checklist Governance

Checklist maintenance is mandatory.

### Canonical Checklist

- `.temp/00_delivery_checklist.md`

### General Rules

1. every persona updates the checklist after concluding a meaningful step
2. the checklist must be refreshed before every human approval gate
3. the checklist must be refreshed before or alongside the commit decision for the current slice
4. if work was validated, the checklist must record it explicitly
5. if scope changed, the checklist must record what was added, deferred, or removed

### Checklist Responsibility by Persona

- `Tech Lead Agent`
  - keeps task map, branch status, and overall progress coherent
- `Architect Agent`
  - records architectural outputs completed and architecture items still pending
- `QA/QE Agent`
  - records validation coverage completed, pending tests, and known risks
- `Backend Developer Agent`
  - records implemented backend slices, executed validations, and remaining backend scope
- `Frontend Developer Agent`
  - records implemented demo slices and remaining UI gaps
- `Technical Writer Agent`
  - records documentation readiness and PR packaging status

### Minimum Checklist Trigger

Update the checklist when one of these happens:

- a task reaches its acceptance criteria
- a slice is validated and becomes commit-ready
- a gate is about to be handed off
- a blocker or scope change alters the remaining plan

## README Governance

README maintenance is mandatory during implementation, not only at the end.

### Canonical README

- `README.md`

### General Rules

1. every validated slice updates the README with the current implemented scope
2. README updates must reflect how to run or validate the slice when relevant
3. README updates must happen before or alongside the commit decision for the slice
4. the README should remain accurate even if the project stopped between slices
5. the final documentation pass refines the README, but does not replace incremental maintenance

### README Responsibility by Persona

- `Backend Developer Agent`
  - updates backend capability notes and execution details introduced by the slice
- `Frontend Developer Agent`
  - updates UI/demo notes introduced by the slice
- `QA/QE Agent`
  - updates validation notes when they materially change how the slice is verified
- `Technical Writer Agent`
  - consolidates style, narrative, and final trade-off documentation

### Minimum README Trigger

Update the README when one of these happens:

- a new slice becomes runnable
- a new slice becomes demoable
- run instructions change
- validation instructions change

### Gate 1

`Tech Lead -> Architect`

Validate:

- sprint plan
- KPIs
- WBS
- risk framing

### Gate 2

`Architect -> QA/QE`

Validate:

- harness design
- ADRs
- diagrams
- module contracts

### Gate 3

`QA/QE -> Backend Developer`

Validate:

- test matrix
- validation coverage
- acceptance criteria

### Gate 4

`Backend Developer -> Frontend Developer`

Validate:

- backend slice behavior
- unit validation status
- readiness for UI integration

### Gate 5

`Frontend Developer -> Technical Writer`

Validate:

- demo readiness
- visibility of system flow
- visibility of HITL and safety checkpoints

### Gate 6

`Technical Writer -> Tech Lead Review`

Validate:

- documentation coherence
- delivery scope
- PR readiness narrative

## Retry Budgets

Retries must stay bounded.

- `Tech Lead Agent`: 2 revisions
- `Architect Agent`: 2 revisions
- `QA/QE Agent`: 2 revisions
- `Backend Developer Agent`: 3 retries for the same bounded implementation slice
- `Frontend Developer Agent`: 2 revisions for the same UI slice
- `Technical Writer Agent`: 2 revisions

## Persona Validation Loops

### Tech Lead loop

1. read challenge and workspace context
2. draft planning artifacts
3. check scope, KPI, risk, and WBS coverage
4. revise within retry budget if needed
5. stop at Gate 1

### Architect loop

1. read planning artifacts
2. research architecture constraints and relevant docs
3. draft diagrams, ADRs, and contracts
4. validate harness boundaries and system clarity
5. revise within retry budget if needed
6. stop at Gate 2

### QA/QE loop

1. read architecture outputs
2. draft QA strategy and deterministic tests
3. validate coverage of RBAC, memory, HITL, emergency, and grounding risks
4. revise within retry budget if needed
5. stop at Gate 3

### Backend loop

1. read approved architecture and QA strategy
2. implement a bounded backend slice for the current vertical use case
3. run unit and local validation
4. update checklist and README for the slice contribution
5. hand off immediately to frontend for minimal integration of the same slice
6. fix within retry budget if needed
7. stop at Gate 4

### Frontend loop

1. read approved architecture and backend interfaces
2. implement the minimum UI needed to validate the same vertical slice
3. validate flow visibility and responsiveness
4. update checklist and README for the slice contribution
5. hand off immediately to QA/QE for slice validation
6. revise within retry budget if needed
7. stop at Gate 5

### Technical Writer loop

1. read implemented system state
2. draft documentation
3. validate against code and architecture
4. revise within retry budget if needed
5. stop at Gate 6

## Cross-Persona QA Loop

Implementation is not self-certifying.

After a meaningful backend slice is complete:

1. `Backend Developer Agent` runs unit tests and local checks
2. `Frontend Developer Agent` exposes the minimum integration surface for that same slice when applicable
3. `QA/QE Agent` runs smoke tests for the slice
4. `QA/QE Agent` runs or updates deterministic tests when applicable
5. checklist and README are updated to reflect validated scope
6. defects route back to Backend or Frontend when implementation-level
7. defects route back to Architect only when they expose architectural contradiction
