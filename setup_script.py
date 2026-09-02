import os
import json
import hashlib
from datetime import datetime

BASE_DIR = 'agentic-finance-evaluation'

def get_hash(file_path):
    h = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()
    except:
        return None

def write_file(path, content):
    with open(os.path.join(BASE_DIR, path), 'w') as f:
        f.write(content)

# 1. Base files
gitignore = """
.env
__pycache__/
*.pyc
.venv/
venv/
.ipynb_checkpoints/
logs/
results/
"""
write_file('.gitignore', gitignore.strip())

envexample = """
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
FRED_API_KEY=
SEC_USER_AGENT=
"""
write_file('.env.example', envexample.strip())

requirements = """
python-dotenv
pandas
numpy
scipy
scikit-learn
pydantic
requests
datasets
tqdm
pyyaml
matplotlib
jupyter
pytest
"""
write_file('requirements.txt', requirements.strip())

pyproject = """
[build-system]
requires = ["setuptools>=42", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "agentic-finance-evaluation"
version = "0.1.0"
description = "Adaptive Agentic Evaluation Environment for Autonomous Financial Agents"
"""
write_file('pyproject.toml', pyproject.strip())

# 2. Configs
datasets_yaml = """
finqa:
  path: "data/raw/finqa/source"
tatqa:
  path: "data/raw/tatqa/source"
financebench:
  path: "data/raw/financebench/source/data"
convfinqa:
  path: "data/raw/convfinqa/source"
finrl:
  path: "data/raw/finrl/source"
"""
write_file('configs/datasets.yaml', datasets_yaml.strip())

dev_yaml = """
environment: "development"
logging_level: "INFO"
random_seed: 42
"""
write_file('configs/development.yaml', dev_yaml.strip())

exp_yaml = """
experiment_id: "PLACEHOLDER"
agent_version: "PLACEHOLDER"
evaluation_budget: 1000
scenario_count: 100
random_seed: 42
model_configuration: "PLACEHOLDER"
"""
write_file('configs/experiment.yaml', exp_yaml.strip())

# 3. Schemas
schema_scenario = """
from pydantic import BaseModel
from typing import Optional, Any

class Scenario(BaseModel):
    scenario_id: str
    source: str
    dimension: str
    difficulty: str
    market_regime: str
    information_state: Any
    task: str
    constraints: list[str]
    ground_truth: Any
    expected_behaviour: str
    holdout: bool
"""
write_file('src/schemas/scenario.py', schema_scenario.strip())

schema_eval = """
from pydantic import BaseModel
from typing import Any

class EvaluationResult(BaseModel):
    run_id: str
    agent_version: str
    scenario_id: str
    evaluator_id: str
    score: float
    failure: bool
    severity: str
    evidence: str
    confidence: float
    cost: float
    latency: float
    timestamp: str
"""
write_file('src/schemas/evaluation.py', schema_eval.strip())

schema_agent = """
from pydantic import BaseModel

class AgentProfile(BaseModel):
    agent_id: str
    agent_version: str
    capability_scores: dict[str, float]
    known_failures: list[str]
    verified_causes: list[str]
    tested_dimensions: list[str]
    untested_dimensions: list[str]
    repair_history: list[str]
    evaluation_history: list[str]
"""
write_file('src/schemas/agent.py', schema_agent.strip())

schema_repair = """
from pydantic import BaseModel

class RepairRecord(BaseModel):
    failure_id: str
    root_cause: str
    repair_type: str
    old_agent_version: str
    new_agent_version: str
    expected_effect: str
    actual_effect: str
    validation_result: str
    regression_result: str
"""
write_file('src/schemas/repair.py', schema_repair.strip())

init_py = ""
write_file('src/schemas/__init__.py', init_py)

# 4. Docs
readme = """
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
"""
write_file('README.md', readme.strip())

write_file('docs/RESEARCH_CONTEXT.md', """
# Research Context
- Research problem: Evaluating autonomous financial agents is difficult due to domain complexity.
- Central hypothesis: An adaptive agentic evaluation environment can discover flaws and repair them more effectively than static benchmarks.
- AEE concept: Agentic Evaluation Environment
- AUE concept: Agent Under Evaluation
""")

write_file('docs/SYSTEM_SPEC.md', """
# System Specification
Environment Orchestrator
↓
Scenario Team | Evaluation Team | Diagnosis Team | Adaptation Agent | Repair Team | Validation Team
↓
Agent Under Evaluation
↓
Financial Simulation Environment
""")

write_file('docs/DATA_SPEC.md', """
# Data Specification
- Datasets: FinQA, TAT-QA, FinanceBench, ConvFinQA, FinRL
- Raw vs Processed: All data must be kept in raw, untouched form.
- Future Pipeline: SEC and FRED datasets will be downloaded programmatically.
- Holdout Principle: Holdout scenarios must never be used for adaptation, diagnosis, or tuning.
""")

write_file('docs/EVALUATION_PROTOCOL.md', """
# Evaluation Protocol
- Static Baseline
- Adaptive Evaluation
- Diagnosis
- Repair
- Validation
- Holdout Evaluation
""")

write_file('docs/EXPERIMENT_PROTOCOL.md', """
# Experiment Protocol
Placeholders for the future experimental structure.
""")

write_file('docs/METRICS.md', """
# Metrics
- Failure Detection
- Evaluation Coverage
- Evaluation Efficiency
- Agent Quality
- Repair Effectiveness
- Generalization
- Cost
""")

write_file('docs/CHANGELOG.md', """
## Initial Setup
- Project repository initialized
- Dataset acquisition performed
- Dataset metadata created
- Initial schemas created
- Development infrastructure prepared
""")

# 5. Tests
test_infra = """
import os
import yaml
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

def test_directories_exist():
    dirs = ['data/raw', 'src/schemas', 'configs', 'tests']
    for d in dirs:
        assert os.path.exists(os.path.join(BASE_DIR, d)), f"Directory {d} does not exist"

def test_config_loads():
    with open(os.path.join(BASE_DIR, 'configs/development.yaml')) as f:
        config = yaml.safe_load(f)
    assert 'environment' in config

def test_schema_instantiation():
    from src.schemas.scenario import Scenario
    s = Scenario(
        scenario_id="test",
        source="FinQA",
        dimension="risk",
        difficulty="hard",
        market_regime="bull",
        information_state={},
        task="predict",
        constraints=[],
        ground_truth={},
        expected_behaviour="hold",
        holdout=False
    )
    assert s.scenario_id == "test"

def test_env_not_exposed():
    assert not os.path.exists(os.path.join(BASE_DIR, '.env')), ".env file should not be committed"
    assert os.path.exists(os.path.join(BASE_DIR, '.env.example')), ".env.example should exist"
"""
write_file('tests/infrastructure/test_setup.py', test_infra.strip())
write_file('tests/infrastructure/__init__.py', "")
write_file('tests/__init__.py', "")

# 6. Metadata generation
def generate_metadata():
    datasets = {
        'finqa': {'name': 'FinQA', 'source': 'https://github.com/czyssrs/FinQA', 'role': 'Financial numerical reasoning'},
        'tatqa': {'name': 'TAT-QA', 'source': 'https://github.com/NExTplusplus/TAT-QA', 'role': 'Text + table financial reasoning'},
        'financebench': {'name': 'FinanceBench', 'source': 'https://github.com/patronus-ai/financebench', 'role': 'Financial factuality and evidence grounding'},
        'convfinqa': {'name': 'ConvFinQA', 'source': 'https://github.com/czyssrs/ConvFinQA', 'role': 'Multi-turn financial reasoning and consistency'},
        'finrl': {'name': 'FinRL', 'source': 'https://github.com/AI4Finance-Foundation/FinRL', 'role': 'Financial market/portfolio simulation infrastructure'}
    }

    manifest = {"datasets": []}
    
    for ds_id, info in datasets.items():
        base_path = os.path.join(BASE_DIR, 'data', 'raw', ds_id, 'source')
        files = []
        hashes = {}
        for root, dirs, filenames in os.walk(base_path):
            if '.git' in root: continue
            for filename in filenames:
                path = os.path.join(root, filename)
                rel_path = os.path.relpath(path, base_path)
                files.append(rel_path)
                h = get_hash(path)
                if h: hashes[rel_path] = h
                
        meta = {
            "name": info['name'],
            "official_source": info['source'],
            "source_url": info['source'],
            "repository": info['source'],
            "version_or_commit": "latest",
            "download_date": datetime.now().isoformat(),
            "license": "See repository",
            "description": info['role'],
            "research_role": info['role'],
            "record_count": None,
            "splits": {},
            "files": files[:100], # truncate list if huge
            "sha256": {k: hashes[k] for k in list(hashes)[:100]},
            "known_limitations": [],
            "citation": ""
        }
        
        with open(os.path.join(BASE_DIR, 'data', 'raw', ds_id, 'dataset_metadata.json'), 'w') as f:
            json.dump(meta, f, indent=2)
            
        manifest['datasets'].append({
            "name": info['name'],
            "status": "acquired",
            "role": info['role']
        })
        
    with open(os.path.join(BASE_DIR, 'data', 'DATASET_MANIFEST.json'), 'w') as f:
        json.dump(manifest, f, indent=2)

generate_metadata()

write_file('data/ACQUISITION_REPORT.md', """
# Acquisition Report
Datasets acquired: FinQA, TAT-QA, FinanceBench (public subset), ConvFinQA, FinRL.
""")
