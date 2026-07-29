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
from contextlib import contextmanager
from pathlib import Path

VARSAYILAN_DIZIN = "veri"
VERI_DIZINI_DEGISKENI = "YT_OTOMASYON_VERI"

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
    # ⚠️ Sıra önemli. `busy_timeout` en başta gelmeli: kendisi kilit istemez ama
    # ondan sonraki her ifadeye "kilit varsa bekle" davranışını kazandırır.
    # Sonra gelselerdi WAL geçişi ve şema kurulumu, başka bir yazar kilidi
    # tutarken beklemek yerine anında `database is locked` ile düşerdi.
    baglanti.execute("PRAGMA busy_timeout=30000")
    # WAL kalıcı bir veritabanı özelliği; okuyucuların yazarı beklememesini sağlar.
    baglanti.execute("PRAGMA journal_mode=WAL")
    baglanti.executescript(SEMA)
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
