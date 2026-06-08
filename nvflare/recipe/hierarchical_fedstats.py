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

import os
from typing import Any, Dict, List

from nvflare.app_common.abstract.statistics_spec import Statistics
from nvflare.app_common.workflows.hierarchical_statistics_controller import HierarchicalStatisticsController
from nvflare.job_config.stats_job import StatsJob
from nvflare.recipe.spec import Recipe


class _HierarchicalStatsJob(StatsJob):
    """StatsJob variant that swaps the controller for HierarchicalStatisticsController.

    Mirrors ``StatsJob.get_stats_controller`` — only the controller class
    and the extra ``hierarchy_config`` parameter differ.
    """

    def __init__(self, *args, hierarchy_config: str, **kwargs):
        self.hierarchy_config = hierarchy_config
        super().__init__(*args, **kwargs)

    def get_stats_controller(self):
        return HierarchicalStatisticsController(
            statistic_configs=self.statistic_configs,
            writer_id=self.writer_id,
            enable_pre_run_task=False,
            hierarchy_config=self.hierarchy_config,
        )


class HierarchicalFedStatsRecipe(Recipe):
    """Federated statistics with hierarchical aggregation.

    Equivalent to :class:`FedStatsRecipe` but uses
    :class:`HierarchicalStatisticsController` on the server, which folds the
    per-site results into a tree (e.g. site → region → country) defined by
    ``hierarchy_config``. The leaves of the hierarchy are individual client
    sites; the controller emits aggregated statistics at every interior node.

    Args:
        name: Job name.
        stats_output_path: Output path on the server for the global stats JSON.
        sites: Client site names that participate. These must match the
            leaf names referenced in ``hierarchy_config``.
        statistic_configs: Same shape as :class:`FedStatsRecipe` —
            ``{"count": {}, "mean": {}, "histogram": {"*": {"bins": 20}}}``.
        stats_generator: A :class:`Statistics` implementation that computes
            local statistics on each client.
        hierarchy_config: Path to a JSON file describing the client hierarchy.
            The file is bundled into the server app's custom directory so it
            is available at runtime; it must exist locally at construction time.
        min_count: Minimum sample count required before a stat is reported.
        min_noise_level / max_noise_level: Noise bounds applied to
            min/max values before they leave the client (privacy filter).
        max_bins_percent: Maximum bin count, as percentage of sample count,
            for histograms (privacy filter).
    """

    def __init__(
        self,
        name: str,
        stats_output_path: str,
        sites: List[str],
        statistic_configs: Dict[str, Any],
        stats_generator: Statistics,
        hierarchy_config: str,
        min_count: int = 10,
        min_noise_level: float = 0.1,
        max_noise_level: float = 0.3,
        max_bins_percent: float = 10,
    ):
        if not sites:
            raise ValueError("sites must be a non-empty list of client names")
        if not isinstance(hierarchy_config, str) or not hierarchy_config:
            raise ValueError("hierarchy_config must be a non-empty path to a JSON file")
        if not os.path.isfile(hierarchy_config):
            raise FileNotFoundError(f"hierarchy_config not found: {hierarchy_config}")

        # The controller reads hierarchy_config by relative path at runtime, so
        # we ship the file via job's custom dir under its basename.
        hierarchy_basename = os.path.basename(hierarchy_config)

        job = _HierarchicalStatsJob(
            name=name,
            statistic_configs=statistic_configs,
            stats_generator=stats_generator,
            output_path=stats_output_path,
            min_count=min_count,
            min_noise_level=min_noise_level,
            max_noise_level=max_noise_level,
            max_bins_percent=max_bins_percent,
            hierarchy_config=hierarchy_basename,
        )

        # Bundle the hierarchy file into the server app.
        job.to_server(hierarchy_config)

        job.setup_clients(sites)

        super().__init__(job)
