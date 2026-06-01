import os
import sys
import requests
import time
import yfinance as yf
import pandas as pd
from google import genai
from google.genai.errors import ServerError

# 解決 Windows 終端機 Unicode 輸出編碼錯誤問題 (CP950/CP936)
if sys.platform.startswith('win') and getattr(sys.stdout, 'encoding', '') != 'utf-8':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

def load_dotenv(dotenv_path=".env"):
    """讀取本地 .env 檔案並將設定載入至 os.environ 中"""
    if os.path.exists(dotenv_path):
        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        os.environ[key] = val
        except Exception as e:
            print(f"⚠️ 載入 .env 檔案時發生錯誤: {e}")

def load_watch_list(file_path="watch_list.txt", default_list=None):
    """從檔案讀取股票監控清單，若檔案不存在則以預設值建立"""
    if default_list is None:
        default_list = ["NVDA", "TSLA", "AAPL", "MSFT"]
        
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("# 美股監控清單 (每一行代表一個美股代碼，# 開頭為註解)\n")
                for ticker in default_list:
                    f.write(f"{ticker}\n")
            print(f"📝 已自動建立預設監控清單檔案: {file_path}")
        except Exception as e:
            print(f"⚠️ 無法建立監控清單檔案 {file_path}: {e}")
            return default_list
            
    watch_list = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                ticker = "".join(c for c in line if c.isalnum() or c in ".-").upper()
                if ticker:
                    watch_list.append(ticker)
    except Exception as e:
        print(f"⚠️ 讀取監控清單檔案時發生錯誤: {e}，將使用預設值。")
        return default_list
        
    return watch_list if watch_list else default_list

# ==================== 2026 核心配置區 ====================
TG_BOT_TOKEN = "8867246156:AAEDKffvwxxcihuAnp8FUEuaOWI_pZ9L4X0" # 確保這是活著的那組
TG_CHAT_ID = "6235795101"
# =======================================================

def calculate_indicators(df):
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['STD20'] = df['Close'].rolling(window=20).std()
    df['Upper_Band'] = df['MA20'] + (df['STD20'] * 2)
    df['Lower_Band'] = df['MA20'] - (df['STD20'] * 2)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def get_stock_report(ticker, skip_news=False):
    print(f"📥 正在下載 {ticker} 歷史數據並計算量化指標...")
    stock = yf.Ticker(ticker)
    df = stock.history(period="60d")
    if df.empty: return None
    df = calculate_indicators(df)
    latest = df.iloc[-1]
    
    # 獲取基礎基本面
    info_data = {}
    try:
        print(f"   - 正在獲取 {ticker} 的基礎基本面...")
        info = stock.info
        if info:
            info_data = {
                "pe": info.get('trailingPE'),
                "forward_pe": info.get('forwardPE'),
                "market_cap": info.get('marketCap'),
                "eps": info.get('trailingEps'),
                "div_yield": info.get('dividendYield')
            }
    except Exception as ie:
        print(f"   ⚠️ 無法取得 {ticker} 的基礎基本面: {ie}")

    # 獲取季度財報 (最新一季)
    fin_data = {}
    try:
        print(f"   - 正在獲取 {ticker} 的季度財報...")
        q_fin = stock.quarterly_financials
        if q_fin is not None and not q_fin.empty:
            latest_col = q_fin.columns[0]
            date_str = latest_col.strftime('%Y-%m-%d') if hasattr(latest_col, 'strftime') else str(latest_col)
            fin_data["date"] = date_str
            
            if 'Total Revenue' in q_fin.index:
                val = q_fin.loc['Total Revenue', latest_col]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                fin_data["revenue"] = float(val) if pd.notna(val) else None
                
            if 'Net Income' in q_fin.index:
                val = q_fin.loc['Net Income', latest_col]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                fin_data["net_income"] = float(val) if pd.notna(val) else None
    except Exception as fe:
        print(f"   ⚠️ 無法取得 {ticker} 的季度財報: {fe}")

    # 獲取最新 3 則新聞
    news_list = []
    if not skip_news:
        try:
            print(f"   - 正在獲取 {ticker} 的最新新聞...")
            news = stock.news
            if news:
                for item in news[:3]:
                    content = item.get('content', {})
                    title = content.get('title')
                    summary = content.get('summary', '')
                    if title:
                        news_list.append({"title": title, "summary": summary})
        except Exception as ne:
            print(f"   ⚠️ 無法取得 {ticker} 的新聞數據: {ne}")
    else:
        print(f"   - 已設定跳過 {ticker} 的新聞抓取")

    return {
        "ticker": ticker,
        "close": float(latest['Close']),
        "ma20": float(latest['MA20']),
        "upper": float(latest['Upper_Band']),
        "lower": float(latest['Lower_Band']),
        "rsi": float(latest['RSI']),
        "info": info_data,
        "financials": fin_data,
        "news": news_list
    }

def main():
    # 載入環境變數
    load_dotenv()
    
    # 允許從環境變數或 .env 檔案覆蓋 Telegram 設定
    global TG_BOT_TOKEN, TG_CHAT_ID
    TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", TG_BOT_TOKEN)
    TG_CHAT_ID = os.environ.get("TG_CHAT_ID", TG_CHAT_ID)

    # 檢查是否跳過新聞
    skip_news = "--skip-news" in sys.argv
    if skip_news:
        print("ℹ️ 本次執行已設定跳過新聞抓取 (節省 Token 與 API 請求)")

    print("1. 🚀 啟動美股量化特徵篩選引擎...")
    watch_list = load_watch_list()
    quant_results = []
    
    for ticker in watch_list:
        try:
            res = get_stock_report(ticker, skip_news=skip_news)
            if res: quant_results.append(res)
        except Exception as e:
            print(f"❌ 處理 {ticker} 數據時異常: {e}")
            
    print("2. 🧠 正在將數學特徵提交給 Gemini 大腦進行策略推理...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n❌ 錯誤：找不到 Gemini API 金鑰 (GEMINI_API_KEY)！")
        print("💡 請選擇以下其中一種方式設定您的 API 金鑰：")
        print("  1. 在專案根目錄下建立一個 `.env` 檔案，並寫入：")
        print("     GEMINI_API_KEY=您的_GEMINI_API_金鑰")
        print("  2. 在 PowerShell 中執行：")
        print('     $env:GEMINI_API_KEY="您的_GEMINI_API_金鑰"')
        print("  3. 在 CMD 中執行：")
        print("     set GEMINI_API_KEY=您的_GEMINI_API_金鑰")
        print("👉 如果您還沒有 API 金鑰，請至此處申請：https://ai.google.dev/gemini-api/docs/api-key\n")
        return

    client = genai.Client(api_key=api_key)
    
    data_context = "【美股最新量化與基本面/新聞數據】\n"
    for r in quant_results:
        # Technicals
        data_context += (
            f"股票: {r['ticker']}\n"
            f"  [技術指標]:\n"
            f"    - 收盤價: ${r['close']:.2f}\n"
            f"    - 20日均線(MA20): ${r['ma20']:.2f}\n"
            f"    - 布林通道上軌: ${r['upper']:.2f}, 下軌: ${r['lower']:.2f}\n"
            f"    - RSI (14日): {r['rsi']:.1f}\n"
        )
        
        # Fundamentals
        info = r.get("info", {})
        fin = r.get("financials", {})
        if info or fin:
            data_context += "  [基本面數據]:\n"
            if info.get("market_cap"):
                mcap_b = info['market_cap'] / 1e9
                data_context += f"    - 市值: ${mcap_b:.2f}B\n"
            if info.get("pe"):
                data_context += f"    - 滾動本益比 (PE): {info['pe']:.2f}\n"
            if info.get("forward_pe"):
                data_context += f"    - 預測本益比 (Forward PE): {info['forward_pe']:.2f}\n"
            if info.get("eps"):
                data_context += f"    - 每股盈餘 (EPS): ${info['eps']:.2f}\n"
            if info.get("div_yield") is not None:
                data_context += f"    - 股息殖利率: {info['div_yield']:.2f}%\n"
            
            if fin.get("date"):
                data_context += f"    - 最新季度財報日: {fin['date']}\n"
                if fin.get("revenue") is not None:
                    rev_m = fin['revenue'] / 1e6
                    data_context += f"      * 營業收入: ${rev_m:.2f}M\n"
                if fin.get("net_income") is not None:
                    ni_m = fin['net_income'] / 1e6
                    data_context += f"      * 淨利: ${ni_m:.2f}M\n"
                    
        # News
        news = r.get("news", [])
        if news:
            data_context += "  [最新相關新聞]:\n"
            for idx, item in enumerate(news, 1):
                short_summary = item['summary'][:100] + "..." if len(item['summary']) > 100 else item['summary']
                summary_suffix = f" - 摘要: {short_summary}" if short_summary else ""
                data_context += f"    {idx}. {item['title']}{summary_suffix}\n"
                
        data_context += "\n"
        
    # 根據是否跳過新聞動態調整 Prompt 指南與範例
    news_intro = "與最新新聞數據" if not skip_news else ""
    strategy_brief = "、基本面財報數據與最新新聞情緒" if not skip_news else "與基本面財報數據"
    news_guideline = """- 消息面分析：快速評估最新新聞是利多、利空或中性。
    - 綜合以上三者（技術面、基本面、消息面）給出明確的核心建議。""" if not skip_news else """- 本次為盤中即時更新，已省略最新新聞數據。請專注於【技術面】與【基本面數據】進行評估，並給出明確的核心建議。"""

    price_label = "現價" if skip_news else "收盤價"
    if skip_news:
        report_title = "盤中即時報"
    else:
        current_hour = int(time.strftime('%H'))
        if current_hour < 12:
            report_title = "盤前即時報"
        else:
            report_title = "盤後收盤報"

    # 這裡大幅優化 Prompt，強制 Gemini 輸出標準的 HTML 標籤排版
    prompt = f"""
    你是一位精通技術分析、基本面與市場心理學的頂級量化對沖基金經理。
    請根據以下提供的技術指標、基本面財報{news_intro}，為投資人撰寫一份精煉、美觀的手機盤前診斷報告。
    
    【重要排版規範】：
    1. 請完全使用繁體中文回答。
    2. 請務必、嚴格使用以下 HTML 標籤包裹對應內容（不要自作聰明漏掉）：
       - 股票代碼兩旁必須加上 <b> 標籤，例如：<b>NVDA</b>、<b>TSLA</b>。
       - 所有價格與數值兩旁必須加上 <code> 標籤，例如：<code>$211.14</code>、<code>84.3</code>、<code>32.38</code>。
       - 操作結論或強烈警示請加上 <b> 標籤，例如：<b>【短線超買過熱】</b>。
    3. 嚴禁使用任何其他 HTML 標籤 (例如 <p>, <div>, <html>, <body>, <h1>~<h6> 等 Telegram 不支援的標籤)，換行請直接使用普通換行。
    4. 嚴禁輸出任何 Markdown 的星號（*）或黑點（•）。
    5. 每一檔個股的分析請嚴格依照以下範例格式輸出，不要有多餘的廢話，內容必須精煉：
    
    📌 <b>[股票代碼]</b> ({price_label}: <code>[{price_label}]</code>)
    • 20日均線: <code>[MA20]</code> | RSI: <code>[RSI]</code> | PE: <code>[PE]</code>
    • 策略短評: [結合技術指標{strategy_brief}，進行兩到三句話的綜合分析。若觸發超買超賣，請在此加上 <b>【短線超買過熱】</b> 或 <b>【短線超跌打底】</b> 的粗體警示。]
    
    【分析指南】：
    - 技術面分析：如果{price_label}接近或突破上軌，且 RSI > 70，提示「短線超買過熱」；如果{price_label}接近或跌破下軌，且 RSI < 30，提示「短線超跌打底」。
    - 基本面分析：結合本益比 (PE) 與最新季度營收、淨利表現，評估估值合理性。
    - {news_guideline}
    - 最後請給出今日「關注度最高」的一檔股票與核心理由。
    
    指標與數據：
    {data_context}
    """
    
    # 多回合自動重試防禦
    ai_analysis = ""
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash', 
                contents=prompt
            )
            ai_analysis = response.text
            print("✅ Gemini 策略推理完成。")
            break
        except Exception as e:
            err_msg = str(e)
            print(f"⚠️ 第 {attempt}/3 次呼叫失敗。錯誤原因: {err_msg}")
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                print("💡 提示: 您的 Gemini API 金鑰可能已達免費額度上限 (20次/天) 或觸發每分鐘頻率限制。")
                print("   請確認您的帳單狀態，或至 Google AI Studio (https://aistudio.google.com/) 建立/更換新的 API 金鑰。")
            
            if attempt < 3:
                print(f"💤 等待 2 秒後將進行第 {attempt+1}/3 次重試...")
                time.sleep(2)
 
    if not ai_analysis:
        print("❌ 投研中斷。")
        return
    
    # 【核心修正】強制清洗 Telegram 不支援的網頁換行與段落標籤，防止 Bad Request 錯誤
    for tag in ["<br>", "<br/>", "<br />"]:
        ai_analysis = ai_analysis.replace(tag, "\n")
    for tag in ["<p>", "<div>", "<html>", "<body>"]:
        ai_analysis = ai_analysis.replace(tag, "")
    for tag in ["</p>", "</div>", "</html>", "</body>"]:
        ai_analysis = ai_analysis.replace(tag, "\n")
    ai_analysis = ai_analysis.replace("```html", "").replace("```", "") # 防止 Gemini 用 code block 包裹 HTML
    
    print("3. 📲 正在推播至 Telegram 手機端...")
    
    # 組裝精美的標頭
    full_message = (
        f"📊 <b>【美股量化 AI 軍師 · {report_title}】</b>\n"
        f"📅 <i>系統偵測時間：{time.strftime('%Y-%m-%d %H:%M')}</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{ai_analysis}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>本報告由 Python 量化引擎 + Gemini 2.5 聯合產出，僅供參考。</i>"
     )
    
    session = requests.Session()
    session.trust_env = False
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    
    # 【關鍵修正】加上 parse_mode="HTML"，通知 Telegram 解析我們的精美排版
    payload = {
        "chat_id": TG_CHAT_ID, 
        "text": full_message,
        "parse_mode": "HTML"
    }
    
    r = session.post(url, data=payload, timeout=10)
    if r.status_code == 200:
        print("🎉 恭喜！全新的精美量化選股報告已成功送達你的手機！")
    else:
        print(f"❌ 傳送失敗: {r.text}")

if __name__ == "__main__":
    main()
