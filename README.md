# Phone-first Nifty 500 15-minute scanner (prototype)

This is a learning prototype, not a licensed real-time market-data service. It uses Yahoo Finance through `yfinance`, which is unofficial and can be delayed, incomplete, rate-limited, or change without notice. Do not rely on it for live trading decisions. For production, replace the data adapter with an authorized NSE real-time provider.

## What it checks
- 15-minute candle close above the previous 20 completed candles' highest high
- close above session VWAP
- close above EMA(20)
- volume >= 1.5x average volume of the prior 20 candles
- Telegram alerts and per-symbol duplicate suppression

## Phone-only setup
1. In your phone browser, create a GitHub account or sign in at https://github.com.
2. Create a **private** repository named `nifty500-phone-scanner`.
3. Upload `scanner.py`, `requirements.txt`, `state.json`, and the `.github/workflows/scan.yml` file, preserving the folders.
4. In Telegram, message `@BotFather`, send `/newbot`, follow its steps, and copy the bot token. Keep it secret.
5. Open your new bot chat and press **Start**. To get your chat ID, temporarily open this URL in your phone browser after replacing TOKEN:
   `https://api.telegram.org/botTOKEN/getUpdates`
   Find `"chat":{"id":123456789,...}` and copy that number. Do not share the token or screenshot publicly. If getUpdates is empty, send `/start` to the bot again and refresh.
6. In GitHub repository: Settings -> Secrets and variables -> Actions -> New repository secret.
   - `TELEGRAM_BOT_TOKEN` = token from BotFather
   - `TELEGRAM_CHAT_ID` = your numeric chat ID
7. Go to Actions and enable workflows if GitHub asks. Open **Nifty 500 15m scanner**, choose **Run workflow** to test.
8. Check Telegram for a signal (if no setup matches, there may be no message); check Actions -> latest run -> logs for errors.
9. The scheduled workflow runs on weekdays around 15-minute intervals. GitHub schedules may be delayed, and scheduled workflows are not a guaranteed real-time service.

## Important limitations
- `yfinance` is unofficial, not an authorized NSE feed; data freshness/coverage is not guaranteed.
- Nifty 500 constituent CSV endpoint may change; update `get_symbols()` if needed.
- Running 500 symbols may be throttled. If it fails, first test with 50 symbols, or use an authorized data vendor with bulk historical candles.
- The script sends a Telegram message only when matching signals are found. It never connects to Religare or places orders.
- This is a prototype, not investment advice. Verify every signal independently.
