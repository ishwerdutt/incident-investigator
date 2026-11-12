"""Drain3 template extraction wrapper."""

from __future__ import annotations

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from incident_investigator.models import TemplateCluster


class TemplateExtractor:
    """Thin wrapper around drain3's TemplateMiner for log clustering."""

    def __init__(self) -> None:
        config = TemplateMinerConfig()
        config.drain_sim_th = 0.4
        config.drain_depth = 4
        config.drain_max_children = 100
        # Use in-memory persistence (no files)
        config.profiling_enabled = False
        self._miner = TemplateMiner(config=config)

    def add_log_message(self, message: str) -> str:
        """Feed *message* to drain3 and return the cluster/template ID string."""
        result = self._miner.add_log_message(message)
        return str(result["cluster_id"])

    def get_templates(self) -> list[TemplateCluster]:
        """Return all current template clusters as ``TemplateCluster`` model objects."""
        clusters: list[TemplateCluster] = []
        for cluster in self._miner.drain.clusters:
            clusters.append(
                TemplateCluster(
                    template_id=str(cluster.cluster_id),
                    pattern=cluster.get_template(),
                    total_count=cluster.size,
                    sample_message=cluster.log_template_tokens[0] if cluster.log_template_tokens else "",
                )
            )
        return clusters
