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
base_bet = None
current_bet = None
balance = None
total_wins = 0
total_losses = 0
round_count = 0
history = deque(maxlen=50)
remaining_cards = {i: 32 for i in range(10)}
previous_suggestion = None  
next_bet_amount = None  

# **優化勝率計算**
def calculate_win_probabilities():
    total_remaining = sum(remaining_cards.values())
    if total_remaining == 0:
        return 0.5068, 0.4932  

    high_card_ratio = (remaining_cards[8] + remaining_cards[9]) / total_remaining
    low_card_ratio = sum(remaining_cards[i] for i in range(6)) / total_remaining
    neutral_card_ratio = (remaining_cards[6] + remaining_cards[7]) / total_remaining

    trend_factor = sum(1 if h["結果"] == "莊家贏" else -1 if h["結果"] == "閒家贏" else 0 for h in history) / len(history) if history else 0

    banker_advantage = 0.5068 + (high_card_ratio - low_card_ratio) * 0.02 + (neutral_card_ratio * 0.01) + (trend_factor * 0.015)

    # **增加隨機變數，讓勝率計算更靈活**
    variance = random.uniform(-0.015, 0.015)
    banker_advantage = max(0.48, min(0.52, banker_advantage + variance))  # 限制範圍在 48%~52% 避免極端
    return banker_advantage, 1 - banker_advantage

# **更均衡的下注策略**
def calculate_best_bet(player_score, banker_score):
    global balance, current_bet, total_wins, total_losses, round_count, previous_suggestion, next_bet_amount

    banker_prob, player_prob = calculate_win_probabilities()

    if player_score > banker_score:
        result = "閒家贏"
        total_wins += 1
    elif banker_score > player_score:
        result = "莊家贏"
        total_losses += 1
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

    history.append({"局數": round_count, "結果": result, "下注": current_bet, "剩餘資金": balance})

    # **調整下注方向，使其更均衡**
    if banker_prob > player_prob:
        if random.random() > 0.6:  # 增加 40% 閒家下注機率
            previous_suggestion = "閒"
        else:
            previous_suggestion = "莊"
    else:
        if random.random() > 0.6:  # 增加 40% 莊家下注機率
            previous_suggestion = "莊"
        else:
            previous_suggestion = "閒"

    # **計算下一局下注金額**
    if round_count == 1:
        next_bet_amount = base_bet  
    else:
        if total_losses >= 3:
            next_bet_amount = base_bet
        elif total_wins >= 2:
            next_bet_amount = current_bet * (1.5 if previous_suggestion == "莊" else 1.75)
        else:
            next_bet_amount = current_bet * (1.25 if previous_suggestion == "莊" else 1.5)

    next_bet_amount = round(next_bet_amount / 50) * 50  
    current_bet = next_bet_amount  

    if round_count == 1:
        return (
            f"📌 第 1 局結果：{result}（僅記錄，不下注）\n\n"
            f"✅ **第 2 局下注建議**\n"
            f"🎯 下注目標：{previous_suggestion}\n"
            f"💰 下注金額：${next_bet_amount}"
        )

    return (
        f"📌 第 {round_count} 局結果：{result}\n"
        f"🎲 下注結果：{bet_result}\n"
        f"💰 下注金額：${current_bet}\n"
        f"💵 剩餘資金：${balance}\n\n"
        f"✅ **第 {round_count + 1} 局下注建議**\n"
        f"🎯 下注目標：{previous_suggestion}\n"
        f"💰 下注金額：${next_bet_amount}"
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
    global game_active, balance, base_bet, current_bet, total_wins, total_losses, round_count, initial_balance

    user_input = event.message.text.strip().lower()

    if user_input == "開始":
        game_active = True
        round_count = 0  
        if balance is not None:
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"使用上次剩餘資金 ${balance}\n請輸入「閒家 莊家」的點數，如 '8 9'"))
        else:
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入您的本金金額，例如：5000"))

    elif user_input == "從頭開始":
        game_active = True
        balance = None
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入您的本金金額，例如：5000"))

    elif user_input.isdigit() and game_active:
        balance = int(user_input)
        initial_balance = balance
        base_bet = round(balance * 0.03 / 50) * 50
        current_bet = 0  
        round_count = 0  
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"本金設定：${balance}\n第一局不下注，請輸入「閒家 莊家」的點數，如 '8 9'"))

    elif game_active and user_input == "結束":
        result_text = f"💵 本次遊戲結束，剩餘資金：${balance}"
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result_text))

    elif game_active:
        try:
            round_count += 1
            player_score, banker_score = map(int, user_input.split())

            if round_count == 2:  
                current_bet = base_bet

            reply_text = calculate_best_bet(player_score, banker_score)
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        except:
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text="輸入格式錯誤，請重新輸入，例如 '8 9'"))