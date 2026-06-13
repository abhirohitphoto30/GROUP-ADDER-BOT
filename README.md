# GROUP ADDER BOT

Ek Telegram bot jo kisi bhi dusre bot ko automatically tumhare saare admin groups mein add kar deta hai.

## Features
- Apna Telegram account securely connect karo (MTProto via Telethon)
- 2FA support
- Koi bhi bot username bhejo — bot automatically saare admin groups (public + private) mein add kar deta hai
- Detailed success/fail report

## Setup

### Requirements
- Python 3.11+
- Telegram Bot Token (BotFather se)
- Telegram API ID & Hash (my.telegram.org/apps se)

### Install
```bash
pip install -r requirements.txt
```

### Environment Variables
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
```

### Run
```bash
python bot.py
```

## Usage
1. `/start` — Bot ke baare mein jaano
2. `/login` — Apna Telegram account connect karo (phone number + OTP)
3. Bot ka username bhejo (e.g. `@SomeBotUsername`)
4. Bot automatically us bot ko tumhare saare admin groups mein add kar deta hai!
5. `/status` — Connection status check karo
6. `/logout` — Disconnect karo
