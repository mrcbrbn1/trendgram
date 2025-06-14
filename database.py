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
            user_id TEXT
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
        
        self.conn.commit()

    def add_product(self, product_data, chat_id, user_id):
        """Ürün ekler ve ilk fiyat kaydını oluşturur."""
        try:
            now = datetime.now().isoformat()
            
            # Ürünü ekleme
            self.cursor.execute('''
            INSERT INTO products 
            (product_id, name, url, image_url, current_price, original_price, added_at, last_checked, chat_id, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                user_id
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