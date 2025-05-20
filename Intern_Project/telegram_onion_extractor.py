import os
import re
import json
import logging
import sys
import asyncio
import aiofiles
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient, events, errors
from telethon.tl.types import Channel
from telethon.errors import (
    FloodWaitError,
    ServerError,
    TimedOutError,
    ChatAdminRequiredError,
    ChannelPrivateError,
    ChannelInvalidError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
    PhoneNumberInvalidError
)
import asyncio
from tqdm import tqdm
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def check_env_file():
    """Check if .env file exists and has required variables."""
    if not os.path.exists('.env'):
        print("Error: .env file not found!")
        print("Please create a .env file with the following content:")
        print("""
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_PHONE_NUMBER=+917993790452
TARGET_CHANNEL=telegram
        """)
        sys.exit(1)

    load_dotenv()
    
    required_vars = ['TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_PHONE_NUMBER', 'TARGET_CHANNEL']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file and make sure all required variables are set.")
        sys.exit(1)

# Load environment variables
check_env_file()

# Telegram API configuration
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
PHONE_NUMBER = '+917993790452'  # Your correct phone number
TARGET_CHANNEL = os.getenv('TARGET_CHANNEL', 'telegram')

# Regular expression for .onion links
ONION_PATTERN = r'[a-zA-Z0-9]{56}\.onion'

# Bot command messages
HELP_MESSAGE = """
🤖 *Onion Link Extractor Bot*

This bot helps you extract .onion links from Telegram channels.

*Available Commands:*
/start - Start the bot and get welcome message
/help - Show this help message
/status - Check bot's current status
/extract [channel] - Extract .onion links from a specific channel
/monitor [channel] - Start monitoring a channel for new .onion links
/stop - Stop monitoring the current channel

*How to use:*
1. Add the bot to the channel you want to monitor
2. Make sure the bot has admin privileges
3. Use /monitor [channel] to start monitoring
4. The bot will automatically save any .onion links it finds

*Note:* The bot needs to be an admin in the channel to monitor it.
"""

START_MESSAGE = """
👋 Welcome to the Onion Link Extractor Bot!

I can help you extract and monitor .onion links from Telegram channels.

Use /help to see all available commands and learn how to use me!
"""

def clean_channel_name(channel):
    """Clean and format channel name."""
    # Remove URL if present
    if channel.startswith(('http://', 'https://', 't.me/', '@')):
        channel = channel.split('/')[-1]
    
    # Remove @ if present
    channel = channel.lstrip('@')
    
    # Remove any whitespace
    channel = channel.strip()
    
    return channel

class MessageTracker:
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.last_message_file = f'last_message_{channel_name}.txt'
        self.last_message_id = self._load_last_message_id()

    def _load_last_message_id(self):
        """Load the last processed message ID from file."""
        try:
            if os.path.exists(self.last_message_file):
                with open(self.last_message_file, 'r') as f:
                    return int(f.read().strip())
            return 0
        except Exception as e:
            print(f"Error loading last message ID: {str(e)}")
            return 0

    async def save_last_message_id(self, message_id):
        """Save the last processed message ID to file."""
        try:
            async with aiofiles.open(self.last_message_file, 'w') as f:
                await f.write(str(message_id))
            self.last_message_id = message_id
        except Exception as e:
            print(f"Error saving last message ID: {str(e)}")

class OnionLinkExtractor:
    def __init__(self):
        self.extracted_links = set()
        self.output_file = 'onion_links.json'
        self.bot_client = None
        self.user_client = None
        self.is_connected = False
        self.message_tracker = None
        self.retry_delay = 5  # seconds
        self.max_retries = 3
        self.monitoring = False
        self.current_channel = None

    async def initialize_clients(self):
        """Initialize both bot and user clients."""
        try:
            print("\n=== Telegram Authentication Process ===")
            print("1. Make sure you have created a Telegram application at https://my.telegram.org/auth")
            print("2. Your bot username is: @ammulu37_bot")
            print("3. Check that your .env file has the correct credentials\n")
            
            # Initialize bot client
            print("\nInitializing bot client...")
            self.bot_client = TelegramClient('bot_session', API_ID, API_HASH)
            await self.bot_client.connect()
            await self.bot_client.sign_in(bot_token=BOT_TOKEN)
            
            # Initialize user client
            print("\nInitializing user client...")
            self.user_client = TelegramClient('user_session', API_ID, API_HASH)
            await self.user_client.connect()
            
            if not await self.user_client.is_user_authorized():
                print("\n=== User Authentication Required ===")
                # Ensure phone number is in international format
                phone = PHONE_NUMBER.strip()
                if not phone.startswith('+'):
                    phone = '+' + phone
                print(f"Phone number: {phone}")
                print("You will receive a verification code on your Telegram app.")
                
                try:
                    await self.user_client.send_code_request(phone)
                    print("Verification code sent! Please check your Telegram app.")
                    
                    while True:
                        try:
                            code = input('Please enter the code you received: ')
                            if not code.strip():
                                print("Code cannot be empty. Please try again.")
                                continue
                                
                            await self.user_client.sign_in(phone, code)
                            print("Successfully signed in!")
                            break
                        except PhoneCodeInvalidError:
                            print("Invalid code. Please try again.")
                        except SessionPasswordNeededError:
                            print("\nTwo-factor authentication is enabled.")
                            password = input("Please enter your 2FA password: ")
                            await self.user_client.sign_in(password=password)
                            print("Successfully signed in with 2FA!")
                            break
                        except Exception as e:
                            print(f"Error during sign in: {str(e)}")
                            print("Please try again.")
                except Exception as e:
                    print(f"Error sending code request: {str(e)}")
                    raise

            # Set up bot command handlers
            @self.bot_client.on(events.NewMessage(pattern='/start'))
            async def start_handler(event):
                await event.respond(START_MESSAGE, parse_mode='markdown')

            @self.bot_client.on(events.NewMessage(pattern='/help'))
            async def help_handler(event):
                await event.respond(HELP_MESSAGE, parse_mode='markdown')

            @self.bot_client.on(events.NewMessage(pattern='/status'))
            async def status_handler(event):
                status = "🟢 Active" if self.monitoring else "🔴 Inactive"
                channel = f"Monitoring: @{self.current_channel}" if self.current_channel else "Not monitoring any channel"
                message = f"""
*Bot Status*
Status: {status}
{channel}
Total links found: {len(self.extracted_links)}
                """
                await event.respond(message, parse_mode='markdown')

            @self.bot_client.on(events.NewMessage(pattern='/extract'))
            async def extract_handler(event):
                try:
                    # Get channel from command
                    args = event.text.split()
                    if len(args) < 2:
                        await event.respond("Please specify a channel: /extract [channel]")
                        return
                    
                    channel = clean_channel_name(args[1])
                    await event.respond(f"Starting to extract links from @{channel}...")
                    
                    # Process the channel using user client
                    total_links = await self.process_channel(channel)
                    await event.respond(f"Extraction complete! Found {total_links} unique .onion links.")
                except Exception as e:
                    await event.respond(f"Error: {str(e)}")

            @self.bot_client.on(events.NewMessage(pattern='/monitor'))
            async def monitor_handler(event):
                try:
                    # Get channel from command
                    args = event.text.split()
                    if len(args) < 2:
                        await event.respond("Please specify a channel: /monitor [channel]")
                        return
                    
                    channel = clean_channel_name(args[1])
                    
                    if self.monitoring:
                        await event.respond(f"Already monitoring @{self.current_channel}. Use /stop first.")
                        return
                    
                    await event.respond(f"Starting to monitor @{channel}...")
                    self.current_channel = channel
                    self.monitoring = True
                    
                    # Start monitoring in the background using user client
                    asyncio.create_task(self.monitor_channel())
                except Exception as e:
                    await event.respond(f"Error: {str(e)}")

            @self.bot_client.on(events.NewMessage(pattern='/stop'))
            async def stop_handler(event):
                if not self.monitoring:
                    await event.respond("Not monitoring any channel.")
                    return
                
                self.monitoring = False
                self.current_channel = None
                await event.respond("Stopped monitoring channel.")
            
            self.is_connected = True
            print("\nSuccessfully connected to Telegram!")
            
        except Exception as e:
            print(f"Error initializing clients: {str(e)}")
            raise

    async def verify_channel_access(self, channel_username):
        """Verify if we have access to the channel."""
        for attempt in range(self.max_retries):
            try:
                channel_username = clean_channel_name(channel_username)
                print(f"Attempting to access channel: {channel_username}")
                
                channel = await self.user_client.get_entity(channel_username)
                if not isinstance(channel, Channel):
                    print(f"Error: {channel_username} is not a channel")
                    return False
                print(f"Successfully connected to channel {channel_username}")
                return True
            except FloodWaitError as e:
                print(f"Rate limited. Waiting {e.seconds} seconds...")
                await asyncio.sleep(e.seconds)
            except (ServerError, TimedOutError) as e:
                if attempt < self.max_retries - 1:
                    print(f"Network error, retrying in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    print(f"Error accessing channel: {str(e)}")
                    return False
            except ChannelPrivateError:
                print(f"Error: Cannot access private channel {channel_username}")
                return False
            except ChannelInvalidError:
                print(f"Error: Invalid channel {channel_username}")
                return False
            except Exception as e:
                print(f"Error accessing channel: {str(e)}")
                return False

    def extract_links_from_message(self, message_text):
        """Extract .onion links from a message text."""
        links = re.findall(ONION_PATTERN, message_text)
        return links

    async def save_links(self, links, context):
        """Save extracted links to a JSON file."""
        current_time = datetime.now(timezone.utc).isoformat()
        
        async with aiofiles.open(self.output_file, 'a', encoding='utf-8') as f:
            for link in links:
                if link not in self.extracted_links:
                    self.extracted_links.add(link)
                    link_data = {
                        "source": "telegram",
                        "url": f"http://{link}",
                        "discovered_at": current_time,
                        "context": f"Found in Telegram channel @{context}",
                        "status": "pending"
                    }
                    await f.write(json.dumps(link_data) + '\n')
                    print(f"Found new .onion link: {link}")

    async def process_channel(self, channel_username):
        """Process messages from a channel to extract .onion links."""
        try:
            channel_username = clean_channel_name(channel_username)
            self.message_tracker = MessageTracker(channel_username)
            
            if not await self.verify_channel_access(channel_username):
                return 0

            channel = await self.user_client.get_entity(channel_username)
            
            print(f"Starting to process messages from {channel_username}")
            print(f"Last processed message ID: {self.message_tracker.last_message_id}")
            
            message_count = 0
            async for message in self.user_client.iter_messages(channel, limit=1000):
                if message.id <= self.message_tracker.last_message_id:
                    continue
                    
                message_count += 1
                if message_count % 100 == 0:
                    print(f"Processed {message_count} messages...")
                
                if message.text:
                    links = self.extract_links_from_message(message.text)
                    if links:
                        await self.save_links(links, channel_username)
                
                await self.message_tracker.save_last_message_id(message.id)
            
            print(f"Finished processing channel {channel_username}. Total messages processed: {message_count}")
            return len(self.extracted_links)
        except Exception as e:
            print(f"Error processing channel {channel_username}: {str(e)}")
            return 0

    async def monitor_channel(self):
        """Monitor the channel for new messages."""
        try:
            channel_username = clean_channel_name(self.current_channel)
            @self.user_client.on(events.NewMessage(chats=channel_username))
            async def handler(event):
                try:
                    if event.message.id <= self.message_tracker.last_message_id:
                        return
                        
                    if event.message.text:
                        links = self.extract_links_from_message(event.message.text)
                        if links:
                            await self.save_links(links, channel_username)
                            await self.message_tracker.save_last_message_id(event.message.id)
                except Exception as e:
                    print(f"Error processing new message: {str(e)}")

            print(f"Started monitoring channel {channel_username}")
            await self.user_client.run_until_disconnected()
        except Exception as e:
            print(f"Error in monitor_channel: {str(e)}")
            raise

async def main():
    """Main function to run the bot."""
    try:
        extractor = OnionLinkExtractor()
        await extractor.initialize_clients()

        if not extractor.is_connected:
            print("Failed to connect to Telegram")
            return

        print("Bot is ready! Use /start to begin.")
        await extractor.bot_client.run_until_disconnected()
    except KeyboardInterrupt:
        print("\nScript stopped by user")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        if extractor.bot_client:
            await extractor.bot_client.disconnect()
        if extractor.user_client:
            await extractor.user_client.disconnect()
        print("Disconnected from Telegram")

if __name__ == '__main__':
    asyncio.run(main()) 