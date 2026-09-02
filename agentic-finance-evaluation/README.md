# Adaptive Agentic Evaluation Environment for Autonomous Financial Agents

## Research Objective
The goal is to build a hierarchical multi-agent system (AEE) that evaluates an autonomous financial agent across financial reasoning, decision quality, risk, robustness, consistency, safety, and adversarial behaviour.

## Repository Structure
- `data/`: Raw and processed datasets, scenarios, splits
- `agents/`: Orchestrator, scenario, evaluation, diagnosis, adaptation, repair, validation
- `environment/`: Market, portfolio, information, constraints
- `evaluation/`: Evaluators, metrics, scorers, benchmarks
- `memory/`: Agent profiles, failure/repair/evaluation history
- `experiments/`: Baseline, static, adaptive, diagnosis, repair, ablation, holdout
- `configs/`: YAML configurations
- `src/`: Data pipeline, schemas, utilities, logging
- `tests/`: Basic infrastructure tests

## Setup Instructions
1. Install dependencies: `pip install -r requirements.txt`
2. Create `.env` based on `.env.example`

## Current Status
The Phase 1 financial-agent and financial-environment foundation has been
audited and frozen for Static Evaluation development. The repository also
contains early evaluator modules from later phases, but the next milestone is to
build the Static Evaluation Pipeline on top of the tested deterministic episode
runner foundation.

See `docs/PHASE1_AUDIT.md` for the current environment contract, information
boundary, reproducibility notes, and known limitations.
