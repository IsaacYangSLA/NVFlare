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
from nvflare.app_common.workflows.cross_site_model_eval import CrossSiteModelEval
from nvflare.app_opt.pt.file_model_locator import PTFileModelLocator
from nvflare.app_opt.pt.job_config.model import PTModel
from nvflare.client.config import ExchangeFormat
from nvflare.job_config.api import FedJob
from nvflare.job_config.script_runner import FrameworkType, ScriptRunner
from nvflare.recipe.spec import Recipe
from nvflare.recipe.utils import extract_persistor_id, prepare_initial_ckpt, recipe_model_to_job_model, validate_ckpt


# Internal validator
class _PTCrossSiteEvalValidator(BaseModel):
    name: str
    min_clients: int
    eval_script: str
    eval_args: str = ""
    launch_external_process: bool = True
    command: str = "python3 -u"
    initial_ckpt: Optional[str] = None
    submit_model_timeout: int = 600
    validation_timeout: int = 6000

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("initial_ckpt")
    @classmethod
    def validate_initial_ckpt(cls, v):
        if v is not None:
            validate_ckpt(v)
        return v


class PTCrossSiteEvalRecipe(Recipe):
    """Standalone cross-site evaluation recipe for PyTorch models.

    Creates a job that loads a pre-trained PyTorch checkpoint on the server and
    asks every client to evaluate every other client's model (and the server's
    global model) against its local data. The recipe wires up:

    - ``PTModel`` (registers a ``PTFileModelPersistor`` for the supplied
      ``nn.Module`` + ``initial_ckpt``).
    - ``PTFileModelLocator`` so the cross-site controller can enumerate the
      models held by the persistor.
    - ``CrossSiteModelEval`` controller.
    - ``ValidationJsonGenerator`` to dump per-pair metrics to JSON.
    - A client ``ScriptRunner`` bound to the ``validate`` and ``submit_model``
      tasks; the eval script must dispatch on ``flare.is_evaluate()`` /
      ``flare.is_submit_model()`` (the standard Client API pattern).

    Unlike :class:`nvflare.recipe.utils.add_cross_site_evaluation`, this recipe
    does not run any training first — it evaluates a model produced by an
    earlier job (or a hand-supplied checkpoint).

    Args:
        name: Job name. Defaults to ``"pt_cross_site_eval"``.
        model: ``nn.Module`` instance, or a dict config of the form
            ``{"class_path": "module.ClassName", "args": {...}}``. The model
            architecture is required because the checkpoint only stores the
            ``state_dict``.
        eval_ckpt: Path to a pre-trained checkpoint file (``.pt``, ``.pth``).
            Relative paths must exist locally — they are bundled into the job's
            custom directory. Absolute paths are interpreted server-side and do
            not need to exist on the machine building the job.
        min_clients: Minimum number of clients required to start the job.
            Defaults to 2.
        eval_script: Path to the client evaluation script (handles the
            ``validate`` and ``submit_model`` tasks).
        eval_args: CLI arguments forwarded to ``eval_script``. Defaults to ``""``.
        launch_external_process: Run the eval script in a separate process.
            Defaults to ``True`` (cross-site validation requires each
            evaluation to enter the Client API cleanly).
        command: Shell prefix when ``launch_external_process=True``.
            Defaults to ``"python3 -u"``.
        server_expected_format: Exchange format between server and clients.
            Defaults to :class:`ExchangeFormat.NUMPY`.
        submit_model_timeout: Seconds to wait for clients to send their
            local best models. Defaults to 600.
        validation_timeout: Seconds to wait for a single validation task.
            Defaults to 6000.
        participating_clients: Optional list of client names to include.
            ``None`` means all clients present at the start of the controller.
        client_memory_gc_rounds: Forwarded to :class:`ScriptRunner`.
        cuda_empty_cache: Forwarded to :class:`ScriptRunner`.

    Example::

        recipe = PTCrossSiteEvalRecipe(
            model=Net(),
            eval_ckpt="/abs/path/to/best_FL_global_model.pt",
            min_clients=2,
            eval_script="client_eval.py",
        )
        recipe.execute(SimEnv(num_clients=2))
    """

    def __init__(
        self,
        *,
        name: str = "pt_cross_site_eval",
        model: Union[Any, Dict[str, Any]],
        eval_ckpt: str,
        min_clients: int = 2,
        eval_script: str,
        eval_args: str = "",
        launch_external_process: bool = True,
        command: str = "python3 -u",
        server_expected_format: ExchangeFormat = ExchangeFormat.NUMPY,
        submit_model_timeout: int = 600,
        validation_timeout: int = 6000,
        participating_clients: Optional[list] = None,
        client_memory_gc_rounds: int = 0,
        cuda_empty_cache: bool = False,
    ):
        _PTCrossSiteEvalValidator(
            name=name,
            min_clients=min_clients,
            eval_script=eval_script,
            eval_args=eval_args,
            launch_external_process=launch_external_process,
            command=command,
            initial_ckpt=eval_ckpt,
            submit_model_timeout=submit_model_timeout,
            validation_timeout=validation_timeout,
        )

        # Normalize model: nn.Module instances pass through; dict configs go
        # through the same `class_path` → `path` rename other PT recipes use.
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
            raise ValueError("Failed to register PT persistor for cross-site evaluation")

        locator_id = job.to_server(PTFileModelLocator(pt_persistor_id=persistor_id), id="model_locator")

        job.to_server(
            CrossSiteModelEval(
                model_locator_id=locator_id,
                submit_model_timeout=submit_model_timeout,
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
        job.to_clients(
            executor,
            tasks=[AppConstants.TASK_VALIDATION, AppConstants.TASK_SUBMIT_MODEL],
        )

        # Declared so add_cross_site_evaluation can detect framework.
        self.framework = FrameworkType.PYTORCH
        self.name = name

        super().__init__(job)
