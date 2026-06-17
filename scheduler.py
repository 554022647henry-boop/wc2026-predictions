"""
调度器 — 定时触发各场比赛的搜集+预测流程
每60秒检查一次是否有比赛需要处理。
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import config
from agents.collector import run_collection
from agents.reviewer import review
from agents.predictor import run_prediction
from agents.html_updater import update_html


def load_fixtures() -> list[dict]:
    fixtures_path = Path(config.FIXTURES_FILE)
    if not fixtures_path.exists():
        print("[调度器] 警告: fixtures.json 不存在")
        return []
    data = json.loads(fixtures_path.read_text(encoding="utf-8"))
    return data.get("matches", [])


def should_run_round(match: dict, round_cfg: dict, now: datetime) -> bool:
    """判断某场比赛的某个预测轮次是否应该现在触发。"""
    match_date_str = match.get("date", "")
    if not match_date_str:
        return False

    try:
        match_dt = datetime.fromisoformat(match_date_str)
    except ValueError:
        return False

    hours_before = round_cfg.get("hours_before")
    round_key = round_cfg["round"]

    # initial 预测：系统启动时手动触发，调度器不处理
    if hours_before is None:
        return False

    # 封盘检查：比赛前10分钟停止
    minutes_to_kickoff = (match_dt - now).total_seconds() / 60
    if minutes_to_kickoff < config.CUTOFF_MINUTES_BEFORE_KICKOFF:
        return False

    # 触发窗口：在目标时间点的 ±30分钟内
    target_time = match_dt - timedelta(hours=hours_before)
    window = timedelta(minutes=30)
    in_window = (target_time - window) <= now <= (target_time + window)
    if not in_window:
        return False

    # 检查是否已经跑过这轮（避免重复触发）
    match_id = match["match_id"]
    pred_file = Path(config.PREDICTIONS_DIR) / match_id / f"{round_key}_prediction.json"
    return not pred_file.exists()


def process_match_round(match: dict, round_cfg: dict):
    """对某场比赛的某个预测轮次执行完整流程。"""
    match_id = match["match_id"]
    round_key = round_cfg["round"]
    round_label = round_cfg["label"]

    print(f"\n{'='*60}")
    print(f"[调度器] 触发: {match['team_a']} vs {match['team_b']} | {round_label}")
    print(f"{'='*60}")

    try:
        # Step 1: Agent1 搜集
        raw_file = run_collection(match, round_key, round_label)

        # Step 2: Agent2 审阅+补充
        reviewed = review(match, round_key, round_label, raw_file)

        # Step 3: 预测引擎
        prediction = run_prediction(match, reviewed, round_key, round_label)

        # Step 4: 更新 HTML
        update_html()

        print(f"\n[调度器] ✓ 完成: {match_id} | {round_label}")
        print(f"  预测结果: {prediction['output']['prediction']} ({prediction['output']['confidence']}置信度)")

    except Exception as e:
        print(f"\n[调度器] ✗ 错误: {match_id} | {round_label} | {e}")
        import traceback
        traceback.print_exc()


def run_scheduler(check_interval: int = 60):
    """
    主循环：每 check_interval 秒检查一次是否有比赛需要处理。
    """
    print(f"[调度器] 启动，检查间隔: {check_interval}秒")
    print(f"[调度器] 预测轮次: {[r['label'] for r in config.PREDICTION_ROUNDS if r['hours_before'] is not None]}")

    while True:
        now = datetime.now()
        matches = load_fixtures()

        for match in matches:
            for round_cfg in config.PREDICTION_ROUNDS:
                if should_run_round(match, round_cfg, now):
                    process_match_round(match, round_cfg)

        time.sleep(check_interval)


if __name__ == "__main__":
    run_scheduler()
