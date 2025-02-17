import os
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# 環境變數
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 記錄百家樂歷史
history = []
balance = 5000
base_bet = round((balance * 0.03) / 50) * 50

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global balance, base_bet

    user_input = event.message.text.strip()
    if len(user_input) == 2 and user_input.isdigit():
        player_score, banker_score = int(user_input[0]), int(user_input[1])
        if player_score > banker_score:
            result = "閒家贏"
            balance += base_bet
        elif banker_score > player_score:
            result = "莊家贏"
            balance += base_bet * 0.95
        else:
            result = "平局"

        # 更新歷史
        history.append({"結果": result, "下注": base_bet, "剩餘資金": balance})

        # 回應用戶
        reply_text = f"🎲 {result}！\n💰 下注金額：${base_bet}\n🏆 剩餘資金：${balance}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入兩位數字，如 '98' 代表閒 9 - 莊 8"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
