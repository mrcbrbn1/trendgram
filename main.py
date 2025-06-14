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
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 300)) # How often the main job runs, e.g., every 5 minutes
DEFAULT_CHAT_INTERVAL = int(os.getenv('DEFAULT_CHAT_INTERVAL', 3600)) # Default per-chat check interval, e.g., 1 hour
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

        all_products = db.get_all_products()

        if not all_products:
            logger.info("Genel ürün listesinde takip edilen ürün bulunamadı.")
            # Still need to close DB if opened
            if db:
                db.close()
            return

        products_by_chat = {}
        for p in all_products:
            chat_id = p.get('chat_id')
            if chat_id:
                if chat_id not in products_by_chat:
                    products_by_chat[chat_id] = []
                products_by_chat[chat_id].append(p)

        if not products_by_chat:
            logger.info("Sohbetlere atanmış ürün bulunamadı.")
            if db:
                db.close()
            return

        logger.info(f"{len(all_products)} ürün {len(products_by_chat)} farklı sohbette kontrol edilecek.")
        current_time = datetime.now()

        for chat_id_str, products_in_chat in products_by_chat.items():
            chat_id = chat_id_str # Already a string from DB usually, but ensure
            logger.info(f"Sohbet {chat_id} için ürünler kontrol ediliyor. ({len(products_in_chat)} ürün)")

            chat_settings = db.get_chat_setting(chat_id)
            custom_interval = DEFAULT_CHAT_INTERVAL
            last_checked_for_this_chat_str = None

            if chat_settings:
                custom_interval = chat_settings.get('check_interval_seconds', DEFAULT_CHAT_INTERVAL)
                last_checked_for_this_chat_str = chat_settings.get('last_check_timestamp')

            if last_checked_for_this_chat_str:
                try:
                    last_checked_dt = datetime.fromisoformat(last_checked_for_this_chat_str)
                    seconds_since_last_check = (current_time - last_checked_dt).total_seconds()
                    if seconds_since_last_check < custom_interval:
                        logger.info(f"Sohbet {chat_id} için interval ({custom_interval}s) henüz dolmadı. Atlanıyor. ({int(seconds_since_last_check)}s/{custom_interval}s)")
                        continue
                except ValueError:
                    logger.warning(f"Sohbet {chat_id} için geçersiz tarih formatı: {last_checked_for_this_chat_str}. Kontrol ediliyor.")
            else: # No last check timestamp, first time for this chat or no settings yet
                logger.info(f"Sohbet {chat_id} için ilk kontrol veya zaman damgası yok. Kontrol ediliyor.")

            # Process products for this chat
            logger.info(f"Sohbet {chat_id} için {len(products_in_chat)} ürün işleniyor...")
            processed_chat = False
            for product in products_in_chat:
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

                    if product.get('notifications_enabled', True): # Check if notifications are enabled
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
                                    safe_name = product['name'].replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('.', '\\.')
                                    safe_url = product['url'] # URLs are generally safe
                                    message_safe = (
                                        f"{change_emoji} *{change_type_text}*\n\n"
                                        f"Ürün: [{safe_name}]({safe_url})\n"
                                        f"Eski Fiyat: {old_price:.2f} TL\n"
                                        f"Yeni Fiyat: *{new_price:.2f} TL*\n"
                                        f"{price_change_summary}"
                                    )
                                    await context.bot.send_message(
                                        chat_id=chat_id, # Corrected: Use chat_id from product
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
                                        f"Yeni Fiyat: {new_price:.2f} TL*\n" # Typo: TL* -> TL
                                        f"{price_change_summary}"
                                    )
                                    await context.bot.send_message(chat_id=chat_id, text=message_plain) # Corrected: Use chat_id from product
                                    logger.info(f"Fiyat değişimi bildirimi (düz metin) gönderildi: {product['name']} -> Chat ID: {chat_id}")
                    else:
                        logger.info(f"Bildirimler ürün {product['product_id']} ({product['name']}) için devre dışı bırakılmış (Chat ID: {chat_id}). Atlanıyor.")
                    processed_chat = True # Mark that at least one product in this chat was processed

                    await asyncio.sleep(1) # Be gentle to the scraper and DB
                except Exception as e:
                    logger.error(f"Ürün kontrolünde hata: {product.get('product_id','Bilinmeyen ID')} - {e}")
                    traceback.print_exc()
                    continue # Continue to the next product in this chat

            # After processing all products for this chat, update its last_check_timestamp
            if processed_chat or not last_checked_for_this_chat_str : # Update if processed or if it was the first time (no last_checked)
                logger.info(f"Sohbet {chat_id} için son kontrol zamanı güncelleniyor.")
                db.update_chat_last_check(chat_id, current_time.isoformat(), default_interval_if_new=custom_interval)
            else:
                logger.info(f"Sohbet {chat_id} için ürün işlenmedi veya zaten günceldi, zaman damgası güncellenmedi.")
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
