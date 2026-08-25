import socket
import random
import time
import threading
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

HOST = "0.0.0.0"
PORT = 5000

def get_local_ip():
    """获取教师机局域网 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

# ============================================================
# 全局对战状态
# ============================================================
game = {
    "started": False,
    "finished": False,
    "round": 0,
    "players": {},          # { id: { name, status, opponent, choice, round, last_bye_round } }
    "matches": [],          # 当前轮次对局
    "all_matches": [],      # 历史所有对局
    "bye_records": [],      # 轮空记录 [{ round, player_id, player_name }]
    "current_winners": [],  # 晋级候选池
    "champion": None,
    "created_at": None,
}

lock = threading.Lock()

def create_player_id():
    return f"player_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

def get_player_name(player_id):
    if not player_id:
        return "未知"
    player = game["players"].get(player_id)
    return player["name"] if player else "未知"

def judge(c1, c2):
    if c1 == c2:
        return 0
    if (
        (c1 == "rock" and c2 == "scissors") or
        (c1 == "scissors" and c2 == "paper") or
        (c1 == "paper" and c2 == "rock")
    ):
        return 1
    return 2

def reset_game():
    game["started"] = True
    game["finished"] = False
    game["round"] = 0
    game["players"] = {}
    game["matches"] = []
    game["all_matches"] = []
    game["bye_records"] = []
    game["current_winners"] = []
    game["champion"] = None
    game["created_at"] = time.time()

def create_player(name):
    player_id = create_player_id()
    game["players"][player_id] = {
        "id": player_id,
        "name": name,
        "status": "waiting",
        "opponent": None,
        "choice": None,
        "round": 0,
        "last_bye_round": -1,  # 记录上一次轮空的轮次
        "joined_at": time.time(),
    }
    return player_id

def start_tournament():
    waiting_players = [pid for pid, p in game["players"].items() if p["status"] == "waiting"]
    if len(waiting_players) < 2:
        return False

    game["round"] = 0
    game["current_winners"] = waiting_players
    create_next_round()
    return True

def select_bye_player(candidates, current_round):
    """
    严禁连续轮空选择策略：
    优先在上一轮没有轮空（last_bye_round != current_round - 1）的候选人中随机挑选。
    """
    eligible = [pid for pid in candidates if game["players"][pid].get("last_bye_round", -1) != (current_round - 1)]
    if not eligible:
        eligible = candidates  # 极端兜底（例如人数极少）
    return random.choice(eligible)

def create_next_round():
    candidates = list(game["current_winners"])
    game["current_winners"] = []

    # 1. 决出全场总冠军
    if len(candidates) == 1:
        champion_id = candidates[0]
        game["champion"] = champion_id
        game["finished"] = True
        game["started"] = False
        game["matches"] = []
        game["players"][champion_id]["status"] = "champion"
        game["players"][champion_id]["opponent"] = None
        return

    if len(candidates) == 0:
        game["finished"] = True
        game["started"] = False
        return

    game["round"] += 1
    game["matches"] = []
    
    # 2. 单数人员挑选轮空（保证不连续轮空）
    bye_player = None
    if len(candidates) % 2 == 1:
        bye_player = select_bye_player(candidates, game["round"])
        candidates.remove(bye_player)
        
        game["players"][bye_player]["status"] = "bye"
        game["players"][bye_player]["opponent"] = None
        game["players"][bye_player]["choice"] = None
        game["players"][bye_player]["round"] = game["round"]
        game["players"][bye_player]["last_bye_round"] = game["round"]
        
        game["bye_records"].append({
            "round": game["round"],
            "player_id": bye_player,
            "player_name": get_player_name(bye_player)
        })
        game["current_winners"].append(bye_player)

    # 3. 剩余选手随机配对
    random.shuffle(candidates)
    for i in range(0, len(candidates), 2):
        p1 = candidates[i]
        p2 = candidates[i + 1]
        match_id = f"R{game['round']}_M{len(game['matches']) + 1}"

        match = {
            "id": match_id,
            "round": game["round"],
            "player1": p1,
            "player2": p2,
            "choice1": None,
            "choice2": None,
            "winner": None,
            "status": "waiting",
            "created_at": time.time(),
        }
        game["matches"].append(match)
        game["all_matches"].append(match)

        for cur_p, opp_p in [(p1, p2), (p2, p1)]:
            game["players"][cur_p]["status"] = "playing"
            game["players"][cur_p]["opponent"] = opp_p
            game["players"][cur_p]["choice"] = None
            game["players"][cur_p]["round"] = game["round"]

    if bye_player and len(game["matches"]) == 0:
        create_next_round()

def check_round_finished():
    if len(game["matches"]) == 0:
        return True
    return all(match["status"] == "finished" for match in game["matches"])

def get_bracket_data():
    rounds_data = {}
    max_round = max(game["round"], 1)
    for r in range(1, max_round + 1):
        rounds_data[r] = {
            "round": r,
            "matches": [],
            "byes": []
        }

    for m in game["all_matches"]:
        r = m["round"]
        if r in rounds_data:
            rounds_data[r]["matches"].append({
                "id": m["id"],
                "player1": get_player_name(m["player1"]),
                "player2": get_player_name(m["player2"]),
                "winner": get_player_name(m["winner"]) if m["winner"] else None,
                "status": m["status"]
            })

    for b in game["bye_records"]:
        r = b["round"]
        if r in rounds_data:
            rounds_data[r]["byes"].append(b["player_name"])

    return {
        "max_round": game["round"],
        "rounds": list(rounds_data.values()),
        "champion": get_player_name(game["champion"]) if game["champion"] else None
    }

# ============================================================
# API 路由
# ============================================================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/game")
def game_page():
    return render_template("game.html")

@app.route("/teacher")
def teacher():
    local_ip = get_local_ip()
    student_url = f"http://{local_ip}:{PORT}/"
    return render_template("teacher.html", student_url=student_url)

@app.route("/api/teacher/start", methods=["POST"])
def teacher_start():
    with lock:
        reset_game()
        return jsonify({"success": True, "message": "新房间已重置开启，请等待学生加入"})

@app.route("/api/teacher/begin_match", methods=["POST"])
def teacher_begin_match():
    with lock:
        if not game["started"] or game["finished"]:
            return jsonify({"success": False, "message": "房间尚未创建或已结束"})
        if game["round"] > 0:
            return jsonify({"success": False, "message": "淘汰赛已在进行中"})
        if len(game["players"]) < 2:
            return jsonify({"success": False, "message": "至少需要 2 名选手才能开始"})

        start_tournament()
        return jsonify({"success": True, "message": "淘汰赛对阵图已生成并开启第 1 轮！"})

@app.route("/api/teacher/stop", methods=["POST"])
def teacher_stop():
    with lock:
        game["started"] = False
        game["finished"] = True
        return jsonify({"success": True, "message": "比赛已终止"})

@app.route("/api/join", methods=["POST"])
def join_game():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()

    if not name:
        return jsonify({"success": False, "message": "请输入姓名"})
    if len(name) > 20:
        return jsonify({"success": False, "message": "姓名不能超过20个字符"})

    with lock:
        if not game["started"]:
            return jsonify({"success": False, "message": "教师尚未开启新房间"})
        if game["finished"]:
            return jsonify({"success": False, "message": "本次比赛已结束"})
        if game["round"] > 0:
            return jsonify({"success": False, "message": "比赛已封线开打，无法中途加入"})

        player_id = create_player(name)
        return jsonify({
            "success": True,
            "player_id": player_id,
            "name": name,
            "message": "报名成功",
        })

@app.route("/api/player/<player_id>", methods=["GET"])
def player_status(player_id):
    with lock:
        if player_id not in game["players"]:
            return jsonify({"success": False, "message": "玩家不存在"})

        player = game["players"][player_id]
        current_match = next(
            (m for m in game["matches"] if m["player1"] == player_id or m["player2"] == player_id),
            None
        )

        return jsonify({
            "success": True,
            "game_started": game["started"],
            "game_finished": game["finished"],
            "round": game["round"],
            "champion": get_player_name(game["champion"]) if game["champion"] else None,
            "player": {
                "id": player["id"],
                "name": player["name"],
                "status": player["status"],
                "opponent": get_player_name(player["opponent"]) if player["opponent"] else None,
                "choice": player["choice"],
                "round": player["round"],
            },
            "match": current_match,
            "bracket": get_bracket_data()
        })

@app.route("/api/play", methods=["POST"])
def player_play():
    data = request.get_json(silent=True) or {}
    player_id = data.get("player_id")
    choice = data.get("choice")

    if choice not in ["rock", "paper", "scissors"]:
        return jsonify({"success": False, "message": "无效的出拳"})

    with lock:
        if player_id not in game["players"]:
            return jsonify({"success": False, "message": "玩家不存在"})

        player = game["players"][player_id]
        if not game["started"] or game["finished"]:
            return jsonify({"success": False, "message": "比赛已结束"})
        if player["status"] != "playing":
            return jsonify({"success": False, "message": "当前不可出拳"})
        if player["choice"] is not None:
            return jsonify({"success": False, "message": "您已出拳，请耐心等待对方"})

        current_match = next(
            (m for m in game["matches"] if m["player1"] == player_id or m["player2"] == player_id),
            None
        )
        if not current_match or current_match["status"] == "finished":
            return jsonify({"success": False, "message": "对局已结束"})

        player["choice"] = choice
        if current_match["player1"] == player_id:
            current_match["choice1"] = choice
        else:
            current_match["choice2"] = choice

        if current_match["choice1"] is None or current_match["choice2"] is None:
            return jsonify({"success": True, "result": "waiting", "message": "已出拳，等待对手"})

        res = judge(current_match["choice1"], current_match["choice2"])

        if res == 0:
            current_match["choice1"] = None
            current_match["choice2"] = None
            game["players"][current_match["player1"]]["choice"] = None
            game["players"][current_match["player2"]]["choice"] = None
            return jsonify({"success": True, "result": "draw", "message": "平局！请重新出拳"})

        winner_id = current_match["player1"] if res == 1 else current_match["player2"]
        loser_id = current_match["player2"] if res == 1 else current_match["player1"]

        current_match["winner"] = winner_id
        current_match["status"] = "finished"

        game["players"][winner_id]["status"] = "winner"
        game["players"][winner_id]["choice"] = None
        game["players"][loser_id]["status"] = "eliminated"
        game["players"][loser_id]["choice"] = None

        if winner_id not in game["current_winners"]:
            game["current_winners"].append(winner_id)

        if check_round_finished():
            create_next_round()

        return jsonify({
            "success": True,
            "result": "win" if winner_id == player_id else "lose",
            "winner": winner_id,
            "message": "晋级成功！" if winner_id == player_id else "被淘汰",
        })

@app.route("/api/teacher/status", methods=["GET"])
def teacher_status():
    with lock:
        players = [{
            "id": p["id"],
            "name": p["name"],
            "status": p["status"],
            "opponent": get_player_name(p["opponent"]) if p["opponent"] else None,
            "round": p["round"],
        } for p in game["players"].values()]

        matches = [{
            "id": m["id"],
            "round": m["round"],
            "player1": get_player_name(m["player1"]),
            "player2": get_player_name(m["player2"]),
            "status": m["status"],
            "winner": get_player_name(m["winner"]) if m["winner"] else None,
        } for m in game["matches"]]

        return jsonify({
            "started": game["started"],
            "finished": game["finished"],
            "round": game["round"],
            "player_count": len(game["players"]),
            "match_count": len(game["matches"]),
            "players": players,
            "matches": matches,
            "champion": get_player_name(game["champion"]) if game["champion"] else None,
            "bracket": get_bracket_data()
        })

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)