# Evaluation

Independent keyless recheck on 17 November 2026 with NVIDIA SkillEvaluator 0.9.0 and SkillSpector 2.13.3. The agentic-loadout Python installer is not itself a supported SkillEvaluator artifact and has **no SkillEvaluator score**. Its v0.7.5 test suite passed 151 tests on Python 3.12.

| Evaluated skill | Revision | Static quality | Keyless security | Tier 1 |
| --- | --- | --- | --- | --- |
| Upstream memory-1 | `a141c5a` | A, 93.5 | Medium, 22; caution | Passed 11 applicable checks |
| Bundled memory-1 with Entire overlay | loadout `e56b5cd` | A, 93.5 | Medium, 28; caution | Passed 11 applicable checks |
| docs-1, upstream and bundled | `13b2e53` | A, 93.5 | Low, 16; caution | Passed 11 applicable checks |
| sdd-html-feature, pinned | `c33218c` | A, 93.5 | 0, no findings; partial analysis | Passed with warnings |
| worktree, pinned | `37674c26` | B, 86.8 | Medium, 38; caution; one high finding | Failed schema and security |

For memory-1 and docs-1, correctness was 85, discoverability 95, reliability 100 and efficiency 100. Security scans were rule-based, without LLM review, and analysis was partial. Findings include undeclared tool permissions and Git subprocesses; memory-1 deliberately persists state. The adapted memory skill adds Git calls for Entire. The worktree high finding concerns a documented `git push` command whose instructions require user authorization; it merits review, and still causes the scanner to fail Tier 1. The HTML SDD scan was static and its QA isolation relies on host safeguards and instructions. No high finding is silently treated as a passing scan.

These quality scores are static heuristics and do not establish agent performance. The original agent benchmarks were not reproduced; paid model checks and valid Tier 3 live comparisons were not run in this recheck. See the upstream [memory-1 evaluation](https://github.com/illescasDaniel/memory-1-skill/blob/main/docs/evaluation.md) and [docs-1 evaluation](https://github.com/illescasDaniel/docs-1-skill/blob/main/docs/evaluation.md).
