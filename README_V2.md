# Nezha V2 - Refactored Version

This is the refactored version of Nezha that integrates with the rcabench_platform. The refactoring follows the requirements to:

1. Use the new platform's event construction and data loading methods
2. Enhance event representation with (pattern, count, depth, service) 
3. Separate preprocessing and algorithm execution
4. Create a standard Python project structure
5. Use service-level analysis (not pod-level)

## Architecture

### Data Structures (`src/nezha/data_structures.py`)
- `EnhancedEventPattern`: Enhanced event patterns with depth and service information
- `ServiceMapping`: Service name to integer ID mapping  
- `TraceData`: Processed trace data structure
- `PatternSupport`: Pattern support calculation and storage

### Preprocessing (`src/nezha/preprocessor.py`)
- `NezhaPreprocessor`: Main preprocessing class that:
  - Integrates with rcabench_platform's event encoding system
  - Computes span depths based on parent-child relationships
  - Enhances event pairs with service and depth information
  - Creates service mappings

### Algorithm (`src/nezha/algorithms.py`)
- `NezhaAlgorithm`: Core algorithm implementation that:
  - Calculates pattern support from trace data
  - Ranks patterns by suspiciousness score
  - Evaluates accuracy against ground truth

### Integration (`src/nezha/integration.py`)
- `NezhaIntegrator`: High-level integration layer
- `run_nezha_pipeline`: Complete pipeline function
- Convenience functions for specific datasets

## Key Changes from Original

### Enhanced Event Representation
Original events were simple ID pairs. Now each pattern includes:
- `pattern`: (source_event_id, target_event_id) tuple
- `count`: Occurrences in the trace  
- `depth`: Span hierarchy depth
- `service`: Service identifier (integer)

### Service-Level Analysis
- Switched from pod-level to service-level analysis
- Service names mapped to integer IDs for efficiency
- Pattern service attribution based on source event

### Depth Calculation
- Implements proper span hierarchy depth calculation
- Root spans (loadgenerator) have depth 0
- Child spans have depth = parent_depth + 1
- Used for pattern ranking and analysis

### Integration with rcabench_platform
- Uses `EventIDManager` and `EventEncoder` from rcabench_platform
- Compatible with new data loading format (parquet files)
- Leverages performance threshold calculation
- Uses rcabench_platform logging system

## Usage

### Basic Usage
```python
from pathlib import Path
from nezha.integration import run_nezha_pipeline

# Run complete pipeline
results = run_nezha_pipeline(
    input_folder=Path("./data/experiment1"),
    min_support=5,
    min_score=0.67,
    top_k=10
)
```

### Step-by-Step Usage
```python
from nezha.preprocessor import NezhaPreprocessor
from nezha.algorithms import run_nezha_analysis

# Step 1: Preprocessing
preprocessor = NezhaPreprocessor(input_folder)
trace_data_list, metrics = preprocessor.load_and_process_data()

# Step 2: Separate traces (implement your time-based logic)
normal_traces = trace_data_list[:len(trace_data_list)//2]
abnormal_traces = trace_data_list[len(trace_data_list)//2:]

# Step 3: Run analysis
results = run_nezha_analysis(
    normal_traces=normal_traces,
    abnormal_traces=abnormal_traces, 
    service_mapping=preprocessor.service_mapping
)
```

### Command Line Usage
```bash
# Run on custom data
python main_nezha.py --input ./data/experiment1 --output results.json

# Run on predefined datasets
python main_nezha.py --dataset hipster --min-score 0.8
python main_nezha.py --dataset ts --min-support 10 --top-k 5
```

## Data Format Requirements

The code expects rcabench_platform format data with:
- `normal_traces.parquet` and `abnormal_traces.parquet`
- `normal_logs.parquet` and `abnormal_logs.parquet` (optional)
- `metrics_sli.parquet` (for performance thresholds)
- `env.json` (for injection time)

### Required Trace Columns
- `trace_id`: Unique trace identifier
- `span_id`: Unique span identifier  
- `parent_span_id`: Parent span ID (null for root spans)
- `service_name`: Service name
- `span_name`: Operation name
- `duration`: Duration in nanoseconds
- `attr.status_code`: Status code ("Error" for errors)
- `time`: Timestamp

### Required Log Columns (if using logs)
- `trace_id`: Trace identifier
- `span_id`: Span identifier
- `service_name`: Service name
- `attr.template_id`: Pre-computed template ID
- `level`: Log level
- `time`: Timestamp

## Algorithm Details

### Pattern Enhancement Process
1. Use rcabench_platform's EventEncoder to get basic event pairs
2. Compute span depths using parent-child relationships
3. Map events to services using event ID ranges
4. Count pattern occurrences within each trace
5. Create EnhancedEventPattern objects with all metadata

### Suspiciousness Scoring
- Score = abnormal_support / (abnormal_support + normal_support)
- Patterns with high abnormal support and low normal support get high scores
- Filters applied for minimum support and score thresholds

### Service Mapping
- Service names sorted and mapped to consecutive integers
- Used for efficient storage and comparison
- Enables service-level aggregation and analysis

## Installation

```bash
# Install dependencies
pip install -r requirements-nezha.txt

# Install in development mode
pip install -e .
```

## Examples

See `src/nezha/example.py` for detailed usage examples with different datasets.

## Compatibility

This refactored version maintains the core algorithm logic while:
- Integrating with rcabench_platform components
- Using enhanced event representation
- Supporting service-level analysis
- Providing better modularity and extensibility
