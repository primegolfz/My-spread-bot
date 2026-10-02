import os
import requests
import hmac
import hashlib
import time
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

app = FastAPI()

# ----------------------------------------------------
# CONFIG & KEYS
# ----------------------------------------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

BINANCE_FUTURES_URL = "https://fapi.binance.com"

# ตั้งค่าความกว้างสูงสุดของ Bid-Ask Spread ที่ยอมรับได้ (USDT)
MAX_ALLOWED_BID_ASK_SPREAD = 0.15 

tg_app = Application.builder().token(TELEGRAM_TOKEN).build() if TELEGRAM_TOKEN else None

# ----------------------------------------------------
# HELPER FUNCTIONS
# ----------------------------------------------------
def get_prices():
    """ดึงราคา BZUSDT และ CLUSDT จาก Binance Futures"""
    url = f"{BINANCE_FUTURES_URL}/fapi/v1/ticker/bookTicker"
    res = requests.get(url).json()
    
    bz_data = next((item for item in res if item["symbol"] == "BZUSDT"), None)
    cl_data = next((item for item in res if item["symbol"] == "CLUSDT"), None)
    
    if bz_data and cl_data:
        bz_bid = float(bz_data["bidPrice"])
        bz_ask = float(bz_data["askPrice"])
        cl_bid = float(cl_data["bidPrice"])
        cl_ask = float(cl_data["askPrice"])
        
        # คำนวณ Bid-Ask Spread ของแต่ละตัว (สำหรับ Spread Guard)
        bz_ba_spread = bz_ask - bz_bid
        cl_ba_spread = cl_ask - cl_bid
        
        # คำนวณ Mid Price
        bz_mid = (bz_bid + bz_ask) / 2
        cl_mid = (cl_bid + cl_ask) / 2
        spread_mid = bz_mid - cl_mid
        
        # Execution Spread
        spread_buy = bz_ask - cl_bid   # Buy BZ @ Ask, Sell CL @ Bid
        spread_sell = bz_bid - cl_ask  # Sell BZ @ Bid, Buy CL @ Ask
        
        return {
            "bz_mid": bz_mid, "cl_mid": cl_mid,
            "bz_ba_spread": bz_ba_spread, "cl_ba_spread": cl_ba_spread,
            "spread_mid": spread_mid,
            "spread_buy": spread_buy,
            "spread_sell": spread_sell
        }
    return None

def check_spread_guard(prices):
    """ตรวจสอบว่าสภาพคล่องปรกติและ Bid-Ask ไม่ถ่างเกินไปหรือไม่"""
    if not prices:
        return False, "❌ ไม่สามารถดึงราคาได้"
    
    if prices["bz_ba_spread"] > MAX_ALLOWED_BID_ASK_SPREAD:
        return False, f"⚠️ **Spread Guard Triggered!**\nBid-Ask ของ BZ ถ่างกว้างเกินไป ({prices['bz_ba_spread']:.2f} > {MAX_ALLOWED_BID_ASK_SPREAD})"
        
    if prices["cl_ba_spread"] > MAX_ALLOWED_BID_ASK_SPREAD:
        return False, f"⚠️ **Spread Guard Triggered!**\nBid-Ask ของ CL ถ่างกว้างเกินไป ({prices['cl_ba_spread']:.2f} > {MAX_ALLOWED_BID_ASK_SPREAD})"
        
    return True, "OK"

def send_binance_order(symbol, side, quantity):
    """ส่งคำสั่ง Market Order ไปยัง Binance Futures"""
    endpoint = "/fapi/v1/order"
    timestamp = int(time.time() * 1000)
    
    params = {
        "symbol": symbol,
        "side": side,  # 'BUY' หรือ 'SELL'
        "type": "MARKET",
        "quantity": quantity,
        "timestamp": timestamp
    }
    
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(BINANCE_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    params["signature"] = signature
    
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    response = requests.post(f"{BINANCE_FUTURES_URL}{endpoint}", headers=headers, params=params)
    return response.json()

# ----------------------------------------------------
# TELEGRAM BOT HANDLERS
# ----------------------------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🤖 **บอทเช็ก Spread BZ - CL (พร้อม Spread Guard)**\n\n"
        "คำสั่งที่ใช้งานได้:\n"
        "• /spread : เช็กส่วนต่างราคาปัจจุบันและสถานะตลาด"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def spread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = get_prices()
    if not prices:
        await update.message.reply_text("❌ ไม่สามารถดึงราคาได้ในขณะนี้")
        return
    
    is_safe, guard_msg = check_spread_guard(prices)
    guard_status_str = "🟢 ปกติ (พร้อมเทรด)" if is_safe else f"🔴 เสี่ยงถ่าง ({prices['bz_ba_spread']:.2f} / {prices['cl_ba_spread']:.2f})"
    
    msg = (
        f"📊 **ส่วนต่างราคา Brent vs WTI (BZ - CL)**\n\n"
        f"• **BZ Price (Mid):** {prices['bz_mid']:.2f} USDT (B-A: {prices['bz_ba_spread']:.2f})\n"
        f"• **CL Price (Mid):** {prices['cl_mid']:.2f} USDT (B-A: {prices['cl_ba_spread']:.2f})\n"
        f"• **Market Status:** {guard_status_str}\n"
        f"----------------------------------\n"
        f"🔹 **Spread (Mid):** `{prices['spread_mid']:.2f}`\n"
        f"🟢 **Spread สำหรับ Long (Buy BZ / Sell CL):** `{prices['spread_buy']:.2f}`\n"
        f"🔴 **Spread สำหรับ Short (Sell BZ / Buy CL):** `{prices['spread_sell']:.2f}`"
    )
    
    keyboard = [
        [InlineKeyboardButton("🟢 Buy Spread (Long 1 BZ / Short 1 CL)", callback_data="buy_spread")],
        [InlineKeyboardButton("🔴 Sell Spread (Short 1 BZ / Long 1 CL)", callback_data="sell_spread")],
        [InlineKeyboardButton("🔄 รีเฟรชราคา", callback_data="refresh_spread")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "refresh_spread":
        await spread_command(update, context)
        return

    # --- เช็ก SPREAD GUARD ก่อนเปิดออเดอร์ ---
    prices = get_prices()
    is_safe, guard_msg = check_spread_guard(prices)
    
    if not is_safe:
        await query.message.reply_text(f"🛑 **ระงับการส่งคำสั่ง!**\n{guard_msg}", parse_mode="Markdown")
        return

    # --- ส่งคำสั่งซื้อขายเมื่อปลอดภัย ---
    if query.data == "buy_spread":
        await query.edit_message_text("⏳ กำลังส่งคำสั่ง **BUY 1 BZ** และ **SELL 1 CL**...")
        res_bz = send_binance_order("BZUSDT", "BUY", 1)
        
        # ตรวจสอบว่า BZ สำเร็จหรือไม่ก่อนยิง CL
        if res_bz.get("status") in ["NEW", "FILLED"]:
            res_cl = send_binance_order("CLUSDT", "SELL", 1)
            status = f"✅ **เปิด Buy Spread สำเร็จ!**\n• BZ Order: {res_bz.get('status')}\n• CL Order: {res_cl.get('status')}"
        else:
            status = f"❌ **เปิด BZ ไม่สำเร็จ การส่งออเดอร์ถูกยกเลิก!**\nError: {res_bz.get('msg', 'Unknown Error')}"
            
        await query.message.reply_text(status, parse_mode="Markdown")
        
    elif query.data == "sell_spread":
        await query.edit_message_text("⏳ กำลังส่งคำสั่ง **SELL 1 BZ** และ **BUY 1 CL**...")
        res_bz = send_binance_order("BZUSDT", "SELL", 1)
        
        # ตรวจสอบว่า BZ สำเร็จหรือไม่ก่อนยิง CL
        if res_bz.get("status") in ["NEW", "FILLED"]:
            res_cl = send_binance_order("CLUSDT", "BUY", 1)
            status = f"✅ **เปิด Sell Spread สำเร็จ!**\n• BZ Order: {res_bz.get('status')}\n• CL Order: {res_cl.get('status')}"
        else:
            status = f"❌ **เปิด BZ ไม่สำเร็จ การส่งออเดอร์ถูกยกเลิก!**\nError: {res_bz.get('msg', 'Unknown Error')}"
            
        await query.message.reply_text(status, parse_mode="Markdown")

# ----------------------------------------------------
# VERCEL WEBHOOK ROUTE
# ----------------------------------------------------
@app.post("/api/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    
    tg_app.add_handler(CommandHandler("start", start_command))
    tg_app.add_handler(CommandHandler("spread", spread_command))
    tg_app.add_handler(CallbackQueryHandler(button_handler))
    
    await tg_app.initialize()
    await tg_app.process_update(update)
    await tg_app.shutdown()
    
    return {"status": "ok"}
