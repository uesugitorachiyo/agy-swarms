# Judge Rubric

All dimensions are scored from 0 to 1. Weights sum to 1.0.

| Dimension | Weight | 1.0 Anchor | 0.0 Anchor |
|---|---:|---|---|
| Correctness | 0.35 | The answer fully satisfies the task and preserves required behavior. | The answer does not solve the requested task. |
| Completeness | 0.20 | All requested files, tests, and verification details are included. | Major requested deliverables are missing. |
| Robustness | 0.20 | Edge cases and failure modes are handled explicitly. | The solution only covers the happy path. |
| Evidence fidelity | 0.15 | Claims are backed by concrete commands, outputs, or cited artifacts. | Claims are unsupported or contradict available evidence. |
| Instruction adherence | 0.10 | Scope, file boundaries, and user constraints are followed. | The response violates explicit constraints. |

## Gate Use

Phase-0 quality-floor scoring uses this rubric at temperature 0 with blinded arm labels, recorded `blinding_seed`, and per-item arm-to-position map.
