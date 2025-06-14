# main.py (ilgili kısımlar)

import asyncio
import os
import logging
import dotenv
from datetime import datetime
import traceback

# Telegram imports
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue, Updater

from database import Database
from scraper import TrendyolScraper

dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# PREFIX = os.getenv('PREFIX', '!') # May not be needed for Telegram
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 3600))
PROXY_ENABLED = os.getenv('PROXY_ENABLED', 'True').lower() == 'true'
VERIFY_SSL = os.getenv('VERIFY_SSL', 'True').lower() == 'true'
DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/trendyol_tracker.sqlite')

# Telegram Bot Initialization
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Database and Scraper instances will be managed globally for simplicity in job, or passed via context data
# For now, let's assume they can be created in the job or handlers as needed.

async def check_prices_job(context: ContextTypes.DEFAULT_TYPE):
    """Checks product prices and sends notifications for changes via Telegram."""
    logger.info("Fiyat kontrol görevi çalışıyor...")
    db = None  # Initialize db to None for finally block
    try:
        # Access db and scraper from bot_data, passed through job.data or directly if Application context is available
        # For run_repeating, it's cleaner to re-initialize based on path/settings from job.data
        # or ensure bot_data is correctly populated and accessible.
        # Let's assume for now context.bot_data is accessible if job is bound to application instance
        # However, the provided job_queue.run_repeating doesn't automatically pass full bot_data to job context in some versions.
        # A common pattern is to pass necessary identifiers (like db_path) via job.data

        job_data = context.job.data if context.job else {}
        db_path = job_data.get('db_path', DATABASE_PATH) # Fallback to global
        proxy_enabled = job_data.get('proxy', PROXY_ENABLED)
        ssl_verify = job_data.get('ssl_verify', VERIFY_SSL)

        db = Database(db_name=db_path)
        scraper = TrendyolScraper(use_proxy=proxy_enabled, verify_ssl=ssl_verify)

        products = db.get_all_products()

        if not products:
            logger.info("Takip edilen ürün bulunamadı.")
            return

        logger.info(f"Toplam {len(products)} ürün kontrol edilecek.")

        for product in products:
            try:
                product_data = scraper.scrape_product(product['url'])

                if not product_data or not product_data.get('success', False):
                    logger.warning(f"Ürün bilgileri alınamadı: {product.get('product_id','Bilinmeyen ID')} - {product.get('name','Bilinmeyen Ürün')}")
                    continue

                old_price = product['current_price']
                new_price = product_data['current_price']

                if new_price is None: # Scraper None dönebilir
                    logger.warning(f"Yeni fiyat bilgisi None geldi: {product.get('product_id','Bilinmeyen ID')}")
                    continue

                db.update_product_price(product['product_id'], new_price)

                if old_price != new_price:
                    chat_id = product.get('chat_id')
                    if not chat_id:
                        logger.warning(f"Ürün için chat_id eksik: {product['product_id']}")
                        continue

                    price_diff = new_price - old_price
                    percentage = abs(price_diff / old_price * 100) if old_price != 0 else 0

                    change_emoji = "🔽" if price_diff < 0 else "🔼"
                    change_type_text = "Fiyat Düştü!" if price_diff < 0 else "Fiyat Arttı!"
                    price_change_summary = f"{abs(price_diff):.2f} TL {'düşüş' if price_diff < 0 else 'artış'} ({'-' if price_diff < 0 else '+'}{percentage:.1f}%)"

                    message = (
                        f"{change_emoji} *{change_type_text}*\n\n"
                        f"Ürün: [{product['name']}]({product['url']})\n"
                        f"Eski Fiyat: {old_price:.2f} TL\n"
                        f"Yeni Fiyat: *{new_price:.2f} TL*\n"
                        f"{price_change_summary}"
                    )
                    
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode='MarkdownV2'
                        )
                        logger.info(f"Fiyat değişimi bildirimi gönderildi: {product['name']} -> Chat ID: {chat_id}")

                        if product.get('image_url'):
                            await context.bot.send_photo(chat_id=chat_id, photo=product['image_url'])

                    except Exception as e:
                        logger.error(f"Telegram mesajı gönderilirken hata: {e} (Ürün: {product['product_id']}, Chat: {chat_id})")
                        # Escape MarkdownV2 characters if there's an error, then retry with plain text or safer Markdown
                        if "Can't parse entities" in str(e):
                            try:
                                safe_name = product['name'].replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)')
                                safe_url = product['url'] # URLs are generally safe
                                message_safe = (
                                    f"{change_emoji} *{change_type_text}*\n\n"
                                    f"Ürün: [{safe_name}]({safe_url})\n"
                                    f"Eski Fiyat: {old_price:.2f} TL\n"
                                    f"Yeni Fiyat: *{new_price:.2f} TL*\n"
                                    f"{price_change_summary}"
                                )
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=message_safe,
                                    parse_mode='MarkdownV2'
                                )
                                logger.info(f"Fiyat değişimi bildirimi (güvenli mod) gönderildi: {product['name']} -> Chat ID: {chat_id}")
                            except Exception as e_safe:
                                logger.error(f"Telegram mesajı (güvenli mod) gönderilirken hata: {e_safe}")
                                # Fallback to plain text
                                message_plain = (
                                    f"{change_emoji} {change_type_text}\n\n"
                                    f"Ürün: {product['name']} ({product['url']})\n"
                                    f"Eski Fiyat: {old_price:.2f} TL\n"
                                    f"Yeni Fiyat: {new_price:.2f} TL\n"
                                    f"{price_change_summary}"
                                )
                                await context.bot.send_message(chat_id=chat_id, text=message_plain)
                                logger.info(f"Fiyat değişimi bildirimi (düz metin) gönderildi: {product['name']} -> Chat ID: {chat_id}")


                await asyncio.sleep(1) # Be gentle to the scraper and DB
            except Exception as e:
                logger.error(f"Ürün kontrolünde hata: {product.get('product_id','Bilinmeyen ID')} - {e}")
                traceback.print_exc()
                continue
    except Exception as e:
        logger.error(f"check_prices_job genel hata: {e}")
        traceback.print_exc()
    finally:
        if db:
            db.close()
        logger.info("Fiyat kontrol görevi tamamlandı.")

from handlers.telegram_commands import register_commands

if __name__ == "__main__":
    if not TELEGRAM_TOKEN:
        logger.error("Telegram token bulunamadı! Lütfen .env dosyasına TELEGRAM_TOKEN ekleyin.")
        exit(1)

    logger.info("Bot başlatılıyor...")

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Store db and scraper instances for handlers to use via context.bot_data
    # Ensure DATABASE_PATH, PROXY_ENABLED, VERIFY_SSL are loaded correctly from .env
    try:
        db_instance = Database(db_name=DATABASE_PATH)
        scraper_instance = TrendyolScraper(use_proxy=PROXY_ENABLED, verify_ssl=VERIFY_SSL)
        application.bot_data['db'] = db_instance
        application.bot_data['scraper'] = scraper_instance
        logger.info("Veritabanı ve kazıyıcı örnekleri başarıyla oluşturuldu ve bot_data'ya eklendi.")
    except Exception as e:
        logger.error(f"Veritabanı veya kazıyıcı başlatılırken hata: {e}")
        traceback.print_exc()
        exit(1) # Critical error, bot cannot function

    # Schedule the price checking job
    job_queue = application.job_queue
    # Pass db and scraper to the job if needed, or it can access from bot_data too if context is properly handled
    # For run_repeating, context.job.data can be used to pass data
    job_queue.run_repeating(check_prices_job, interval=CHECK_INTERVAL, first=10, data={'db_path': DATABASE_PATH, 'proxy': PROXY_ENABLED, 'ssl_verify': VERIFY_SSL})
    logger.info(f"Fiyat kontrol görevi {CHECK_INTERVAL} saniyede bir çalışacak şekilde ayarlandı.")

    # Register command handlers
    register_commands(application)
    logger.info("Komut işleyicileri yüklendi.")

    logger.info("Telegram botu başlatıldı ve poling yapıyor...")
    application.run_polling()
    logger.info("Bot durduruldu.")
