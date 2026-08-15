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

    # Check cache
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

        async with aiohttp.ClientSession() as session:
            async with session.get(league['url'], headers=headers, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"HTTP {response.status} for {league['name']}")
                    return None

                html_content = await response.text()
                
                # Parse HTML with BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Find the standings table
                table = soup.find('table', {'class': re.compile(r'standings|table')})
                if not table:
                    logger.error(f"Table not found for {league['name']}")
                    return None

                standings = []
                rows = table.find_all('tr')
                
                for row in rows[1:]:  # Skip header row
                    cols = row.find_all('td')
                    if len(cols) < 6:
                        continue

                    try:
                        # Extract position
                        pos_text = cols[0].get_text(strip=True) if len(cols) > 0 else ""
                        position = int(re.search(r'\d+', pos_text).group()) if re.search(r'\d+', pos_text) else 0

                        # Extract team name
                        team_text = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                        team = re.sub(r'^\d+\.?\s*', '', team_text).strip()

                        # Extract stats
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
                    # Cache the data
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

    for team in standings[:20]:  # Show top 20
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

        # Highlight top 3
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
    """Welcome message"""
    chat_id = update.effective_chat.id
    if chat_id not in subscribed_chats:
        subscribed_chats.append(chat_id)

    welcome_text = """🏆 **Welcome to League Standing Checker!**

Get real-time league standings from the top football leagues around the world.

📊 **Available Leagues:**
• 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
• 🇪🇸 La Liga
• 🇮🇹 Serie A
• 🇩🇪 Bundesliga
• 🇫🇷 Ligue 1
• 🇵🇹 Primeira Liga
• 🇳🇱 Eredivisie
• 🏆 Champions League

📌 **Commands:**
/start - Welcome menu
/standings - View live league standings
/leagues - List all available leagues
/select - Choose a league to view
/refresh - Force refresh data
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

    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)

async def standings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show standings for user's preferred league or default"""
    chat_id = update.effective_chat.id
    preferred = user_preferences.get(chat_id, "premier-league")
    
    await update.message.reply_text(f"📊 Fetching {LEAGUES[preferred]['name']} standings...")

    standings = await fetch_standings(preferred)
    if standings:
        message = format_standings(standings, LEAGUES[preferred]['name'])
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{preferred}")],
            [InlineKeyboardButton("📊 Change League", callback_data="select_league")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text("❌ Failed to fetch standings. Please try again later.")

async def leagues_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all available leagues"""
    message = "🏆 **Available Leagues:**\n\n"
    for key, league in LEAGUES.items():
        message += f"{league['icon']} **{league['name']}**\n"
    
    message += "\n📊 Use /select to choose a league or /standings to view the default."

    keyboard = [[InlineKeyboardButton("📊 Select League", callback_data="select_league")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)

async def select_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show league selection menu"""
    keyboard = []
    row = []
    for i, (key, league) in enumerate(LEAGUES.items()):
        row.append(InlineKeyboardButton(
            f"{league['icon']} {league['name'].split(' ')[1] if len(league['name'].split(' ')) > 1 else league['name']}",
            callback_data=f"select_{key}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📊 **Select a League:**\n\nChoose a league to view its standings.",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force refresh standings data"""
    chat_id = update.effective_chat.id
    preferred = user_preferences.get(chat_id, "premier-league")
    
    # Clear cache
    cache_key = f"standings_{preferred}"
    if cache_key in cache:
        del cache[cache_key]
    
    await update.message.reply_text("🔄 Refreshing standings...")
    await standings_command(update, context)

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe to automatic updates"""
    chat_id = update.effective_chat.id
    if chat_id not in subscribed_chats:
        subscribed_chats.append(chat_id)
        await update.message.reply_text(
            "✅ **Subscription activated!**\n\n"
            "You'll receive automatic league standings updates every 30 minutes.\n"
            "Use /unsubscribe to stop notifications."
        )
    else:
        await update.message.reply_text("ℹ️ You're already subscribed!")

async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from automatic updates"""
    chat_id = update.effective_chat.id
    if chat_id in subscribed_chats:
        subscribed_chats.remove(chat_id)
        await update.message.reply_text("✅ **Subscription cancelled!**")
    else:
        await update.message.reply_text("ℹ️ You're not subscribed.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    help_text = """📖 **Help - League Standing Checker**

**Commands:**
/start - Welcome menu
/standings - View live league standings
/leagues - List all available leagues
/select - Choose a league to view
/refresh - Force refresh data
/subscribe - Enable auto-updates
/unsubscribe - Disable auto-updates
/help - This help message
/about - About this bot

**How to use:**
1️⃣ Send /standings to see your preferred league
2️⃣ Use /select to change your preferred league
3️⃣ Subscribe to get automatic updates every 30 minutes

**Leagues Available:**
• 🇬🇧 Premier League
• 🇪🇸 La Liga
• 🇮🇹 Serie A
• 🇩🇪 Bundesliga
• 🇫🇷 Ligue 1
• 🇵🇹 Primeira Liga
• 🇳🇱 Eredivisie
• 🏆 Champions League
"""

    await update.message.reply_text(help_text, parse_mode="Markdown")

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """About this bot"""
    about_text = """⚽ **About League Standing Checker**

A real-time league standings aggregator that fetches live tables from public sources.

🌍 **Coverage:** 8 top European leagues
📊 **Data:** Position, Team, Played, W/D/L, Goals, GD, Points
🔄 **Updates:** Real-time with 5-minute cache
📱 **Platform:** Telegram Bot

**Features:**
• No API keys required
• Automatic updates for subscribers
• League selection
• Clean, formatted tables
• Fast and reliable

Built with ❤️ for football fans worldwide ⚽

🤖 Bot: @League_Standing_Bot
"""

    await update.message.reply_text(about_text, parse_mode="Markdown")

# ==================== CALLBACK HANDLERS ====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks"""
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    if query.data == "view_standings":
        preferred = user_preferences.get(chat_id, "premier-league")
        await query.message.reply_text(f"📊 Fetching {LEAGUES[preferred]['name']} standings...")
        standings = await fetch_standings(preferred)
        if standings:
            message = format_standings(standings, LEAGUES[preferred]['name'])
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{preferred}")],
                [InlineKeyboardButton("📊 Change League", callback_data="select_league")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await query.message.reply_text("❌ Failed to fetch standings. Please try again.")

    elif query.data == "select_league":
        keyboard = []
        row = []
        for key, league in LEAGUES.items():
            row.append(InlineKeyboardButton(
                f"{league['icon']} {league['name']}",
                callback_data=f"select_{key}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "📊 **Select a League:**\n\nChoose a league to view its standings.",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    elif query.data.startswith("select_"):
        league_key = query.data.replace("select_", "")
        user_preferences[chat_id] = league_key
        league = LEAGUES[league_key]
        await query.message.reply_text(f"✅ **League set to: {league['name']}**\n\nUse /standings to view the table.")
        await select_command(update, context)

    elif query.data.startswith("refresh_"):
        league_key = query.data.replace("refresh_", "")
        cache_key = f"standings_{league_key}"
        if cache_key in cache:
            del cache[cache_key]
        await query.message.reply_text("🔄 Refreshing standings...")
        standings = await fetch_standings(league_key)
        if standings:
            message = format_standings(standings, LEAGUES[league_key]['name'])
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{league_key}")],
                [InlineKeyboardButton("📊 Change League", callback_data="select_league")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)

    elif query.data == "subscribe":
        if chat_id not in subscribed_chats:
            subscribed_chats.append(chat_id)
            await query.message.reply_text("✅ **Subscription activated!**")
        else:
            await query.message.reply_text("ℹ️ You're already subscribed!")

    elif query.data == "help":
        await help_command(update, context)

    elif query.data == "back_to_menu":
        await start(update, context)

# ==================== AUTO-UPDATE JOB ====================
async def auto_send_standings(context: ContextTypes.DEFAULT_TYPE):
    """Send standings to all subscribers"""
    if not subscribed_chats:
        return

    logger.info(f"📊 Sending auto-updates to {len(subscribed_chats)} subscribers")

    for chat_id in subscribed_chats:
        try:
            preferred = user_preferences.get(chat_id, "premier-league")
            standings = await fetch_standings(preferred)
            if standings:
                message = format_standings(standings, LEAGUES[preferred]['name'])
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{preferred}")],
                    [InlineKeyboardButton("📊 Change League", callback_data="select_league")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="Markdown",
                    reply_markup=reply_markup
                )
                await asyncio.sleep(1)  # Rate limiting
        except Exception as e:
            logger.error(f"Error sending to {chat_id}: {e}")

# ==================== ERROR HANDLER ====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

# ==================== MAIN ====================
async def main():
    """Start the bot"""
    logger.info("🏆 Starting League Standing Checker Bot...")
    logger.info(f"📊 {len(LEAGUES)} leagues configured")

    # Create application
    application = Application.builder().token(TOKEN).build()

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

    # Add callback handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Add error handler
    application.add_error_handler(error_handler)

    # Setup job queue for auto-updates
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(
            auto_send_standings,
            interval=1800,  # 30 minutes
            first=30
        )
        logger.info("⏰ Auto-update job scheduled (every 30 minutes)")
    else:
        logger.warning("⚠️ JobQueue not available - auto-updates disabled")

    # Start the bot
    await application.initialize()
    await application.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook removed, using polling mode")

    await application.start()
    await application.updater.start_polling()

    logger.info("✅ League Standing Checker Bot started successfully!")
    logger.info(f"📊 Subscribers: {len(subscribed_chats)}")
    logger.info("🤖 Bot is ready to receive messages")

    # Keep running
    while True:
        await asyncio.sleep(3600)
        logger.info(f"📊 Status: {len(subscribed_chats)} subscribers, {len(cache)} cached entries")

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
