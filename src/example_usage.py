"""
Example usage of the refactored Nezha system.
This demonstrates how to use the preprocessing and methods modules together.
"""

from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from loguru import logger

# Import common types
from .common.types import (
    TimeWindow,
    EventGraph,
    AlarmEvent,
    RankedPattern,
    AnalysisResult,
)

# Import preprocessing modules
from .preprocessing import LogParser, DataLoader, EventGraphBuilder

# Import analysis methods
from .methods import PatternMiner, PatternRanker, AlarmDetector, Evaluator


class NezhaPipeline:
    """Complete Nezha analysis pipeline combining preprocessing and methods."""

    def __init__(
        self,
        data_root_path: str,
        log_template_config: str,
        log_template_persistence: str,
        namespace: str = "default",
    ):
        """
        Initialize Nezha pipeline.

        Args:
            data_root_path: Root directory containing data files
            log_template_config: Path to Drain3 configuration file
            log_template_persistence: Path to template persistence file
            namespace: Namespace for processing (hipster, ts, etc.)
        """
        self.namespace = namespace

        # Initialize preprocessing components
        self.log_parser = LogParser(
            config_file=log_template_config, persistence_file=log_template_persistence
        )
        self.data_loader = DataLoader(data_root_path)
        self.event_graph_builder = EventGraphBuilder(self.log_parser)

        # Initialize analysis methods
        self.pattern_miner = PatternMiner(min_support=5)
        self.pattern_ranker = PatternRanker(min_score=0.67, min_support=5)
        self.alarm_detector = AlarmDetector()
        self.evaluator = Evaluator()

        logger.info(f"Initialized Nezha pipeline for namespace: {namespace}")

    def process_time_window(
        self, timestamp: str, include_alarms: bool = True
    ) -> tuple[List[EventGraph], List[AlarmEvent]]:
        """
        Process data for a single time window.

        Args:
            timestamp: Timestamp in format "YYYY-MM-DD HH:MM"
            include_alarms: Whether to detect and include alarms

        Returns:
            Tuple of (event_graphs, alarms)
        """
        time_window = TimeWindow.from_timestamp(timestamp)
        logger.info(f"Processing time window: {timestamp}")

        # Load data
        trace_df, log_df, trace_ids, missing_files = (
            self.data_loader.load_time_window_data(time_window)
        )

        if missing_files:
            logger.warning(f"Missing files for {timestamp}: {missing_files}")

        # Detect alarms if requested
        alarms = []
        if include_alarms and trace_df is not None:
            metrics = self.data_loader.load_metric_data(time_window, timestamp)
            if metrics:
                alarms = self.alarm_detector.detect_alarms(metrics, self.namespace)

        # Build event graphs
        event_graphs = []
        if trace_df is not None and log_df is not None and len(trace_ids) > 0:
            # Type checker needs help understanding these are not None after the check
            assert trace_df is not None and log_df is not None
            event_graphs = self.event_graph_builder.build_event_graphs(
                trace_df, log_df, trace_ids, alarms, self.namespace
            )

        logger.info(
            f"Generated {len(event_graphs)} event graphs and {len(alarms)} alarms"
        )
        return event_graphs, alarms

    def extract_patterns(
        self, event_graphs: List[EventGraph], pattern_type: str = "edge"
    ) -> Dict[str, int]:
        """
        Extract patterns from event graphs.

        Args:
            event_graphs: List of event graphs
            pattern_type: Type of patterns to extract ("edge", "sequential", "subgraph")

        Returns:
            Dictionary mapping pattern keys to support counts
        """
        logger.info(
            f"Extracting {pattern_type} patterns from {len(event_graphs)} graphs"
        )

        if pattern_type == "edge":
            return self.pattern_miner.mine_edge_patterns(event_graphs)
        elif pattern_type == "sequential":
            return self.pattern_miner.mine_sequential_patterns(event_graphs)
        elif pattern_type == "subgraph":
            return self.pattern_miner.mine_subgraph_patterns(event_graphs)
        else:
            raise ValueError(f"Unknown pattern type: {pattern_type}")

    def rank_patterns(
        self,
        normal_patterns: Dict[str, int],
        abnormal_patterns: Dict[str, int],
        event_graphs: List[EventGraph],
        alarms: List[AlarmEvent],
    ) -> List[RankedPattern]:
        """
        Rank patterns by comparing normal and abnormal frequencies.

        Args:
            normal_patterns: Patterns from normal time periods
            abnormal_patterns: Patterns from abnormal time periods
            event_graphs: Event graphs for depth calculation
            alarms: Alarms for association

        Returns:
            List of ranked patterns
        """
        logger.info("Ranking patterns")

        # Define helper functions for ranking
        def template_resolver(event_id: int) -> str:
            return self.log_parser.get_template(event_id)

        def depth_calculator(graphs: List[EventGraph], pattern_key: str) -> tuple:
            source_id, _ = self.pattern_ranker._parse_pattern_key(pattern_key)
            max_depth, pod = 0, "unknown"

            for graph in graphs:
                depth, graph_pod = graph.get_deepth_pod(source_id)
                if depth > max_depth:
                    max_depth = depth
                    pod = graph_pod

            return max_depth, pod

        def alarm_associator(
            pattern_key: str, pod: str, alarm_list: List[AlarmEvent]
        ) -> tuple:
            for alarm in alarm_list:
                if alarm.pod == pod:
                    return True, alarm
            return False, None

        return self.pattern_ranker.rank_patterns(
            normal_patterns=normal_patterns,
            abnormal_patterns=abnormal_patterns,
            event_graphs=event_graphs,
            alarms=alarms,
            template_resolver=template_resolver,
            depth_calculator=depth_calculator,
            alarm_associator=alarm_associator,
        )

    def run_complete_analysis(
        self,
        normal_timestamps: List[str],
        abnormal_timestamps: List[str],
        ground_truth_file: Optional[str] = None,
    ) -> AnalysisResult:
        """
        Run complete Nezha analysis.

        Args:
            normal_timestamps: List of normal time periods
            abnormal_timestamps: List of abnormal time periods
            ground_truth_file: Optional ground truth file for evaluation

        Returns:
            Complete analysis results
        """
        logger.info("Running complete Nezha analysis")

        # Extract normal patterns
        logger.info("Processing normal time periods")
        normal_patterns = {}
        normal_event_graphs = []

        for timestamp in normal_timestamps:
            graphs, _ = self.process_time_window(timestamp, include_alarms=False)
            normal_event_graphs.extend(graphs)

            patterns = self.extract_patterns(graphs)
            for pattern_key, support in patterns.items():
                normal_patterns[pattern_key] = (
                    normal_patterns.get(pattern_key, 0) + support
                )

        # Process abnormal periods
        logger.info("Processing abnormal time periods")
        all_ranked_patterns = []
        all_alarms = []

        for timestamp in abnormal_timestamps:
            graphs, alarms = self.process_time_window(timestamp, include_alarms=True)
            abnormal_patterns = self.extract_patterns(graphs)

            ranked_patterns = self.rank_patterns(
                normal_patterns, abnormal_patterns, normal_event_graphs, alarms
            )

            all_ranked_patterns.extend(ranked_patterns)
            all_alarms.extend(alarms)

        # Create result object (use current time as analysis time)
        result = AnalysisResult(
            ranked_patterns=all_ranked_patterns,
            event_graphs=normal_event_graphs,
            alarms=all_alarms,
            analysis_time=datetime.now(),
            metadata={
                "namespace": self.namespace,
                "normal_periods": len(normal_timestamps),
                "abnormal_periods": len(abnormal_timestamps),
                "total_normal_patterns": len(normal_patterns),
            },
        )

        # Run evaluation if ground truth provided
        if ground_truth_file:
            ground_truth = self.evaluator.load_ground_truth_from_file(ground_truth_file)
            if ground_truth:
                metrics = self.evaluator.evaluate_ranking_performance(
                    all_ranked_patterns, ground_truth
                )
                result.metadata["evaluation_metrics"] = metrics

        logger.info("Analysis complete")
        return result


def create_example_config() -> Dict:
    """Create example configuration for different namespaces."""
    base_path = Path(__file__).parent.parent

    return {
        "hipster": {
            "data_path": str(base_path / "rca_data"),
            "log_config": str(base_path / "log_template" / "drain3_hipster.ini"),
            "log_persistence": str(base_path / "log_template" / "hipster.bin"),
            "normal_times": ["2022-08-22 03:51", "2022-08-23 17:00"],
            "fault_files": [
                str(
                    base_path / "rca_data" / "2022-08-22" / "2022-08-22-fault_list.json"
                ),
                str(
                    base_path / "rca_data" / "2022-08-23" / "2022-08-23-fault_list.json"
                ),
            ],
        },
        "ts": {
            "data_path": str(base_path / "rca_data"),
            "log_config": str(base_path / "log_template" / "drain3_ts.ini"),
            "log_persistence": str(base_path / "log_template" / "ts.bin"),
            "normal_times": ["2023-01-29 08:50", "2023-01-30 11:39"],
            "fault_files": [
                str(
                    base_path / "rca_data" / "2023-01-29" / "2023-01-29-fault_list.json"
                ),
                str(
                    base_path / "rca_data" / "2023-01-30" / "2023-01-30-fault_list.json"
                ),
            ],
        },
    }


def main():
    config = create_example_config()
    namespace = "ts"

    ns_config = config[namespace]

    pipeline = NezhaPipeline(
        data_root_path=ns_config["data_path"],
        log_template_config=ns_config["log_config"],
        log_template_persistence=ns_config["log_persistence"],
        namespace=namespace,
    )

    # Run analysis
    result = pipeline.run_complete_analysis(
        normal_timestamps=ns_config["normal_times"],
        abnormal_timestamps=["2022-08-22 03:53"],  # Example abnormal time
        ground_truth_file=ns_config["fault_files"][0],
    )

    # Display results
    logger.info(f"Analysis complete with {len(result.ranked_patterns)} ranked patterns")

    top_patterns = result.get_top_patterns(k=5)
    for i, pattern in enumerate(top_patterns, 1):
        logger.info(f"{i}. {pattern.pattern.pattern_key} (score: {pattern.score:.3f})")


if __name__ == "__main__":
    main()
