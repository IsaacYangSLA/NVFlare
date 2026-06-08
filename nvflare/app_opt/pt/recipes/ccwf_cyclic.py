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

from nvflare.app_common.ccwf.ccwf_job import CCWFJob, CrossSiteEvalConfig, CyclicClientConfig, CyclicServerConfig
from nvflare.app_common.ccwf.comps.simple_model_shareable_generator import SimpleModelShareableGenerator
from nvflare.app_opt.pt.file_model_persistor import PTFileModelPersistor
from nvflare.job_config.script_runner import ScriptRunner
from nvflare.recipe.spec import Recipe
from nvflare.recipe.utils import prepare_initial_ckpt, recipe_model_to_job_model, validate_ckpt


class _CCWFCyclicValidator(BaseModel):
    name: str
    num_rounds: int
    min_clients: int
    train_script: str
    initial_ckpt: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("initial_ckpt")
    @classmethod
    def validate_initial_ckpt(cls, v):
        if v is not None:
            validate_ckpt(v)
        return v


class CCWFCyclicRecipe(Recipe):
    """Client-Controlled Cyclic federated learning recipe for PyTorch.

    Wraps :meth:`CCWFJob.add_cyclic` so clients hand the model to each other in
    a ring without going through the server every round — the server's role
    reduces to coordination (round counting, status, optional cross-site eval).
    Compared with the controller-side :class:`CyclicRecipe`
    (``nvflare.app_opt.pt.recipes.cyclic.CyclicRecipe``) the server never
    touches the model weights; the persistor lives on each client.

    Mirrors :class:`SwarmLearningRecipe`'s shape (same persistor / shareable
    generator wiring), just with cyclic instead of swarm semantics.

    Args:
        name: Job name. Defaults to ``"ccwf_cyclic"``.
        model: ``nn.Module`` instance or
            ``{"class_path": "module.ClassName", "args": {...}}`` config.
        num_rounds: Number of cyclic rounds (one round = one full pass
            around the ring of clients).
        train_script: Path to the client training script.
        min_clients: Minimum number of clients required.
        initial_ckpt: Optional checkpoint to bootstrap from. Relative paths
            are bundled into the job's custom directory; absolute paths are
            interpreted at runtime on the server.
        train_args: CLI arguments for ``train_script``.
        launch_external_process: Run the train script in a subprocess.
        command: Shell prefix used when ``launch_external_process=True``.
        starting_client: Name of the client that begins the ring. Empty
            string means the server picks (typically alphabetical).
        cyclic_order: Order policy; one of the ``CyclicOrder`` constants.
            Defaults to ``"fixed"``.
        do_cross_site_eval: Append a CCWF cross-site eval phase after training.
        cross_site_eval_timeout: Per-evaluation timeout.
        max_status_report_interval: Max seconds between client status reports.
        progress_timeout: Seconds with no progress before declaring stall.
        memory_gc_rounds: Forwarded to :class:`ScriptRunner`.
        cuda_empty_cache: Forwarded to :class:`ScriptRunner`.
    """

    def __init__(
        self,
        *,
        name: str = "ccwf_cyclic",
        model: Union[Any, Dict[str, Any]],
        num_rounds: int,
        train_script: str,
        min_clients: int,
        initial_ckpt: Optional[str] = None,
        train_args: str = "",
        launch_external_process: bool = False,
        command: str = "python3 -u",
        starting_client: str = "",
        cyclic_order: str = "fixed",
        do_cross_site_eval: bool = False,
        cross_site_eval_timeout: float = 300,
        max_status_report_interval: float = 300,
        progress_timeout: float = 3600,
        memory_gc_rounds: int = 1,
        cuda_empty_cache: bool = False,
    ):
        _CCWFCyclicValidator(
            name=name,
            num_rounds=num_rounds,
            min_clients=min_clients,
            train_script=train_script,
            initial_ckpt=initial_ckpt,
        )

        if isinstance(model, dict):
            model = recipe_model_to_job_model(model)

        job = CCWFJob(name=name, min_clients=min_clients)
        ckpt_path = prepare_initial_ckpt(initial_ckpt, job)

        server_config = CyclicServerConfig(
            num_rounds=num_rounds,
            starting_client=starting_client,
            max_status_report_interval=max_status_report_interval,
            progress_timeout=progress_timeout,
            cyclic_order=cyclic_order,
        )

        client_config = CyclicClientConfig(
            executor=ScriptRunner(
                script=train_script,
                script_args=train_args,
                launch_external_process=launch_external_process,
                command=command,
                memory_gc_rounds=memory_gc_rounds,
                cuda_empty_cache=cuda_empty_cache,
            ),
            persistor=PTFileModelPersistor(model=model, source_ckpt_file_full_name=ckpt_path),
            shareable_generator=SimpleModelShareableGenerator(),
        )

        cse_config = CrossSiteEvalConfig(eval_task_timeout=cross_site_eval_timeout) if do_cross_site_eval else None

        job.add_cyclic(server_config=server_config, client_config=client_config, cse_config=cse_config)

        self.name = name
        super().__init__(job)
