import os
import random
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

# **遊戲狀態**
game_active = False
initial_balance = None
base_bet = None
current_bet = None
balance = None
history = deque(maxlen=50)  # 記錄最多 50 局
remaining_cards = {i: 32 for i in range(10)}  # 8副牌，共416張，每個數字32張

# **獲利鎖定與回撤保護**
profit_target = None  
loss_threshold = None  
recovery_threshold = None  

# **撲克牌對應數值**
card_values = {
    "A": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, 
    "10": 0, "J": 0, "Q": 0, "K": 0
}

# **更新剩餘牌組**
def update_card_counts(cards):
    """ 記錄本局已出現的牌，減少剩餘張數 """
    for card in cards:
        value = card_values.get(card.upper(), None)
        if value is not None and remaining_cards[value] > 0:
            remaining_cards[value] -= 1

# **解析牌輸入**
def parse_card_input(input_str):
    """ 解析用戶輸入的莊家與閒家牌，如 'AJ / K8J' """
    try:
        parts = input_str.split("/")
        if len(parts) != 2:
            return None, None
        
        player_cards = parts[0].strip().upper()
        banker_cards = parts[1].strip().upper()

        # 計算點數
        player_score = sum(card_values.get(card, 0) for card in player_cards) % 10
        banker_score = sum(card_values.get(card, 0) for card in banker_cards) % 10

        # 更新剩餘牌組
        update_card_counts(player_cards)
        update_card_counts(banker_cards)

        return player_score, banker_score
    except Exception:
        return None, None

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
    global balance, current_bet

    banker_prob, player_prob = calculate_win_probabilities()

    banker_win = random.random() < banker_prob  
    player_win = not banker_win  

    result = "莊家贏" if banker_win else "閒家贏"
    win_multiplier = 0.95 if banker_win else 1  

    balance += current_bet * win_multiplier
    history.append({"局數": len(history) + 1, "結果": result, "下注": current_bet, "剩餘資金": balance})

    return f"🎯 本局結果：{result}\n💰 下注金額：${current_bet}\n🏆 剩餘資金：${balance}"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global game_active, initial_balance, balance, base_bet, current_bet, profit_target, loss_threshold, recovery_threshold

    user_input = event.message.text.strip().lower()
    
    if user_input == "開始":
        game_active = True
        reply_text = "請輸入您的本金金額，例如：5000"
    elif user_input.isdigit() and game_active and initial_balance is None:
        initial_balance = int(user_input)
        balance = initial_balance
        base_bet = round((initial_balance * 0.03) / 50) * 50  # 計算最佳單注金額
        current_bet = base_bet
        profit_target = initial_balance * 2
        loss_threshold = initial_balance * 0.6
        recovery_threshold = initial_balance * 0.8
        reply_text = f"🎯 設定成功！\n💰 本金：${initial_balance}\n🃏 建議單注金額：${base_bet}\n請輸入莊家與閒家的發牌（格式：AJ / K8J）"
    elif user_input == "結束":
        game_active = False
        win_count = sum(1 for h in history if h["結果"] == "莊家贏")
        lose_count = len(history) - win_count
        reply_text = f"🎉 遊戲結束！\n💰 最終資本金額：${balance}\n📈 總局數：{len(history)}\n✅ 莊家勝局數：{win_count}\n❌ 閒家勝局數：{lose_count}"
    elif game_active and initial_balance is not None:
        player_score, banker_score = parse_card_input(user_input)
        if player_score is not None and banker_score is not None:
            reply_text = calculate_best_bet(player_score, banker_score)
        else:
            reply_text = "❌ 請輸入正確格式（例如：AJ / K8J 代表閒家 A、J，莊家 K、8、J）"
    else:
        reply_text = "請輸入「開始」來設定本金，或「結束」來結束遊戲！"

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
