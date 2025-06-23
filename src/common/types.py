"""
Common data types and structures for Nezha analysis system.
These types define the standard interface between preprocessing and analysis methods.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple, Union
from datetime import datetime


@dataclass
class EventNode:
    """Represents a single event in the system."""

    event_id: int
    timestamp: int  # Unix timestamp in nanoseconds
    pod: str
    service: str
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    event_type: str = "log"  # log, span_start, span_end, alarm
    raw_content: Optional[str] = None

    def __hash__(self) -> int:
        return hash((self.event_id, self.timestamp, self.pod, self.span_id))


@dataclass
class EventGraph:
    """Represents an event graph for a single trace."""

    trace_id: str
    nodes: List[EventNode] = field(default_factory=list)
    edges: List[Tuple[EventNode, EventNode]] = field(default_factory=list)
    adjacency_list: Dict[EventNode, List[EventNode]] = field(default_factory=dict)

    def add_node(self, node: EventNode) -> None:
        """Add a node to the graph."""
        if node not in self.nodes:
            self.nodes.append(node)
            if node not in self.adjacency_list:
                self.adjacency_list[node] = []

    def add_edge(self, source: EventNode, target: EventNode) -> None:
        """Add an edge between two nodes."""
        self.add_node(source)
        self.add_node(target)
        if target not in self.adjacency_list[source]:
            self.adjacency_list[source].append(target)
            self.edges.append((source, target))

    def get_deepth_pod(self, source_event_id: int) -> Tuple[int, str]:
        """Get the maximum depth and pod for a given source event ID."""
        max_depth = 0
        event_pod = ""

        for node in self.nodes:
            if node.event_id == source_event_id:
                depth = self._calculate_depth(node)
                if depth > max_depth:
                    max_depth = depth
                    event_pod = node.pod

        return max_depth, event_pod

    def _calculate_depth(self, node: EventNode, visited: Optional[set] = None) -> int:
        """Calculate the depth of a node in the graph."""
        if visited is None:
            visited = set()

        if node in visited:
            return 0

        visited.add(node)
        max_child_depth = 0

        for child in self.adjacency_list.get(node, []):
            child_depth = self._calculate_depth(child, visited.copy())
            max_child_depth = max(max_child_depth, child_depth)

        return max_child_depth + 1


@dataclass
class AlarmEvent:
    """Represents an alarm/anomaly event."""

    pod: str
    service: str
    metric_type: str  # Cpu, Memory, Network, etc.
    metric_value: float
    threshold: float
    timestamp: datetime
    severity: str = "warning"

    def to_event_node(self, event_id: int) -> EventNode:
        """Convert alarm to EventNode."""
        return EventNode(
            event_id=event_id,
            timestamp=int(self.timestamp.timestamp() * 1e9),
            pod=self.pod,
            service=self.service,
            event_type="alarm",
            raw_content=f"{self.metric_type}:{self.metric_value}",
        )


@dataclass
class Pattern:
    """Represents a mined pattern."""

    pattern_key: str  # format: "source_id_target_id"
    source_event_id: int
    target_event_id: int
    support: int
    confidence: float = 0.0

    @classmethod
    def from_key(cls, pattern_key: str, support: int = 1) -> "Pattern":
        """Create pattern from key string."""
        parts = pattern_key.split("_")
        if len(parts) >= 2:
            source_id = int(parts[0])
            target_id = int(parts[1])
        else:
            source_id = target_id = 0

        return cls(
            pattern_key=pattern_key,
            source_event_id=source_id,
            target_event_id=target_id,
            support=support,
        )


@dataclass
class RankedPattern:
    """Represents a ranked pattern with additional metadata."""

    pattern: Pattern
    score: float
    depth: int
    pod: str
    alarm_flag: bool = False
    alarm_info: Optional[AlarmEvent] = None
    source_template: str = ""
    target_template: str = ""


@dataclass
class TimeWindow:
    """Represents a time window for analysis."""

    start_time: str  # Format: "YYYY-MM-DD HH:MM"
    date: str
    hour: str
    minute: str

    @classmethod
    def from_timestamp(cls, timestamp: str) -> "TimeWindow":
        """Create TimeWindow from timestamp string."""
        date_part, time_part = timestamp.strip().split(" ")
        hour, minute = time_part.split(":")
        return cls(start_time=timestamp, date=date_part, hour=hour, minute=minute)


@dataclass
class MetricData:
    """Represents metric data for a pod."""

    pod: str
    service: str
    timestamp: datetime
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    network_latency: float = 0.0
    syscall_read: int = 0
    syscall_write: int = 0
    custom_metrics: Dict[str, Union[float, int, str]] = field(default_factory=dict)


@dataclass
class FaultInjection:
    """Represents a fault injection event."""

    inject_time: str
    inject_pod: str
    inject_service: str
    inject_type: str  # cpu, memory, network, etc.
    severity: float = 1.0
    duration: Optional[int] = None  # seconds


@dataclass
class GroundTruth:
    """Represents ground truth for evaluation."""

    fault_injection: FaultInjection
    root_cause_pattern: str
    affected_services: List[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis result."""

    ranked_patterns: List[RankedPattern]
    event_graphs: List[EventGraph]
    alarms: List[AlarmEvent]
    analysis_time: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_top_patterns(self, k: int = 10) -> List[RankedPattern]:
        """Get top k patterns by score."""
        return sorted(self.ranked_patterns, key=lambda x: x.score, reverse=True)[:k]


@dataclass
class EvaluationMetrics:
    """Evaluation metrics for analysis results."""

    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mean_average_rank: float
    total_faults: int
    namespace: str


# Type aliases for commonly used types
PatternDict = Dict[str, int]  # pattern_key -> support
ThresholdDict = Dict[str, Dict[str, float]]  # service -> metric -> threshold
TemplateDict = Dict[int, str]  # event_id -> template
