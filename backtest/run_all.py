"""
一键运行完整回测流程：
  1. 构建2022数据集
  2. 构建2018数据集
  3. 运行2022预测
  4. 运行2018预测
  5. 生成报告
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.dataset_builder import build_dataset
from backtest.run_backtest import run_backtest
from backtest.report import generate_report

print("="*60)
print("世界杯预测系统 — 2018/2022 完整回测")
print("="*60)

# Step 1: 构建数据集
print("\n[Step 1/4] 构建2022世界杯赛前数据集...")
build_dataset(2022)

print("\n[Step 2/4] 构建2018世界杯赛前数据集...")
build_dataset(2018)

# Step 3: 运行预测
print("\n[Step 3/4] 运行2022世界杯预测...")
run_backtest(2022)

print("\n[Step 4/4] 运行2018世界杯预测...")
run_backtest(2018)

# Step 5: 生成报告
print("\n[Step 5/5] 生成完整报告...")
generate_report()

print("\n回测完成！报告已保存到 backtest/backtest_report.md")
