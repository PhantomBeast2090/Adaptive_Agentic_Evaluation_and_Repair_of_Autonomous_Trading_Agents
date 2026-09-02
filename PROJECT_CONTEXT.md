# PROJECT CONTEXT

## Adaptive Agentic Evaluation and Repair of Autonomous Financial Agents

**Document status:** Master project context
**Research status:** Conceptually frozen; implementation in development
**Primary experimental domain:** Autonomous trading agents
**Project type:** Research prototype / experimental evaluation platform
**Primary objective:** Build an adaptive agentic environment that can test, diagnose, intervene on, and re-evaluate autonomous trading agents.

**Current implementation checkpoint:** Phase 1 core infrastructure and Phase
1.5 financial-environment contract are complete. Phase 2 Static Evaluation is
next. See `agentic-finance-evaluation/docs/PHASE1_AUDIT.md` and
`agentic-finance-evaluation/docs/ENVIRONMENT_CONTRACT.md`.

---

# 1. PURPOSE OF THIS DOCUMENT

This document is the primary context and source of truth for the software implementation of the research project.

Any coding agent, software engineer, research assistant, or AI agent working on this repository MUST read this document before making substantial changes.

The repository is not merely a software project. It is the implementation of a research framework.

Therefore:

> Scientific validity, experimental controllability, reproducibility, and faithful implementation of the research design take priority over engineering convenience or feature volume.

The purpose of this document is to prevent the implementation agent from:

* misunderstanding the research objective;
* turning the project into a generic trading bot;
* building only a static benchmark;
* optimizing the trading agent rather than studying evaluation and repair;
* inventing research methodology without approval;
* introducing unnecessary complexity;
* hard-coding assumptions that should remain experimental variables;
* creating an impressive-looking but scientifically untestable system;
* modifying the research question through implementation decisions.

---

# 2. PROJECT TITLE

## Adaptive Agentic Evaluation and Repair of Autonomous Financial Agents

The implementation is experimentally scoped to autonomous trading agents.

The broader conceptual motivation is financial-agent evaluation, but the first research system should focus specifically on autonomous trading because trading provides:

* observable decisions;
* measurable outcomes;
* sequential feedback;
* portfolio-level consequences;
* risk measurements;
* market-regime variation;
* historical data suitable for accelerated replay;
* controlled simulation;
* counterfactual experimentation;
* out-of-distribution validation.

The project should NOT be reframed as:

> "Build a better autonomous trading agent."

The project IS:

> "Build and experimentally evaluate an adaptive agentic environment capable of evaluating, diagnosing, repairing, and re-evaluating autonomous trading agents."

---

# 3. CORE RESEARCH IDEA

Traditional evaluation of autonomous agents is generally static.

A benchmark or evaluator presents a predetermined set of tasks or scenarios and produces a score.

The fundamental limitation being investigated is:

> A sufficiently capable autonomous agent may perform well on known/static evaluations while still possessing vulnerabilities that are not exposed by the evaluation environment.

A second limitation is that evaluation and improvement are often treated as separate processes.

This project proposes an integrated closed-loop evaluation-and-repair environment.

The environment does not merely ask:

> "How well did the agent perform?"

Instead, it asks:

> "What vulnerabilities does this agent exhibit, under what conditions do they appear, why might they occur, can targeted feedback/intervention mitigate them, and does the improvement generalize to previously unseen conditions?"

---

# 4. FROZEN CORE LOOP

The central system loop is:

```text
Trading Agent
      ↓
Agentic Testing Environment
      ↓
Adaptive Testing
      ↓
Vulnerability Discovery
      ↓
Diagnosis
      ↓
Structured Feedback / Intervention
      ↓
Agent Self-Adaptation
      ↓
Re-Evaluation
      ↓
Independent Generalization Validation
      ↓
Further Adaptation or Stop
```

This loop is central to the research contribution.

The system should preserve this conceptual structure even if the implementation architecture evolves.

---

# 5. WHAT MAKES THE ENVIRONMENT "AGENTIC"

The testing environment should not simply be a collection of manually scripted tests.

It should contain an agentic evaluation layer capable of reasoning about the evaluated trading agent.

Conceptually, the evaluator should be capable of:

1. profiling the agent;
2. observing its behaviour;
3. identifying weaknesses;
4. hypothesizing possible causes;
5. selecting or generating targeted evaluation scenarios;
6. analysing resulting behaviour;
7. diagnosing vulnerabilities;
8. determining an appropriate intervention;
9. providing structured feedback;
10. requesting or enabling agent adaptation;
11. re-testing the agent;
12. checking whether the vulnerability was actually mitigated;
13. checking for regressions and newly introduced weaknesses;
14. validating whether improvement generalizes beyond the training/evaluation conditions.

The implementation should therefore distinguish between:

* **testing**
* **evaluation**
* **diagnosis**
* **intervention**
* **validation**

These are related but conceptually distinct operations.

---

# 6. CENTRAL RESEARCH PROBLEM

The research investigates whether an adaptive, agentic evaluation-and-repair environment can provide a more meaningful assessment and improvement process for autonomous trading agents than static evaluation.

The core problem can be expressed as:

> Static evaluation provides a snapshot of agent behaviour under predefined conditions. Autonomous agents operating in financial environments may possess conditional vulnerabilities that remain hidden until they encounter particular market regimes, constraints, perturbations, or behavioural situations.

Therefore, the proposed environment continuously searches for weaknesses rather than relying exclusively on a fixed test suite.

---

# 7. RESEARCH OBJECTIVE

The primary objective is to design, implement, and experimentally evaluate an environment that:

### A. Evaluates

Measures autonomous trading-agent behaviour across multiple dimensions.

### B. Discovers

Actively searches for vulnerabilities rather than relying only on predefined tests.

### C. Diagnoses

Attempts to determine why a vulnerability occurred.

### D. Intervenes

Provides targeted structured feedback/intervention intended to mitigate the identified vulnerability.

### E. Re-evaluates

Tests whether the intervention actually improved the relevant behaviour.

### F. Checks side effects

Determines whether improvement in one dimension caused deterioration elsewhere.

### G. Validates generalization

Tests the adapted agent on unseen scenarios and/or historical market segments.

### H. Studies the complete closed loop

Measures whether adaptive evaluation-and-repair produces benefits over static or partially adaptive alternatives.

---

# 8. WHAT IS NOT THE RESEARCH CONTRIBUTION

The following are NOT, by themselves, considered the primary novelty:

* creating another LLM trading agent;
* using an LLM to make trading decisions;
* creating another financial QA benchmark;
* creating another backtesting engine;
* creating another static stress-test suite;
* creating another portfolio-performance metric;
* using an LLM as an evaluator;
* generating synthetic market scenarios;
* giving agents feedback;
* fine-tuning a trading model.

These may be implementation components.

The intended novelty lies in their integration into an adaptive closed-loop evaluation-and-repair framework.

The research contribution should therefore be evaluated at the **system/process level**, not by claiming that any individual component is unprecedented.

---

# 9. RESEARCH NOVELTY HYPOTHESIS

The central novelty claim under investigation is:

> An evaluation environment that adaptively searches for agent-specific vulnerabilities, diagnoses those vulnerabilities, applies targeted interventions, and independently validates the resulting behaviour can evaluate and improve autonomous trading agents more effectively than static or non-adaptive evaluation procedures.

The project must experimentally test this claim rather than assume it is true.

---

# 10. CONCEPTUAL SYSTEM ARCHITECTURE

The initial conceptual architecture is:

```text
                         ┌───────────────────────┐
                         │   Trading Agent       │
                         │                       │
                         │ Policy / LLM / Tools  │
                         └───────────┬───────────┘
                                     │
                              Observations
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │ Adaptive Evaluation Environment│
                    │                                │
                    │  Scenario Selection             │
                    │  Stress Testing                 │
                    │  Behaviour Observation          │
                    │  Vulnerability Search           │
                    └───────────────┬────────────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │      Evaluator       │
                         │                      │
                         │ Performance          │
                         │ Risk                 │
                         │ Robustness           │
                         │ Behaviour            │
                         │ Consistency          │
                         │ Adaptability         │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     Diagnosis        │
                         │                      │
                         │ What failed?         │
                         │ When?                │
                         │ Why?                 │
                         │ Under what regime?   │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Intervention /       │
                         │ Structured Feedback  │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Agent Adaptation     │
                         │                      │
                         │ Context / Memory /   │
                         │ Strategy adjustment  │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   Re-Evaluation      │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Independent / OOD    │
                         │ Validation           │
                         └──────────────────────┘
```

The exact implementation may change.

The conceptual responsibilities must remain identifiable.

---

# 11. MAJOR SYSTEM COMPONENTS

The implementation should eventually contain the following logical components.

## 11.1 Trading Agent

The evaluated system.

The environment should treat the trading agent as a modular component rather than assuming one particular model architecture.

Potential agent implementations may include:

* rule-based agent;
* classical algorithmic trading strategy;
* ML trading agent;
* LLM-based agent;
* tool-using autonomous agent;
* other autonomous financial agents.

The evaluator should interact with the agent through a defined interface.

The evaluation environment should NOT be tightly coupled to a single model provider.

---

# 12. AGENT INTERFACE

The trading agent should have a well-defined interface.

Conceptually:

```text
Environment Observation
        ↓
Agent
        ↓
Decision / Action
        ↓
Environment
        ↓
Next Observation
```

The interface should support:

* receiving market observations;
* receiving portfolio/account state where appropriate;
* making decisions;
* returning actions;
* optionally exposing reasoning/decision metadata where permitted;
* receiving structured evaluation feedback;
* optionally updating context/memory/configuration;
* continuing subsequent evaluation episodes.

The implementation should separate:

```text
Agent implementation
```

from:

```text
Agent evaluation protocol
```

so that multiple agents can be evaluated under the same environment.

---

# 13. MARKET / SIMULATION ENVIRONMENT

The environment provides the world in which the trading agent operates.

It should eventually support controlled experimentation involving:

* historical market data;
* simulated market data;
* different market regimes;
* volatility changes;
* trend/reversal conditions;
* shocks;
* liquidity changes;
* transaction costs;
* constraints;
* portfolio conditions;
* potentially adversarial or stress scenarios.

The environment must support deterministic replay where possible.

Reproducibility is essential.

Every experiment should record sufficient configuration information to reproduce the environment.

---

# 14. SCENARIO GENERATION

A major component is scenario generation and selection.

The environment should eventually support two broad classes:

## Static scenarios

Predefined scenarios that remain constant across agents.

Examples:

* fixed market periods;
* predefined stress events;
* predefined volatility conditions;
* fixed transaction-cost settings.

## Adaptive scenarios

Scenarios selected or generated based on observed agent behaviour.

For example:

```text
Agent shows excessive risk under volatility
            ↓
Environment identifies weakness
            ↓
Environment selects/generates additional
high-volatility scenarios
            ↓
Agent is tested again
```

The adaptive scenario mechanism is a key research variable.

---

# 15. EVALUATION DIMENSIONS

The framework is intended to evaluate agents across multiple dimensions rather than using return alone.

Candidate dimensions include:

### Financial performance

* return;
* risk-adjusted return;
* cumulative performance;
* drawdown;
* profitability;
* benchmark-relative performance.

### Risk

* maximum drawdown;
* volatility;
* downside risk;
* tail exposure;
* concentration;
* leverage;
* risk-adjusted metrics.

### Decision quality

* trade timing;
* position sizing;
* consistency;
* response to changing conditions;
* action appropriateness.

### Robustness

* performance under perturbations;
* performance under regime changes;
* resilience to shocks;
* sensitivity to transaction costs;
* sensitivity to execution assumptions.

### Behavioural characteristics

Potentially including:

* overtrading;
* excessive risk-taking;
* loss-chasing;
* trend dependence;
* excessive conservatism;
* inconsistent responses;
* instability under similar conditions.

### Adaptability

* ability to adjust behaviour following feedback;
* ability to recover after failure;
* ability to maintain performance across regimes;
* ability to generalize adaptation.

### Constraint adherence

* risk limits;
* exposure limits;
* trading constraints;
* operational constraints.

### Recovery

* behaviour following losses;
* behaviour after shocks;
* recovery from adverse conditions.

These dimensions are currently conceptual.

DO NOT hard-code every candidate dimension immediately.

Metrics must be formally specified before becoming experimental claims.

---

# 16. IMPORTANT DISTINCTION: METRIC VS RESEARCH DIMENSION

A dimension such as:

> "Robustness"

is not itself a metric.

The implementation should distinguish:

```text
Evaluation Dimension
        ↓
Operational Definition
        ↓
Metric(s)
        ↓
Measurement Procedure
        ↓
Score / Result
```

Example:

```text
Dimension:
Risk

Operational definition:
Ability to maintain acceptable risk exposure under changing market conditions.

Metric:
Maximum Drawdown

Measurement:
...

Interpretation:
...
```

Research metrics must be explicitly documented.

The coding agent must NOT invent scientifically significant metrics silently.

---

# 17. VULNERABILITY DISCOVERY

A vulnerability is a measurable undesirable behaviour that occurs under identifiable conditions.

A vulnerability should ideally have:

```text
Vulnerability ID
Agent ID
Scenario
Market Regime
Observed Behaviour
Metric
Threshold / Reference
Severity
Evidence
Potential Cause
Confidence
```

Example conceptual record:

```text
Vulnerability:
Excessive risk exposure during volatility spikes

Observed under:
High-volatility regime

Evidence:
Position size increases despite volatility increase

Severity:
High

Potential cause:
Failure to adjust risk policy under volatility shift
```

The exact schema is an implementation decision.

---

# 18. DIAGNOSIS

Diagnosis is distinct from detection.

Detection asks:

> "What went wrong?"

Diagnosis asks:

> "Why did it happen?"

The diagnostic component should use observed trajectories, actions, state information, scenario characteristics, and other available evidence to formulate hypotheses about the cause of a vulnerability.

Diagnosis may be probabilistic or uncertain.

The system should therefore avoid representing speculative explanations as established facts.

Conceptually:

```text
Observed failure
      ↓
Evidence collection
      ↓
Pattern identification
      ↓
Cause hypothesis
      ↓
Confidence
      ↓
Candidate intervention
```

---

# 19. INTERVENTION / REPAIR

The framework should support structured interventions intended to mitigate discovered vulnerabilities.

Possible intervention mechanisms may include:

* structured feedback;
* explicit behavioural guidance;
* context updates;
* memory updates;
* policy constraints;
* strategy reminders;
* additional examples;
* targeted scenario exposure;
* configuration changes;
* other controlled adaptation mechanisms.

The research question is NOT:

> "Can feedback make the agent better?"

It is:

> "Can targeted interventions generated from adaptive evaluation mitigate identified vulnerabilities, and do those improvements generalize without unacceptable side effects?"

---

# 20. AGENT SELF-ADAPTATION

The current conceptual design allows the agent to adapt after receiving structured feedback.

This can involve an agent's:

* context;
* memory;
* policy;
* strategy instructions;
* decision process;
* configuration.

The exact adaptation mechanism should remain modular.

Do not assume that one particular adaptation technique is the research contribution.

The framework should allow different intervention mechanisms to be compared experimentally.

---

# 21. RE-EVALUATION

After intervention, the same vulnerability should be tested again.

The system must not assume that:

```text
new score > old score
```

automatically means successful repair.

Instead, re-evaluation should examine:

1. Was the original vulnerability reduced?
2. Was the improvement statistically/experimentally meaningful?
3. Did overall performance change?
4. Did another metric deteriorate?
5. Did a new vulnerability emerge?
6. Does the improvement persist?
7. Does it generalize outside the intervention scenario?

---

# 22. REGRESSION AND SIDE-EFFECT DETECTION

Repair can introduce unintended consequences.

Example:

```text
Intervention:
Reduce excessive risk-taking

Result:
Risk decreases
BUT
Return collapses
OR
Agent becomes excessively conservative
```

This should not automatically be considered successful repair.

The framework should therefore compare multiple evaluation dimensions before and after intervention.

Conceptually:

```text
Before:
Risk       = high
Return     = good
Robustness = poor

After:
Risk       = lower
Return     = poor
Robustness = unchanged
```

This represents a trade-off, not an unqualified success.

---

# 23. STOPPING CONDITION

The adaptive loop should not run indefinitely.

Possible stopping conditions include:

* target vulnerabilities mitigated;
* improvement falls below a predefined threshold;
* repeated iterations produce no meaningful improvement;
* evaluation budget exhausted;
* intervention budget exhausted;
* new vulnerabilities outweigh improvements;
* convergence/plateau detected.

The exact stopping criteria are an experimental design decision and must be explicitly documented.

---

# 24. GENERALIZATION

Generalization is a central component of the research.

A repaired agent must not only perform better on the scenarios used for diagnosis/intervention.

It must also be tested on conditions it did not directly adapt to.

Conceptually:

```text
Discovery / Intervention Data
             ↓
        Agent Adaptation
             ↓
       Re-evaluation
             ↓
       UNSEEN CONDITIONS
             ↓
       Generalization Test
```

Possible unseen conditions include:

* unseen historical periods;
* unseen market regimes;
* unseen synthetic scenarios;
* unseen stress combinations;
* different volatility levels;
* different transaction-cost assumptions;
* different sequences of market events.

The precise validation protocol must be formally specified before final experiments.

---

# 25. OVERFITTING RISK

A major research concern is:

> The adaptive environment may teach the agent to pass the evaluator rather than genuinely improve the underlying behaviour.

This is analogous to evaluator gaming or test overfitting.

For example:

```text
Evaluator repeatedly attacks weakness X
        ↓
Agent learns specifically to survive X
        ↓
Evaluator reports improvement
        ↓
Agent fails under unseen weakness Y
```

Therefore the system must distinguish:

### Evaluation-set improvement

from:

### Genuine generalization.

Independent validation is mandatory for strong claims.

---

# 26. EVALUATOR VALIDITY

Another central research concern is evaluator quality.

An adaptive evaluator may itself:

* make incorrect diagnoses;
* select poor scenarios;
* create biased evaluations;
* over-focus on one metric;
* generate noisy interventions;
* mistake correlation for causation;
* reward undesirable behaviour;
* create circular evaluation.

Therefore evaluator performance and limitations must themselves be studied.

The research should not assume:

> "The evaluator is correct because it is an agent."

---

# 27. FINANCIAL STATISTICAL VALIDITY

Trading results are noisy.

A small number of profitable trades does not necessarily demonstrate improvement.

Experiments should therefore consider:

* sufficient sample sizes;
* multiple seeds;
* repeated runs where appropriate;
* confidence intervals where appropriate;
* statistical significance where appropriate;
* effect sizes;
* market-regime variation;
* transaction costs;
* realistic execution assumptions;
* multiple time periods;
* out-of-sample evaluation.

The coding architecture should make repeated experiments easy.

---

# 28. REPRODUCIBILITY

Reproducibility is a first-class requirement.

Every experiment should ideally record:

```text
Experiment ID
Agent version
Environment version
Dataset
Dataset version
Date range
Scenario configuration
Random seed(s)
Model configuration
Prompt/context configuration
Intervention configuration
Evaluation configuration
Software version / commit
Results
```

Experiments should be executable from saved configuration rather than relying on undocumented manual steps.

---

# 29. EXPERIMENT TRACKING

The system should maintain a clear distinction between:

```text
Experiment configuration
```

and:

```text
Experiment result
```

Never hard-code experimental results into source code.

Prefer structured experiment configurations such as:

```text
experiments/
    baseline_static/
    adaptive_evaluation/
    adaptive_repair/
    generalization/
    ablations/
```

The exact directory structure can be modified by the implementation agent if a better structure is justified.

---

# 30. CORE RESEARCH HYPOTHESES

The current conceptual hypotheses are:

## H1 — Vulnerability Discovery

Adaptive evaluation can discover vulnerabilities that are missed or insufficiently exposed by static evaluation.

## H2 — Diagnosis

Agentic diagnosis can identify useful causal or explanatory hypotheses about observed trading-agent vulnerabilities.

## H3 — Intervention / Repair

Targeted interventions derived from adaptive evaluation can mitigate identified vulnerabilities.

## H4 — Generalization

Improvements produced through adaptive evaluation and repair can generalize to previously unseen conditions.

## H5 — Regression Safety

The adaptive repair process can reduce targeted vulnerabilities without introducing unacceptable deterioration in other important evaluation dimensions.

## H6 — Evaluation Efficiency

Adaptive scenario selection can discover meaningful vulnerabilities more efficiently than indiscriminate or purely static evaluation under a comparable evaluation budget.

These hypotheses are subject to formalization before final experiments.

The coding agent must not treat them as proven conclusions.

---

# 31. BASELINES

The experimental framework should eventually support comparison against progressively stronger baselines.

Conceptual baseline hierarchy:

### Baseline 1 — Static Benchmark

Fixed scenarios and fixed evaluation.

```text
Agent → Fixed Tests → Score
```

### Baseline 2 — Static Stress Testing

Fixed but difficult stress scenarios.

```text
Agent → Fixed Stress Tests → Score
```

### Baseline 3 — Adaptive Evaluation Without Repair

Environment adapts testing based on agent behaviour but does not intervene.

```text
Agent → Adaptive Tests → Evaluation
```

### Baseline 4 — Repair Without Adaptive Discovery

Agent receives a predefined or non-agent-specific intervention.

### Baseline 5 — Partial Adaptive System

Some adaptive components are enabled while others remain fixed.

### Proposed Full Framework

```text
Agent
 ↓
Adaptive Discovery
 ↓
Diagnosis
 ↓
Targeted Intervention
 ↓
Re-Evaluation
 ↓
Generalization Validation
```

The exact baseline implementation should be determined during experimental design.

---

# 32. ABLATION STUDIES

Ablations are central to demonstrating that the integrated system is responsible for observed benefits.

Potential ablations include removing:

* adaptive scenario selection;
* vulnerability diagnosis;
* targeted intervention;
* re-evaluation;
* generalization validation;
* side-effect detection;
* adaptive feedback;
* specific evaluator components.

The purpose is to determine which components materially contribute to performance.

The paper should not rely solely on comparing:

```text
old system vs new system
```

when the contribution is an integrated architecture.

---

# 33. POTENTIAL EXPERIMENTAL MATRIX

A conceptual experiment matrix may look like:

| System              | Static Tests | Adaptive Tests |    Diagnosis | Repair | Generalization |
| ------------------- | -----------: | -------------: | -----------: | -----: | -------------: |
| Static Baseline     |            ✓ |                |              |        |                |
| Adaptive Evaluation |              |              ✓ |              |        |              ✓ |
| Repair Baseline     |            ✓ |                | ✓/predefined |      ✓ |              ✓ |
| Proposed Framework  |              |              ✓ |            ✓ |      ✓ |              ✓ |

This is a conceptual starting point.

Do not implement the matrix rigidly until the experimental protocol is finalized.

---

# 34. AGENT-LEVEL VARIABLES

The framework should eventually allow experiments across multiple agent configurations.

Potential variables:

* agent architecture;
* model;
* prompt;
* tools;
* memory;
* context;
* strategy;
* risk preferences;
* adaptation mechanism.

The evaluator should remain as independent from the agent as reasonably possible.

---

# 35. ENVIRONMENT-LEVEL VARIABLES

Potential environment variables include:

* market regime;
* volatility;
* liquidity;
* transaction costs;
* market shocks;
* trend/reversal behaviour;
* constraints;
* initial capital;
* portfolio conditions;
* execution assumptions;
* scenario difficulty.

These should ideally be configurable rather than hard-coded.

---

# 36. ADAPTIVE ENVIRONMENT PRINCIPLE

The environment should be capable of responding to the agent's observed behaviour.

For example:

```text
Agent behaviour:
Repeatedly increases exposure during volatility spikes.

Evaluator:
Detects pattern.

Environment:
Selects more targeted volatility-transition scenarios.

Agent:
Continues exhibiting behaviour.

Evaluator:
Diagnoses vulnerability.

Intervention:
Provides targeted feedback.

Agent:
Adapts.

Environment:
Tests same vulnerability under unseen conditions.

Result:
Determine whether behaviour genuinely improved.
```

This example is illustrative, not a prescribed implementation.

---

# 37. IMPORTANT RESEARCH DISTINCTION

The environment is not supposed to simply become "harder" over time.

Adaptive difficulty alone is insufficient.

The adaptation should ideally be:

> **agent-specific and evidence-driven.**

That means the environment should adapt based on observed vulnerabilities rather than randomly increasing difficulty.

The research should therefore distinguish:

```text
Random difficulty escalation
```

from:

```text
Evidence-driven adaptive evaluation
```

---

# 38. POTENTIAL FAILURE MODES

The implementation and experiments should explicitly consider:

### Agent gaming

The agent learns evaluator-specific behaviour.

### Evaluator bias

The evaluator systematically favours particular strategies.

### Diagnosis hallucination

The evaluator invents explanations unsupported by evidence.

### Reward hacking

The agent optimizes the evaluation metric while becoming worse in meaningful ways.

### Overfitting

The agent improves only on scenarios used during adaptation.

### Regression

Repair of one vulnerability causes another.

### Scenario leakage

Validation scenarios unintentionally influence adaptation.

### Statistical noise

Observed improvement is random.

### Data leakage

Historical information improperly enters decision-making.

### Non-reproducibility

Results depend heavily on seeds or uncontrolled conditions.

### Excessive complexity

The platform becomes too complex to validate scientifically.

---

# 39. SOFTWARE DESIGN PRINCIPLES

The implementation should follow these principles.

## Principle 1 — Modularity

Each major research component should be replaceable.

## Principle 2 — Explicit interfaces

Components should communicate through clear contracts.

## Principle 3 — Reproducibility

Experiments should be deterministic where possible.

## Principle 4 — Configuration over hard-coding

Research variables should be configurable.

## Principle 5 — Separation of concerns

Separate:

* agent;
* environment;
* evaluator;
* diagnosis;
* intervention;
* experiment runner;
* metrics;
* logging;
* visualization.

## Principle 6 — Observability

The system should record enough information to understand why a result occurred.

## Principle 7 — Testability

Each component should be independently testable.

## Principle 8 — Minimalism

Do not implement infrastructure that is not required for the current research stage.

## Principle 9 — Experiment first

Every major feature should have a research purpose.

## Principle 10 — Reversible development

Prefer small changes that can be tested and reverted.

---

# 40. RECOMMENDED CONCEPTUAL REPOSITORY

A possible structure is:

```text
project/
│
├── PROJECT_CONTEXT.md
├── AGENTS.md
├── README.md
│
├── research/
│   ├── research_question.md
│   ├── hypotheses.md
│   ├── evaluation_framework.md
│   ├── experimental_protocol.md
│   ├── metrics.md
│   ├── baselines.md
│   └── ablations.md
│
├── src/
│   ├── agents/
│   ├── environment/
│   ├── scenarios/
│   ├── evaluator/
│   ├── diagnosis/
│   ├── intervention/
│   ├── validation/
│   ├── experiments/
│   ├── metrics/
│   └── logging/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── reproducibility/
│
├── configs/
│   ├── agents/
│   ├── environments/
│   ├── experiments/
│   └── evaluation/
│
├── datasets/
│
├── experiments/
│
├── results/
│
├── analysis/
│
└── docs/
```

This is a proposed structure, not a mandatory one.

The implementation agent may recommend changes after inspecting the actual project.

---

# 41. MVP — MINIMUM VIABLE RESEARCH SYSTEM

The first implementation should NOT attempt to build the complete final research platform.

The MVP should demonstrate the central closed-loop concept.

Minimum viable loop:

```text
One Trading Agent
        ↓
One Controlled Market Environment
        ↓
Baseline Evaluation
        ↓
Vulnerability Detection
        ↓
Simple Diagnosis
        ↓
Structured Intervention
        ↓
Agent Adaptation
        ↓
Re-Evaluation
        ↓
Unseen Validation
```

The MVP should answer:

> Can we technically execute the complete adaptive evaluation-and-repair loop from beginning to end?

Only after this works should the system become more sophisticated.

---

# 42. DEVELOPMENT PHASES

## Phase 0 — Research specification

Define:

* research question;
* hypotheses;
* evaluation dimensions;
* metrics;
* baselines;
* experimental protocol.

No major implementation yet.

---

## Phase 1 — Core environment

Implement:

* market environment;
* trading interface;
* action space;
* observation space;
* portfolio/account state;
* deterministic replay;
* basic logging.

Goal:

> One agent can trade inside a controlled environment.

---

## Phase 2 — Static evaluation

Implement:

* evaluation runner;
* metrics;
* scoring;
* experiment storage;
* reproducible runs.

Goal:

> We can reliably measure an agent.

---

## Phase 3 — Vulnerability detection

Implement:

* behaviour analysis;
* threshold/rule-based vulnerability detection initially;
* vulnerability records;
* evidence collection.

Goal:

> The system can identify meaningful weaknesses.

Start simple.

Agentic diagnosis does not need to be implemented before the underlying measurement pipeline works.

---

## Phase 4 — Agentic evaluation

Introduce:

* evaluator reasoning;
* scenario selection;
* adaptive testing;
* evidence aggregation.

Goal:

> The evaluator can actively decide what to test next.

---

## Phase 5 — Diagnosis

Implement:

* failure analysis;
* cause hypotheses;
* confidence;
* structured diagnosis records.

Goal:

> The evaluator moves from detecting failures to reasoning about their causes.

---

## Phase 6 — Intervention / repair

Implement:

* structured feedback;
* agent adaptation mechanism;
* intervention logging.

Goal:

> The agent can respond to diagnosed vulnerabilities.

---

## Phase 7 — Re-evaluation

Implement:

* post-intervention evaluation;
* before/after comparison;
* vulnerability resolution;
* regression detection.

Goal:

> Determine whether the repair actually worked.

---

## Phase 8 — Independent validation

Implement:

* unseen scenarios;
* held-out historical periods;
* different market regimes;
* out-of-distribution testing.

Goal:

> Determine whether improvements generalize.

---

## Phase 9 — Baselines and ablations

Implement the experimental comparison framework.

Goal:

> Establish whether each adaptive component contributes meaningfully.

---

## Phase 10 — Scale and polish

Only after scientific validity is established:

* additional agents;
* additional markets;
* richer scenario generation;
* improved visualization;
* additional evaluator sophistication;
* performance optimization;
* UI/dashboard if necessary.

---

# 43. DEVELOPMENT ORDER IS IMPORTANT

Do NOT begin with:

* dashboard;
* fancy UI;
* multi-agent orchestration;
* complex LLM chains;
* sophisticated scenario generation;
* massive datasets;
* elaborate memory systems.

Begin with:

```text
Environment
    ↓
Agent
    ↓
Action
    ↓
Outcome
    ↓
Metrics
    ↓
Evaluation
```

Then add:

```text
Adaptive Testing
    ↓
Diagnosis
    ↓
Intervention
    ↓
Validation
```

The research loop must work before the platform becomes visually or architecturally sophisticated.

---

# 44. AGENTIC CODING RULES

Any AI coding agent working on this repository must follow:

### Rule 1

Read `PROJECT_CONTEXT.md` before substantial implementation.

### Rule 2

Do not modify the research question.

### Rule 3

Do not silently invent research methodology.

### Rule 4

Do not convert an experimental proposal into a fixed assumption without documenting it.

### Rule 5

Do not implement large architectural changes without explaining them.

### Rule 6

Prefer the smallest implementation that enables the current experiment.

### Rule 7

Every meaningful feature should have tests.

### Rule 8

Run tests after implementation.

### Rule 9

Do not claim an experiment succeeded without actually running it.

### Rule 10

Do not fabricate data, results, benchmarks, or citations.

### Rule 11

Keep experimental results separate from implementation code.

### Rule 12

Record important architectural decisions.

### Rule 13

Preserve reproducibility.

### Rule 14

Flag uncertainty instead of hiding it.

### Rule 15

If a research decision is required, STOP and ask the researcher rather than deciding silently.

---

# 45. CODING AGENT BEHAVIOUR

Before implementing a substantial feature, the agent should:

```text
1. Read relevant documentation.
2. Inspect existing code.
3. Identify affected components.
4. Explain the intended change.
5. Identify potential research implications.
6. Implement the smallest reasonable version.
7. Add tests.
8. Run tests.
9. Inspect failures.
10. Fix issues.
11. Re-run tests.
12. Report what changed.
```

The agent should never assume that more code means better research.

---

# 46. DECISION AUTHORITY

The coding agent may independently decide:

* variable names;
* file organization;
* implementation details;
* refactoring;
* testing utilities;
* boilerplate;
* low-level engineering choices.

The coding agent should NOT independently decide:

* research question;
* research hypotheses;
* final metrics;
* experimental protocol;
* statistical methodology;
* baseline definitions;
* what constitutes successful repair;
* what constitutes a vulnerability;
* final claims of novelty;
* final interpretation of research results.

Those require researcher approval.

---

# 47. RESEARCHER VS AGENT RESPONSIBILITIES

## Researcher

Responsible for:

* research question;
* hypotheses;
* experimental design;
* scientific interpretation;
* metric definitions;
* baseline selection;
* final claims;
* validity assessment.

## Coding Agent

Responsible for:

* implementation;
* testing;
* refactoring;
* documentation;
* debugging;
* infrastructure;
* experiment execution support;
* identifying engineering risks.

## Shared

* architecture;
* implementation trade-offs;
* experiment tooling;
* identifying methodological risks.

---

# 48. DATA PRINCIPLES

Financial data must be treated carefully.

The system should distinguish:

```text
Training / Adaptation Data
```

from:

```text
Evaluation Data
```

from:

```text
Independent Validation Data
```

Avoid leakage between these categories.

Where historical data is used, record:

* source;
* time period;
* instruments;
* frequency;
* preprocessing;
* missing-data handling;
* corporate-action handling where relevant;
* transaction-cost assumptions;
* execution assumptions.

---

# 49. HISTORICAL REPLAY

Historical market replay is intended as an important validation mechanism.

The system should eventually allow:

```text
Historical Market Data
        ↓
Replay Engine
        ↓
Agent
        ↓
Actions
        ↓
Portfolio Evolution
        ↓
Evaluation
```

Accelerated historical replay is useful because it allows many experimental episodes to be executed efficiently.

However:

> Historical replay should not automatically be treated as proof of real-world profitability.

It is an experimental validation mechanism.

---

# 50. SIMULATION VS REAL MARKETS

The initial research platform should be simulation/replay based.

Do not connect to live financial markets unless explicitly required and separately approved.

The goal is controlled scientific experimentation, not live trading deployment.

---

# 51. EXPERIMENT LOGGING

Every adaptive evaluation episode should ideally produce a trace.

Conceptually:

```json
{
  "experiment_id": "...",
  "episode_id": "...",
  "agent_version": "...",
  "environment_version": "...",
  "scenario": "...",
  "market_regime": "...",
  "observations": [],
  "actions": [],
  "portfolio_state": [],
  "metrics": {},
  "vulnerabilities": [],
  "diagnosis": [],
  "interventions": [],
  "adaptation": {},
  "reevaluation": {},
  "validation": {},
  "seed": 0
}
```

This is illustrative.

The actual schema should be designed during implementation.

---

# 52. OBSERVABILITY

The system should make it possible to answer:

> Why did the agent receive this score?

and:

> Why did the environment choose this test?

and:

> Why did the evaluator diagnose this vulnerability?

and:

> Why did the system conclude that the repair succeeded?

If the system cannot answer these questions, it becomes difficult to defend scientifically.

---

# 53. VERSIONING

The following should ideally be versioned:

* agent;
* prompts;
* model configuration;
* environment;
* scenario generator;
* evaluator;
* diagnosis logic;
* intervention logic;
* datasets;
* experiment configurations.

A result should be traceable to the exact configuration that produced it.

---

# 54. FUTURE EXTENSIONS

These are explicitly NOT MVP requirements.

Potential future extensions:

* multiple trading agents;
* multiple asset classes;
* richer market simulators;
* multi-agent market environments;
* adversarial evaluators;
* competing evaluators;
* more sophisticated causal diagnosis;
* learned scenario generation;
* dynamic evaluator populations;
* cross-agent vulnerability analysis;
* automated research hypothesis generation;
* more advanced repair mechanisms.

These should only be implemented if they strengthen the research question.

---

# 55. SECONDARY RESEARCH DIRECTION

A potentially interesting secondary question is whether repeated evaluation across multiple agents reveals recurring vulnerability patterns.

For example:

```text
Agent A ─┐
Agent B ─┼──→ Evaluator ─→ Vulnerability Patterns
Agent C ─┘
```

This could eventually allow the environment to learn that certain failure modes recur across agents.

However:

> Cross-agent vulnerability discovery is secondary to the central adaptive evaluation-and-repair loop.

It should not distract from the primary research contribution.

---

# 56. CORE RESEARCH QUESTIONS

The implementation should support investigation of questions such as:

### RQ1

Can an adaptive evaluator discover vulnerabilities that static evaluation misses?

### RQ2

Can agentic diagnosis provide useful explanations for observed vulnerabilities?

### RQ3

Can targeted intervention mitigate identified vulnerabilities?

### RQ4

Do improvements generalize to unseen market conditions?

### RQ5

Does adaptive repair introduce regressions or new vulnerabilities?

### RQ6

Does adaptive evaluation achieve better vulnerability discovery under a comparable evaluation budget?

These questions may be refined during the research process.

---

# 57. WHAT SUCCESS LOOKS LIKE

The project is successful if it produces a scientifically defensible demonstration that:

1. the environment can evaluate autonomous trading agents;
2. adaptive testing can identify agent-specific weaknesses;
3. diagnosis can produce actionable hypotheses;
4. targeted intervention can change agent behaviour;
5. re-evaluation can determine whether the vulnerability was mitigated;
6. the framework can detect regressions;
7. independent validation can distinguish genuine improvement from evaluator overfitting;
8. experiments demonstrate whether the complete adaptive loop provides measurable benefits over appropriate baselines.

A visually impressive platform without these capabilities is NOT sufficient.

---

# 58. WHAT FAILURE LOOKS LIKE

The project should explicitly accept the possibility that:

* adaptive evaluation does not outperform static evaluation;
* diagnosis is unreliable;
* interventions do not generalize;
* repair causes harmful trade-offs;
* evaluator adaptation creates overfitting;
* results are statistically weak;
* the proposed architecture adds complexity without meaningful benefit.

Negative results are scientifically valid.

The system must be designed to discover the truth rather than manufacture evidence supporting the hypothesis.

---

# 59. CURRENTLY FROZEN DECISIONS

The following are considered frozen at the conceptual level:

1. Research direction:
   **Adaptive Agentic Evaluation and Repair of Autonomous Financial Agents**

2. Experimental scope:
   **Autonomous trading agents**

3. Central concept:
   **An adaptive agentic evaluation environment rather than a better trading agent**

4. Core loop:

```text
Evaluate
→ Discover
→ Diagnose
→ Intervene
→ Adapt
→ Re-evaluate
→ Independently Validate
```

5. Generalization is central.

6. Overfitting/evaluator gaming is a central concern.

7. Diagnosis and repair are central, not optional add-ons.

8. Multidimensional evaluation is required.

9. Baselines and ablations are required.

10. Reproducibility and financial statistical validity are first-class requirements.

11. Historical-data replay is intended as an important validation mechanism.

12. Cross-agent recurring vulnerability analysis is secondary.

---

# 60. CURRENTLY OPEN DECISIONS

The following should NOT be silently decided by the coding agent:

* exact trading-agent implementation;
* exact model/provider;
* exact market dataset;
* exact market simulator;
* exact evaluation metrics;
* metric thresholds;
* exact vulnerability taxonomy;
* exact diagnosis mechanism;
* exact intervention mechanism;
* exact adaptation mechanism;
* statistical testing methodology;
* final experiment count;
* exact scenario-generation algorithm;
* final baseline configurations;
* stopping criteria;
* final user interface;
* deployment architecture.

These should be resolved progressively as the research design develops.

---

# 61. IMPLEMENTATION PHILOSOPHY

The project should follow:

> Build the smallest scientifically meaningful system first.

Do not build a production-grade fintech platform.

Do not optimize prematurely.

Do not introduce infrastructure merely because it is technologically interesting.

The purpose of the software is to enable rigorous experimentation.

The preferred development sequence is:

```text
Research Question
      ↓
Experimental Requirement
      ↓
Minimal Architecture
      ↓
Implementation
      ↓
Test
      ↓
Experiment
      ↓
Observation
      ↓
Refinement
```

Not:

```text
Cool Technology
      ↓
Build Everything
      ↓
Find a Research Question
```

---

# 62. FINAL INSTRUCTION TO ANY CODING AGENT

You are implementing a research instrument.

Treat the platform as an experimental laboratory rather than merely an application.

When uncertain:

1. preserve the research intent;
2. choose the simplest implementation;
3. make assumptions explicit;
4. maintain reproducibility;
5. add tests;
6. document important decisions;
7. ask the researcher before changing methodology.

Never fabricate evidence.

Never fabricate experiment results.

Never claim a hypothesis has been validated merely because the code runs.

Never silently alter the research direction.

The ultimate goal is not to produce the largest or most sophisticated codebase.

The goal is to produce a **controlled, reproducible, extensible experimental environment capable of rigorously testing the research hypothesis.**

---

# 63. IMMEDIATE NEXT STEP

Before implementation begins, the coding agent should:

1. Read this document completely.
2. Inspect the repository.
3. Identify what is currently present.
4. Translate this conceptual framework into a proposed technical architecture.
5. Identify the minimum viable implementation.
6. Identify research decisions that must be finalized.
7. Propose a development plan.
8. STOP and request researcher approval.

No substantial code should be written until the architecture and MVP have been reviewed.
