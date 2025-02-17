import os
import random
import numpy as np
from scipy.stats import beta
from collections import deque
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# **設定 LINE Bot 環境變數**
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("請確保 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 已正確設定！")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# **遊戲狀態**
game_active = False
initial_balance = None
base_bet = None
current_bet = None
balance = None
history = deque(maxlen=50)  # 記錄最多 50 局
remaining_cards = {i: 32 for i in range(10)}  # 8副牌，共416張，每個數字32張
waiting_for_player = False
waiting_for_banker = False
last_player_score = None  # 記錄閒家計算後的點數

# **貝葉斯機率計算**
alpha_banker = 1
beta_banker = 1
alpha_player = 1
beta_player = 1

# **動態下注參數**
win_streak = 0  
lose_streak = 0  

# **解析數字輸入**
def parse_number_input(input_str):
    """ 解析用戶輸入的數字，如 '89' 或 '354'，並計算最終點數 """
    try:
        numbers = [int(digit) for digit in input_str.strip()]
        if len(numbers) not in [2, 3]:
            return None, None  # 只能輸入2或3個數字
        
        final_score = sum(numbers) % 10  # 百家樂點數計算
        return numbers, final_score
    except ValueError:
        return None, None

# **更新剩餘牌組**
def update_card_counts(cards):
    """ 記錄本局已出現的牌，減少剩餘張數 """
    for card in cards:
        if card in remaining_cards and remaining_cards[card] > 0:
            remaining_cards[card] -= 1

# **貝葉斯更新**
def bayesian_update(alpha, beta, history, wins):
    """ 使用貝葉斯更新機率，調整下注方向 """
    return beta.rvs(alpha + wins, beta + (len(history) - wins))

# **蒙地卡羅模擬**
def monte_carlo_simulation(trials=10000):
    """ 使用蒙地卡羅模擬計算莊家和閒家獲勝機率 """
    banker_wins = 0
    player_wins = 0

    for _ in range(trials):
        banker_prob, player_prob = calculate_win_probabilities()
        if random.random() < banker_prob:
            banker_wins += 1
        else:
            player_wins += 1

    return banker_wins / trials, player_wins / trials

# **計算勝率**
def calculate_win_probabilities():
    """ 根據剩餘牌組計算莊家與閒家的勝率變化 """
    total_remaining = sum(remaining_cards.values())

    if total_remaining == 0:
        return 0.5068, 0.4932  # 預設莊家 50.68%，閒家 49.32%

    high_card_ratio = (remaining_cards[8] + remaining_cards[9]) / total_remaining
    low_card_ratio = (remaining_cards[0] + remaining_cards[1] + remaining_cards[2] + remaining_cards[3] + remaining_cards[4]) / total_remaining

    banker_advantage = 0.5068 + (high_card_ratio - low_card_ratio) * 0.02
    player_advantage = 1 - banker_advantage

    return banker_advantage, player_advantage

# **計算下注策略**
def calculate_best_bet(player_score, banker_score):
    global balance, current_bet, win_streak, lose_streak

    banker_prob, player_prob = monte_carlo_simulation()

    banker_win = random.random() < banker_prob  
    player_win = not banker_win  

    result = "莊家贏" if banker_win else "閒家贏"
    win_multiplier = 0.95 if banker_win else 1  

    balance += current_bet * win_multiplier
    win_streak = win_streak + 1 if banker_win else 0
    lose_streak = lose_streak + 1 if not banker_win else 0

    history.append({"局數": len(history) + 1, "結果": result, "下注": current_bet, "剩餘資金": balance})

    # **動態調整下注策略**
    next_bet_target = "莊" if banker_prob > player_prob else "閒"
    next_bet_amount = current_bet

    if win_streak >= 2:
        next_bet_amount *= 1.5  # 連勝增加下注
    elif lose_streak >= 3:
        next_bet_amount *= 0.7  # 連輸降低風險

    next_bet_amount = max(100, round(next_bet_amount))

    return (
        f"🎯 本局結果：{result}\n"
        f"💰 下注金額：${current_bet}\n"
        f"🏆 剩餘資金：${balance}\n\n"
        f"🔮 **下一局推薦下注：{next_bet_target}**\n"
        f"💵 **建議下注金額：${next_bet_amount}**"
    )

# **處理 Webhook**
@app.route("/callback", methods=['POST'])
def callback():
    """ LINE Webhook 入口點，處理來自 LINE 的請求 """
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK", 200  # **⚠️ 確保回應 HTTP 200**

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global game_active, waiting_for_player, waiting_for_banker, last_player_score

    user_input = event.message.text.strip().lower()
    
    if user_input == "開始":
        game_active = True
        waiting_for_player = True
        reply_text = "請輸入您的本金金額，例如：5000"
    elif user_input.isdigit() and game_active:
        last_player_score = int(user_input)
        waiting_for_player = False
        waiting_for_banker = True
        reply_text = "請輸入**莊家發牌**（如：67 或 805）"
    elif waiting_for_banker:
        _, banker_score = parse_number_input(user_input)
        if banker_score is not None:
            waiting_for_banker = False
            reply_text = calculate_best_bet(last_player_score, banker_score)
        else:
            reply_text = "❌ 請輸入正確的莊家數字"
    else:
        reply_text = "請輸入「開始」來設定本金"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
