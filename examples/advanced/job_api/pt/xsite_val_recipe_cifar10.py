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

"""Recipe-based equivalent of fedavg_script_runner_xsite_val_cifar10.py.

This example combines two distinct workflows: FedAvg training and CrossSiteModelEval,
which evaluates the trained model on every client's local data. The non-recipe variant
wires SAG + persistor + locator + aggregator + shareable generator + cross-site
controller + ValidationJsonGenerator by hand. With recipes, training is FedAvgRecipe
and `add_cross_site_evaluation` appends the CSE workflow as a second stage.

The client script (src/cifar10_fl_partitioned.py) already branches on
``flare.is_evaluate()`` to handle the validation task, which is the contract the
cross-site eval workflow expects.
"""

# Reuse the data-splitting helper from the non-recipe sibling so the two examples
# operate on identical partitions.
from fedavg_script_runner_xsite_val_cifar10 import create_data_splits
from src.net import Net

from nvflare.app_opt.pt.recipes.fedavg import FedAvgRecipe
from nvflare.recipe import SimEnv, add_experiment_tracking
from nvflare.recipe.utils import add_cross_site_evaluation

if __name__ == "__main__":
    n_clients = 2
    num_rounds = 2
    alpha = 0.5
    data_split_root = f"/tmp/nvflare/data/cifar10_splits/clients{n_clients}_alpha{alpha}"

    create_data_splits(data_split_root, n_clients, alpha)

    recipe = FedAvgRecipe(
        name="cifar10_fedavg_xsite_val",
        min_clients=n_clients,
        num_rounds=num_rounds,
        model=Net(),
        train_script="src/cifar10_fl_partitioned.py",
        train_args=f"--data_split_path {data_split_root}",
        # CSE requires validation to run in a separate process so the client API
        # context can be re-entered for each evaluation task.
        launch_external_process=True,
        key_metric="accuracy",
    )

    add_experiment_tracking(recipe, tracking_type="tensorboard")
    add_cross_site_evaluation(recipe)

    env = SimEnv(
        num_clients=n_clients,
        workspace_root="/tmp/nvflare/jobs/workdir/pt_xsite_val_recipe",
        gpu_config="0",
    )

    run = recipe.execute(env)
    print("Job Status:", run.get_status())
    print("Results at:", run.get_result())
