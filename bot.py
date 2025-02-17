import os
import random
import numpy as np
from collections import deque
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# **環境變數**
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# **撲克牌計數（8 副牌，共 416 張，每個數字 32 張）**
card_counts = {i: 32 for i in range(10)}
total_cards = sum(card_counts.values())

# **動態下注參數**
initial_balance = None  # 使用者輸入的本金
base_bet = None  # 動態計算基礎下注金額
min_bet = 100  
current_bet = None
balance = None
win_streak = 0  
lose_streak = 0  
history = deque(maxlen=20)  

# **獲利鎖定與回撤保護**
profit_target = None  
loss_threshold = None  
recovery_threshold = None  

# **更新剩餘牌組**
def update_card_counts(*drawn_cards):
    global total_cards
    for card in drawn_cards:
        if card is not None and card_counts[card] > 0:
            card_counts[card] -= 1
            total_cards -= 1

# **補牌規則計算**
def should_banker_draw(banker_score, player_third_card):
    if player_third_card is None:
        return banker_score <= 5
    if banker_score <= 2:
        return True
    elif banker_score == 3 and player_third_card != 8:
        return True
    elif banker_score == 4 and player_third_card in [2, 3, 4, 5, 6, 7]:
        return True
    elif banker_score == 5 and player_third_card in [4, 5, 6, 7]:
        return True
    elif banker_score == 6 and player_third_card in [6, 7]:
        return True
    return False

# **分析剩餘牌組影響勝率**
def analyze_card_counts():
    if total_cards == 0:
        return 0.5068, 0.4932  

    high_cards = sum(card_counts[i] for i in [8, 9]) / total_cards
    low_cards = sum(card_counts[i] for i in [0, 1, 2, 3, 4, 5]) / total_cards

    banker_advantage = 0.5068 + (high_cards - low_cards) * 0.02
    player_advantage = 1 - banker_advantage

    return banker_advantage, player_advantage

# **最近 10 局勝率分析**
def analyze_recent_trends():
    banker_wins = sum(1 for h in history if h["結果"] == "banker_win")
    player_wins = sum(1 for h in history if h["結果"] == "player_win")

    if len(history) < 10:
        return 0.5068, 0.4932  

    trend_banker = banker_wins / len(history)
    trend_player = player_wins / len(history)

    return trend_banker, trend_player

# **更新下注金額**
def update_bet():
    global current_bet, win_streak, lose_streak, balance

    if balance >= profit_target:
        current_bet = min(balance * 0.05, current_bet)
    elif balance <= loss_threshold:
        current_bet = max(min_bet, base_bet * 0.5)
    elif balance >= recovery_threshold:
        current_bet = base_bet
    else:
        if win_streak >= 2:
            current_bet += 50  
        if lose_streak == 3:
            current_bet = max(base_bet * 0.75, min_bet)  
        if lose_streak >= 6:
            current_bet = base_bet  

# **計算最佳下注**
def calculate_best_bet():
    global balance, win_streak, lose_streak

    banker_prob, player_prob = analyze_card_counts()
    trend_banker, trend_player = analyze_recent_trends()

    final_banker_prob = (banker_prob + trend_banker) / 2
    final_player_prob = (player_prob + trend_player) / 2

    banker_win = random.random() < final_banker_prob  
    player_win = not banker_win  

    result = "banker_win" if banker_win else "player_win"
    balance += current_bet * (0.95 if banker_win else 1)
    win_streak = win_streak + 1 if banker_win else 0
    lose_streak = lose_streak + 1 if not banker_win else 0

    history.append({
        "結果": result,
        "下注金額": current_bet,
        "剩餘資金": balance
    })

    update_bet()

    return f"🎯 最佳下注：{result.upper()} \n💰 下注金額：${current_bet} \n💵 剩餘資金：${balance}"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global initial_balance, balance, base_bet, current_bet, profit_target, loss_threshold, recovery_threshold

    user_input = event.message.text.strip().lower()
    
    if user_input == "開始":
        reply_text = "請輸入您的本金金額，例如：5000"
    elif user_input.isdigit():
        initial_balance = int(user_input)
        balance = initial_balance
        base_bet = round((initial_balance * 0.03) / 50) * 50
        current_bet = base_bet
        profit_target = initial_balance * 2
        loss_threshold = initial_balance * 0.6
        recovery_threshold = initial_balance * 0.8
        reply_text = f"🎯 設定成功！\n💰 本金：${initial_balance}\n🃏 建議單注金額：${base_bet}\n請輸入「下注」開始！"
    elif user_input == "下注":
        best_bet = calculate_best_bet()
        reply_text = best_bet
    elif user_input == "結束":
        reply_text = f"🎉 遊戲結束！\n💰 最終資本金額：${balance}\n📈 歷史記錄：{len(history)} 局"
    else:
        reply_text = "請輸入「開始」來設定本金，或「下注」來計算最佳下注策略！"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
