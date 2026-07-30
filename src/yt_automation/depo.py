"""SQLite deposu — süreçler arası paylaşılan durum.

Neden veritabanı: ADR-0004 *"veritabanı yok"* demişti ve gerekçesi doğruydu —
günde 6 videoluk bir kuyruğun çözeceği bir problemi yok. Kota sayacı farklı
bir şekil: **iki ayrı süreç** aynı günlük bütçeden içiyor (yükleme hattı ve
trend hattı) ve "oku, kontrol et, yaz" sırası bölünürse bütçe sessizce aşılır.

Dosya + kilit ile de çözülebilirdi ama doğru kilitleme yazmak, `sqlite3`'ün
standart kütüphanede hazır verdiği şeyi elde etmeye çalışmak olurdu.
Ayrıntılı gerekçe: `docs/decisions/0005-kota-kaliciligi-sqlite.md`.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

VARSAYILAN_DIZIN = "veri"
VERI_DIZINI_DEGISKENI = "YT_OTOMASYON_VERI"

# Şema sürümü — `PRAGMA user_version` ile saklanıyor. Tablo veya indeks
# eklediğinizde **artırın**, yoksa mevcut veritabanları yeni şemayı almaz.
#
# 1 → kota defteri + YouTube trend tabloları
# 2 → Wikipedia makale/okunma tabloları (DW-34)
# 3 → kaynak dosyası: referans, olgu, görsel (DW-37)
# 4 → arz sondajı: talep-arz boşluğu ölçümü (DW-35)
SEMA_SURUMU = 4

SEMA = """
CREATE TABLE IF NOT EXISTS kota_harcama (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    gun    TEXT    NOT NULL,  -- Pasifik takvim günü (YYYY-AA-GG) — kotanın sıfırlandığı sınır
    an     TEXT    NOT NULL,  -- UTC, ISO 8601
    islem  TEXT    NOT NULL,
    birim  INTEGER NOT NULL,
    surec  TEXT              -- harcamayı kimin yaptığı: "yukleme", "trend", …
);

CREATE INDEX IF NOT EXISTS kota_harcama_gun ON kota_harcama(gun);

-- Bir videonun değişmeyen bilgisi. Aynı video onlarca bölgede ve her koşuda
-- yeniden görünür; burada bir kez durur.
CREATE TABLE IF NOT EXISTS video (
    video_id        TEXT PRIMARY KEY,
    baslik          TEXT NOT NULL,
    kanal_id        TEXT,
    kanal_adi       TEXT,
    yayin_zamani    TEXT,     -- UTC, ISO 8601
    kategori_id     INTEGER,  -- YouTube'un videoya atadığı kategori
    sure_sn         INTEGER,
    dil             TEXT,     -- DW-30 dolduracak
    dil_kaynagi     TEXT,     -- defaultAudioLanguage | defaultLanguage | llm
    konu_etiketleri TEXT,     -- JSON dizi, topicDetails.topicCategories
    sinif           TEXT,     -- DW-30 dolduracak: tarih | bilim | diger
    sinif_kaynagi   TEXT,     -- kategori | konu | llm
    ilk_gorulme     TEXT NOT NULL
);

-- Zaman serisi: bir videonun bir bölgede, bir koşu anındaki durumu.
-- DW-29'un hız/ivme hesabı bu tablodan türetilecek.
CREATE TABLE IF NOT EXISTS olcum (
    video_id       TEXT    NOT NULL,
    bolge          TEXT    NOT NULL,
    an             TEXT    NOT NULL,  -- koşu zamanı (UTC); tüm çağrılar aynı değeri taşır
    liste_kategori INTEGER,           -- hangi listede göründü (0 = kısıtsız)
    sira           INTEGER,
    izlenme        INTEGER,
    begeni         INTEGER,
    yorum          INTEGER,
    PRIMARY KEY (video_id, bolge, an)
);

CREATE INDEX IF NOT EXISTS olcum_an ON olcum(an);
CREATE INDEX IF NOT EXISTS olcum_video ON olcum(video_id);

-- Koşu defteri: ne zaman, ne kadar bölge, kaç çağrı, kaç birim, kaç hata.
CREATE TABLE IF NOT EXISTS kosu (
    an            TEXT PRIMARY KEY,
    tur           TEXT NOT NULL,  -- genis | derin
    bolge_sayisi  INTEGER,
    cagri_sayisi  INTEGER,
    harcanan_kota INTEGER,
    hata          TEXT            -- boşsa hatasız; doluysa "<sayı> bölge: <örnek>"
);

-- Wikipedia makalesi. Anahtar (dil, başlık): aynı konu her dilde ayrı satır,
-- çünkü okunma da dil bazında. Diller arası bağ `qid` üzerinden kurulur.
CREATE TABLE IF NOT EXISTS makale (
    dil           TEXT NOT NULL,
    baslik        TEXT NOT NULL,
    qid           TEXT,     -- Wikidata kimliği; diller arası ortak kimlik
    turler        TEXT,     -- JSON, Wikidata P31/P279 kimlikleri
    sinif         TEXT,     -- tarih | bilim | diger | belirsiz
    sinif_kaynagi TEXT,     -- wikidata | llm
    ilk_gorulme   TEXT NOT NULL,
    PRIMARY KEY (dil, baslik)
);

CREATE INDEX IF NOT EXISTS makale_qid ON makale(qid);
CREATE INDEX IF NOT EXISTS makale_sinif ON makale(sinif);

-- Günlük okunma serisi. Wikipedia gün bazında yayımlıyor, saat bazında değil —
-- hız/ivme hesabının çözünürlüğü bu yüzden bir gün.
CREATE TABLE IF NOT EXISTS okunma (
    dil     TEXT    NOT NULL,
    baslik  TEXT    NOT NULL,
    gun     TEXT    NOT NULL,  -- YYYY-AA-GG
    okunma  INTEGER NOT NULL,
    sira    INTEGER,           -- o günün listesindeki yeri; seri çekiminde boş
    PRIMARY KEY (dil, baslik, gun)
);

CREATE INDEX IF NOT EXISTS okunma_gun ON okunma(gun);

-- Bir adayın kaynak dosyası: videodaki iddiaların dayanağı.
--
-- PRD'nin YPP karşı önlemlerinin birincisi "her videonun altında gerçek bir
-- kaynak" diyor. Diğer tablolar konu **seçiyor**; bu tablo seçilen konunun
-- neye dayanacağını tutuyor.
--
-- `qid` üzerinden anahtarlanıyor, (dil, baslik) üzerinden değil: aynı konu
-- her dilde ayrı makale ama kaynaklar ortak. Bir kez çekilir, hepsi kullanır.
CREATE TABLE IF NOT EXISTS kaynak (
    qid      TEXT NOT NULL,
    tur      TEXT NOT NULL,  -- referans | olgu | gorsel
    deger    TEXT NOT NULL,  -- URL, olgu metni ya da dosya adı
    etiket   TEXT,           -- olgunun ne olduğu ("kuruluş tarihi")
    atif     TEXT,           -- görselde zorunlu: kime atıf verilecek
    lisans   TEXT,           -- görselde zorunlu: boşsa kullanılmaz
    cekilme  TEXT NOT NULL,
    PRIMARY KEY (qid, tur, deger)
);

CREATE INDEX IF NOT EXISTS kaynak_qid ON kaynak(qid);

-- Arz sondajı: bir konuda YouTube'da **ne varsa** onun ölçümü.
--
-- Huninin tek pahalı adımı burası (sondaj başına 102 birim), o yüzden sonuç
-- diske yazılıyor: aynı konuyu iki kez sondalamak 102 birimi çöpe atmak olur.
--
-- ⚠️ **Skor burada yok ve bu bilinçli.** Skor bu ölçümlerden türetiliyor;
-- saklanırsa ağırlıklar ayarlandığında bayatlar ve "hangi formülle
-- hesaplanmıştı" sorusu doğar. Ham ölçüm kalıcı, skor okuma anında.
--
-- `search.list`'in `totalResults` alanı **kaydedilmiyor**: Google onu tahmini
-- veriyor ve gerçekten yanıltıcı. Arz, dönen videoların kendi
-- istatistiklerinden ölçülüyor.
CREATE TABLE IF NOT EXISTS arz (
    qid            TEXT    NOT NULL,
    dil            TEXT    NOT NULL,  -- sondajın dili (relevanceLanguage)
    an             TEXT    NOT NULL,
    sorgu          TEXT    NOT NULL,
    donen          INTEGER NOT NULL,  -- search.list'in döndürdüğü video sayısı
    alakali        INTEGER NOT NULL,  -- başlığı konuyla gerçekten örtüşen
    medyan_izlenme INTEGER,
    ust_izlenme    INTEGER,
    medyan_yas_gun INTEGER,
    medyan_abone   INTEGER,
    harcanan       INTEGER NOT NULL,  -- bu sondajın gerçek kota maliyeti
    PRIMARY KEY (qid, dil, an)
);

CREATE INDEX IF NOT EXISTS arz_qid ON arz(qid);
"""


def varsayilan_yol() -> Path:
    """Veritabanının varsayılan yeri.

    `YT_OTOMASYON_VERI` ortam değişkeni verilmişse orası, yoksa çalışma
    dizinindeki `veri/`. Depo git'e girmez (`.gitignore`).
    """
    return Path(os.environ.get(VERI_DIZINI_DEGISKENI) or VARSAYILAN_DIZIN) / "yt_automation.db"


def baglan(yol: Path) -> sqlite3.Connection:
    """Şeması hazır bir bağlantı açar.

    `isolation_level=None` bilinçli: Python'un örtük işlem yönetimi kapanır,
    işlemi biz `BEGIN IMMEDIATE` ile açarız. Örtük mod `BEGIN DEFERRED`
    kullanıyor ve yazma kilidini ilk `INSERT`'e kadar almıyor — tam olarak
    kaçındığımız yarış oradan doğar.
    """
    yol.parent.mkdir(parents=True, exist_ok=True)
    baglanti = sqlite3.connect(yol, isolation_level=None, timeout=30.0)
    baglanti.row_factory = sqlite3.Row

    # ⚠️ `busy_timeout` en başta gelmeli: kendisi kilit istemez ama ondan
    # sonraki ifadelere "kilit varsa bekle" davranışını kazandırır.
    baglanti.execute("PRAGMA busy_timeout=30000")

    # ⚠️ `journal_mode` değişimi özel (exclusive) kilit istiyor ve
    # `busy_timeout`u **onurlandırmıyor**: başka bağlantı işlemdeyse beklemeden
    # `SQLITE_BUSY` döner. Bu satır iki kez "düzeltildi" ve iki kez geri geldi:
    #
    #   1. Pragma sırası düzeltildi (busy_timeout önce)     → 25 iş parçacığında düştü
    #   2. Koşullu hale getirildi (önce oku, gerekiyorsa yaz) → yeni veritabanında düştü
    #
    # İkincisinin kaçırdığı: **yeni** bir dosyada tüm bağlantılar aynı anda
    # "WAL değil" görüyor ve hepsi geçişi deniyor. Koşul pencereyi daralttı,
    # kapatmadı.
    #
    # Yarışı kazanmaya çalışmak yanlış çerçeve. WAL **kalıcı bir veritabanı
    # özelliği**: yarışı başkası kazandıysa bizim için de kurulmuş demektir.
    # Bu yüzden hata yutuluyor — kaybetmek zararsız.
    if (baglanti.execute("PRAGMA journal_mode").fetchone()[0] or "").lower() != "wal":
        # Hata yutuluyor: başka bir bağlantı tam bu anda kuruyor olabilir. O
        # durumda bu bağlantı bu seferlik eski kip'te çalışır — doğruluk
        # etkilenmez, yalnızca eşzamanlılık.
        with suppress(sqlite3.OperationalError):
            baglanti.execute("PRAGMA journal_mode=WAL")

    # Aynı gerekçe şema için: `CREATE TABLE IF NOT EXISTS` var olan tabloda
    # işe yaramıyor ama yine de yazma kilidi alıyor. `user_version` ucuz bir
    # okuma; şema yalnızca gerçekten eksikse kuruluyor.
    if baglanti.execute("PRAGMA user_version").fetchone()[0] < SEMA_SURUMU:
        baglanti.executescript(SEMA)
        baglanti.execute(f"PRAGMA user_version = {SEMA_SURUMU}")
    return baglanti


@contextmanager
def yazma_islemi(yol: Path) -> Iterator[sqlite3.Connection]:
    """Serileştirilmiş yazma işlemi.

    `BEGIN IMMEDIATE` yazma kilidini **işlemin başında** alır. İki süreç aynı
    anda girerse biri bekler; ikisi de aynı "kalan" değerini okuyup ikisi de
    harcayamaz. Kota muhasebesinin tek gerçek güvencesi budur.
    """
    baglanti = baglan(yol)
    try:
        baglanti.execute("BEGIN IMMEDIATE")
        try:
            yield baglanti
        except BaseException:
            baglanti.execute("ROLLBACK")
            raise
        baglanti.execute("COMMIT")
    finally:
        baglanti.close()
