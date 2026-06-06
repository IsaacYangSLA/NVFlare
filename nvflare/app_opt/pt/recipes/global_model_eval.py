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

from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, field_validator

from nvflare.app_common.app_constant import AppConstants
from nvflare.app_common.widgets.validation_json_generator import ValidationJsonGenerator
from nvflare.app_common.workflows.global_model_eval import GlobalModelEval
from nvflare.app_opt.pt.file_model_locator import PTFileModelLocator
from nvflare.app_opt.pt.job_config.model import PTModel
from nvflare.client.config import ExchangeFormat
from nvflare.job_config.api import FedJob
from nvflare.job_config.script_runner import FrameworkType, ScriptRunner
from nvflare.recipe.spec import Recipe
from nvflare.recipe.utils import (
    extract_persistor_id,
    prepare_initial_ckpt,
    recipe_model_to_job_model,
    validate_ckpt,
)


class _GlobalModelEvalValidator(BaseModel):
    name: str
    min_clients: int
    eval_script: str
    eval_args: str = ""
    launch_external_process: bool = True
    command: str = "python3 -u"
    eval_ckpt: str
    validation_timeout: int = 6000

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("eval_ckpt")
    @classmethod
    def validate_eval_ckpt(cls, v):
        validate_ckpt(v)
        return v


class GlobalModelEvalRecipe(Recipe):
    """Recipe wrapping the ``GlobalModelEval`` workflow for PyTorch.

    ``GlobalModelEval`` is the "one-direction" sibling of cross-site model
    evaluation: the server distributes a single global model to every client,
    each client evaluates it on its local data, and per-client metrics are
    collected. Unlike ``CrossSiteModelEval`` it does **not** ask clients to
    submit their own models — there is no all-pairs matrix, just
    "server-model-vs-each-client".

    Use this when you want a single, lightweight federated-evaluation pass on
    a pre-trained checkpoint (e.g. the final FedAvg global model) without the
    cost of cross-site validation.

    Args:
        name: Job name. Defaults to ``"global_model_eval"``.
        model: ``nn.Module`` instance or
            ``{"class_path": "module.ClassName", "args": {...}}`` config.
        eval_ckpt: Absolute path to the checkpoint to evaluate.
        min_clients: Minimum number of clients required. Defaults to 2.
        eval_script: Path to the client eval script (handles the ``validate``
            task via the Client API ``flare.is_evaluate()`` pattern).
        eval_args: CLI arguments for ``eval_script``.
        launch_external_process: Run the eval script in a subprocess.
            Defaults to ``True``.
        command: Shell prefix used when launching externally.
        server_expected_format: Exchange format between server and clients.
        validation_timeout: Per-task timeout in seconds. Defaults to 6000.
        participating_clients: Optional list of client names to include;
            ``None`` means all clients connected when the controller starts.
        client_memory_gc_rounds: Forwarded to :class:`ScriptRunner`.
        cuda_empty_cache: Forwarded to :class:`ScriptRunner`.
    """

    def __init__(
        self,
        *,
        name: str = "global_model_eval",
        model: Union[Any, Dict[str, Any]],
        eval_ckpt: str,
        min_clients: int = 2,
        eval_script: str,
        eval_args: str = "",
        launch_external_process: bool = True,
        command: str = "python3 -u",
        server_expected_format: ExchangeFormat = ExchangeFormat.NUMPY,
        validation_timeout: int = 6000,
        participating_clients: Optional[list] = None,
        client_memory_gc_rounds: int = 0,
        cuda_empty_cache: bool = False,
    ):
        _GlobalModelEvalValidator(
            name=name,
            min_clients=min_clients,
            eval_script=eval_script,
            eval_args=eval_args,
            launch_external_process=launch_external_process,
            command=command,
            eval_ckpt=eval_ckpt,
            validation_timeout=validation_timeout,
        )

        if isinstance(model, dict):
            model = recipe_model_to_job_model(model)

        job = FedJob(name=name, min_clients=min_clients)

        ckpt_path = prepare_initial_ckpt(eval_ckpt, job)
        pt_model = PTModel(model=model, initial_ckpt=ckpt_path)
        result = job.to_server(pt_model, id="persistor")
        if isinstance(result, dict) and hasattr(job, "comp_ids"):
            job.comp_ids.update(result)
        persistor_id = extract_persistor_id(result)
        if not persistor_id:
            raise RuntimeError("Failed to register PT persistor for global model evaluation")

        locator_id = job.to_server(PTFileModelLocator(pt_persistor_id=persistor_id), id="model_locator")

        # GlobalModelEval requires model_locator_id; it does not submit_model.
        job.to_server(
            GlobalModelEval(
                model_locator_id=locator_id,
                validation_timeout=validation_timeout,
                participating_clients=participating_clients,
            )
        )

        job.to_server(ValidationJsonGenerator())

        executor = ScriptRunner(
            script=eval_script,
            script_args=eval_args,
            launch_external_process=launch_external_process,
            command=command,
            framework=FrameworkType.PYTORCH,
            server_expected_format=server_expected_format,
            memory_gc_rounds=client_memory_gc_rounds,
            cuda_empty_cache=cuda_empty_cache,
        )
        job.to_clients(executor, tasks=[AppConstants.TASK_VALIDATION])

        self.framework = FrameworkType.PYTORCH
        self.name = name

        super().__init__(job)
