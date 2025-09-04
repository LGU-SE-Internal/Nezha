import pandas as pd
from rcabench_platform.v2.datasets.spec import get_datapack_list

df = pd.read_parquet(
    "/home/nn/workspace/Nezha/output/rcabench-platform-v2/meta/rcabench_sampler_filtered/datapack.perf.parquet"
)
df_original = df.copy()

df["datapack"].unique().tolist()
all_list = get_datapack_list("rcabench_sampler_filtered")
print(f"lost datapack: {set(all_list) - set(df['datapack'].unique().tolist())}")
