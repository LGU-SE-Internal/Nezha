"""
Data structures for Nezha algorithm.

Defines enhanced event patterns and data structures that integrate with rcabench_platform.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from rcabench_platform.v2.logging import logger


@dataclass
class EnhancedEventPattern:
    """
    Enhanced event pattern representation.

    Attributes:
        pattern: Unique tuple representation (source_event_id, target_event_id)
        count: Number of occurrences of this pattern in the trace
        depth: Depth of the pattern in the span hierarchy
        service: Service name (string)
    """

    pattern: Tuple[int, int]
    count: int
    depth: int
    service: str

    def __hash__(self) -> int:
        return hash(self.pattern)

    def __eq__(self, other) -> bool:
        return isinstance(other, EnhancedEventPattern) and self.pattern == other.pattern


@dataclass
class TraceData:
    """
    Processed trace data structure.

    Attributes:
        trace_id: Unique trace identifier
        enhanced_patterns: List of enhanced event patterns for this trace
        root_service: Root service name (e.g., loadgenerator)
        total_spans: Total number of spans in this trace
        error_count: Number of error spans
        performance_score: Performance degradation score
    """

    trace_id: str
    enhanced_patterns: List[EnhancedEventPattern]
    root_service: str
    total_spans: int
    error_count: int
    performance_score: float

    def get_pattern_dict(self) -> Dict[Tuple[int, int], EnhancedEventPattern]:
        """Get patterns as dictionary for fast lookup."""
        return {pattern.pattern: pattern for pattern in self.enhanced_patterns}


@dataclass
class ProcessingMetrics:
    """
    Metrics for tracking processing performance.
    """

    total_traces: int
    processed_traces: int
    total_patterns: int
    unique_patterns: int
    processing_time_seconds: float

    def log_summary(self) -> None:
        """Log processing summary."""
        logger.info(
            f"Processing complete: {self.processed_traces}/{self.total_traces} traces"
        )
        logger.info(
            f"Generated {self.total_patterns} patterns ({self.unique_patterns} unique)"
        )
        logger.info(f"Processing time: {self.processing_time_seconds:.2f}s")


class PatternSupport:
    """
    Pattern support calculation and storage.
    """

    def __init__(self):
        self.pattern_counts: Dict[Tuple[int, int], int] = {}
        self.pattern_depths: Dict[Tuple[int, int], List[int]] = {}
        self.pattern_services: Dict[Tuple[int, int], Set[str]] = {}

    def add_pattern(self, pattern: EnhancedEventPattern) -> None:
        """Add a pattern to support calculation."""
        key = pattern.pattern

        # Update counts
        self.pattern_counts[key] = self.pattern_counts.get(key, 0) + pattern.count

        # Track depths
        if key not in self.pattern_depths:
            self.pattern_depths[key] = []
        self.pattern_depths[key].append(pattern.depth)

        # Track services
        if key not in self.pattern_services:
            self.pattern_services[key] = set()
        self.pattern_services[key].add(pattern.service)

    def get_sorted_patterns(
        self, min_support: int = 1
    ) -> List[Tuple[Tuple[int, int], int]]:
        """Get patterns sorted by support (descending)."""
        filtered_patterns = [
            (pattern, count)
            for pattern, count in self.pattern_counts.items()
            if count >= min_support
        ]
        return sorted(filtered_patterns, key=lambda x: x[1], reverse=True)

    def get_pattern_info(self, pattern: Tuple[int, int]) -> Dict:
        """Get comprehensive information about a pattern."""
        return {
            "pattern": pattern,
            "total_support": self.pattern_counts.get(pattern, 0),
            "avg_depth": sum(self.pattern_depths.get(pattern, [0]))
            / len(self.pattern_depths.get(pattern, [1])),
            "max_depth": max(self.pattern_depths.get(pattern, [0])),
            "services": list(self.pattern_services.get(pattern, set())),
            "service_count": len(self.pattern_services.get(pattern, set())),
        }


# Type aliases for clarity
EventPairSet = Set[Tuple[int, int]]
PatternDict = Dict[Tuple[int, int], EnhancedEventPattern]
ServiceDict = Dict[str, int]
