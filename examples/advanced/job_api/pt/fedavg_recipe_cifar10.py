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

"""Recipe-based equivalent of fedavg_script_runner_cifar10.py.

The non-recipe variant wires up FedJob, FedAvg, PTModel, IntimeModelSelector,
TBAnalyticsReceiver and a ScriptRunner per client by hand. FedAvgRecipe
collapses all of that into a single declarative object: the recipe builds the
job, the SimEnv runs it.
"""

from src.net import Net

from nvflare.app_opt.pt.recipes.fedavg import FedAvgRecipe
from nvflare.recipe import SimEnv, add_experiment_tracking

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 2

    recipe = FedAvgRecipe(
        name="cifar10_fedavg",
        min_clients=n_clients,
        num_rounds=num_rounds,
        model=Net(),
        train_script="src/cifar10_fl.py",
        key_metric="accuracy",
    )

    add_experiment_tracking(recipe, tracking_type="tensorboard")

    env = SimEnv(
        num_clients=n_clients,
        workspace_root="/tmp/nvflare/jobs/workdir/pt_recipe",
        gpu_config="0",
    )

    run = recipe.execute(env)
    print("Job Status:", run.get_status())
    print("Results at:", run.get_result())
