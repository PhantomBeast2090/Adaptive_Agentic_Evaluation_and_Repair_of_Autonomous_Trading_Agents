import json
import os
import pandas as pd
from typing import Dict, Any, List

class TraceLogger:
    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.current_trace = None
        
    def start_episode(self, metadata: Dict[str, Any]):
        self.current_trace = {
            "episode_metadata": metadata,
            "trajectory": [],
            "evaluation": {},
            "diagnosis": {},
            "intervention_applied": {},
            "metrics": {}
        }
        
    def log_step(self, step_index: int, date: str, observation: Dict[str, Any], decision: Dict[str, Any], outcome: Dict[str, Any]):
        if self.current_trace is None:
            raise ValueError("Episode not started")
            
        self.current_trace["trajectory"].append({
            "step_index": step_index,
            "date": date,
            "observation": observation,
            "decision": decision,
            "outcome": outcome
        })
        
    def add_evaluation(self, evaluation: Dict[str, Any]):
        self.current_trace["evaluation"] = evaluation
        
    def add_diagnosis(self, diagnosis: Dict[str, Any]):
        self.current_trace["diagnosis"] = diagnosis
        
    def add_intervention(self, intervention: Dict[str, Any]):
        self.current_trace["intervention_applied"] = intervention
        
    def add_metrics(self, metrics: Dict[str, Any]):
        self.current_trace["metrics"] = metrics
        
    def save(self):
        if self.current_trace is None:
            return
            
        episode_id = self.current_trace["episode_metadata"]["episode_id"]
        phase = self.current_trace["episode_metadata"]["phase"]
        
        # Save as JSON
        json_path = os.path.join(self.log_dir, f"{episode_id}_{phase}.json")
        with open(json_path, 'w') as f:
            json.dump(self.current_trace, f, indent=2)
            
        # Flatten and save trajectory to Parquet for fast tabular analysis
        if self.current_trace["trajectory"]:
            flat_trajectory = []
            for step in self.current_trace["trajectory"]:
                flat_step = {
                    "episode_id": episode_id,
                    "phase": phase,
                    "step_index": step["step_index"],
                    "date": step["date"],
                    **self._flatten_dict(step["observation"], prefix="obs_"),
                    **self._flatten_dict(step["decision"], prefix="dec_"),
                    **self._flatten_dict(step["outcome"], prefix="out_")
                }
                flat_trajectory.append(flat_step)
                
            df = pd.DataFrame(flat_trajectory)
            parquet_path = os.path.join(self.log_dir, f"{episode_id}_{phase}_trajectory.parquet")
            df.to_parquet(parquet_path)
            
    def _flatten_dict(self, d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        items = {}
        for k, v in d.items():
            new_key = f"{prefix}{k}"
            if isinstance(v, dict):
                items.update(self._flatten_dict(v, new_key + "_"))
            else:
                items[new_key] = v
        return items
