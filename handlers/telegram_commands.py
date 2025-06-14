# handlers/telegram_commands.py
import asyncio
import os
from datetime import datetime
import logging
import re

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

# Assuming database.py and scraper.py are in the parent directory or accessible in PYTHONPATH
# Adjust import if necessary, e.g., from ..database import Database
from database import Database
from scraper import TrendyolScraper

logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS ---

def escape_markdown_v2(text: str) -> str:
    """Escapes special characters for MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def get_db_scraper(context: ContextTypes.DEFAULT_TYPE) -> tuple[Database | None, TrendyolScraper | None]:
    """Helper to get db and scraper instances from bot_data."""
    db = context.bot_data.get('db')
    scraper = context.bot_data.get('scraper')
    if not db:
        logger.error("Database instance not found in bot_data.")
    if not scraper:
        logger.error("Scraper instance not found in bot_data.")
    return db, scraper

# --- INTERNAL LOGIC FUNCTIONS (Adapted for Telegram) ---

async def _internal_add_product_logic(url: str, chat_id: str, user_id: str, db: Database, scraper: TrendyolScraper):
    """Internal logic for adding a product."""
    if not scraper.is_valid_url(url):
        return False, "❌ Geçersiz Trendyol URL'si. Lütfen geçerli bir Trendyol ürün linki girin."

    product_data = scraper.scrape_product(url)
    if not product_data or not product_data.get('success', False):
        return False, "❌ Ürün bilgileri alınamadı. Lütfen URL'yi kontrol edin veya daha sonra tekrar deneyin."

    if product_data.get('current_price') is None:
         return False, "❌ Ürün fiyat bilgisi alınamadı. Ürün stokta olmayabilir veya sayfa yapısı değişmiş olabilir."

    # In Telegram, channel_id is not directly equivalent. We use chat_id.
    # The add_product method in database.py was already changed to accept chat_id.
    if db.add_product(product_data, chat_id, user_id): # Pass chat_id
        return True, product_data
    else:
        existing_product = db.get_product(product_data['product_id'])
        # Check if it exists for this specific chat_id
        if existing_product and str(existing_product.get('chat_id')) == str(chat_id):
             return False, "❌ Bu ürün zaten bu sohbette takip listenizde bulunuyor!"
        return False, "❌ Ürün eklenirken bir hata oluştu veya bu ürün zaten genel takip listenizde mevcut (başka bir sohbetten)."

async def _internal_list_products_logic(chat_id: str, db: Database):
    """Internal logic for listing products for a specific chat."""
    products = db.get_all_products(chat_id=str(chat_id)) # Filter by chat_id
    if not products:
        return False, "📋 Bu sohbette takip edilen ürün bulunmuyor."
    return True, products

async def _internal_product_info_logic(product_identifier: str, db: Database, scraper: TrendyolScraper):
    """Internal logic for getting product info."""
    product_id = scraper.extract_product_id(product_identifier)
    if not product_id:
        # Try to see if the identifier itself is a valid product ID (e.g. if it's just a number)
        # This part can be improved based on how product_id vs identifier is handled.
        # For now, assume extract_product_id handles both URLs and plain IDs.
        if scraper.is_valid_url(product_identifier): # It was a URL but not extractable
             return False, "❌ Geçerli bir ürün ID'si veya URL'si bulunamadı. URL yapısı tanınmıyor olabilir."
        # If not a valid URL, and not extractable, assume it might be an ID attempt
        product_id = product_identifier # Treat as direct ID

    product = db.get_product(product_id)
    if not product:
        if scraper.is_valid_url(product_identifier): # Check if it was a URL
            scraped_data = scraper.scrape_product(product_identifier)
            if scraped_data and scraped_data.get('success'):
                return True, {"scraped_data": scraped_data, "not_tracked": True}
        return False, f"❌ ID'si `{escape_markdown_v2(product_id)}` olan ürün veritabanında bulunamadı."

    price_history = db.get_price_history(product_id)
    return True, {"product": product, "price_history": price_history}

async def _internal_delete_product_logic(product_identifier: str, chat_id: str, requesting_user_id: str, db: Database, scraper: TrendyolScraper, is_chat_admin: bool = False):
    """Internal logic for deleting a product."""
    product_id = scraper.extract_product_id(product_identifier)
    if not product_id:
        product_id = product_identifier # Assume it's an ID if not extractable from URL

    product = db.get_product(product_id)
    if not product:
        return False, f"❌ ID'si `{escape_markdown_v2(product_id)}` olan bir ürün takip listenizde bulunamadı."

    # Check if the product is tracked in this specific chat
    if str(product.get('chat_id')) != str(chat_id):
        return False, f"❌ ID'si `{escape_markdown_v2(product_id)}` olan ürün bu sohbette takip edilmiyor."

    product_owner_id = product.get('user_id')
    # For Telegram, chat admin logic is more complex.
    # Simplification: only the user who added or a pre-defined admin/bot owner can delete.
    # For group chats, checking for chat admin status is possible but adds complexity.
    # For now, let's stick to user_id or allow if is_chat_admin (passed externally if needed).
    if str(requesting_user_id) != str(product_owner_id) and not is_chat_admin: # Add is_chat_admin check if implementing
        return False, "❌ Bu ürünü silmek için yetkiniz yok. Sadece ürünü ekleyen kişi silebilir." # Simplified message

    # db.delete_product was modified to accept chat_id for targeted deletion
    if db.delete_product(product_id, chat_id=str(chat_id), user_id=str(requesting_user_id)): # Ensure user matches for deletion
        return True, product.get('name', 'İsimsiz Ürün')
    elif db.delete_product(product_id, chat_id=str(chat_id)): # Fallback for admin if user_id doesn't match but admin wants to delete
        logger.warning(f"Product {product_id} deleted by non-owner {requesting_user_id} in chat {chat_id} (likely admin action).")
        return True, product.get('name', 'İsimsiz Ürün')
    else:
        # This case might happen if the product existed but couldn't be deleted by the db method (e.g. foreign key issues not expected here)
        # or if the product was from another chat_id but had the same product_id (less likely with current get_product)
        return False, f"❌ Ürün (`{escape_markdown_v2(product_id)}`) silinirken bir hata oluştu veya yetkiniz yok."


async def _internal_update_product_logic(product_identifier: str, db: Database, scraper: TrendyolScraper):
    """Internal logic for manually updating a product."""
    product_id = scraper.extract_product_id(product_identifier)
    if not product_id:
        product_id = product_identifier

    product_db = db.get_product(product_id) # This gets product globally, might need chat_id context if products can be non-unique globally
    if not product_db: # To update, it must be tracked somewhere
        return False, f"❌ ID'si `{escape_markdown_v2(product_id)}` olan bir ürün takip listesinde (herhangi bir sohbette) bulunamadı."

    product_url = product_db.get('url')
    if not product_url:
        return False, f"❌ Ürünün (`{escape_markdown_v2(product_id)}`) kayıtlı bir URL'si bulunamadı."

    new_data = scraper.scrape_product(product_url)
    if not new_data or not new_data.get('success', False):
        return False, f"❌ Ürün (`{escape_markdown_v2(product_id)}`) bilgileri Trendyol'dan alınamadı."

    if new_data.get('current_price') is None:
        return False, f"❌ Yeni fiyat bilgisi alınamadı (`{escape_markdown_v2(product_id)}`)."

    old_price = product_db.get('current_price')
    # update_product_price updates globally, which is fine. Price is an attribute of the product itself.
    db.update_product_price(product_id, new_data['current_price'])
    return True, {"new_data": new_data, "old_price": old_price, "product_id": product_id, "name": product_db.get("name")}


# --- TELEGRAM COMMAND HANDLERS ---

async def add_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db, scraper = await get_db_scraper(context)
    if not db or not scraper:
        await update.message.reply_text("Botun veritabanı veya kazıyıcı modülü hazır değil. Lütfen daha sonra tekrar deneyin.")
        return

    if not context.args:
        await update.message.reply_text("❌ Lütfen bir Trendyol ürün URL'si girin. Örnek: `/ekle https://www.trendyol.com/...`")
        return

    url = context.args[0]
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)

    # Defer reply if it takes time
    # await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    success, result = await _internal_add_product_logic(url, chat_id, user_id, db, scraper)

    if success:
        product_data = result
        message = (
            f"✅ *Ürün Takibe Alındı*\n\n"
            f"*{escape_markdown_v2(product_data['name'])}* artık takip listesinde\\!\n"
            f"ID: `{escape_markdown_v2(product_data['product_id'])}`\n"
            f"Fiyat: {product_data.get('current_price', 0):.2f} TL\n"
            f"[Trendyol'da Görüntüle]({product_data['url']})"
        )
        if product_data.get('image_url'):
            try:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=product_data['image_url'],
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e: # If photo fails, send text
                logger.warning(f"Telegram photo send failed for {product_data['product_id']}: {e}. Sending text only.")
                await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=False)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=False)
    else:
        await update.message.reply_text(result) # Error message

async def list_products_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db, scraper = await get_db_scraper(context)
    if not db or not scraper:
        await update.message.reply_text("Botun veritabanı veya kazıyıcı modülü hazır değil.")
        return

    chat_id = str(update.effective_chat.id)
    success, result = await _internal_list_products_logic(chat_id, db)

    if not success:
        await update.message.reply_text(result) # Error or no products message
        return

    products = result
    message_parts = [f"📋 *Bu Sohbette Takip Edilen Ürünler* \\({len(products)} adet\\):\n"]

    for i, p_db in enumerate(products[:20]): # Limit to avoid too long messages
        product_name = escape_markdown_v2(p_db.get('name', 'İsimsiz Ürün'))
        part = (
            f"\n*{i+1}\\. {product_name}*\n"
            f"   ID: `{escape_markdown_v2(p_db['product_id'])}`\n"
            f"   Fiyat: {p_db.get('current_price', 0):.2f} TL\n"
            f"   [Link]({p_db['url']})"
        )
        message_parts.append(part)

    if not message_parts: # Should not happen if success is True
        await update.message.reply_text("Takip edilen ürün bulunmuyor.")
        return

    final_message = "\n".join(message_parts)
    if len(products) > 20:
        final_message += f"\n\nℹ️ Toplam {len(products)} ürünün ilk 20 tanesi gösteriliyor."

    # Telegram has message length limits (4096 chars)
    if len(final_message) > 4000:
        await update.message.reply_text("Çok fazla ürün var, liste kısaltıldı. Daha sonra sayfalama eklenebilir.")
        # Basic truncation, could be smarter
        await update.message.reply_text(final_message[:4000] + "...", parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
    else:
        await update.message.reply_text(final_message, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)


async def product_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db, scraper = await get_db_scraper(context)
    if not db or not scraper:
        await update.message.reply_text("Botun veritabanı veya kazıyıcı modülü hazır değil.")
        return

    if not context.args:
        await update.message.reply_text("❌ Lütfen bir ürün ID'si veya URL'si girin. Örnek: `/bilgi <ID veya URL>`")
        return

    product_identifier = context.args[0]
    success, result = await _internal_product_info_logic(product_identifier, db, scraper)

    if not success:
        await update.message.reply_text(result)
        return

    if result.get("not_tracked"):
        scraped = result["scraped_data"]
        message = (
            f"*{escape_markdown_v2(scraped['name'])}*\n"
            f"⚠️ Bu ürün henüz takip listenizde değil\\. Takip etmek için `/ekle` komutunu kullanın\\.\n"
            f"ID: `{escape_markdown_v2(scraped['product_id'])}`\n"
            f"Fiyat: {scraped.get('current_price',0):.2f} TL\n"
            f"[Link]({scraped['url']})"
        )
        if scraped.get('image_url'):
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=scraped['image_url'], caption=message, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        return

    product = result["product"]
    price_history = result["price_history"]

    user_id_who_added = product.get('user_id')
    chat_id_where_added = product.get('chat_id') # This is the chat_id where it was added

    # Note: Getting user_name from user_id across chats is not straightforward or always possible for privacy reasons.
    # We can show the user_id or a generic message.
    added_by_info = f"Ekleyen Kullanıcı ID: `{escape_markdown_v2(str(user_id_who_added))}`"
    if str(chat_id_where_added) == str(update.effective_chat.id):
        added_by_info = f"Bu sohbette `{escape_markdown_v2(str(user_id_who_added))}` ID'li kullanıcı tarafından eklendi."
    else:
        added_by_info = f"Başka bir sohbette (`{escape_markdown_v2(str(chat_id_where_added))}`) `{escape_markdown_v2(str(user_id_who_added))}` ID'li kullanıcı tarafından eklendi."


    message = (
        f"*{escape_markdown_v2(product.get('name', 'İsimsiz Ürün'))}*\n"
        f"{added_by_info}\n\n"
        f"ID: `{escape_markdown_v2(product['product_id'])}`\n"
        f"Mevcut Fiyat: *{product.get('current_price',0):.2f} TL*\n"
    )

    original_price = product.get('original_price')
    current_price = product.get('current_price')
    if original_price and current_price and original_price != current_price and original_price > 0:
        discount_rate = ((original_price - current_price) / original_price) * 100
        message += f"Normal Fiyat: {original_price:.2f} TL \\(İndirim: %{discount_rate:.1f}\\)\n"

    message += f"[Trendyol'da Görüntüle]({product['url']})\n\n"

    if price_history:
        prices = [item['price'] for item in price_history if item.get('price') is not None]
        if prices:
            min_price = min(prices)
            max_price = max(prices)
            avg_price = sum(prices) / len(prices)
            message += (
                f"*Fiyat İstatistikleri:*\n"
                f"En Düşük: {min_price:.2f} TL\n"
                f"En Yüksek: {max_price:.2f} TL\n"
                f"Ortalama: {avg_price:.2f} TL\n\n"
            )

    try:
        added_at_dt = datetime.fromisoformat(product['added_at'])
        message += f"Eklenme Tarihi: {added_at_dt.strftime('%d.%m.%Y')}\n"
    except: pass
    try:
        last_checked_dt = datetime.fromisoformat(product['last_checked'])
        message += f"Son Kontrol: {last_checked_dt.strftime('%d.%m.%Y %H:%M')}\n"
    except: pass

    message += "\n*Fiyat Geçmişi \\(Son 5\\):*\n"
    if price_history:
        for entry in price_history[:5]:
            try:
                dt_object = datetime.fromisoformat(entry['date'])
                formatted_date = dt_object.strftime("%d.%m.%Y %H:%M")
                message += f"\\- {formatted_date}: {entry.get('price', 0):.2f} TL\n"
            except:
                 message += f"\\- {escape_markdown_v2(entry.get('date','Bilinmeyen Tarih'))}: {entry.get('price', 0):.2f} TL\n"
    else:
        message += "Kayıt yok\\.\n"

    if product.get('image_url'):
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=product['image_url'], caption=message, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)


async def delete_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db, scraper = await get_db_scraper(context)
    if not db or not scraper:
        await update.message.reply_text("Botun veritabanı veya kazıyıcı modülü hazır değil.")
        return

    if not context.args:
        await update.message.reply_text("❌ Lütfen silmek istediğiniz ürünün ID'sini veya URL'sini girin. Örnek: `/sil <ID>`")
        return

    product_identifier = context.args[0]
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)

    # Basic admin check (e.g. from a list of admin user IDs in .env) - not implemented here for simplicity
    # is_admin = user_id in context.bot_data.get('admin_users', [])
    is_admin = False # Placeholder

    success, result = await _internal_delete_product_logic(product_identifier, chat_id, user_id, db, scraper, is_admin)

    if success:
        product_name = result
        await update.message.reply_text(f"✅ *{escape_markdown_v2(product_name)}* adlı ürün bu sohbet için takip listesinden silindi.")
    else:
        await update.message.reply_text(result)


async def update_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db, scraper = await get_db_scraper(context)
    if not db or not scraper:
        await update.message.reply_text("Botun veritabanı veya kazıyıcı modülü hazır değil.")
        return

    if not context.args:
        await update.message.reply_text("❌ Lütfen güncellemek istediğiniz ürünün ID'sini veya URL'sini girin. Örnek: `/guncelle <ID>`")
        return

    product_identifier = context.args[0]
    # await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    success, result = await _internal_update_product_logic(product_identifier, db, scraper)

    if success:
        new_data = result["new_data"]
        old_price = result["old_price"]
        product_name = escape_markdown_v2(result.get("name", "İsimsiz Ürün"))

        message = (
            f"✅ *Ürün Güncellendi*\n\n"
            f"*{product_name}* (`{escape_markdown_v2(result['product_id'])}`) adlı ürünün fiyatı güncellendi\\.\n"
            f"Eski Fiyat: {old_price:.2f} TL\n"
            f"Yeni Fiyat: *{new_data.get('current_price',0):.2f} TL*\n"
        )

        current_price = new_data.get('current_price')
        if old_price is not None and current_price is not None and old_price != current_price:
            price_diff = current_price - old_price
            if old_price > 0: # Avoid division by zero
                percentage_change = abs(price_diff / old_price * 100)
                change_direction = "düşüş" if price_diff < 0 else "artış"
                emoji = "🔽" if price_diff < 0 else "🔼"
                message += f"Fiyat Değişimi: {emoji} {abs(price_diff):.2f} TL {change_direction} \\(%{percentage_change:.1f}\\)"
        elif old_price is not None and current_price is not None and old_price == current_price:
             message += "Fiyat değişmedi\\."

        if new_data.get('image_url'):
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=new_data['image_url'], caption=message, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(result)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📚 *Trendyol Takip Botu - Komutlar*\n\n"
        "`/ekle <URL>` \\- Belirtilen Trendyol ürününü takip listesine ekler\\.\n"
        "`/liste` veya `/takiptekiler` \\- Bu sohbette takip edilen ürünleri listeler\\.\n"
        "`/bilgi <ID veya URL>` \\- Belirtilen ürün hakkında detaylı bilgi ve fiyat geçmişi verir\\.\n"
        "`/sil <ID veya URL>` \\- Takip edilen bir ürünü bu sohbet için listeden çıkarır\\.\n"
        "`/guncelle <ID veya URL>` \\- Ürün fiyatını manuel olarak günceller ve veritabanına kaydeder\\.\n"
        "`/yardim` \\- Bu yardım mesajını gösterir\\."
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)

def register_commands(application):
    # Database and Scraper instances are expected to be in application.bot_data
    # They are retrieved by `get_db_scraper` in each handler.

    application.add_handler(CommandHandler("ekle", add_product_handler))
    application.add_handler(CommandHandler("add", add_product_handler)) # Alias

    application.add_handler(CommandHandler("takiptekiler", list_products_handler))
    application.add_handler(CommandHandler("liste", list_products_handler)) # Alias
    application.add_handler(CommandHandler("list", list_products_handler)) # Alias

    application.add_handler(CommandHandler("bilgi", product_info_handler))
    application.add_handler(CommandHandler("info", product_info_handler)) # Alias

    application.add_handler(CommandHandler("sil", delete_product_handler))
    application.add_handler(CommandHandler("delete", delete_product_handler)) # Alias
    application.add_handler(CommandHandler("remove", delete_product_handler)) # Alias

    application.add_handler(CommandHandler("guncelle", update_product_handler))
    application.add_handler(CommandHandler("update", update_product_handler)) # Alias

    application.add_handler(CommandHandler("yardim", help_handler))
    application.add_handler(CommandHandler("help", help_handler)) # Alias

    logger.info("Telegram command handlers registered.")
