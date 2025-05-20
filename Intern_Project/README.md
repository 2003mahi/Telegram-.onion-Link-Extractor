# Telegram .onion Link Extractor

A Python script that extracts .onion links from Telegram channels using the Telethon library.

## Features

- Monitors specified Telegram channels for .onion links
- Extracts links using regex pattern matching
- Saves links in JSON format with metadata
- Real-time monitoring of new messages
- Processes up to 1000 historical messages
- Automatic deduplication of links

## Prerequisites

- Python 3.7 or higher
- Telegram API credentials (API ID and API Hash)
- Telegram account phone number
- Access to the target Telegram channels

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd telegram-onion-extractor
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file with your Telegram credentials:
```bash
# Get these from https://my.telegram.org/apps
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_PHONE_NUMBER=your_phone_number
TARGET_CHANNEL=toronionlinks  # or your preferred channel
```

## Usage

1. Start the script:
```bash
python telegram_onion_extractor.py
```

2. On first run, you'll need to authenticate with Telegram:
   - Enter your phone number when prompted
   - Enter the verification code sent to your Telegram account

The script will:
1. Process existing messages in the target channel
2. Start monitoring for new messages
3. Save extracted .onion links to `onion_links.json`

## Output Format

The script saves links in the following JSON format (one object per line):
```json
{
    "source": "telegram",
    "url": "http://abcd1234xyz.onion",
    "discovered_at": "2025-05-12T10:00:00Z",
    "context": "Found in Telegram channel @toronionlinks",
    "status": "pending"
}
```

## Security Notes

- Keep your `.env` file secure and never commit it to version control
- The script requires your Telegram account credentials for authentication
- Only monitor channels you have permission to access

## License

MIT License

## Contributing

Feel free to submit issues and enhancement requests! 