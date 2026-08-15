import os
import logging
import asyncio
import re
import html
from typing import List, Dict, Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import aiohttp
from bs4 import BeautifulSoup

# ==================== CONFIGURATION ====================
TOKEN = os.environ.get("BOT_TOKEN")

if not TOKEN:
    logging.error("❌ BOT_TOKEN environment variable is not set!")
    exit(1)

# ==================== VIDEO CONFIGURATION ====================
WELCOME_VIDEO_FILE_ID = "BAACAgQAAxkBAAFR6rZqgOKuxBwbqZmSAcvMZZkXcUD6BAACMiEAAlAyAAFQmUO9QEni8PY9BA"

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== LEAGUE CONFIGURATION ====================
LEAGUES = {
    "premier-league": {
        "name": "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",
        "url": "https://www.flashscore.com/standings/3eqIwnuN/1GmFODHa/",
        "country": "England",
        "icon": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"
    },
    "la-liga": {
        "name": "🇪🇸 La Liga",
        "url": "https://www.flashscore.com/standings/8RqYgO0S/1GmFODHa/",
        "country": "Spain",
        "icon": "🇪🇸"
    },
    "serie-a": {
        "name": "🇮🇹 Serie A",
        "url": "https://www.flashscore.com/standings/8Rv95Q1T/1GmFODHa/",
        "country": "Italy",
        "icon": "🇮🇹"
    },
    "bundesliga": {
        "name": "🇩🇪 Bundesliga",
        "url": "https://www.flashscore.com/standings/8mjcqriC/1GmFODHa/",
        "country": "Germany",
        "icon": "🇩🇪"
    },
    "ligue-1": {
        "name": "🇫🇷 Ligue 1",
        "url": "https://www.flashscore.com/standings/8k1s7VHK/1GmFODHa/",
        "country": "France",
        "icon": "🇫🇷"
    },
    "primeira-liga": {
        "name": "🇵🇹 Primeira Liga",
        "url": "https://www.flashscore.com/standings/8k1s7VHK/1GmFODHa/",
        "country": "Portugal",
        "icon": "🇵🇹"
    },
    "eredivisie": {
        "name": "🇳🇱 Eredivisie",
        "url": "https://www.flashscore.com/standings/8wR4LyPZ/1GmFODHa/",
        "country": "Netherlands",
        "icon": "🇳🇱"
    },
    "champions-league": {
        "name": "🏆 Champions League",
        "url": "https://www.flashscore.com/standings/8wR4LyPZ/1GmFODHa/",
        "country": "Europe",
        "icon": "🏆"
    }
}

# ==================== DATA STORAGE ====================
subscribed_chats: List[int] = []
user_preferences: Dict[int, str] = {}
cache: Dict[str, Dict] = {}
CACHE_DURATION = 300  # 5 minutes

# ==================== SCRAPER FUNCTIONS ====================
async def fetch_standings(league_key: str) -> Optional[List[Dict]]:
    """Fetch and parse league standings from FlashScore"""
    league = LEAGUES.get(league_key)
    if not league:
        return None

    cache_key = f"standings_{league_key}"
    if cache_key in cache:
        cached_data, timestamp = cache[cache_key]
        if (datetime.now() - timestamp).seconds < CACHE_DURATION:
            logger.info(f"Using cached data for {league['name']}")
            return cached_data

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(league['url'], headers=headers) as response:
                if response.status != 200:
                    logger.error(f"HTTP {response.status} for {league['name']}")
                    return None

                html_content = await response.text()
                soup = BeautifulSoup(html_content, 'html.parser')
                table = soup.find('table', {'class': re.compile(r'standings|table')})
                
                if not table:
                    logger.error(f"Table not found for {league['name']}")
                    return None

                standings = []
                rows = table.find_all('tr')
                
                for row in rows[1:]:
                    cols = row.find_all('td')
                    if len(cols) < 6:
                        continue

                    try:
                        pos_text = cols[0].get_text(strip=True) if len(cols) > 0 else ""
                        position = int(re.search(r'\d+', pos_text).group()) if re.search(r'\d+', pos_text) else 0

                        team_text = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                        team = re.sub(r'^\d+\.?\s*', '', team_text).strip()

                        played = int(re.search(r'\d+', cols[2].get_text(strip=True)).group()) if len(cols) > 2 and re.search(r'\d+', cols[2].get_text(strip=True)) else 0
                        won = int(re.search(r'\d+', cols[3].get_text(strip=True)).group()) if len(cols) > 3 and re.search(r'\d+', cols[3].get_text(strip=True)) else 0
                        drawn = int(re.search(r'\d+', cols[4].get_text(strip=True)).group()) if len(cols) > 4 and re.search(r'\d+', cols[4].get_text(strip=True)) else 0
                        lost = int(re.search(r'\d+', cols[5].get_text(strip=True)).group()) if len(cols) > 5 and re.search(r'\d+', cols[5].get_text(strip=True)) else 0
                        goals_for = int(re.search(r'\d+', cols[6].get_text(strip=True)).group()) if len(cols) > 6 and re.search(r'\d+', cols[6].get_text(strip=True)) else 0
                        goals_against = int(re.search(r'\d+', cols[7].get_text(strip=True)).group()) if len(cols) > 7 and re.search(r'\d+', cols[7].get_text(strip=True)) else 0
                        goal_diff = goals_for - goals_against
                        points = int(re.search(r'\d+', cols[8].get_text(strip=True)).group()) if len(cols) > 8 and re.search(r'\d+', cols[8].get_text(strip=True)) else 0

                        if team and position > 0:
                            standings.append({
                                'position': position,
                                'team': team,
                                'played': played,
                                'won': won,
                                'drawn': drawn,
                                'lost': lost,
                                'goals_for': goals_for,
                                'goals_against': goals_against,
                                'goal_diff': goal_diff,
                                'points': points
                            })
                    except Exception as e:
                        logger.warning(f"Error parsing row: {e}")
                        continue

                if standings:
                    cache[cache_key] = (standings, datetime.now())
                    logger.info(f"✅ Fetched {len(standings)} teams for {league['name']}")
                    return standings

                return None

    except Exception as e:
        logger.error(f"Error fetching {league['name']}: {e}")
        return None

# ==================== MESSAGE FORMATTER ====================
def format_standings(standings: List[Dict], league_name: str) -> str:
    """Format standings data into a Telegram message"""
    if not standings:
        return "❌ No standings data available at the moment."

    message = f"🏆 **{league_name}**\n\n"
    message += "```\n"
    message += " Pos | Team                | P  | W  | D  | L  | GF | GA | GD | PTS\n"
    message += "-----|---------------------|----|----|----|----|----|----|----|-----\n"

    for team in standings[:20]:
        pos = str(team['position']).rjust(3)
        team_name = team['team'][:19].ljust(19)
        played = str(team['played']).rjust(2)
        won = str(team['won']).rjust(2)
        drawn = str(team['drawn']).rjust(2)
        lost = str(team['lost']).rjust(2)
        gf = str(team['goals_for']).rjust(2)
        ga = str(team['goals_against']).rjust(2)
        gd = f"+{team['goal_diff']}" if team['goal_diff'] > 0 else str(team['goal_diff']).rjust(3)
        pts = str(team['points']).rjust(3)

        if team['position'] == 1:
            team_name = f"🏆 {team_name}"
        elif team['position'] == 2:
            team_name = f"🥈 {team_name}"
        elif team['position'] == 3:
            team_name = f"🥉 {team_name}"

        message += f" {pos} | {team_name} | {played} | {won} | {drawn} | {lost} | {gf} | {ga} | {gd} | {pts}\n"

    message += "```\n"
    message += f"\n📊 *Last updated: {datetime.now().strftime('%H:%M:%S')}*"
    message += f"\n📱 Use /standings to refresh"

    return message

# ==================== BOT COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with video"""
    chat_id = update.effective_chat.id
    if chat_id not in subscribed_chats:
        subscribed_chats.append(chat_id)

    welcome_text = """🏆 **Welcome to League Standing Checker!**

Check the latest league standings instantly and stay updated!

📊 **Available Leagues:**
• 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
• 🇪🇸 La Liga
• 🇮🇹 Serie A
• 🇩🇪 Bundesliga
• 🇫🇷 Ligue 1
• 🇵🇹 Primeira Liga
• 🇳🇱 Eredivisie
• 🏆 Champions League

⚡ **Features:**
• 🔴 Live Standings
• 🏆 All Major Leagues
• ⚡ Fast & Accurate
• 🔄 Instant Updates

📌 **Commands:**
/standings - View live league standings
/leagues - List all available leagues
/select - Choose a league to view
/refresh - Force refresh data
/subscribe - Enable auto-updates
/unsubscribe - Disable auto-updates
/help - Help & info
/about - About this bot

🔔 Auto-updates every 30 minutes for subscribers!
"""

    keyboard = [
        [InlineKeyboardButton("🏆 View Standings", callback_data="view_standings")],
        [InlineKeyboardButton("📊 Select League", callback_data="select_league")],
        [InlineKeyboardButton("🔔 Subscribe", callback_data="subscribe")],
        [InlineKeyboardButton("❓ Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await update.message.reply_video(
            video=WELCOME_VIDEO_FILE_ID,
            caption=welcome_text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
            supports_streaming=True,
            height=1024,
            width=576
        )
        logger.info(f"✅ Welcome video sent to {chat_id}")
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await update.message.reply_text(
            welcome_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

# ... (all other commands remain the same - standings_command, leagues_command, etc.)

# ==================== ERROR HANDLER ====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

# ==================== MAIN ====================
async def main():
    """Start the bot with better timeout handling"""
    logger.info("🏆 Starting League Standing Checker Bot...")
    logger.info(f"📊 {len(LEAGUES)} leagues configured")
    logger.info("🎬 Welcome video configured")

    # Create application with longer timeouts
    application = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(60.0)
        .read_timeout(60.0)
        .write_timeout(60.0)
        .pool_timeout(60.0)
        .build()
    )

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("standings", standings_command))
    application.add_handler(CommandHandler("leagues", leagues_command))
    application.add_handler(CommandHandler("select", select_command))
    application.add_handler(CommandHandler("refresh", refresh_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    # Setup job queue
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            auto_send_standings,
            interval=1800,
            first=30
        )
        logger.info("⏰ Auto-update job scheduled (every 30 minutes)")

    # Start with retry
    max_retries = 5
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Connection attempt {attempt + 1}/{max_retries}")
            
            await asyncio.wait_for(application.initialize(), timeout=60.0)
            await asyncio.wait_for(
                application.bot.delete_webhook(drop_pending_updates=True),
                timeout=30.0
            )
            logger.info("✅ Webhook removed")

            await asyncio.wait_for(application.start(), timeout=60.0)
            await asyncio.wait_for(
                application.updater.start_polling(
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True
                ),
                timeout=60.0
            )

            logger.info("✅ League Standing Checker Bot started successfully!")
            logger.info(f"📊 Subscribers: {len(subscribed_chats)}")
            logger.info("🤖 Bot is ready to receive messages")
            
            # Keep running
            while True:
                await asyncio.sleep(3600)
                logger.info(f"📊 Status: {len(subscribed_chats)} subscribers, {len(cache)} cached entries")
                
        except asyncio.TimeoutError:
            logger.error(f"❌ Attempt {attempt + 1} timed out")
            if attempt < max_retries - 1:
                logger.info(f"⏳ Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error("❌ All attempts failed. Exiting.")
                return
        except Exception as e:
            logger.error(f"❌ Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                logger.info(f"⏳ Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error("❌ All attempts failed. Exiting.")
                return

# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
