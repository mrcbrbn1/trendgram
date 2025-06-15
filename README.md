# Trendyol Takip Telegram Botu

Telegram üzerinden Trendyol ürünlerinin fiyatlarını takip etmenizi sağlayan bir bot.

## Özellikler

- Trendyol ürünlerini takip etme
- Fiyat değişikliklerinde otomatik Telegram bildirimi gönderme
- Ürün fiyat geçmişini izleme (son 10 kayıt)
- Proxy desteği ile istekleri yönetme (isteğe bağlı)
- Telegram üzerinden kolay kullanılabilir komutlar:
    - Sohbet bazlı özel fiyat kontrol aralığı ayarlama
    - Ürün bazlı bildirimleri açma/kapama

## Kurulum

Bu botu çalıştırmak için bilgisayarınızda Python 3.8 veya üzeri bir sürümün kurulu olması gerekmektedir.

**Ön Hazırlıklar:**

1.  **Python Kurulumu:**
    *   Eğer Python kurulu değilse, [python.org](https://www.python.org/downloads/) adresinden işletim sisteminize uygun sürümü indirip kurun. Kurulum sırasında "Add Python to PATH" seçeneğini işaretlemeyi unutmayın.
    *   Kurulumu doğrulamak için komut satırına (Terminal veya Komut İstemi) `python --version` veya `python3 --version` yazın.

2.  **Proje Dosyalarını Edinme:**
    *   Bu depoyu klonlayın veya ZIP olarak indirin.
        ```bash
        git clone <repository_url>
        cd <repository_directory_adı>
        ```
    *   Komut satırı/terminal üzerinden proje klasörünün içine gidin.

**Kurulum Adımları:**

1.  **(Önerilen) Sanal Ortam Oluşturma ve Aktifleştirme:**
    Proje bağımlılıklarını sistem genelindeki Python paketlerinden ayırmak için bir sanal ortam oluşturmanız önerilir.
    ```bash
    # Proje klasörünün içindeyken:
    python -m venv venv
    # veya macOS/Linux üzerinde python3 kullanıyorsanız:
    # python3 -m venv venv
    ```
    Sanal ortamı aktifleştirin:
    *   **Windows (Komut İstemi veya PowerShell):**
        ```cmd
        venv\Scriptsctivate
        ```
    *   **macOS / Linux (Terminal):**
        ```bash
        source venv/bin/activate
        ```
    Bundan sonraki komutları bu aktif sanal ortamda çalıştıracaksınız.

2.  **Gerekli Paketleri Yükleme:**
    Proje klasörünüzde `requirements.txt` dosyası bulunmaktadır. Aşağıdaki komut ile gerekli Python paketlerini yükleyin:
    ```bash
    pip install -r requirements.txt
    ```

3.  **`.env` Yapılandırma Dosyasını Oluşturma ve Düzenleme:**
    Proje ana dizininde `.env` adında bir dosya oluşturun ve aşağıdaki içeriği kendi bilgilerinize göre düzenleyerek içine yapıştırın:

    ```dotenv
    # Telegram Bot Token - BotFather'dan alınacak
    TELEGRAM_TOKEN=buraya_telegram_bot_tokeninizi_ekleyin

    # Bot Ayarları
    CHECK_INTERVAL=300 # Ana fiyat kontrol görevinin ne sıklıkla çalışacağı (saniye). Örn: 300 (5 dakika)
    DEFAULT_CHAT_INTERVAL=3600 # Sohbetler için varsayılan fiyat kontrol aralığı (saniye). Örn: 3600 (1 saat)

    PROXY_ENABLED=False # Proxy kullanımını etkinleştirmek için True yapın
    VERIFY_SSL=True # SSL sertifika doğrulaması. Proxy veya yerel ağ sorunları için False yapılabilir.

    # Veritabanı Ayarları
    DATABASE_PATH=data/trendyol_tracker.sqlite # Ana veritabanı dosyası
    BACKUP_DATABASE_PATH=data/database.sqlite # init_db.py tarafından oluşturulan yedek veritabanı yolu (isteğe bağlı)
    ```
    *   `TELEGRAM_TOKEN`: Telegram'da BotFather ile oluşturduğunuz botunuza ait token'ı buraya girin.
    *   `CHECK_INTERVAL`: Botun genel olarak ne sıklıkta fiyatları kontrol etmek için uyanacağını belirler.
    *   `DEFAULT_CHAT_INTERVAL`: Bir sohbet için özel bir aralık ayarlanmamışsa kullanılacak varsayılan kontrol aralığı.

4.  **Veritabanını Oluşturma:**
    `init_db.py` scriptini çalıştırarak veritabanı tablolarını oluşturun:
    ```bash
    python init_db.py
    # veya macOS/Linux üzerinde python3 kullanıyorsanız:
    # python3 init_db.py
    ```

5.  **Botu Çalıştırma:**
    Sanal ortamınızın aktif olduğundan emin olun.
    ```bash
    python main.py
    # veya macOS/Linux üzerinde python3 kullanıyorsanız:
    # python3 main.py
    ```
    Botunuz artık Telegram'da aktif olmalıdır.

## Komutlar

Aşağıda bot ile kullanabileceğiniz ana komutlar listelenmiştir:

*   `/ekle <Trendyol Linki>`: Belirtilen Trendyol ürününü takip listesine ekler.
    *   *Alias: `/add`*
*   `/liste`: Bu sohbette takip edilen ürünleri listeler.
    *   *Alias: `/takiptekiler`, `/list`*
*   `/bilgi <Ürün ID veya URL>`: Belirtilen ürün hakkında detaylı bilgi ve fiyat geçmişini verir.
    *   *Alias: `/info`*
*   `/sil <Ürün ID veya URL>`: Takip edilen bir ürünü bu sohbet için listeden çıkarır. (Sadece ürünü ekleyen kişi silebilir).
    *   *Alias: `/delete`, `/remove`*
*   `/guncelle <Ürün ID veya URL>`: Ürün fiyatını manuel olarak günceller ve veritabanına kaydeder.
    *   *Alias: `/update`*
*   `/ayarla_interval <saniye>`: Bu sohbet için ürün fiyatlarının ne sıklıkta kontrol edileceğini ayarlar.
    *   Minimum: 300 (5 dakika), Maksimum: 86400 (1 gün).
    *   Örnek: `/ayarla_interval 3600` (1 saatte bir kontrol)
    *   *Alias: `/set_interval`*
*   `/bildirimler <Ürün ID/URL> <on|off|aç|kapat>`: Belirli bir ürün için fiyat değişikliği bildirimlerini açar veya kapatır.
    *   Örnek: `/bildirimler urun123 on`
    *   *Alias: `/notifications`*
*   `/yardim`: Tüm komutları ve açıklamalarını gösterir.
    *   *Alias: `/help`*

## Proje Yapısı

- `main.py` - Ana Telegram bot dosyası
- `database.py` - Veritabanı işlemleri
- `scraper.py` - Trendyol ürün bilgilerini çekme işlemleri
- `handlers/telegram_commands.py` - Telegram komut işleyicileri
- `.env` - Konfigürasyon dosyası (sizin oluşturmanız gerekir)
- `proxies.txt` - Proxy listesi (isteğe bağlı, `PROXY_ENABLED=True` ise kullanılır)
- `requirements.txt` - Gerekli Python paketleri
- `init_db.py` - Veritabanını başlatan script
- `data/` - Veritabanı dosyalarının saklandığı klasör
  - `trendyol_tracker.sqlite` - Ana veritabanı dosyası

**Not (Proje Geçmişi Hakkında):**
Bu proje daha önce Discord botu olarak geliştirilmiş ve sonrasında Telegram'a uyarlanmıştır. Kod tabanında yapay zeka destekli araçlar kullanılarak düzenlemeler yapılmış olabilir. Bu süreçte artık kullanılmayan bazı eski dosyalar (örneğin `TrendyolTakipBotu/` klasörü, `database_alt.py`, `scraper_alt.py` gibi) temizlenmiştir. `manuel_kurulum.txt`, `req.txt`, `requirements_fix.txt` gibi dosyalarla karşılaşırsanız, bunlar genellikle projenin önceki versiyonlarından kalma veya alternatif kurulum denemelerine ait dosyalardır; güncel kurulum için yukarıdaki adımları takip etmeniz yeterlidir.

## Sorun Giderme

- **Python veya pip komutu bulunamadı hatası**: Python kurulumu sırasında "Add Python to PATH" seçeneğini işaretlediğinizden emin olun.
- **Sanal ortam hataları**: Sanal ortamı doğru oluşturup aktifleştirdiğinizden emin olun. Komut satırınızın başında `(venv)` gibi bir ifade görmelisiniz.
- **Veritabanı bağlantı hatası**: `data` klasörünün var olduğundan ve yazma izinlerine sahip olduğunuzdan emin olun. `init_db.py` scriptini çalıştırarak veritabanını oluşturduğunuzu teyit edin.
- **Proxy bağlantı sorunları**:
  - `.env` dosyasında `PROXY_ENABLED=False` ayarını kullanarak proxy kullanımını devre dışı bırakabilirsiniz.
  - `proxies.txt` dosyasına çalışan proxy'ler eklediğinizden emin olun.
  - SSL hataları alıyorsanız `.env` dosyasında `VERIFY_SSL=False` olarak ayarlamayı deneyebilirsiniz (özellikle kendi kendine imzalanmış sertifikalı proxy'ler için).

## Proxy Kullanımı

Bot, (eğer `.env` dosyasında `PROXY_ENABLED=True` olarak ayarlanmışsa) `proxies.txt` dosyasındaki proxy listesini kullanır.

1.  Proje ana dizininde `proxies.txt` adında bir dosya oluşturun (eğer yoksa).
2.  Her satıra bir proxy `IP:PORT` formatında ekleyin.
3.  Yorum satırlarını `#` ile başlatabilirsiniz.

## Lisans

Bu proje MIT lisansı altında lisanslanmıştır. Daha fazla bilgi için proje içerisindeki `LICENSE` dosyasına bakın.