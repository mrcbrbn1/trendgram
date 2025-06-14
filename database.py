import sqlite3
import json
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_name="data/trendyol_tracker.sqlite"):
        """Veritabanı bağlantısını başlatır ve tabloları oluşturur."""
        self.db_name = db_name
        
        try:
            # Eğer data klasörü yoksa oluştur
            os.makedirs(os.path.dirname(db_name), exist_ok=True)
            
            # Tam dosya yolunu al
            abs_path = os.path.abspath(db_name)
            logger.info(f"Veritabanı dosyası yolu: {abs_path}")
            
            # Klasör yazılabilir mi?
            if os.access(os.path.dirname(abs_path), os.W_OK):
                logger.info(f"Klasöre yazma izni var: {os.path.dirname(abs_path)}")
            else:
                logger.error(f"HATA: Klasöre yazma izni yok: {os.path.dirname(abs_path)}")
            
            # Veritabanı bağlantısı oluştur
            self.conn = sqlite3.connect(db_name)
            self.cursor = self.conn.cursor()
            self.create_tables()
            logger.info(f"Veritabanı bağlantısı başarıyla kuruldu: {db_name}")
        except Exception as e:
            logger.error(f"Veritabanı bağlantısı oluşturulurken hata: {e}")
            logger.error(f"Veritabanı dosyası: {db_name}")
            raise

    def create_tables(self):
        """Gerekli tabloları oluşturur."""
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT UNIQUE,
            name TEXT,
            url TEXT,
            image_url TEXT,
            current_price REAL,
            original_price REAL,
            added_at TIMESTAMP,
            last_checked TIMESTAMP,
            chat_id TEXT,
            user_id TEXT,
            notifications_enabled BOOLEAN DEFAULT 1
        )
        ''')

        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            price REAL,
            date TIMESTAMP,
            FOREIGN KEY(product_id) REFERENCES products(product_id)
        )
        ''')
        
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_settings (
            chat_id TEXT PRIMARY KEY,
            check_interval_seconds INTEGER,
            last_check_timestamp TIMESTAMP
        )
        ''')

        self.conn.commit()

    def set_chat_check_interval(self, chat_id: str, interval_seconds: int, default_last_check: str | None = None):
        """Belirli bir sohbet için kontrol aralığını ayarlar veya günceller."""
        try:
            if default_last_check is None:
                # If setting interval for the first time and no last_check, don't set it to now,
                # let the check_prices_job handle the first check immediately if needed.
                # Or, set to a very old timestamp to ensure it runs soon.
                # For simplicity, we can set it to NULL or let the ON CONFLICT handle it.
                # If we want to ensure last_check_timestamp is populated, we might need a different strategy.
                # Let's assume last_check_timestamp can be NULL initially or managed by update_chat_last_check.
                # The provided SQL in plan uses excluded.last_check_timestamp, so it must exist or be defaulted.
                # The plan's SQL for this method seems to assume last_check_timestamp is always provided or defaulted.
                # Let's use current time if not provided, as per plan.
                default_last_check = datetime.now().isoformat()

            self.cursor.execute('''
                INSERT INTO chat_settings (chat_id, check_interval_seconds, last_check_timestamp)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    check_interval_seconds = excluded.check_interval_seconds
            ''', (chat_id, interval_seconds, default_last_check))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Chat ({chat_id}) için interval ayarlanırken hata: {e}")
            return False

    def get_chat_setting(self, chat_id: str) -> dict | None:
        """Belirli bir sohbetin ayarlarını getirir."""
        self.cursor.execute("SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,))
        row = self.cursor.fetchone()
        if row:
            columns = [desc[0] for desc in self.cursor.description]
            return dict(zip(columns, row))
        return None

    def update_chat_last_check(self, chat_id: str, timestamp: str, default_interval_if_new: int = 3600):
        """Bir sohbetin son kontrol zamanını günceller, yoksa varsayılan interval ile yeni kayıt oluşturur."""
        try:
            self.cursor.execute('''
                INSERT INTO chat_settings (chat_id, check_interval_seconds, last_check_timestamp)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    last_check_timestamp = excluded.last_check_timestamp
            ''', (chat_id, default_interval_if_new, timestamp))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Chat ({chat_id}) için son kontrol zamanı güncellenirken hata: {e}")
            return False

    def add_product(self, product_data, chat_id, user_id):
        """Ürün ekler ve ilk fiyat kaydını oluşturur."""
        try:
            now = datetime.now().isoformat()
            
            # Ürünü ekleme
            self.cursor.execute('''
            INSERT INTO products 
            (product_id, name, url, image_url, current_price, original_price, added_at, last_checked, chat_id, user_id, notifications_enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                product_data['product_id'],
                product_data['name'],
                product_data['url'],
                product_data['image_url'],
                product_data['current_price'],
                product_data['original_price'],
                now,
                now,
                chat_id,
                user_id,
                1 # notifications_enabled defaults to True (1)
            ))
            
            # Fiyat geçmişi kaydı ekleme
            self.cursor.execute('''
            INSERT INTO price_history 
            (product_id, price, date) 
            VALUES (?, ?, ?)
            ''', (
                product_data['product_id'],
                product_data['current_price'],
                now
            ))
            
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Aynı ürün zaten eklenmişse
            return False
        except Exception as e:
            print(f"Ürün eklenirken hata: {e}")
            return False

    def get_product(self, product_id):
        """Belirli bir ürünün bilgilerini getirir."""
        self.cursor.execute('''
        SELECT * FROM products WHERE product_id = ?
        ''', (product_id,))
        
        result = self.cursor.fetchone()
        if result:
            columns = [desc[0] for desc in self.cursor.description]
            return dict(zip(columns, result))
        return None

    def get_all_products(self, chat_id=None, user_id=None):
        """Tüm ürünleri veya belirli bir kullanıcı/sunucu için ürünleri getirir."""
        query = "SELECT * FROM products"
        params = []
        
        if chat_id:
            query += " WHERE chat_id = ?"
            params.append(chat_id)
            
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
        
        self.cursor.execute(query, params)
        results = self.cursor.fetchall()
        
        products = []
        if results:
            columns = [desc[0] for desc in self.cursor.description]
            for row in results:
                products.append(dict(zip(columns, row)))
        
        return products

    def update_product_price(self, product_id, new_price):
        """Ürün fiyatını günceller ve fiyat geçmişine ekler."""
        try:
            now = datetime.now().isoformat()
            
            logger.info(f"Ürün fiyatı güncelleniyor: {product_id} -> {new_price} TL")
            
            # Ürün fiyatını güncelleme
            self.cursor.execute('''
            UPDATE products 
            SET current_price = ?, last_checked = ? 
            WHERE product_id = ?
            ''', (new_price, now, product_id))
            
            update_row_count = self.cursor.rowcount
            logger.info(f"Güncellenen satır sayısı: {update_row_count}")
            
            # Fiyat geçmişi kaydı ekleme
            self.cursor.execute('''
            INSERT INTO price_history 
            (product_id, price, date) 
            VALUES (?, ?, ?)
            ''', (product_id, new_price, now))
            
            insert_row_count = self.cursor.rowcount
            logger.info(f"Eklenen fiyat geçmişi satır sayısı: {insert_row_count}")
            
            self.conn.commit()
            logger.info(f"İşlemler veritabanına kaydedildi (commit yapıldı)")
            return True
        except Exception as e:
            logger.error(f"Ürün fiyatı güncellenirken hata: {e}")
            self.conn.rollback()
            logger.error(f"İşlemler geri alındı (rollback yapıldı)")
            return False

    def get_price_history(self, product_id, limit=10):
        """Ürün fiyat geçmişini getirir."""
        self.cursor.execute('''
        SELECT price, date FROM price_history 
        WHERE product_id = ? 
        ORDER BY date DESC LIMIT ?
        ''', (product_id, limit))
        
        results = self.cursor.fetchall()
        history = []
        
        if results:
            for row in results:
                history.append({"price": row[0], "date": row[1]})
        
        return history

    def delete_product(self, product_id, chat_id=None, user_id=None):
        """Ürünü ve fiyat geçmişini siler."""
        try:
            if chat_id and user_id:
                self.cursor.execute('''
                DELETE FROM products 
                WHERE product_id = ? AND chat_id = ? AND user_id = ?
                ''', (product_id, chat_id, user_id))
            else:
                self.cursor.execute('''
                DELETE FROM products 
                WHERE product_id = ?
                ''', (product_id,))
                
            # İlişkili fiyat geçmişini silme
            self.cursor.execute('''
            DELETE FROM price_history 
            WHERE product_id = ?
            ''', (product_id,))
            
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            print(f"Ürün silinirken hata: {e}")
            return False

    def check_price_changes(self):
        """Fiyat değişikliklerini kontrol eder ve değişen ürünleri döndürür."""
        self.cursor.execute('''
        SELECT p.*, 
            (SELECT price FROM price_history 
             WHERE product_id = p.product_id 
             ORDER BY date DESC LIMIT 1, 1) as previous_price
        FROM products p
        ''')
        
        results = self.cursor.fetchall()
        changed_products = []
        
        if results:
            columns = [desc[0] for desc in self.cursor.description]
            for row in results:
                product = dict(zip(columns, row))
                
                # Eğer önceki fiyat varsa ve farklıysa
                if product['previous_price'] and product['current_price'] != product['previous_price']:
                    product['price_change'] = product['current_price'] - product['previous_price']
                    product['price_change_percentage'] = (product['price_change'] / product['previous_price']) * 100
                    changed_products.append(product)
        
        return changed_products

    def close(self):
        """Veritabanı bağlantısını kapatır."""
        if self.conn:
            self.conn.close()
        
    def test_database(self):
        """Veritabanı bağlantısını ve işlemlerini test eder."""
        try:
            # Test verisi oluştur
            test_data = {
                'product_id': 'test123',
                'name': 'Test Ürün',
                'url': 'https://www.trendyol.com/test-urun-p-123456',
                'image_url': 'https://test.com/image.jpg',
                'current_price': 99.99,
                'original_price': 129.99,
                'success': True
            }
            
            # Test verisini ekle
            result = self.add_product(test_data, 'test_chat', 'test_user')
            if result:
                logger.info("Veritabanı test verisi başarıyla eklendi.")
                
                # Eklenen veriyi kontrol et
                product = self.get_product('test123')
                if product:
                    logger.info(f"Test verisi başarıyla okundu: {product['name']}")
                    
                    # Test verisini sil
                    self.delete_product('test123')
                    logger.info("Test verisi silindi.")
                    return True
                else:
                    logger.error("Test verisi eklendi ancak okunamadı!")
            else:
                logger.error("Test verisi eklenemedi!")
            
            return False
        except Exception as e:
            logger.error(f"Veritabanı testi sırasında hata oluştu: {e}")
            return False

    def set_product_notification(self, product_id: str, chat_id: str, user_id: str, enabled: bool) -> bool:
        """Bir ürün için bildirim ayarını günceller."""
        try:
            self.cursor.execute('''
                UPDATE products
                SET notifications_enabled = ?
                WHERE product_id = ? AND chat_id = ? AND user_id = ?
            ''', (1 if enabled else 0, product_id, chat_id, user_id))
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logger.info(f"Product {product_id} in chat {chat_id} for user {user_id} notifications set to {enabled}. Rows affected: {self.cursor.rowcount}")
                return True
            else:
                # This can happen if product_id doesn't exist OR if chat_id/user_id doesn't match
                logger.warning(f"No product found for {product_id} in chat {chat_id} by user {user_id} to update notification status, or status is already {enabled}.")
                # To differentiate, we can do a SELECT first, but for now, this is acceptable.
                # Check if the product exists at all for this chat_id by this user_id
                self.cursor.execute("SELECT id FROM products WHERE product_id = ? AND chat_id = ? AND user_id = ?", (product_id, chat_id, user_id))
                if self.cursor.fetchone():
                    # Product exists, so it means the status was already what we tried to set it to.
                    # Or, if we want to be strict and say "updated", this should be False if value is same.
                    # For simplicity, if it exists and matches criteria, and new value is same, we can consider it "successful" in a way.
                    # However, rowcount will be 0 if value doesn't change.
                    # Let's return True if the final state is as requested, even if no change was made.
                    self.cursor.execute("SELECT notifications_enabled FROM products WHERE product_id = ? AND chat_id = ? AND user_id = ?", (product_id, chat_id, user_id))
                    current_db_state = self.cursor.fetchone()
                    if current_db_state and bool(current_db_state[0]) == enabled:
                        return True # State is already as requested
                return False # No row updated and state is not as requested or product not found by this user in this chat
        except Exception as e:
            logger.error(f"Product {product_id} için bildirim ayarı güncellenirken hata: {e}")
            return False