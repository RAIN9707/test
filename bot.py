import os
import random
from collections import deque
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# 設定 LINE Bot 環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("請確保 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 已正確設定！")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 遊戲狀態
game_active = False
initial_balance = None
base_bet = 100
current_bet = 100
balance = None
saved_balance = None
round_count = 0
history = deque(maxlen=50)
remaining_cards = {i: 32 for i in range(10)}
previous_suggestion = "莊"

# 根據資金調整下注金額
def update_base_bet():
    global base_bet, current_bet, balance
    if balance < 2000:
        base_bet = 50
    elif balance < 5000:
        base_bet = 100
    elif balance < 10000:
        base_bet = 150
    elif balance < 20000:
        base_bet = 200
    else:
        base_bet = 300
    current_bet = base_bet

# 計算勝率
def calculate_win_probabilities():
    total_remaining = sum(remaining_cards.values())
    if total_remaining == 0:
        return 0.5068, 0.4932

    # 高牌：8和9，低牌：0到5，中牌：6和7
    high_cards = remaining_cards[8] + remaining_cards[9]
    low_cards = sum(remaining_cards[i] for i in range(6))
    mid_cards = remaining_cards[6] + remaining_cards[7]

    # 計算各類牌的比例
    high_card_ratio = high_cards / total_remaining
    low_card_ratio = low_cards / total_remaining
    mid_card_ratio = mid_cards / total_remaining

    # 根據牌比例調整莊家優勢
    banker_advantage = 0.5068
    banker_advantage += (high_card_ratio - low_card_ratio) * 0.05
    banker_advantage += mid_card_ratio * 0.02

    # 限制莊家優勢在合理範圍內
    banker_advantage = max(0.45, min(0.55, banker_advantage))

    return banker_advantage, 1 - banker_advantage

# 更新剩餘牌數
def update_remaining_cards(player_score, banker_score):
    global remaining_cards
    for card in [player_score, banker_score]:
        if card in remaining_cards and remaining_cards[card] > 0:
            remaining_cards[card] -= 1

# 下注策略
def calculate_best_bet(player_score, banker_score):
    global balance, current_bet, round_count, previous_suggestion, game_active

    # 更新剩餘牌數
    update_remaining_cards(player_score, banker_score)

    banker_prob, player_prob = calculate_win_probabilities()

    if player_score > banker_score:
        result = "閒家贏"
    elif banker_score > player_score:
        result = "莊家贏"
    else:
        result = "和局"

    bet_result = "❌ 錯誤"
    if previous_suggestion == "莊" and result == "莊家贏":
        balance += current_bet * 0.95
        bet_result = "✅ 正確"
    elif previous_suggestion == "閒" and result == "閒家贏":
        balance += current_bet
        bet_result = "✅ 正確"
    elif result == "和局":
        bet_result = "🔄 和局 - 本金不變"
    else:
        balance -= current_bet

    # 資金歸零，自動結束
    if balance <= 0:
        game_active = False
        return (
            f"📌 第 {round_count} 局結果：{result}\n"
            f"🎲 下注結果：{bet_result}\n"
            f"💵 剩餘資金：${balance}\n\n"
            "💸 資金已歸零，遊戲結束。請重新開始或增加資金。"
        )

    history.append({"局數": round_count, "結果": result, "下注": current_bet, "剩餘資金": balance})

    update_base_bet()

    if round_count == 1:
        previous_suggestion = "莊"
    else:
        previous_suggestion = "莊" if banker_prob > player_prob else "閒"

    return (
        f"📌 第 {round_count} 局結果：{result}\n"
        f"🎲 下注結果：{bet_result}\n"
        f"💵 剩餘資金：${balance}\n\n"
        f"✅ **第 {round_count + 1} 局下注建議**\n"
        f"🎯 下注目標：{previous_suggestion}\n"
        f"💰 下注金額：${current_bet}\n"
        f"📊 勝率分析：莊 {banker_prob*100:.2f}%, 閒 {player_prob*100:.2f}%"
    )

# Webhook
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK", 200

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global game_active, balance, base_bet, current_bet, round_count, initial_balance, saved_balance

    user_input = event.message.text.strip().lower()

    if not game_active and user_input != "開始":
        return

    if user_input == "開始":
        game_active = True
        round_count = 0
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入您的本金金額，例如：5000"))
        return

    elif user_input == "重置":
        game_active = False
        balance = None
        base
::contentReference[oaicite:0]{index=0}
 
