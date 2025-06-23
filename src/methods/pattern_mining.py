"""
Pattern mining methods for extracting frequent patterns from event graphs.
This module provides generic pattern mining algorithms that work with standardized data types.
"""

from typing import List, Set, Optional
from collections import defaultdict
from loguru import logger

from ..common.types import EventGraph, Pattern, PatternDict


class PatternMiner:
    """Generic pattern mining algorithms for event graphs."""

    def __init__(self, min_support: int = 1):
        """
        Initialize pattern miner.

        Args:
            min_support: Minimum support threshold for patterns
        """
        self.min_support = min_support

    def mine_edge_patterns(
        self, event_graphs: List[EventGraph], min_support: Optional[int] = None
    ) -> PatternDict:
        """
        Mine edge patterns (direct relationships) from event graphs.

        Args:
            event_graphs: List of event graphs to mine patterns from
            min_support: Override default minimum support threshold

        Returns:
            Dictionary mapping pattern keys to their support counts
        """
        min_sup = min_support if min_support is not None else self.min_support
        logger.info(
            f"Mining edge patterns from {len(event_graphs)} graphs with min_support={min_sup}"
        )

        pattern_support = defaultdict(int)

        for graph in event_graphs:
            graph_patterns = self._extract_edge_patterns_from_graph(graph)

            for pattern_key in graph_patterns:
                pattern_support[pattern_key] += 1

        # Filter by minimum support
        filtered_patterns = {
            pattern: support
            for pattern, support in pattern_support.items()
            if support >= min_sup
        }

        logger.info(
            f"Found {len(filtered_patterns)} edge patterns with min_support >= {min_sup}"
        )
        return filtered_patterns

    def mine_sequential_patterns(
        self,
        event_graphs: List[EventGraph],
        max_length: int = 3,
        min_support: Optional[int] = None,
    ) -> PatternDict:
        """
        Mine sequential patterns from event graphs.

        Args:
            event_graphs: List of event graphs
            max_length: Maximum sequence length to consider
            min_support: Override default minimum support threshold

        Returns:
            Dictionary mapping sequential pattern keys to support counts
        """
        min_sup = min_support if min_support is not None else self.min_support
        logger.info(f"Mining sequential patterns with max_length={max_length}")

        sequence_support = defaultdict(int)

        for graph in event_graphs:
            sequences = self._extract_sequences_from_graph(graph, max_length)

            for sequence in sequences:
                seq_key = "_".join(map(str, sequence))
                sequence_support[seq_key] += 1

        # Filter by minimum support
        filtered_sequences = {
            seq: support
            for seq, support in sequence_support.items()
            if support >= min_sup
        }

        logger.info(f"Found {len(filtered_sequences)} sequential patterns")
        return filtered_sequences

    def mine_subgraph_patterns(
        self,
        event_graphs: List[EventGraph],
        max_nodes: int = 4,
        min_support: Optional[int] = None,
    ) -> PatternDict:
        """
        Mine subgraph patterns from event graphs.

        Args:
            event_graphs: List of event graphs
            max_nodes: Maximum number of nodes in subgraph
            min_support: Override default minimum support threshold

        Returns:
            Dictionary mapping subgraph pattern keys to support counts
        """
        min_sup = min_support if min_support is not None else self.min_support
        logger.info(f"Mining subgraph patterns with max_nodes={max_nodes}")

        subgraph_support = defaultdict(int)

        for graph in event_graphs:
            subgraphs = self._extract_subgraphs_from_graph(graph, max_nodes)

            for subgraph_key in subgraphs:
                subgraph_support[subgraph_key] += 1

        # Filter by minimum support
        filtered_subgraphs = {
            pattern: support
            for pattern, support in subgraph_support.items()
            if support >= min_sup
        }

        logger.info(f"Found {len(filtered_subgraphs)} subgraph patterns")
        return filtered_subgraphs

    def _extract_edge_patterns_from_graph(self, graph: EventGraph) -> Set[str]:
        """Extract all edge patterns from a single graph."""
        patterns = set()

        for source_node, target_nodes in graph.adjacency_list.items():
            for target_node in target_nodes:
                pattern_key = f"{source_node.event_id}_{target_node.event_id}"
                patterns.add(pattern_key)

        return patterns

    def _extract_sequences_from_graph(
        self, graph: EventGraph, max_length: int
    ) -> List[List[int]]:
        """Extract sequences from graph based on timestamp ordering."""
        # Sort nodes by timestamp
        sorted_nodes = sorted(graph.nodes, key=lambda x: x.timestamp)

        sequences = []

        # Extract sequences of different lengths
        for start_idx in range(len(sorted_nodes)):
            for end_idx in range(
                start_idx + 1, min(start_idx + max_length, len(sorted_nodes))
            ):
                sequence = [
                    node.event_id for node in sorted_nodes[start_idx : end_idx + 1]
                ]
                sequences.append(sequence)

        return sequences

    def _extract_subgraphs_from_graph(
        self, graph: EventGraph, max_nodes: int
    ) -> Set[str]:
        """Extract connected subgraphs from graph."""
        subgraphs = set()

        # Use DFS to find connected subgraphs
        for start_node in graph.nodes:
            subgraph_nodes = self._dfs_subgraph(graph, start_node, max_nodes, set(), [])

            for nodes in subgraph_nodes:
                if len(nodes) >= 2:  # At least one edge
                    # Sort by event_id for canonical representation
                    sorted_ids = sorted([node.event_id for node in nodes])
                    subgraph_key = "_".join(map(str, sorted_ids))
                    subgraphs.add(subgraph_key)

        return subgraphs

    def _dfs_subgraph(
        self,
        graph: EventGraph,
        current_node,
        max_nodes: int,
        visited: Set,
        current_path: List,
    ) -> List[List]:
        """DFS to find subgraphs starting from current node."""
        if len(current_path) >= max_nodes:
            return [current_path.copy()]

        if current_node in visited:
            return [current_path.copy()] if current_path else []

        visited_copy = visited.copy()
        visited_copy.add(current_node)
        current_path.append(current_node)

        subgraphs = [current_path.copy()]

        # Explore neighbors
        for neighbor in graph.adjacency_list.get(current_node, []):
            if neighbor not in visited:
                neighbor_subgraphs = self._dfs_subgraph(
                    graph, neighbor, max_nodes, visited_copy, current_path.copy()
                )
                subgraphs.extend(neighbor_subgraphs)

        return subgraphs

    def convert_to_pattern_objects(self, pattern_dict: PatternDict) -> List[Pattern]:
        """Convert pattern dictionary to Pattern objects."""
        patterns = []

        for pattern_key, support in pattern_dict.items():
            pattern = Pattern.from_key(pattern_key, support)
            patterns.append(pattern)

        return patterns

    def filter_patterns_by_support(
        self, patterns: PatternDict, min_support: int
    ) -> PatternDict:
        """Filter patterns by minimum support threshold."""
        return {
            pattern: support
            for pattern, support in patterns.items()
            if support >= min_support
        }
