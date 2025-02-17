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
total_wins = 0
total_losses = 0
history = deque(maxlen=50)
remaining_cards = {i: 32 for i in range(10)}

# **補牌規則影響計算**
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

# **勝率計算**
def calculate_win_probabilities(player_cards, banker_cards):
    total_remaining = sum(remaining_cards.values())
    if total_remaining == 0:
        return 0.5068, 0.4932

    high_card_ratio = (remaining_cards[8] + remaining_cards[9]) / total_remaining
    low_card_ratio = sum(remaining_cards[i] for i in range(5)) / total_remaining
    trend_factor = sum(1 if h["結果"] == "莊家贏" else -1 for h in history) / len(history) if history else 0
    banker_advantage = 0.5068 + (high_card_ratio - low_card_ratio) * 0.02 + (trend_factor * 0.01)

    # **加入補牌影響**
    player_third_card = player_cards[2] if len(player_cards) == 3 else None
    if should_banker_draw(sum(banker_cards) % 10, player_third_card):
        banker_advantage += 0.02  
    else:
        banker_advantage -= 0.02

    return banker_advantage, 1 - banker_advantage

# **下注策略**
def calculate_best_bet(player_cards, banker_cards):
    global balance, current_bet, total_wins, total_losses
    banker_prob, player_prob = calculate_win_probabilities(player_cards, banker_cards)

    player_score = sum(player_cards) % 10
    banker_score = sum(banker_cards) % 10

    if player_score > banker_score:
        result = "閒家贏"
        balance += current_bet
        total_wins += 1
    elif banker_score > player_score:
        result = "莊家贏"
        balance += current_bet * 0.95
        total_wins += 1
    else:
        result = "和局"

    history.append({"局數": len(history) + 1, "結果": result, "下注": current_bet, "剩餘資金": balance})

    next_bet_amount = base_bet if total_losses >= 3 else current_bet * 1.75 if total_wins >= 2 else current_bet
    next_bet_amount = round(next_bet_amount / 50) * 50  

    return (
        f"本局結果：{result}\n"
        f"下注金額：${current_bet}\n"
        f"剩餘資金：${balance}\n\n"
        f"下一局推薦下注：{'莊' if banker_prob > player_prob else '閒'}\n"
        f"建議下注金額：${next_bet_amount}"
    )

# **模擬 10,000 局**
def simulate_games(trials=10000):
    temp_balance = initial_balance
    wins, losses = 0, 0
    temp_bet = base_bet

    for _ in range(trials):
        player_cards = [random.randint(0, 9), random.randint(0, 9)]
        banker_cards = [random.randint(0, 9), random.randint(0, 9)]

        if should_banker_draw(sum(banker_cards) % 10, player_cards[1]):
            banker_cards.append(random.randint(0, 9))

        player_score = sum(player_cards) % 10
        banker_score = sum(banker_cards) % 10

        if player_score > banker_score:
            temp_balance += temp_bet
            wins += 1
        elif banker_score > player_score:
            temp_balance += temp_bet * 0.95
            wins += 1
        else:
            continue  

        temp_bet = base_bet if losses >= 3 else temp_bet * 1.75 if wins >= 2 else temp_bet
        temp_bet = round(temp_bet / 50) * 50  

    profit = temp_balance - initial_balance
    return f"模擬 10,000 局結果：\n勝率：{(wins/trials)*100:.2f}%\n最終本金：${temp_balance}\n盈虧變化：${profit}"

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
    global game_active, balance, base_bet, current_bet, total_wins, total_losses

    user_input = event.message.text.strip().lower()

    if user_input == "開始":
        game_active = True
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入您的本金金額，例如：5000"))

    elif user_input.isdigit() and game_active:
        balance = int(user_input)
        base_bet = round(balance * 0.03 / 50) * 50
        current_bet = base_bet
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"本金設定：${balance}\n基礎下注金額：${base_bet}\n請輸入「閒家 莊家」的牌數，如 '89 76'"))

    elif user_input == "模擬":
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=simulate_games()))

    elif game_active and user_input == "結束":
        total_games = len(history)
        profit = balance - initial_balance
        return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"總局數：{total_games}\n勝場數：{total_wins}\n敗場數：{total_losses}\n勝率：{(total_wins/total_games)*100:.2f}%\n盈虧金額：${profit}\n最終資本金：${balance}"))

    elif game_active:
        player, banker = parse_number_input(user_input)
        if player and banker:
            reply_text = calculate_best_bet(player[0], banker[0])
            return line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
