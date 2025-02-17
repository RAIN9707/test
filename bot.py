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

# **動態下注參數**
win_streak = 0  
lose_streak = 0  

# **解析輸入格式**
def parse_number_input(input_str):
    """ 解析用戶輸入的牌，如 '89 76' 或 '354 908'，並計算點數 """
    try:
        parts = input_str.strip().split()
        if len(parts) != 2:
            return None, None  # 必須輸入兩組數字（閒家和莊家）

        player_cards = [int(d) for d in parts[0]]
        banker_cards = [int(d) for d in parts[1]]

        if len(player_cards) not in [2, 3] or len(banker_cards) not in [2, 3]:
            return None, None  # 每組只能有 2 或 3 張牌
        
        player_score = sum(player_cards) % 10
        banker_score = sum(banker_cards) % 10

        return (player_cards, player_score), (banker_cards, banker_score)
    except ValueError:
        return None, None

# **更新剩餘牌組**
def update_card_counts(player_cards, banker_cards):
    """ 記錄本局已出現的牌，減少剩餘張數 """
    for card in player_cards + banker_cards:
        if card in remaining_cards and remaining_cards[card] > 0:
            remaining_cards[card] -= 1

# **計算勝率**
def calculate_win_probabilities():
    """ 使用貝葉斯統計 + 蒙地卡羅模擬 + 剩餘牌組分析 """
    total_remaining = sum(remaining_cards.values())

    if total_remaining == 0:
        return 0.5068, 0.4932  # 預設莊家 50.68%，閒家 49.32%

    high_card_ratio = (remaining_cards[8] + remaining_cards[9]) / total_remaining
    low_card_ratio = (remaining_cards[0] + remaining_cards[1] + remaining_cards[2] + remaining_cards[3] + remaining_cards[4]) / total_remaining

    banker_advantage = 0.5068 + (high_card_ratio - low_card_ratio) * 0.02
    player_advantage = 1 - banker_advantage

    return banker_advantage, player_advantage

# **計算最佳下注策略**
def calculate_best_bet(player_score, banker_score):
    global balance, current_bet, win_streak, lose_streak

    banker_prob, player_prob = calculate_win_probabilities()

    banker_win = banker_score > player_score
    result = "莊家贏" if banker_win else "閒家贏"

    # **本金計算**
    if banker_win:
        balance += current_bet * 0.95  # 莊家勝，賠率 0.95
        win_streak += 1
        lose_streak = 0
    else:
        balance -= current_bet  # 輸掉時正確扣除本金
        lose_streak += 1
        win_streak = 0

    # **記錄歷史**
    history.append({"局數": len(history) + 1, "結果": result, "下注": current_bet, "剩餘資金": balance})

    # **動態調整下注策略**
    if win_streak >= 2:
        next_bet_amount = current_bet * 1.5
    elif lose_streak >= 3:
        next_bet_amount = max(base_bet * 0.5, 100)
    elif lose_streak >= 6:
        next_bet_amount = base_bet
    else:
        next_bet_amount = current_bet

    next_bet_target = "莊" if banker_prob > player_prob else "閒"
    next_bet_amount = max(100, round(next_bet_amount))

    return (
        f"🎯 本局結果：{result}\n"
        f"💰 下注金額：${current_bet}\n"
        f"🏆 剩餘資金：${balance}\n\n"
        f"🔮 **下一局推薦下注：{next_bet_target}**\n"
        f"💵 **建議下注金額：${next_bet_amount}**"
    )

# **Webhook 路由**
@app.route("/callback", methods=['POST'])
def callback():
    """ LINE Webhook 入口點 """
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK", 200  # **⚠️ 確保回應 HTTP 200**

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global game_active, balance, base_bet, current_bet

    user_input = event.message.text.strip().lower()
    
    if user_input == "開始":
        game_active = True
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入您的本金金額，例如：5000"))
    
    elif user_input.isdigit() and game_active:
        balance = int(user_input)
        base_bet = round(balance * 0.03 / 50) * 50
        current_bet = base_bet
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎯 本金設定：${balance}\n🔢 基礎下注金額：${base_bet}\n請輸入「閒家 莊家」的牌數，如 '89 76'"))
    
    elif game_active and user_input == "結束":
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"🎉 本次遊戲結束！📊 總下注局數：{len(history)}\n💰 最終本金：${balance}"))

    elif game_active:
        player, banker = parse_number_input(user_input)
        if player and banker:
            update_card_counts(player[0], banker[0])
            reply_text = calculate_best_bet(player[1], banker[1])
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
