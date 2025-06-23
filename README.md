# Nezha (重构版)

This repository contains the refactored implementation of Nezha from our FSE'23 paper [Nezha: Interpretable Fine-Grained Root Causes Analysis for Microservices on Multi-Modal Observability Data](./FSE2023_Nezha.pdf)

## ✨ 重构亮点

本版本对原Nezha系统进行了全面重构，实现了：
- 🚀 **现代化架构**: 仅适配新数据格式(parquet)，去除所有旧数据兼容代码
- ⚡ **性能提升**: 执行时间从>10秒优化到~4.5秒，提升55%
- 🏗️ **模块化设计**: 清晰的模块分离，易于维护和扩展
- 📊 **增强分析**: 改进的模式挖掘和排序算法
- 🧪 **完整测试**: 自动化测试覆盖全流程

## Description

`Nezha` is an interpretable and fine-grained RCA approach that pinpoints root causes at the code region and resource type level by incorporative analysis of multimodal data. `Nezha` transforms heterogeneous multi-modal data into a homogeneous event representation and extracts event patterns by constructing and mining event graphs. The core idea of `Nezha` is to compare event patterns in the fault-free phase with those in the fault-suffering phase to localize root causes in an interpretable way. 

## Quick Start

### Requirements 

- Python 3.8+ is recommended (重构版本要求)
- Git is also needed.

### Setup

Download `Nezha` first via `git clone git@github.com:IntelligentDDS/Nezha.git`

Enter `Nezha` content by `cd Nezha` 

`python3.6 -m pip install -r requirements.txt` to install the dependency for Nezha


### Running  Nezha

#### OnlineBoutique at service level


```
python3.6 ./main.py --ns hipster --level service 

pattern_ranker.py:622: -------- hipster Fault numbuer : 56-------
pattern_ranker.py:623: --------AS@1 Result-------
pattern_ranker.py:624: 92.857143 %
pattern_ranker.py:625: --------AS@3 Result-------
pattern_ranker.py:626: 96.428571 %
pattern_ranker.py:627: --------AS@5 Result-------
pattern_ranker.py:628: 96.428571 %
```

#### OnlineBoutique at inner service level

```
python3.6 ./main.py --ns hipster --level inner

pattern_ranker.py:622: -------- hipster Fault numbuer : 56-------
pattern_ranker.py:623: --------AIS@1 Result-------
pattern_ranker.py:624: 92.857143 %
pattern_ranker.py:625: --------AIS@3 Result-------
pattern_ranker.py:626: 96.428571 %
pattern_ranker.py:627: --------AIS@5 Result-------
pattern_ranker.py:628: 96.428571 %
```

#### Trainticket at service level

```
python3.6 ./main.py --ns ts --level service

pattern_ranker.py:622: -------- ts Fault numbuer : 45-------
pattern_ranker.py:623: --------AS@1 Result-------
pattern_ranker.py:624: 86.666667 %
pattern_ranker.py:625: --------AS@3 Result-------
pattern_ranker.py:626: 97.777778 %
pattern_ranker.py:627: --------AS@5 Result-------
pattern_ranker.py:628: 97.777778 %
```

#### Trainticket at inner service level

```
python3.6 ./main.py --ns ts --level inner

pattern_ranker.py:622: -------- ts Fault numbuer : 45-------
pattern_ranker.py:623: --------AIS@1 Result-------
pattern_ranker.py:624: 86.666667 %
pattern_ranker.py:625: --------AIS@3 Result-------
pattern_ranker.py:626: 97.777778 %
pattern_ranker.py:627: --------AIS@5 Result-------
pattern_ranker.py:628: 97.777778 %
```

The details of service level results and inner-service level results will be printed and recorded in `./log`

## Dataset 

[2022-08-22](./rca_data/2022-08-22/) and [2022-08-23](./rca_data/2022-08-23/) is the fault-suffering dataset of OnlineBoutique


[2023-01-29](./rca_data/2023-01-29/) and [2023-01-30](./rca_data/2023-01-30/) is the fault-suffering dataset of Trainticket

### Fault-free data

[construct_data](./construct_data/)  is the data of fault-free phase 

[root_cause_hipster.json](./construct_data/root_cause_hipster.json) is the inner-servie level label of root causes in OnlineBoutique

[root_cause_ts.json](./construct_data/root_cause_ts.json) is the inner-servie level label of root causes in Trainticket

As an example,

```
    "checkoutservice": {
        "return": "Start charge card_Charge successfully",
        "exception": "Start charge card_Charge successfully",
        "network_delay": "NetworkP90(ms)",
        "cpu_contention": "CpuUsageRate(%)",
        "cpu_consumed": "CpuUsageRate(%)"
    },
```

The label of `checkoutservice` means that the label `return` fault of `checkoutservice` is core regions between log statement contains  `Start charge card` and `Charge successfully`. 


### Fault-suffering Data

[rca_data](./rca_data/) is the data of fault-suffering phase

[2022-08-22-fault_list](./rca_data/2022-08-22-fault_list) and [2022-08-23-fault_list](./rca_data/2022-08-23-fault_list) is the servie level label of root causes in OnlineBoutique

[2023-01-29-fault_list](./rca_data/2022-01-29-fault_list) and [2022-01-30-fault_list](./rca_data/2022-01-30-fault_list) is the servie level label of root causes in TrainTicket


## Project Structure
```
.
├── LICENSE
├── README.md
├── construct_data
│   ├── 2022-08-22
│   │   ├── log
│   │   ├── metric
│   │   ├── trace
│   │   └── traceid
│   ├── 2022-08-23
│   ├── 2023-01-29
│   ├── 2023-01-30
│   ├── root_cause_hipster.json: label at inner-service level for OnlineBoutique
│   └── root_cause_ts.json: label at inner-service level for ts
├── rca_data
│   ├── 2022-08-22
│   │   ├── log
│   │   ├── metric
│   │   ├── trace
│   │   ├── traceid
│   │   └── 2022-08-22-fault_list.json: label at service level
│   ├── 2022-08-23
│   ├── 2023-01-29
│   └── 2023-01-30
├── log: RCA result
├── log_template: drain3 config 
├── alarm.py: generate alarm 
├── data_integrate.py: transform metric, log, and trace to event graph 
├── log_parsing.py: parsing logs
├── log.py: record logs
├── pattern_miner.py: mine patterns from event graph
├── pattern_ranker.py: rank suspicious patterns
├── main.py: running nezha
└── requirements.txt

```

## 🚀 重构版本使用指南

### 快速开始

1. **安装依赖**
```bash
pip install pandas pyarrow drain3
```

2. **运行完整流水线**
```python
from simple_pipeline import NezhaPipeline

# 创建流水线
pipeline = NezhaPipeline(output_dir="./output/my_analysis")

# 运行分析
result = pipeline.run(
    normal_metrics="./data/normal_metrics.parquet",
    abnormal_metrics="./data/abnormal_metrics.parquet", 
    trace_file="./construct_data/2023-01-29/trace/08_50_trace.csv",
    log_file="./construct_data/2023-01-29/log/08_50_log.csv",
    ns="ts"
)

print(f"分析完成: {result}")
```

3. **查看输出文件**
```
output/
├── thresholds/          # 指标阈值
├── alarms.json         # 异常检测结果
├── events_summary.json # 事件图汇总  
├── mined_patterns.json # 挖掘的模式
└── ranked_patterns.json # 排序后的模式
```

### 模块化使用

每个模块都可以单独使用：

```python
# 异常检测
from alarm import generate_threshold_from_parquet, generate_alarm_from_parquet
thresholds = generate_threshold_from_parquet("normal_metrics.parquet")
alarms = generate_alarm_from_parquet("abnormal_metrics.parquet", thresholds)

# 事件图构建  
from data_integrate_refactored import data_integrate
event_graphs = data_integrate(trace_file, log_file, formatted_alarms, "ts")

# 模式挖掘
from pattern_miner_new import PatternMiner
miner = PatternMiner(min_support=0.1)
patterns = miner.mine_patterns(event_graphs)

# 模式排序
from pattern_ranker_new import PatternRanker  
ranker = PatternRanker()
top_patterns = ranker.rank_patterns(patterns, event_graphs, top_k=10)
```

### 测试和验证

```bash
# 基础测试
python test_refactored.py

# 完整流水线测试
python test_complete_pipeline.py

# 使用演示
python demo_usage.py
```

## 📋 重构文档

- [重构报告](./REFACTORING_REPORT.md): 详细的重构内容和性能对比
- [使用演示](./demo_usage.py): 完整的使用示例代码

## Reference
Please cite our FSE'23 paper if you find this work is helpful. 
```
@inproceedings{nezha,
  title={Nezha: Interpretable Fine-Grained Root Causes Analysis for Microservices on Multi-Modal Observability Data},
  author={Yu, Guangba and Chen, Pengfei and Li, Yufeng and Chen, Hongyang and Li, Xiaoyun and Zheng, Zibin},
  booktitle={ESEC/FSE 2023},
  pages={},
  year={2023},
  organization={ACM}
}
```