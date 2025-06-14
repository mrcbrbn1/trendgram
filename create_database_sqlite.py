#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
database.sqlite dosyasını oluşturan script.
"""

import sqlite3
import os
import logging
import dotenv

# .env dosyasını yükle
dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Veritabanı yolunu .env'den al
DB_PATH = os.getenv('BACKUP_DATABASE_PATH', 'data/database.sqlite')

if __name__ == "__main__":
    logger.info(f"{DB_PATH} oluşturuluyor...")
    
    # Eğer data klasörü yoksa oluştur
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # Boş bir database.sqlite dosyası oluştur
    conn = sqlite3.connect(DB_PATH)
    
    # Temel tabloları oluştur
    cursor = conn.cursor()
    
    # Ürünler tablosu
    cursor.execute('''
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
    
    # Fiyat geçmişi tablosu
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT,
        price REAL,
        date TIMESTAMP,
        FOREIGN KEY(product_id) REFERENCES products(product_id)
    )
    ''')
    
    conn.commit()
    conn.close()
    
    logger.info(f"Veritabanı başarıyla oluşturuldu: {DB_PATH}")
    logger.info("Artık hem trendyol_tracker.sqlite hem de database.sqlite dosyaları mevcut.") 