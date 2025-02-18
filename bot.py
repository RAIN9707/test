import os
import random
import numpy as np
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
base_bet = 100  
current_bet = 100  
balance = None  
saved_balance = None  
round_count = 0  
win_streak = 0
lose_streak = 0
history = deque(maxlen=50)
remaining_cards = {i: 32 for i in range(10)}
previous_suggestion = "莊"  

# **根據資金調整下注金額**
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

# **計算勝率**
def calculate_win_probabilities():
    total_remaining = sum(remaining_cards.values())
    if total_remaining == 0:
        return 0.5068, 0.4932, 0.00  

    high_card_ratio = (remaining_cards[8] + remaining_cards[9]) / total_remaining
    low_card_ratio = sum(remaining_cards[i] for i in range(6)) / total_remaining
    neutral_card_ratio = (remaining_cards[6] + remaining_cards[7]) / total_remaining

    trend_factor = sum(1 if h["結果"] == "莊家贏" else -1 if h["結果"] == "閒家贏" else 0 for h in history) / len(history) if history else 0

    banker_advantage = 0.5068 + (high_card_ratio - low_card_ratio) * 0.02 + (neutral_card_ratio * 0.01) + (trend_factor * 0.015)
    variance = random.uniform(-0.015, 0.015)
    banker_advantage = max(0.47, min(0.53, banker_advantage + variance))  
    tie_probability = 1 - (banker_advantage + (1 - banker_advantage))
    
    return banker_advantage, 1 - banker_advantage - tie_probability, tie_probability

# **下注策略**
def calculate_best_bet(player_score, banker_score):
    global balance, current_bet, round_count, previous_suggestion, game_active, win_streak, lose_streak

    banker_prob, player_prob, tie_prob = calculate_win_probabilities()

    if player_score > banker_score:
        result = "閒家贏"
        win_streak += 1
        lose_streak = 0
    elif banker_score > player_score:
        result = "莊家贏"
        win_streak = 0
        lose_streak += 1
    else:
        result = "和局"
        win_streak = 0
        lose_streak = 0

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

    if balance <= 0:
        game_active = False
        return "💸 你也太爛了吧！"

    history.append({"局數": round_count, "結果": result, "下注": current_bet, "剩餘資金": balance})

    update_base_bet()

    if banker_prob > 0.57:
        previous_suggestion = "莊"
    elif player_prob > 0.57:
        previous_suggestion = "閒"
    else:
        previous_suggestion = "莊" if banker_prob > player_prob else "閒"

    if lose_streak >= 4:
        current_bet = base_bet  

    return (
        f"📌 第 {round_count} 局結果：{result}\n"
        f"🎲 下注結果：{bet_result}\n"
        f"💵 剩餘資金：${balance}\n\n"
        f"✅ **第 {round_count + 1} 局下注建議**\n"
        f"🎯 下注目標：{previous_suggestion}\n"
        f"💰 下注金額：${current_bet}\n"
        f"📊 勝率分析：莊 {banker_prob*100:.2f}%, 閒 {player_prob*100:.2f}%, 和 {tie_prob*100:.2f}%"
    )

# **Webhook**
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
        base_bet = 100  
        current_bet = 100  
        previous_suggestion = "莊"  
        history.clear()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已重置系統，請輸入『開始』來重新設定本金"))
        return

    elif user_input == "結束":
        game_active = False
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🎉 期待下次再來賺錢！"))
        return

    elif game_active:
        try:
            round_count += 1
            player_score, banker_score = map(int, user_input.split())
            reply_text = calculate_best_bet(player_score, banker_score)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        except:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 輸入錯誤，請輸入『閒家 莊家』的點數，如 '8 9'"))
