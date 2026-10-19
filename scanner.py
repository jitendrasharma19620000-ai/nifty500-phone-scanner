import os
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

IST = ZoneInfo("Asia/Kolkata")
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = "state.json"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")

def get_symbols():
    # Public constituent CSV endpoint. This is convenient for a prototype, but may change.
    url = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    from io import StringIO
    constituents = pd.read_csv(StringIO(r.text))
    if "Symbol" not in constituents.columns:
        raise RuntimeError(f"Unexpected Nifty 500 CSV columns: {list(constituents.columns)}")
    return [f"{s}.NS" for s in constituents["Symbol"].dropna().astype(str).str.strip().unique()]

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def normalize_download(df, ticker):
    # yfinance may return either flat columns or a MultiIndex.
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        if ticker in df.columns.get_level_values(-1):
            df = df.xs(ticker, axis=1, level=-1, drop_level=True)
        elif ticker in df.columns.get_level_values(0):
            df = df.xs(ticker, axis=1, level=0, drop_level=True)
        else:
            return pd.DataFrame()
    needed = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in needed):
        return pd.DataFrame()
    df = df[needed].dropna()
    if df.empty:
        return df
    idx = pd.to_datetime(df.index, utc=True).tz_convert(IST)
    df.index = idx
    return df.sort_index()

def evaluate(df, now):
    if df.empty:
        return None
    # Only use candles that should have finished at least 2 minutes ago.
    cutoff = now - timedelta(minutes=2)
    df = df[df.index + pd.Timedelta(minutes=15) <= cutoff]
    if df.empty:
        return None
    # Keep current trading day for session VWAP.
    today = now.date()
    df = df[[ts.date() == today for ts in df.index]]
    if len(df) < 22:
        return None

    typical = (df["High"] + df["Low"] + df["Close"]) / 3.0
    vol = df["Volume"].fillna(0)
    if vol.sum() <= 0:
        return None
    df = df.copy()
    df["VWAP"] = (typical * vol).cumsum() / vol.cumsum()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()

    current = df.iloc[-1]
    prior = df.iloc[-21:-1]
    avg_vol = prior["Volume"].mean()
    if pd.isna(avg_vol) or avg_vol <= 0:
        return None

    breakout = current["Close"] > prior["High"].max()
    above_vwap = current["Close"] > current["VWAP"]
    above_ema = current["Close"] > current["EMA20"]
    volume_ok = current["Volume"] >= 1.5 * avg_vol

    if breakout and above_vwap and above_ema and volume_ok:
        return {
            "candle_time": df.index[-1].strftime("%Y-%m-%d %H:%M IST"),
            "close": float(current["Close"]),
            "vwap": float(current["VWAP"]),
            "ema20": float(current["EMA20"]),
            "volume": int(current["Volume"]),
            "avg_volume": int(avg_vol),
            "volume_ratio": float(current["Volume"] / avg_vol),
        }
    return None

def main():
    now = datetime.now(IST)
    # Avoid alerts outside normal NSE cash-market hours.
    if now.weekday() >= 5 or not (now.hour > 9 or (now.hour == 9 and now.minute >= 15)) or (now.hour > 15 or (now.hour == 15 and now.minute > 30)):
        print(f"Outside market window: {now:%Y-%m-%d %H:%M:%S %Z}")
        return

    symbols = get_symbols()
    state = load_state()
    hits = []
    errors = []

    # Batch requests to reduce request size; public Yahoo data is unofficial and may throttle.
    for start in range(0, len(symbols), 40):
        batch = symbols[start:start + 40]
        try:
            raw = yf.download(
                tickers=batch,
                period="5d",
                interval="15m",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
                prepost=False,
                timeout=25,
            )
            for ticker in batch:
                try:
                    frame = normalize_download(raw, ticker)
                    result = evaluate(frame, now)
                    if result:
                        key = f"{ticker}|{result['candle_time']}"
                        if state.get(ticker) != result["candle_time"]:
                            hits.append((ticker, result))
                            state[ticker] = result["candle_time"]
                except Exception as e:
                    errors.append(f"{ticker}: {e}")
        except Exception as e:
            errors.append(f"batch {start}: {e}")
        time.sleep(1)

    if hits:
        lines = ["📈 NIFTY 500 — 15m bullish setup", f"Scan time: {now:%d-%b-%Y %H:%M IST}", ""]
        for ticker, x in hits[:35]:
            lines.append(
                f"{ticker.replace('.NS','')} | Close ₹{x['close']:.2f}\n"
                f"VWAP ₹{x['vwap']:.2f} | EMA20 ₹{x['ema20']:.2f}\n"
                f"Volume {x['volume']:,} / avg {x['avg_volume']:,} "
                f"({x['volume_ratio']:.2f}x)\n"
                f"Candle: {x['candle_time']}"
            )
            lines.append("")
        if len(hits) > 35:
            lines.append(f"Plus {len(hits)-35} more matches; see workflow logs.")
        lines.append("Prototype data only; verify quotes and candle timing before trading.")
        send_telegram("\n".join(lines))
    else:
        print("No matching setups.")

    if errors:
        print(f"Warnings/errors for {len(errors)} symbols/batches; sample: {errors[:15]}")

    save_state(state)

if __name__ == "__main__":
    main()
