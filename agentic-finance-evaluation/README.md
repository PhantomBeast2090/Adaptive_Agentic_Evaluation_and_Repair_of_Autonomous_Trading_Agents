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
Implementation of the AEE has not yet begun. Only the preliminary directory structure, datasets, and infrastructure are set up.