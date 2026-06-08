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

"""Recipe-based equivalent of cyclic_cc_script_runner_cifar10.py.

The non-recipe variant wires CCWFJob, CyclicServerConfig, CyclicClientConfig,
PTFileModelPersistor, SimpleModelShareableGenerator, and a ScriptRunner by hand,
then calls job.simulator_run(). CCWFCyclicRecipe collapses that wiring into a
single declarative object; SimEnv runs it.

Key difference from controller-side CyclicRecipe: the server never touches the
model weights.  The persistor lives on each client and clients pass the model
directly around the ring.  The server's only role is round counting and
coordination.

TensorBoard tracking is added client-side because CCWFJob does not include a
ConvertToFedEvent bridge.  Each client writes its own TensorBoard logs locally.
"""

from src.net import Net

from nvflare.app_opt.pt.recipes.ccwf_cyclic import CCWFCyclicRecipe
from nvflare.recipe import SimEnv, add_experiment_tracking

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 3

    recipe = CCWFCyclicRecipe(
        name="cifar10_cyclic_cc",
        min_clients=n_clients,
        num_rounds=num_rounds,
        model=Net(),
        train_script="src/cifar10_fl.py",
    )

    add_experiment_tracking(recipe, tracking_type="tensorboard", client_side=True, server_side=False)

    env = SimEnv(
        num_clients=n_clients,
        workspace_root="/tmp/nvflare/jobs/workdir/pt_cyclic_cc_recipe",
        gpu_config="0",
    )

    run = recipe.execute(env)
    print("Job Status:", run.get_status())
    print("Results at:", run.get_result())
