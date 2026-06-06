# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Smoke tests for newly added recipes covering workflows that previously had none."""

import os

import pytest
import torch
import torch.nn as nn


class TinyNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc = nn.Linear(4, 2)


@pytest.fixture
def ckpt_file(tmp_path):
    path = tmp_path / "ckpt.pt"
    torch.save({"fc.weight": torch.zeros(2, 4), "fc.bias": torch.zeros(2)}, path)
    return str(path)


@pytest.fixture
def eval_script(tmp_path, monkeypatch):
    script = tmp_path / "eval.py"
    script.write_text("# stub")
    monkeypatch.chdir(tmp_path)
    return "eval.py"


@pytest.fixture
def train_script(tmp_path, monkeypatch):
    script = tmp_path / "train.py"
    script.write_text("# stub")
    monkeypatch.chdir(tmp_path)
    return "train.py"


def _server_workflow_names(recipe):
    server_app = recipe.job._deploy_map["server"]
    return [type(getattr(w, "controller", w)).__name__ for w in server_app.app_config.workflows]


class TestPTCrossSiteEvalRecipe:
    def test_constructs_and_wires_cross_site_model_eval(self, ckpt_file, eval_script):
        from nvflare.app_opt.pt.recipes.cross_site_eval import PTCrossSiteEvalRecipe

        recipe = PTCrossSiteEvalRecipe(
            model=TinyNet(),
            eval_ckpt=ckpt_file,
            min_clients=2,
            eval_script=eval_script,
        )
        assert _server_workflow_names(recipe) == ["CrossSiteModelEval"]
        from nvflare.job_config.script_runner import FrameworkType

        assert recipe.framework == FrameworkType.PYTORCH

    def test_dict_config_model_accepted(self, ckpt_file, eval_script):
        from nvflare.app_opt.pt.recipes.cross_site_eval import PTCrossSiteEvalRecipe

        recipe = PTCrossSiteEvalRecipe(
            model={
                "class_path": f"{TinyNet.__module__}.TinyNet",
                "args": {},
            },
            eval_ckpt=ckpt_file,
            min_clients=2,
            eval_script=eval_script,
        )
        assert _server_workflow_names(recipe) == ["CrossSiteModelEval"]

    def test_missing_relative_eval_ckpt_rejected(self, eval_script):
        """Relative ckpt paths must exist locally so they can be bundled into the job."""
        from nvflare.app_opt.pt.recipes.cross_site_eval import PTCrossSiteEvalRecipe

        with pytest.raises(Exception):
            PTCrossSiteEvalRecipe(
                model=TinyNet(),
                eval_ckpt="missing_relative_ckpt.pt",
                min_clients=2,
                eval_script=eval_script,
            )


class TestGlobalModelEvalRecipe:
    def test_constructs_and_wires_global_model_eval(self, ckpt_file, eval_script):
        from nvflare.app_opt.pt.recipes.global_model_eval import GlobalModelEvalRecipe

        recipe = GlobalModelEvalRecipe(
            model=TinyNet(),
            eval_ckpt=ckpt_file,
            min_clients=2,
            eval_script=eval_script,
        )
        assert _server_workflow_names(recipe) == ["GlobalModelEval"]

    def test_no_submit_model_task_on_clients(self, ckpt_file, eval_script):
        """GlobalModelEval differs from CrossSiteModelEval by not asking clients to submit their own models."""
        from nvflare.app_opt.pt.recipes.global_model_eval import GlobalModelEvalRecipe

        recipe = GlobalModelEvalRecipe(
            model=TinyNet(),
            eval_ckpt=ckpt_file,
            min_clients=2,
            eval_script=eval_script,
        )
        client_app = recipe.job._deploy_map["@ALL"]
        executors = client_app.app_config.executors
        assigned_tasks = set()
        for ex in executors:
            tasks = getattr(ex, "tasks", None) or []
            assigned_tasks.update(tasks)
        assert "validate" in assigned_tasks
        assert "submit_model" not in assigned_tasks


class TestCCWFCyclicRecipe:
    def test_constructs_cyclic_workflow_on_server(self, train_script):
        from nvflare.app_opt.pt.recipes.ccwf_cyclic import CCWFCyclicRecipe

        recipe = CCWFCyclicRecipe(
            model=TinyNet(),
            num_rounds=2,
            min_clients=2,
            train_script=train_script,
        )
        assert _server_workflow_names(recipe) == ["CyclicServerController"]

    def test_cross_site_eval_appends_second_workflow(self, train_script):
        from nvflare.app_opt.pt.recipes.ccwf_cyclic import CCWFCyclicRecipe

        recipe = CCWFCyclicRecipe(
            model=TinyNet(),
            num_rounds=2,
            min_clients=2,
            train_script=train_script,
            do_cross_site_eval=True,
        )
        assert _server_workflow_names(recipe) == [
            "CyclicServerController",
            "CrossSiteEvalServerController",
        ]
