# Nezha 重构总结

## 重构概述

根据要求，我已经完成了 Nezha 算法的重构，将其集成到新的平台格式中，并增强了 event 的表示方式。重构后的代码位于 `src/nezha/` 目录下，采用了标准的 Python 项目结构。

## 主要变更

### 1. 增强的 Event 表示
- **原来**: 简单的 event ID 对
- **现在**: `EnhancedEventPattern(pattern, count, depth, service)`
  - `pattern`: tuple(int, int) - 唯一的模式表示
  - `count`: int - 在 trace 中的出现次数  
  - `depth`: int - 在 span 层次结构中的深度
  - `service`: int - 所属服务的编号

### 2. 集成新平台组件
- 使用 `rcabench_platform.v2.samplers.event_encoding` 的 `EventIDManager` 和 `EventEncoder`
- 使用 `rcabench_platform.v2.logging` 的 logger
- 兼容新的数据加载格式 (parquet 文件)
- 利用性能阈值计算功能

### 3. 服务级别分析
- 从 pod 级别切换到 service 级别
- 服务名称映射为整数 ID 以提高效率
- 基于源 event 进行模式服务归属

### 4. 深度计算
- 实现了适当的 span 层次深度计算
- 根 spans (loadgenerator) 深度为 0
- 子 spans 深度 = 父深度 + 1
- 用于模式排序和分析

### 5. 模块化结构
分为两个主要部分：

#### 预处理部分 (`preprocessor.py`)
- 数据加载和预处理
- Event 编码和增强
- 服务映射创建
- 深度计算

#### 算法部分 (`algorithms.py`)  
- 模式支持度计算
- 可疑度评分
- 模式排序
- 准确性评估

## 文件结构

```
src/nezha/
├── __init__.py              # 包初始化
├── data_structures.py       # 数据结构定义
├── preprocessor.py          # 预处理模块
├── algorithms.py            # 算法模块
├── integration.py           # 集成层
└── example.py              # 使用示例

main_nezha.py               # 主入口脚本
test_nezha.py              # 测试脚本
setup.py                   # 安装脚本
requirements-nezha.txt     # 依赖列表
README_V2.md              # 详细文档
```

## 核心算法流程

### 1. 预处理阶段
```python
preprocessor = NezhaPreprocessor(input_folder)
trace_data_list, metrics = preprocessor.load_and_process_data()
```

### 2. 数据分离
```python
normal_traces, abnormal_traces = separate_traces(trace_data_list)
```

### 3. 算法执行
```python
results = run_nezha_analysis(
    normal_traces=normal_traces,
    abnormal_traces=abnormal_traces,
    service_mapping=preprocessor.service_mapping
)
```

## 可疑度评分公式

```
score = abnormal_support / (abnormal_support + normal_support)
```

- 异常 traces 中支持度高而正常 traces 中支持度低的模式得到高分
- 应用最小支持度和评分阈值过滤

## 使用方法

### 命令行使用
```bash
# 自定义数据
python main_nezha.py --input ./data/experiment1 --output results.json

# 预定义数据集
python main_nezha.py --dataset hipster --min-score 0.8
python main_nezha.py --dataset ts --min-support 10 --top-k 5
```

### 编程使用
```python
from nezha.integration import run_nezha_pipeline

results = run_nezha_pipeline(
    input_folder=Path("./data/experiment1"),
    min_support=5,
    min_score=0.67, 
    top_k=10
)
```

## 数据格式要求

需要 rcabench_platform 格式的数据：
- `normal_traces.parquet` 和 `abnormal_traces.parquet`
- `normal_logs.parquet` 和 `abnormal_logs.parquet` (可选)
- `metrics_sli.parquet` (用于性能阈值)
- `env.json` (用于注入时间)

## 兼容性

重构版本在保持核心算法逻辑的同时：
- 集成了 rcabench_platform 组件
- 使用增强的 event 表示
- 支持服务级别分析
- 提供更好的模块化和可扩展性

## 测试

运行测试脚本验证重构：
```bash
python test_nezha.py
```

## 关键改进

1. **性能**: 使用整数 ID 和优化的数据结构
2. **可扩展性**: 模块化设计便于扩展
3. **集成性**: 与新平台无缝集成
4. **可读性**: 清晰的代码结构和文档
5. **功能性**: 增强的模式表示提供更丰富的信息

重构完成后，Nezha 现在可以高效地处理新平台格式的数据，并提供增强的根因分析能力。
