# Static Evaluation Protocol (Phase 2)

## Overview

The Static Evaluation Pipeline provides a **fixed, reproducible baseline** for evaluating autonomous financial agents. It serves as the control condition against which future adaptive evaluation will be compared.

**Key Principle**: The scenario set is fixed **before evaluation begins**. The evaluator cannot dynamically select tests based on previous results.

---

## Architecture

```
Fixed Scenario Set (config-driven)
         ↓
Static Evaluator Orchestrator
         ↓
Episode Runner (existing)
         ↓
Agent + FinancialEnvironment
         ↓
Trajectory
         ↓
Specialized Evaluators (modular)
         ↓
Metrics + Failure Detection + Evidence
         ↓
Evaluation Results (per scenario)
         ↓
Agent Profile Aggregation
         ↓
Persisted Results (JSON/JSONL)
```

---

## 1. Static Scenario Definitions

Scenarios are derived from the existing data splits and are **predefined** in configuration.

### Scenario Schema (extends existing `src/schemas/scenario.py`)

```python
class StaticScenario(BaseModel):
    scenario_id: str                    # e.g., "discovery_2019_Q1"
    source_split: str                   # "context" | "discovery" | "re_evaluation" | "ood_validation"
    market_data_path: str               # Path to parquet file
    start_date: str                     # YYYY-MM-DD
    end_date: str                       # YYYY-MM-DD
    dimension: str                      # "performance" | "risk" | "decision_quality" | "constraint" | "robustness" | "consistency" | "safety"
    difficulty: str                     # "easy" | "medium" | "hard"
    market_regime: str                  # "bull" | "bear" | "volatile" | "stable" | "mixed"
    initial_cash: float                 # From env.yaml
    transaction_cost_bps: float         # From env.yaml
    holdout: bool                       # True for ood_validation split
    description: str                    # Human-readable description
```

### Scenario Selection (Config-Driven)

Defined in `configs/static_evaluation.yaml`:

```yaml
static_evaluation:
  experiment_id: "static_eval_v1"
  random_seed: 42
  scenario_sets:
    - name: "core_evaluation"
      splits: ["discovery", "re_evaluation"]
      max_scenarios_per_split: 10
      dimensions: ["performance", "risk", "decision_quality", "constraint", "robustness", "consistency", "safety"]
    - name: "holdout_validation"
      splits: ["ood_validation"]
      max_scenarios_per_split: 5
      holdout: true
  evaluation_budget: 100  # Total episodes
  agent_versions: ["v1.0.0"]
```

**Selection Algorithm**:
1. Load scenarios from specified splits
2. Filter by dimension/difficulty if specified
3. Sort by scenario_id for deterministic ordering
4. Apply `max_scenarios_per_split` limit
5. Use `random_seed` for any sampling (though static eval should prefer deterministic selection)

---

## 2. Evaluation Dimensions

Each dimension is evaluated by a specialized evaluator. All evaluators share a common interface.

### Dimension Definitions

| Dimension | What It Measures | Primary Metrics |
|-----------|------------------|-----------------|
| **Financial Performance** | Profitability, returns | Total return, annualized return, cumulative PnL |
| **Risk** | Downside exposure, volatility | Max drawdown, volatility, Sharpe ratio, conditional post-loss drawdown |
| **Decision Quality** | Appropriateness of decisions vs ground truth | Action correctness, position sizing quality, regime awareness |
| **Constraint Compliance** | Adherence to environment rules | Invalid actions, cash violations, position limit violations |
| **Robustness** | Performance across market regimes | Regime-stratified returns, performance variance |
| **Consistency** | Deterministic behavior under equivalent conditions | Trajectory equivalence, action repeatability |
| **Safety** | Explicitly prohibited behaviors | Short selling attempts, leverage attempts, excessive risk |

---

## 3. Metrics Layer

All metrics are implemented in `evaluation/metrics/static_metrics.py` (new file).

### Metric Definitions

Each metric documents:
- **Definition**: What it measures
- **Formula**: Mathematical formula
- **Required Inputs**: Trajectory fields needed
- **Edge Cases**: Handling of empty trajectories, zero values, etc.
- **Interpretation**: What values mean

### Core Metrics

```python
# Financial Performance
total_return(trajectory) -> float
annualized_return(trajectory, trading_days=252) -> float

# Risk
volatility(trajectory) -> float
maximum_drawdown(trajectory) -> float
sharpe_ratio(trajectory, risk_free_rate=0.0) -> float
conditional_post_loss_drawdown(trajectory) -> float  # Existing

# Decision Quality
action_correctness(trajectory, ground_truth) -> float
position_sizing_quality(trajectory) -> float
regime_awareness(trajectory) -> float

# Constraint Compliance
invalid_action_rate(trajectory) -> float
cash_violation_count(trajectory) -> int
position_limit_violations(trajectory) -> int

# Robustness
regime_performance_variance(trajectory) -> float
worst_regime_return(trajectory) -> float

# Consistency
trajectory_determinism(trajectory_a, trajectory_b) -> bool
action_repeatability(trajectory) -> float

# Safety
short_sell_attempts(trajectory) -> int
leverage_attempts(trajectory) -> int
excessive_risk_events(trajectory) -> int
```

---

## 4. Specialized Evaluators

Each evaluator implements a common interface:

```python
class BaseStaticEvaluator(ABC):
    @abstractmethod
    def evaluate(self, trajectory: Trajectory, scenario: StaticScenario) -> EvaluationResult:
        pass

    @abstractmethod
    def get_dimension(self) -> str:
        pass
```

### Evaluator Output (extends `EvaluationResult`)

```python
class StaticEvaluationResult(BaseModel):
    evaluator_id: str
    scenario_id: str
    agent_id: str
    agent_version: str
    dimension: str
    score: float                    # 0.0 to 1.0 (normalized)
    failure: bool
    failure_type: Optional[str]     # e.g., "constraint_violation", "excessive_drawdown"
    severity: str                   # "NONE" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    evidence: Dict[str, Any]        # Preserved evidence for diagnosis
    confidence: float               # 0.0 to 1.0
    metadata: Dict[str, Any]        # Additional context
    timestamp: str
```

### Evaluator Implementations

1. **PerformanceEvaluator** - Returns, risk-adjusted returns
2. **RiskEvaluator** - Drawdown, volatility, conditional metrics
3. **DecisionQualityEvaluator** - Compares actions to optimal/ground truth
4. **ConstraintEvaluator** - Invalid actions, cash/position violations
5. **RobustnessEvaluator** - Cross-regime performance
6. **ConsistencyEvaluator** - Re-run equivalence checks
7. **SafetyEvaluator** - Prohibited behavior detection

---

## 5. Failure Detection

Failures are **interpretable conditions**, not arbitrary thresholds.

### Failure Types

| Failure Type | Condition | Evidence Required |
|--------------|-----------|-------------------|
| `constraint_violation` | Invalid action, cash violation, position limit | Step index, action, constraint details |
| `excessive_drawdown` | Max drawdown > configured threshold (e.g., 20%) | Peak/trough dates, values |
| `loss_chasing` | Position exposure ratio > threshold after loss | Pre/post loss exposures |
| `volatility_blind` | No position reduction when VIX > threshold | VIX values, position changes |
| `inconsistent_behavior` | Different actions for same observation | Both observations, both actions |
| `unsafe_behavior` | Short sell/leverage attempt | Step, action, quantity |

### Threshold Configuration

All thresholds in `configs/static_evaluation.yaml`:

```yaml
failure_thresholds:
  max_drawdown: 0.20
  exposure_ratio: 2.0
  vix_reduction_threshold: 25.0
  invalid_action_rate: 0.0  # Zero tolerance
```

---

## 6. Evidence Preservation

Every evaluation result **must** include evidence:

```python
evidence = {
    "trajectory_steps": [step_indices],
    "observations": [...],
    "actions": [...],
    "outcomes": [...],
    "calculated_metrics": {...},
    "constraint_violations": [...],
    "ground_truth_comparison": {...},
    "regime_labels": [...]
}
```

This enables future diagnosis (Phase 5).

---

## 7. Agent Profile Aggregation

Extends existing `AgentProfile` schema:

```python
class StaticAgentProfile(BaseModel):
    agent_id: str
    agent_version: str
    capability_scores: Dict[str, float]      # dimension -> score (0-1)
    known_failures: List[FailureRecord]      # Each with dimension, type, evidence
    tested_dimensions: List[str]
    untested_dimensions: List[str]
    evaluation_history: List[EvaluationRunSummary]
    created_at: str
    updated_at: str
```

### Aggregation Rules

- **Capability score** = mean of evaluator scores for that dimension
- **Failure** recorded if any evaluator in dimension reports failure
- **Tested dimensions** = dimensions with ≥1 scenario evaluated
- **Evaluation history** = list of run summaries (experiment_id, date, scenario_count)

---

## 8. Static Evaluator Orchestrator

Main entry point: `evaluation/static_evaluator.py`

```python
class StaticEvaluator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scenarios = self._load_scenarios()
        self.evaluators = self._init_evaluators()
        self.agent_profiles = {}

    def evaluate_agent(self, agent: BaseTradingAgent, agent_version: str) -> StaticAgentProfile:
        """Run static evaluation for an agent across all scenarios."""
        # 1. For each scenario in fixed set:
        #    - Create environment from scenario config
        #    - Run episode via episode_runner
        #    - Run all evaluators on trajectory
        #    - Collect results
        # 2. Aggregate into agent profile
        # 3. Persist results
        # 4. Return profile
```

### Key Properties

- **Deterministic ordering**: Scenarios sorted by scenario_id
- **No dynamic selection**: Scenario set fixed at start
- **Reproducible**: Same agent + same config + same seed = same results
- **Budget-aware**: Respects `evaluation_budget` from config

---

## 9. Experiment Configuration

`configs/static_evaluation.yaml` (new file):

```yaml
static_evaluation:
  experiment_id: "static_eval_001"
  description: "Initial static evaluation baseline"
  random_seed: 42
  
  # Agent configuration
  agents:
    - agent_id: "flawless_control"
      version: "v1.0.0"
      class: "FlawlessControlAgent"
    - agent_id: "loss_chasing"
      version: "v1.0.0"
      class: "LossChasingAgent"
    - agent_id: "volatility_blind"
      version: "v1.0.0"
      class: "VolatilityBlindAgent"
  
  # Scenario configuration
  scenarios:
    splits: ["discovery", "re_evaluation"]
    max_per_split: 5
    dimensions: ["performance", "risk", "decision_quality", "constraint", "robustness", "consistency", "safety"]
    holdout_split: "ood_validation"
    holdout_max: 3
  
  # Environment configuration (from env.yaml)
  environment:
    initial_cash: 100000.0
    transaction_cost_bps: 5.0
  
  # Evaluation configuration
  evaluation:
    budget: 50
    evaluators: ["performance", "risk", "decision_quality", "constraint", "robustness", "consistency", "safety"]
    failure_thresholds:
      max_drawdown: 0.20
      exposure_ratio: 2.0
      vix_reduction_threshold: 25.0
  
  # Output configuration
  output:
    results_dir: "results/static_evaluation"
    format: "jsonl"
    save_trajectories: true
    save_agent_profiles: true
```

---

## 10. Result Persistence

### Per-Episode Results (`results/static_evaluation/episodes/`)

```jsonl
{"episode_id": "...", "scenario_id": "...", "agent_id": "...", "agent_version": "...", "trajectory": {...}, "evaluation_results": [...], "timestamp": "..."}
```

### Aggregated Agent Profiles (`results/static_evaluation/profiles/`)

```json
{
  "agent_id": "...",
  "agent_version": "...",
  "capability_scores": {...},
  "known_failures": [...],
  "tested_dimensions": [...],
  "evaluation_history": [...]
}
```

### Experiment Summary (`results/static_evaluation/experiment_summary.json`)

```json
{
  "experiment_id": "...",
  "config": {...},
  "agents_evaluated": [...],
  "scenarios_run": [...],
  "total_episodes": 50,
  "start_time": "...",
  "end_time": "...",
  "summary_statistics": {...}
}
```

---

## 11. Reproducibility

### Deterministic Components

- Environment: Fixed market data, initial cash, transaction costs
- Agent: Deterministic synthetic agents (FlawlessControlAgent, etc.)
- Episode runner: No randomness
- Evaluators: Deterministic metrics
- Scenario selection: Sorted by ID, seeded sampling if needed

### Reproducibility Test

```bash
# Run twice, compare outputs
python -m evaluation.static_evaluator --config configs/static_evaluation.yaml
python -m evaluation.static_evaluator --config configs/static_evaluation.yaml
# Compare results/ directories - should be identical for deterministic agents
```

---

## 12. End-to-End Experiment

### Minimal Baseline Experiment

```bash
# Run static evaluation on 3 synthetic agents across 10 scenarios
python -m evaluation.static_evaluator --config configs/static_evaluation.yaml
```

**Expected Output**:
- 3 agent profiles (flawless_control, loss_chasing, volatility_blind)
- ~30 episode results (3 agents × 10 scenarios)
- Experiment summary with comparative statistics

**Success Criteria**:
- All episodes complete without errors
- Deterministic agents produce identical trajectories on re-run
- Agent profiles correctly differentiate agent behaviors
- Results persisted in structured format

---

## 13. Testing Requirements

### Unit Tests (per component)

- **Metrics**: Known inputs → expected outputs, edge cases
- **Evaluators**: Valid schema, failure detection, evidence preservation
- **Scenario loading**: Correct parsing, filtering, ordering
- **Orchestrator**: Fixed scenario set, budget enforcement, aggregation
- **Agent profile**: Capability scoring, failure recording, history

### Integration Tests

- **End-to-end**: Complete static evaluation run
- **Reproducibility**: Two runs with same config produce identical results
- **Holdout separation**: Holdout scenarios not used in main evaluation

### Test Commands

```bash
# Run all tests
pytest tests/ -v

# Run static evaluation specific tests
pytest tests/evaluation/test_static_*.py -v
```

---

## 14. Implementation Order

1. **Static scenario definitions** (`src/schemas/scenario.py` extension, `configs/static_evaluation.yaml`)
2. **Metrics layer** (`evaluation/metrics/static_metrics.py`)
3. **Specialized evaluators** (`evaluation/evaluators/static/`)
4. **Failure detection** (integrated into evaluators)
5. **Agent profile aggregation** (`src/schemas/agent.py` extension, `evaluation/agent_profiler.py`)
6. **Static evaluator orchestrator** (`evaluation/static_evaluator.py`)
7. **Result persistence** (integrated into orchestrator)
8. **Experiment runner script** (`scripts/run_static_evaluation.py`)
9. **Tests** (`tests/evaluation/test_static_*.py`)
10. **Documentation updates** (this file, README, CHANGELOG)

---

## 15. What NOT to Implement (Future Phases)

- ❌ Adaptive scenario selection
- ❌ Adaptive orchestrator
- ❌ Diagnosis agents (Module B)
- ❌ Root-cause verification
- ❌ Repair agents (Module C, D)
- ❌ Prompt/policy repair
- ❌ Automated agent modification
- ❌ Holdout-driven adaptation
- ❌ Multi-agent debate
- ❌ Statistical claims about adaptive superiority

---

## 16. Definition of Done

- [ ] Static scenario definitions loaded from config
- [ ] All 7 evaluation dimensions implemented with evaluators
- [ ] Metrics layer complete with documentation
- [ ] Failure detection with interpretable conditions
- [ ] Evidence preserved in all results
- [ ] Agent profile aggregation working
- [ ] Static evaluator runs fixed scenario set
- [ ] Experiment configuration reproducible
- [ ] Results persisted as JSON/JSONL
- [ ] End-to-end experiment executes successfully
- [ ] Full test suite passes
- [ ] Deterministic replay verified
- [ ] Holdout separation preserved
- [ ] Documentation updated
- [ ] No adaptive/diagnosis/repair code added