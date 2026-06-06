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

import json

import pytest

from nvflare.app_common.abstract.statistics_spec import Statistics


class _StubGenerator(Statistics):
    def initialize(self, fl_ctx):
        pass

    def pre_run(self, statistics, num_of_bins, bin_ranges):
        pass

    def features(self):
        return {}

    def count(self, dataset_name, feature_name):
        return 0


@pytest.fixture
def hierarchy_file(tmp_path):
    path = tmp_path / "hierarchy.json"
    path.write_text(
        json.dumps({"name": "global", "children": [{"name": "r1", "children": ["site-1", "site-2"]}]})
    )
    return str(path)


def test_hierarchical_fedstats_recipe_uses_hierarchical_controller(hierarchy_file):
    from nvflare.recipe.hierarchical_fedstats import HierarchicalFedStatsRecipe

    recipe = HierarchicalFedStatsRecipe(
        name="hier_stats_job",
        stats_output_path="stats.json",
        sites=["site-1", "site-2"],
        statistic_configs={"count": {}, "mean": {}},
        stats_generator=_StubGenerator(),
        hierarchy_config=hierarchy_file,
    )
    server_app = recipe.job._deploy_map["server"]
    workflow_names = [type(getattr(w, "controller", w)).__name__ for w in server_app.app_config.workflows]
    assert workflow_names == ["HierarchicalStatisticsController"]
    assert "site-1" in recipe.job._deploy_map
    assert "site-2" in recipe.job._deploy_map


def test_hierarchy_file_missing_raises(tmp_path):
    from nvflare.recipe.hierarchical_fedstats import HierarchicalFedStatsRecipe

    with pytest.raises(FileNotFoundError):
        HierarchicalFedStatsRecipe(
            name="hier_stats_job",
            stats_output_path="stats.json",
            sites=["site-1"],
            statistic_configs={"count": {}},
            stats_generator=_StubGenerator(),
            hierarchy_config=str(tmp_path / "missing.json"),
        )
