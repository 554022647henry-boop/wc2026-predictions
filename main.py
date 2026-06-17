"""
世界杯2026预测系统 — 命令行入口

用法：
  python main.py predict --match WC2026_GS_A_01          # 手动预测某场（初始）
  python main.py predict-all                              # 初始预测全部比赛
  python main.py result --match WC2026_GS_A_01 --outcome "A胜" --score "2-1"
  python main.py html                                     # 手动更新HTML
  python main.py schedule                                 # 启动自动调度器
  python main.py serve                                    # 启动本地HTTP服务器
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import config
from agents.collector import run_collection
from agents.reviewer import review
from agents.predictor import run_prediction
from agents.html_updater import update_html
from agents.momentum_agent import add_match_result


def load_fixtures() -> list[dict]:
    fixtures_path = Path(config.FIXTURES_FILE)
    if not fixtures_path.exists():
        print(f"错误: fixtures.json 不存在，请先创建 {config.FIXTURES_FILE}")
        sys.exit(1)
    data = json.loads(fixtures_path.read_text(encoding="utf-8"))
    return data.get("matches", [])


def find_match(match_id: str) -> dict:
    matches = load_fixtures()
    for m in matches:
        if m["match_id"] == match_id:
            return m
    print(f"错误: 未找到比赛 {match_id}")
    sys.exit(1)


# ─────────────────────────────────────────
# 命令：预测单场比赛
# ─────────────────────────────────────────

def cmd_predict(match_id: str, round_key: str = "initial", round_label: str = "初始预测"):
    match = find_match(match_id)
    print(f"\n开始处理: {match['team_a']} vs {match['team_b']}")

    # Agent1: 搜集
    raw_file = run_collection(match, round_key, round_label)

    # Agent2: 审阅+补充
    reviewed = review(match, round_key, round_label, raw_file)

    # 预测引擎
    prediction = run_prediction(match, reviewed, round_key, round_label)

    # 更新HTML
    update_html()

    print(f"\n✓ 预测完成")
    print(f"  {match['team_a']} vs {match['team_b']}")
    print(f"  结果: {prediction['output']['prediction']}")
    print(f"  置信度: {prediction['output']['confidence']}")
    for i, r in enumerate(prediction['output']['reasons'], 1):
        print(f"  理由{i}: {r}")


# ─────────────────────────────────────────
# 命令：初始预测全部比赛
# ─────────────────────────────────────────

def cmd_predict_all():
    matches = load_fixtures()
    print(f"\n开始初始预测全部 {len(matches)} 场比赛...\n")

    success = 0
    failed = []

    for i, match in enumerate(matches, 1):
        match_id = match["match_id"]
        team_a = match["team_a"]
        team_b = match["team_b"]

        # 跳过已有初始预测的比赛
        pred_file = Path(config.PREDICTIONS_DIR) / match_id / "initial_prediction.json"
        if pred_file.exists():
            print(f"[{i}/{len(matches)}] 跳过（已有初始预测）: {team_a} vs {team_b}")
            continue

        print(f"\n[{i}/{len(matches)}] 处理: {team_a} vs {team_b}")
        try:
            raw_file = run_collection(match, "initial", "初始预测")
            reviewed = review(match, "initial", "初始预测", raw_file)
            run_prediction(match, reviewed, "initial", "初始预测")
            success += 1
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            failed.append(match_id)

    update_html()
    print(f"\n初始预测完成: {success} 成功, {len(failed)} 失败")
    if failed:
        print(f"失败的比赛: {failed}")


# ─────────────────────────────────────────
# 命令：录入实际结果
# ─────────────────────────────────────────

def cmd_record_result(match_id: str, outcome: str, score: str):
    """
    录入比赛实际结果。
    outcome: "A胜" / "平局" / "B胜"
    score: "2-1" 等
    """
    results_file = Path(config.RESULTS_FILE)
    results_file.parent.mkdir(parents=True, exist_ok=True)

    results = {}
    if results_file.exists():
        results = json.loads(results_file.read_text(encoding="utf-8"))

    match = find_match(match_id)
    results[match_id] = {
        "outcome": outcome,
        "score": score,
        "team_a": match["team_a"],
        "team_b": match["team_b"],
        "recorded_at": datetime.now().isoformat(),
    }

    results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 已录入结果: {match['team_a']} vs {match['team_b']} → {outcome} ({score})")

    # 同步更新赛事动能日志
    result_map = {"A胜": "W", "平局": "D", "B胜": "L"}
    result_code = result_map.get(outcome, "W")
    add_match_result(
        team_a=match["team_a"],
        team_b=match["team_b"],
        stage=match.get("stage", "group_stage"),
        result_a=result_code,
        score=score,
    )
    print(f"✓ 赛事动能日志已更新")

    # 重新生成HTML
    update_html()


# ─────────────────────────────────────────
# 命令：启动本地服务器
# ─────────────────────────────────────────

def cmd_serve(port: int = 8080):
    import http.server
    import webbrowser
    web_dir = Path(config.HTML_FILE).parent

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_dir), **kwargs)
        def log_message(self, format, *args):
            pass  # 静默日志

    print(f"✓ 启动本地服务器: http://localhost:{port}")
    print(f"  目录: {web_dir}")
    print(f"  按 Ctrl+C 停止")
    webbrowser.open(f"http://localhost:{port}")

    with http.server.HTTPServer(("", port), Handler) as httpd:
        httpd.serve_forever()


# ─────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────

def main():
    if not os.environ.get("DEEPSEEK_API_KEY") and not config.ANTHROPIC_API_KEY:
        print("错误: 请设置 DEEPSEEK_API_KEY 或 ANTHROPIC_API_KEY")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="世界杯2026预测系统")
    subparsers = parser.add_subparsers(dest="command")

    # predict
    p_predict = subparsers.add_parser("predict", help="预测单场比赛")
    p_predict.add_argument("--match", required=True, help="比赛ID，如 WC2026_GS_A_01")
    p_predict.add_argument("--round", default="initial", help="预测轮次键，如 T-24h")
    p_predict.add_argument("--label", default="初始预测", help="预测轮次标签")

    # predict-all
    subparsers.add_parser("predict-all", help="初始预测全部比赛")

    # result
    p_result = subparsers.add_parser("result", help="录入实际比赛结果（同时更新动能日志）")
    p_result.add_argument("--match", required=True)
    p_result.add_argument("--outcome", required=True, help="A胜/平局/B胜")
    p_result.add_argument("--score", required=True, help="如 2-1")

    # log-result（直接按队名录入动能日志，无需 match ID）
    p_log = subparsers.add_parser("log-result", help="直接录入赛事动能日志（适合补录）")
    p_log.add_argument("--team-a", required=True, help="A队名称")
    p_log.add_argument("--team-b", required=True, help="B队名称")
    p_log.add_argument("--stage", default="group_stage",
                       help="阶段: group_stage/round_of_16/quarterfinal/semifinal/final")
    p_log.add_argument("--result", required=True, help="A队结果: W/D/L")
    p_log.add_argument("--score", required=True, help="比分，如 2-1")
    p_log.add_argument("--xg-a", type=float, help="A队xG（可选）")
    p_log.add_argument("--xg-b", type=float, help="B队xG（可选）")

    # show-momentum（查看当前赛事动能概览）
    p_momentum = subparsers.add_parser("show-momentum", help="查看某队本届赛事动能")
    p_momentum.add_argument("--team", required=True, help="队伍名称")

    # html
    subparsers.add_parser("html", help="手动重新生成HTML")

    # schedule
    subparsers.add_parser("schedule", help="启动自动调度器")

    # serve
    p_serve = subparsers.add_parser("serve", help="启动本地HTTP服务器")
    p_serve.add_argument("--port", type=int, default=8080)

    args = parser.parse_args()

    if args.command == "predict":
        cmd_predict(args.match, args.round, args.label)
    elif args.command == "predict-all":
        cmd_predict_all()
    elif args.command == "result":
        cmd_record_result(args.match, args.outcome, args.score)
    elif args.command == "log-result":
        add_match_result(
            team_a=args.team_a,
            team_b=args.team_b,
            stage=args.stage,
            result_a=args.result,
            score=args.score,
            xg_a=args.xg_a,
            xg_b=args.xg_b,
        )
        print(f"✓ 已录入: {args.team_a} {args.score} {args.team_b}")
    elif args.command == "show-momentum":
        from agents.momentum_agent import format_team_log
        print(format_team_log(args.team))
    elif args.command == "html":
        update_html()
        print("✓ HTML 已更新")
    elif args.command == "schedule":
        from scheduler import run_scheduler
        run_scheduler()
    elif args.command == "serve":
        cmd_serve(args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
