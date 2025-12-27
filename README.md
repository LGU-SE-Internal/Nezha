# Nezha

```sh
sudo juicefs mount redis://10.10.10.119:6379/1 /mnt/jfs -d --cache-size=1024
mkdir data
ln -s /mnt/jfs/rcabench_dataset ./data/
export RCABENCH_BASE_URL=http://10.10.10.220:32080
export RCABENCH_USERNAME=admin
export RCABENCH_PASSWORD=admin123


```
# build
```sh
docker build -t 10.10.10.240/library/rca-algo-nezha:study .
```
# upload
```sh
rca upload-algorithm-harbor ./
```
# test
```sh
sudo -E .venv/bin/python run.py batch-test --label 9.6nezha # note this label, we will use it later for cross-dataset metrics
```

# check accuracy
```sh
# use the latest platform
rca cross-dataset-metrics -a nezha -d pair-diag -dv all-absolute_anomaly-9.3 --tag 9.6nezha
```

