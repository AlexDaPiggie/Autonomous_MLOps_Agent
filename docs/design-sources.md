# Design references

[Back to the README](../README.md#why-this-architecture)

The README pairs each animation with a concrete local design choice and its source. These connections are interpretations: the project does not implement every feature or reproduce the results of the systems below.

| Reference | Connection to our choices |
|---|---|
| [ML Agent Harness](https://github.com/juliversa/ml-agent-harness) and [lessons](https://github.com/juliversa/ml-agent-harness/blob/main/LESSONS.md) | Independent watcher and executable gates; separate the writer from the judge. |
| [autoresearch](https://github.com/karpathy/autoresearch) | A measurable propose/run/evaluate loop; deterministic computation outside the model conversation. |
| [MLEvolve](https://github.com/InternScience/MLEvolve), [AIDE](https://github.com/WecoAI/aideml) | Explore and evaluate alternative candidates. Our implementation uses a small heuristic portfolio rather than their full search methods. |
| [ML-Master](https://github.com/sjtu-sai-agents/ML-Master), [EvoMaster](https://github.com/sjtu-sai-agents/EvoMaster) | Memory organization references; our simplified version retrieves evidence into compact briefs. |
| [Chris Deotte review](../CHRIS_DEOTTE_2026_REVIEW.md) | Campaigns, model diversity, independent validation, and contribution to an ensemble. The review links individual primary write-ups and records evidence limits. |
| [MLE-bench](https://github.com/openai/mle-bench) | Evaluation reference. Synthetic implementation checks and retrospective benchmarks are different from live competition results. |

Additional references retained from the project's design specification:

- [Microsoft R&D-Agent](https://github.com/microsoft/rd-agent): research decisions separated from implementation.
- [Historical solutions collection](https://github.com/TaeyanG4/kaggle-top-solutions-and-strategies): candidate research leads; verify provenance and licensing against originals.
- [BirdCLEF write-up](https://www.kaggle.com/competitions/birdclef-2026/writeups/96th-place-solution-only-claude-code-custom-har): an additional harness reference. Audio is outside this project's scope; placement claims are not reproduced here.
- [NeuroGolf write-up](https://www.kaggle.com/c/neurogolf-2026/writeups/1st-place-kaggle-agent): an additional optimization and human–AI collaboration reference, not a claim that its architecture is implemented here.
- [tinyKaggleClaw](https://github.com/lhwcv/tinyKaggleClaw): an additional orchestration reference, not an installed backend.

Budget caps, one selected subscription agent, supported domains, and the absence of automatic paid fallback come from this project's operating constraints. They are not performance conclusions about which agent is best. See [shared rules](../rules.md), [budget enforcement](../kaggle_agent/supervisor/budget.py), and [agent adapters](../kaggle_agent/agents/base.py).
