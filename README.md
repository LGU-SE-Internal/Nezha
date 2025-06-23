# Nezha: Pattern Mining and Ranking System for Root Cause Analysis

Nezha 是一个用于微服务系统根因分析的模式挖掘和排序系统。该系统通过分析日志、链路追踪和指标数据，自动识别异常模式并进行根因定位。

## 📁 项目结构

经过重构，Nezha 项目采用模块化设计，分为预处理（preprocessing）和方法（methods）两个核心模块：

```
src/
├── common/              # 通用数据类型和工具
│   ├── types.py        # 标准化数据结构定义
│   └── __init__.py
├── preprocessing/       # 数据预处理模块
│   ├── log_parsing.py  # 日志解析
│   ├── data_loader.py  # 数据加载
│   ├── event_graph_builder.py  # 事件图构建
│   └── __init__.py
├── methods/            # 分析方法模块
│   ├── pattern_mining.py    # 模式挖掘
│   ├── pattern_ranking.py   # 模式排序
│   ├── alarm_detection.py   # 告警检测
│   ├── evaluation.py        # 评估方法
│   └── __init__.py
└── example_usage.py    # 完整使用示例
```

## 🚀 快速开始

### 安装依赖

项目使用 `uv` 进行依赖管理：

```bash
# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境并安装依赖
uv sync
```

或者使用传统的 pip 方式：

```bash
pip install -r requirements.txt
```

### 基本使用

#### 1. 快速集成使用（推荐）

使用 `NezhaPipeline` 类进行完整的分析流程：

```python
from src.example_usage import NezhaPipeline

# 初始化管道
pipeline = NezhaPipeline(
    data_root_path="/path/to/data",
    log_template_config="log_template/drain3_hipster.ini",
    log_template_persistence="log_template/hipster.bin",
    namespace="hipster"
)

# 运行完整分析
result = pipeline.run_complete_analysis(
    normal_timestamps=["2021-01-01_10-00"],  # 正常时间段
    abnormal_timestamps=["2021-01-01_11-00"], # 异常时间段
    ground_truth_file="ground_truth.csv"  # 可选：用于评估
)

# 查看结果
print(f"发现 {len(result.ranked_patterns)} 个排序模式")
print(f"检测到 {len(result.alarms)} 个告警")
```

#### 2. 模块化使用

分别使用预处理和方法模块：

```python
from src.preprocessing import LogParser, DataLoader, EventGraphBuilder
from src.methods import PatternMiner, PatternRanker, AlarmDetector
from src.common.types import TimeWindow

# 1. 数据预处理
log_parser = LogParser(
    config_file="log_template/drain3_hipster.ini",
    persistence_file="log_template/hipster.bin"
)

data_loader = DataLoader("/path/to/data")
graph_builder = EventGraphBuilder(log_parser)

# 加载数据
time_window = TimeWindow.from_timestamp("2021-01-01_10-00")
trace_df, log_df, trace_ids, missing_files = data_loader.load_time_window_data(time_window)

# 构建事件图
event_graphs = graph_builder.build_event_graphs(
    trace_df, log_df, trace_ids, [], "hipster"
)

# 2. 模式分析
pattern_miner = PatternMiner()
pattern_ranker = PatternRanker()

# 挖掘模式
patterns = pattern_miner.mine_patterns(event_graphs)

# 排序模式
ranked_patterns = pattern_ranker.rank_patterns(
    patterns, normal_patterns={}, threshold=0.1
)
```

## 📊 数据格式说明

### 输入数据格式

Nezha 支持以下数据格式：

#### 1. 链路追踪数据 (trace.csv)
```csv
TraceId,SpanId,OperationName,StartTime,FinishTime,Tags,Process
trace123,span456,checkout,1609459200,1609459201,"{""service"":""frontend""}","{""serviceName"":""frontend""}"
```

#### 2. 日志数据 (log.csv)
```csv
Time,Content,EventId,EventTemplate
2021-01-01 10:00:01,"User login successful",E001,"User <*> login <*>"
```

#### 3. 指标数据 (metrics.csv)
```csv
Time,PodName,CpuUsageRate(%),MemoryUsageRate(%),NetworkP90(ms),SyscallRead,SyscallWrite
2021-01-01 10:00:01,frontend-pod,50.5,60.2,100,1000,500
```

#### 4. 告警数据 (alarms.csv)
```csv
Time,Content
2021-01-01 10:00:01,"High CPU usage detected on frontend-pod"
```

### 输出数据格式

#### 分析结果 (AnalysisResult)
```python
@dataclass
class AnalysisResult:
    ranked_patterns: List[RankedPattern]  # 排序后的模式
    event_graphs: List[EventGraph]       # 事件图
    alarms: List[AlarmEvent]            # 告警事件
    analysis_time: datetime             # 分析时间
    metadata: Dict[str, Any]            # 元数据
```

## 🔧 配置说明

### 日志解析配置

修改 `log_template/drain3_hipster.ini` 配置文件：

```ini
[DRAIN]
sim_th = 0.4          # 相似度阈值
depth = 4             # 解析树深度
max_children = 100    # 最大子节点数
max_clusters = 1024   # 最大聚类数

[MASKING]
masking = [
    {"regex_pattern": "(\\d+\\.\\d+\\.\\d+\\.\\d+)", "mask_with": "<IP>"},
    {"regex_pattern": "(\\d{4}-\\d{2}-\\d{2})", "mask_with": "<DATE>"}
]
```

### 参数配置

所有分析方法都支持参数配置：

```python
# 模式挖掘参数
patterns = pattern_miner.mine_patterns(
    event_graphs,
    min_support=2,      # 最小支持度
    max_pattern_size=10, # 最大模式大小
    depth_limit=5       # 深度限制
)

# 模式排序参数
ranked_patterns = pattern_ranker.rank_patterns(
    patterns,
    normal_patterns,
    threshold=0.1,           # 阈值
    lambda_param=0.5,        # 权重参数
    include_single_nodes=True # 包含单节点模式
)

# 告警检测参数
alarms = alarm_detector.detect_alarms(
    metrics,
    namespace,
    cpu_threshold=80.0,       # CPU 阈值
    memory_threshold=80.0,    # 内存阈值
    network_threshold=1000.0  # 网络阈值
)
```

## 📈 评估和验证

### 性能评估

```python
from src.methods import Evaluator

evaluator = Evaluator()

# 评估模式质量
scores = evaluator.evaluate_patterns(
    ranked_patterns,
    ground_truth_patterns,
    metrics=['precision', 'recall', 'f1']
)

# 评估告警检测
alarm_scores = evaluator.evaluate_alarms(
    detected_alarms,
    ground_truth_alarms,
    time_tolerance=300  # 5分钟容忍度
)
```

### 地面真值格式

```csv
timestamp,root_cause_service,fault_type,description
2021-01-01_11-00,frontend,cpu_spike,"CPU usage spike in frontend service"
```

## 🛠️ 扩展和自定义

### 适配新数据集

1. **实现新的数据加载器**：
```python
from src.preprocessing import DataLoader
from src.common.types import TimeWindow, EventGraph

class CustomDataLoader(DataLoader):
    def load_time_window_data(self, time_window: TimeWindow):
        # 自定义数据加载逻辑
        # 返回标准格式：trace_df, log_df, trace_ids, missing_files
        pass
```

2. **添加新的分析方法**：
```python
from src.common.types import EventGraph, Pattern
from typing import List, Dict

def custom_pattern_mining(
    event_graphs: List[EventGraph],
    custom_param: float = 1.0
) -> Dict[str, int]:
    """自定义模式挖掘方法"""
    # 实现自定义逻辑
    return patterns
```

### 自定义评估指标

```python
from src.methods.evaluation import Evaluator

class CustomEvaluator(Evaluator):
    def custom_metric(self, predictions, ground_truth):
        """自定义评估指标"""
        # 实现自定义评估逻辑
        return score
```

## 📝 使用示例

### 端到端分析示例

```python
#!/usr/bin/env python3
"""完整的 Nezha 分析示例"""

from src.example_usage import NezhaPipeline
from pathlib import Path

def main():
    # 配置路径
    data_path = "rca_data/TrainSet"
    config_file = "log_template/drain3_hipster.ini"
    persistence_file = "log_template/hipster.bin"
    
    # 初始化管道
    pipeline = NezhaPipeline(
        data_root_path=data_path,
        log_template_config=config_file,
        log_template_persistence=persistence_file,
        namespace="hipster"
    )
    
    # 定义时间窗口
    normal_periods = [
        "2021-01-01_10-00",
        "2021-01-01_10-05",
        "2021-01-01_10-10"
    ]
    
    abnormal_periods = [
        "2021-01-01_11-00",
        "2021-01-01_11-05"
    ]
    
    # 运行分析
    result = pipeline.run_complete_analysis(
        normal_timestamps=normal_periods,
        abnormal_timestamps=abnormal_periods
    )
    
    # 输出结果
    print(f"分析完成！")
    print(f"- 发现异常模式: {len(result.ranked_patterns)}")
    print(f"- 检测到告警: {len(result.alarms)}")
    print(f"- 生成事件图: {len(result.event_graphs)}")
    
    # 显示前5个最重要的模式
    for i, pattern in enumerate(result.ranked_patterns[:5]):
        print(f"模式 {i+1}: 重要性={pattern.importance:.3f}, "
              f"节点数={len(pattern.pattern.nodes)}")

if __name__ == "__main__":
    main()
```

## 🐛 故障排除

### 常见问题

1. **日志解析失败**
   - 检查日志格式是否正确
   - 调整 Drain3 配置参数
   - 确保日志模板文件路径正确

2. **数据加载错误**
   - 确认数据文件存在且格式正确
   - 检查时间戳格式是否匹配
   - 验证文件权限

3. **内存不足**
   - 减少批处理大小
   - 限制事件图大小
   - 使用流式处理

### 日志调试

```python
from loguru import logger

# 启用详细日志
logger.add("nezha_debug.log", level="DEBUG")

# 在代码中添加调试信息
logger.debug("Processing time window: {}", timestamp)
```

## 📚 API 文档

### 核心类

- **`NezhaPipeline`**: 完整分析管道
- **`LogParser`**: 日志解析器
- **`DataLoader`**: 数据加载器
- **`EventGraphBuilder`**: 事件图构建器
- **`PatternMiner`**: 模式挖掘器
- **`PatternRanker`**: 模式排序器
- **`AlarmDetector`**: 告警检测器
- **`Evaluator`**: 评估器

### 数据类型

- **`EventGraph`**: 事件图表示
- **`Pattern`**: 模式表示
- **`AlarmEvent`**: 告警事件
- **`MetricData`**: 指标数据
- **`AnalysisResult`**: 分析结果

详细的 API 文档请参考各模块的 docstring。

## 🤝 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [Drain3](https://github.com/logpai/Drain3) - 日志解析库
- [Loguru](https://github.com/Delgan/loguru) - 日志记录库
- [Pandas](https://pandas.pydata.org/) - 数据处理库

## 📧 联系方式

如有问题或建议，请通过以下方式联系：

- 提交 Issue
- 发送邮件
- 参与讨论

---

*Nezha: 让微服务根因分析变得简单而高效*
