# Phoenix AI Code Agent — Design Document (Phase 3)

This directory defines the interfaces and design agreements for the planned Phase 3 extension.
It has zero impact on the runtime agent, keeping version 1 clean and lightweight.

## Architecture Vision

When a failure repeats or escalates, rather than just restarting the container indefinitely, Phoenix will attempt to patch the underlying application bug automatically.

```
                  ┌──────────────────────┐
                  │ Phoenix Agent Runtime│
                  └──────────┬───────────┘
                             │ Escalated
                             ▼
                  ┌──────────────────────┐
                  │    Git Integrator    │  ──► Clone repository sandbox
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │    AI Code Agent     │  ──► Scan code & generate patch diff
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │    Git Integrator    │  ──► Apply patch, commit, open Pull Request
                  └──────────────────────┘
```

## Security Sandboxing Principles

1. **Isolation**: Code analysis and patch testing must occur in separate ephemeral sandboxed containers, never on the host directly or inside active deployment environments.
2. **Review Toggles**: Code patches cannot be pushed straight to main. The Code Agent must always open a Pull Request for human engineer review and sign-off.
3. **Reproducibility**: Sandbox runs must include unit test executions. A patch is considered candidate only if existing tests pass and the specific incident behavior is solved.
