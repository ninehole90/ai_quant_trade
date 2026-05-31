import os
import sys
import time
import datetime
import pytz
import subprocess

# 解決 Windows 終端機 Unicode 輸出編碼錯誤問題
if sys.platform.startswith('win') and getattr(sys.stdout, 'encoding', '') != 'utf-8':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# 載入環境變數
try:
    from run_quant_brain import load_dotenv
    load_dotenv()
except ImportError:
    pass

def is_market_holiday(d):
    """
    判斷該日期是否為美股休市日
    """
    # 週末不開盤
    if d.weekday() >= 5:
        return True
        
    year = d.year
    
    # 1. New Year's Day (元旦): Jan 1 (若為週六移至前一天週五，週日移至後一天週一)
    ny = datetime.date(year, 1, 1)
    if ny.weekday() == 5: 
        ny = datetime.date(year - 1, 12, 31)
    elif ny.weekday() == 6: 
        ny = datetime.date(year, 1, 2)
    if d == ny: 
        return True
    
    # 2. Martin Luther King Jr. Day: 一月的第三個週一
    mlk = datetime.date(year, 1, 15)
    while mlk.weekday() != 0:
        mlk += datetime.timedelta(days=1)
    if d == mlk: 
        return True
    
    # 3. Presidents' Day (Washington's Birthday): 二月的第三個週一
    pres = datetime.date(year, 2, 15)
    while pres.weekday() != 0:
        pres += datetime.timedelta(days=1)
    if d == pres: 
        return True
    
    # 4. Good Friday (耶穌受難日) - 靜態對照表 (2025-2030)
    good_fridays = {
        2025: datetime.date(2025, 4, 18),
        2026: datetime.date(2026, 4, 3),
        2027: datetime.date(2027, 3, 26),
        2028: datetime.date(2028, 4, 14),
        2029: datetime.date(2029, 3, 30),
        2030: datetime.date(2030, 4, 19),
    }
    if year in good_fridays and d == good_fridays[year]:
        return True
        
    # 5. Memorial Day (陣亡將士紀念日): 五月的最後一個週一
    mem = datetime.date(year, 5, 31)
    while mem.weekday() != 0:
        mem -= datetime.timedelta(days=1)
    if d == mem: 
        return True
    
    # 6. Juneteenth (六月節): June 19 (若週六移至週五，週日移至週一)
    june = datetime.date(year, 6, 19)
    if june.weekday() == 5: 
        june = datetime.date(year, 6, 18)
    elif june.weekday() == 6: 
        june = datetime.date(year, 6, 20)
    if d == june: 
        return True
    
    # 7. Independence Day (美國國慶): July 4 (若週六移至週五，週日移至週一)
    july = datetime.date(year, 7, 4)
    if july.weekday() == 5: 
        july = datetime.date(year, 7, 3)
    elif july.weekday() == 6: 
        july = datetime.date(year, 7, 5)
    if d == july: 
        return True
    
    # 8. Labor Day (勞動節): 九月的第一個週一
    lab = datetime.date(year, 9, 1)
    while lab.weekday() != 0:
        lab += datetime.timedelta(days=1)
    if d == lab: 
        return True
    
    # 9. Thanksgiving Day (感恩節): 十一月的第四個週四
    tg = datetime.date(year, 11, 22)
    while tg.weekday() != 3:
        tg += datetime.timedelta(days=1)
    if d == tg: 
        return True
    
    # 10. Christmas Day (聖誕節): Dec 25 (若週六移至週五，週日移至週一)
    xm = datetime.date(year, 12, 25)
    if xm.weekday() == 5: 
        xm = datetime.date(year, 12, 24)
    elif xm.weekday() == 6: 
        xm = datetime.date(year, 12, 26)
    if d == xm: 
        return True
    
    return False

def get_next_trigger_time():
    """
    計算下一個執行時間點（美東時間）
    """
    tz = pytz.timezone("America/New_York")
    now_tz = datetime.datetime.now(tz)
    
    # 每日的監控排程時間點 (小時, 分鐘)
    schedule_times = [
        (9, 0),   # 盤前診斷 (美股開盤前 30 分鐘)
        (9, 30),  # 開盤第一時間分析
        (10, 30), # 盤中每小時更新
        (11, 30),
        (12, 30),
        (13, 30),
        (14, 30),
        (15, 30),
        (16, 0),  # 收盤診斷
    ]
    
    # 搜尋未來第一個交易日的合格時間點
    check_day = now_tz.date()
    for offset in range(30):  # 往後搜尋最多 30 天
        current_date = check_day + datetime.timedelta(days=offset)
        
        # 排除週末與休市日
        if is_market_holiday(current_date):
            continue
            
        for hour, minute in schedule_times:
            # 建立該時區的時間點
            candidate_dt = tz.localize(datetime.datetime(
                current_date.year, current_date.month, current_date.day,
                hour, minute, 0
            ))
            # 加上 5 秒防抖，避免同一分鐘內重複觸發
            if candidate_dt > now_tz + datetime.timedelta(seconds=5):
                return candidate_dt
                
    return now_tz + datetime.timedelta(hours=1)

def main():
    print("=" * 60)
    print("📈 美股量化 AI 軍師 - 背景守護排程系統")
    print(f"🕒 本地時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    script_path = os.path.join(os.path.dirname(__file__), "run_quant_brain.py")
    if not os.path.exists(script_path):
        print(f"❌ 找不到分析主程式 {script_path}，排程終止。")
        return
        
    # 支援 --test 參數：即時啟動一次測試分析以確保串接正常
    if "--test" in sys.argv:
        print("\n🔍 偵測到 --test 參數，正在進行即時測試執行以確保排程呼叫正常...")
        print("-" * 45)
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        print(result.stdout)
        if result.stderr:
            print("⚠️ 錯誤日誌輸出：")
            print(result.stderr)
        print("-" * 45)
        print("✅ 測試執行完成！即將進入常規排程循環...")
        
    while True:
        try:
            next_run = get_next_trigger_time()
            now_tz = datetime.datetime.now(pytz.timezone("America/New_York"))
            
            # 計算剩餘秒數
            wait_seconds = (next_run - now_tz).total_seconds()
            
            # 將美東時間轉換為使用者本地時間以便顯示
            next_run_local = next_run.astimezone()
            
            print(f"\n📅 下一次分析排程時間:")
            print(f"   - 美東時間: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"   - 本地時間: {next_run_local.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   - 剩餘時間: {wait_seconds / 60:.1f} 分鐘")
            print("💤 正在進入睡眠等待中...")
            
            # 分段睡眠，以防電腦休眠喚醒或需要手動中斷 Ctrl+C
            while wait_seconds > 0:
                sleep_time = min(10, wait_seconds)
                time.sleep(sleep_time)
                now_tz = datetime.datetime.now(pytz.timezone("America/New_York"))
                wait_seconds = (next_run - now_tz).total_seconds()
                
            print("\n⏰ 觸發時間已到！正在啟動量化特徵分析與策略推理...")
            print("-" * 45)
            
            # 呼叫主程式執行
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            
            print(result.stdout)
            if result.stderr:
                print("⚠️ 錯誤日誌輸出：")
                print(result.stderr)
                
            print("-" * 45)
            print(f"✅ 排程任務執行完成。時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
        except KeyboardInterrupt:
            print("\n🛑 背景排程程式已被手動終止。")
            break
        except Exception as e:
            print(f"\n❌ 排程器發生異常錯誤: {e}")
            print("💤 等待 60 秒後嘗試重啟排程...")
            time.sleep(60)

if __name__ == "__main__":
    main()
