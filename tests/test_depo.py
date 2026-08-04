"""Depo bağlantısı — WAL kurulumunun kilit altındaki davranışı.

Bu dosya `test_kota_kalicilik.py`'den ayrı çünkü oradaki testler **kota
muhasebesini** doğruluyor; buradakiler **bağlantı kurulumunu**. Aynı hata
ikisini birden düşürüyordu ama sebep depoda.

## Neden eşzamanlılık testi değil

İlk denemem 32 iş parçacığını bariyerle senkronlayıp yarışı tetiklemekti.
Kusurlu kodda ölçtüm: 1280 açmada 1 hata. Yani tek koşuda **geçiyor** —
`test_kota_kalicilik.py`'deki eşzamanlılık testlerinin kusurlu `main`'de
yerelde 15/15 geçmesinin sebebi de bu.

İki kez düzeltilip iki kez geri gelmiş bir hatayı olasılığa bağlı bir test
koruyamaz. Buradaki testler bunun yerine **kilidi kendileri tutuyor**:
yarışı beklemek yerine kaybedilen hâli doğrudan kuruyorlar.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from yt_automation import depo


def _wal_olmayan_veritabani(yol: Path) -> None:
    """`baglan` dokunmadan önce dosyayı `delete` kip'inde var eder."""
    yol.parent.mkdir(parents=True, exist_ok=True)
    kur = sqlite3.connect(yol)
    kur.execute("CREATE TABLE _tohum(a)")
    kur.commit()
    kur.close()


def test_wal_gecisi_engellenmisken_baglanti_yine_de_aciliyor(tmp_path: Path):
    """WAL'a geçilemiyorsa bağlantı açılmaya devam etmeli — patlamamalı.

    ## Neden deterministik

    Başka bir bağlantı `BEGIN IMMEDIATE` tutarken:

    - `PRAGMA journal_mode` **okuması** geçiyor (rezerve kilit okuyucuyu
      engellemiyor) — yani "önce oku" adımı hâlâ "wal değil" görüyor,
    - `PRAGMA journal_mode=WAL` **yazması** anında `database is locked`
      veriyor; ölçüldü: 0.00 s, yani `busy_timeout=30000` devrede değil.

    Bu tam olarak yarışı kaybeden bağlantının gördüğü hâl — ama şansa değil,
    kurguya bağlı. Kusurlu kodda bu test her koşuda düşer.

    ## Neden kilit bırakılıyor

    `baglan`, WAL adımından sonra `executescript(SEMA)` çağırıyor ve **o**
    sıradan bir yazma kilidi — yani `busy_timeout`u onurlandırıyor. Kilit
    tutulmaya devam etseydi düzeltilmiş kod 30 saniye beklerdi. Kilit
    yalnızca WAL adımını düşürecek kadar tutuluyor.

    İki kilidin farklı davranması bu hatanın tam kalbi: biri bekliyor,
    diğeri beklemiyor.
    """
    yol = tmp_path / "veri" / "test.db"
    _wal_olmayan_veritabani(yol)

    kilit_alindi = threading.Event()
    birak = threading.Event()

    def engelle() -> None:
        baglanti = sqlite3.connect(yol, isolation_level=None, timeout=30.0)
        baglanti.execute("BEGIN IMMEDIATE")
        kilit_alindi.set()
        birak.wait(timeout=10)
        baglanti.execute("ROLLBACK")
        baglanti.close()

    engelleyen = threading.Thread(target=engelle)
    engelleyen.start()
    assert kilit_alindi.wait(timeout=10), "kilit alınamadı — test kurulumu bozuk"

    try:
        # Kusurlu kodda burası sqlite3.OperationalError fırlatıyor.
        # Düzeltilmişte WAL adımı sessizce atlanıyor, sonra şema adımı
        # kilidin bırakılmasını bekliyor.
        zamanlayici = threading.Timer(0.2, birak.set)
        zamanlayici.start()
        baglanti = depo.baglan(yol)
    finally:
        birak.set()
        zamanlayici.cancel()
        engelleyen.join(timeout=10)

    # Bağlantı yalnızca "patlamamış" değil, kullanılabilir de olmalı.
    assert baglanti.execute("SELECT 1").fetchone()[0] == 1
    baglanti.close()


def test_wal_zaten_kuruluyken_gecis_denenmiyor(tmp_path: Path):
    """Sıcak yolda gereksiz özel kilit istenmemeli.

    Yalnızca hatayı yutmak da bir üstteki testi geçirirdi. Bu test
    düzeltmenin **"önce oku"** yarısını koruyor: WAL kuruluysa geçiş hiç
    denenmemeli, çünkü her denemede özel kilit isteniyor ve o kilit her
    bağlantı açılışında diğer yazarları gereksizce bekletiyor.
    """
    yol = tmp_path / "veri" / "test.db"
    depo.baglan(yol).close()  # WAL burada kuruluyor

    denenen: list[str] = []
    gercek_connect = sqlite3.connect

    class Izleyen(sqlite3.Connection):
        """`sqlite3.Connection` C tipi ve değiştirilemez; alt sınıf gerekiyor."""

        def execute(self, sql, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN201
            if "journal_mode" in sql.lower() and "=" in sql:
                denenen.append(sql)
            return super().execute(sql, *args, **kwargs)

    def sahte_connect(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        kwargs["factory"] = Izleyen
        return gercek_connect(*args, **kwargs)

    sqlite3.connect = sahte_connect
    try:
        depo.baglan(yol).close()
    finally:
        sqlite3.connect = gercek_connect

    assert denenen == [], f"WAL zaten kuruluyken geçiş denendi: {denenen}"


# --- Şema geçişleri (DW-52) ------------------------------------------------


def test_gecis_eski_veritabanina_kirilim_kolonlarini_ekler(tmp_path: Path):
    """v6 → v7: `CREATE TABLE IF NOT EXISTS` var olan tabloya kolon ekleyemez;
    geçiş katmanı ekler. Eski satırlar NULL kalır — "kırılım ölçülmedi",
    sıfır değil."""
    yol = tmp_path / "eski.db"
    baglanti = sqlite3.connect(yol)
    # DW-52 öncesi arz tablosunun gerçek şekli (depo.py v6'dan)
    baglanti.execute(
        """
        CREATE TABLE arz (
            qid TEXT NOT NULL, dil TEXT NOT NULL, an TEXT NOT NULL,
            sorgu TEXT NOT NULL, donen INTEGER NOT NULL, alakali INTEGER NOT NULL,
            medyan_izlenme INTEGER, ust_izlenme INTEGER, medyan_yas_gun INTEGER,
            medyan_abone INTEGER, harcanan INTEGER NOT NULL,
            PRIMARY KEY (qid, dil, an)
        )
        """
    )
    baglanti.execute("INSERT INTO arz VALUES ('Q','en','t','s',50,10,100,200,30,400,102)")
    baglanti.execute("PRAGMA user_version = 6")
    baglanti.commit()
    baglanti.close()

    b = depo.baglan(yol)
    try:
        kolonlar = {s[1] for s in b.execute("PRAGMA table_info(arz)")}
        assert {
            "alakali_shorts",
            "medyan_izlenme_shorts",
            "alakali_uzun",
            "medyan_izlenme_uzun",
        } <= kolonlar
        assert b.execute("SELECT alakali_shorts FROM arz").fetchone()[0] is None
        assert b.execute("PRAGMA user_version").fetchone()[0] == depo.SEMA_SURUMU
    finally:
        b.close()

    # İkinci bağlanma idempotent: geçiş bir daha koşmaz, koşsa da düşmez.
    depo.baglan(yol).close()


def test_sifirdan_kurulum_gecis_gerektirmez(tmp_path: Path):
    """Yeni dosyada kolonlar SEMA'dan gelir; ALTER hiç denenmemeli (sürüm 0
    "hiç kurulmamış" demek). Deneseydi "duplicate column" yutulurdu ama bunu
    davranışa değil tesadüfe borçlu olmak istemiyoruz."""
    yol = tmp_path / "yeni.db"
    b = depo.baglan(yol)
    try:
        kolonlar = {s[1] for s in b.execute("PRAGMA table_info(arz)")}
        assert "alakali_shorts" in kolonlar
        assert b.execute("PRAGMA user_version").fetchone()[0] == depo.SEMA_SURUMU
    finally:
        b.close()
