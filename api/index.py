import os
import requests
from fastapi import FastAPI, Request

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")

def send_telegram_message(chat_id: int, text: str):
    """ส่งข้อความกลับหา Telegram ผ่าน HTTP API โดยตรง"""
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN is missing")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending message: {e}")

def get_binance_price(symbol: str) -> float:
    """ดึงราคา Mark Price ล่าสุดจาก Binance Futures"""
    try:
        url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
        headers = {}
        if BINANCE_API_KEY:
            headers["X-MBX-APIKEY"] = BINANCE_API_KEY
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return float(res.json().get("markPrice", 0))
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
    return 0.0

@app.post("/api/webhook")
async def webhook_handler(request: Request):
    """จุดรับ Webhook จาก Telegram (POST)"""
    try:
        data = await request.json()
        
        # ดึง chat_id และข้อความที่ส่งมา
        message = data.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if chat_id and text:
            if text.startswith("/start"):
                send_telegram_message(
                    chat_id, 
                    "👋 **บอท My-Spread พร้อมทำงานแล้ว!**\nพิมพ์ /spread เพื่อดูราคา Spread Guard ได้เลยครับ"
                )
            elif text.startswith("/spread"):
                # เปลี่ยน BTCUSDT / ETHUSDT เป็น Symbol ที่ต้องการได้ครับ
                bz_price = get_binance_price("BTCUSDT")
                cl_price = get_binance_price("ETHUSDT")

                if bz_price == 0 or cl_price == 0:
                    reply_text = "⚠️ ไม่สามารถดึงราคาจาก Binance ได้ในขณะนี้ กรุณาตรวจสอบ API Key หรือ Symbol"
                else:
                    spread = bz_price - cl_price
                    reply_text = (
                        f"📊 **My Spread Report**\n\n"
                        f"🔹 **Leg A (BZ):** {bz_price:,.2f}\n"
                        f"🔹 **Leg B (CL):** {cl_price:,.2f}\n"
                        f"📈 **Spread Current:** {spread:,.2f}\n\n"
                        f"🛡️ **Status:** Spread Guard Active"
                    )
                send_telegram_message(chat_id, reply_text)

        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/webhook")
def webhook_get():
    """เพิ่มเพื่อให้สามารถเปิดทดสอบผ่าน Browser ได้โดยไม่ขึ้น Method Not Allowed"""
    return {"status": "Telegram Webhook Endpoint is Ready!"}

@app.get("/")
def root():
    return {"status": "My-Spread-Bot is active"}
