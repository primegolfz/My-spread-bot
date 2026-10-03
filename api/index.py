import os
import requests
from fastapi import FastAPI, Request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler

app = FastAPI()

# ดึงค่า Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# สร้าง Instance ของ Telegram Bot
bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

def get_binance_price(symbol: str) -> float:
    """ดึงราคา Mark Price ล่าสุดของ Futures จาก Binance"""
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

async def start_command(update: Update, context):
    """คำสั่ง /start"""
    await update.message.reply_text("👋 บอท My-Spread พร้อมทำงานแล้ว! พิมพ์ /spread เพื่อดูราคา Spread Guard ได้เลยครับ")

async def spread_command(update: Update, context):
    """คำสั่ง /spread"""
    # หมายเหตุ: ปรับ Symbol ตามคู่สัญญาจริงที่คุณเทรดบน Binance Futures ได้ครับ
    bz_price = get_binance_price("BTCUSDT") # ตัวอย่างคู่ทดสอบ หากเป็นน้ำมันใช้ Symbol ตามสัญญา Binance
    cl_price = get_binance_price("ETHUSDT")

    if bz_price == 0 or cl_price == 0:
        msg = "⚠️ ไม่สามารถดึงราคาจาก Binance ได้ในขณะนี้ กรุณาเช็ก API Key หรือ Symbol"
    else:
        spread = bz_price - cl_price
        msg = (
            f"📊 **My Spread Report**\n\n"
            f"🔹 **Leg A (BZ):** {bz_price:,.2f}\n"
            f"🔹 **Leg B (CL):** {cl_price:,.2f}\n"
            f"📈 **Spread Current:** {spread:,.2f}\n\n"
            f"🛡️ **Status:** Spread Guard Active"
        )
    await update.message.reply_text(msg, parse_mode="Markdown")

@app.post("/api/webhook")
async def webhook_handler(request: Request):
    """จุดรับ Webhook จาก Telegram"""
    try:
        data = await request.json()
        update = Update.de_json(data, bot)
        
        # จัดการคำสั่ง
        if update and update.message and update.message.text:
            text = update.message.text.strip()
            if text.startswith("/start"):
                await start_command(update, None)
            elif text.startswith("/spread"):
                await spread_command(update, None)
                
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook Error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
def root():
    return {"message": "My-Spread-Bot is running alive!"}
