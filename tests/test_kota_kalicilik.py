"""Kalıcı kota sayacı — süreçler arası muhasebe.

Buradaki asıl iddia "harcama diske yazılıyor" değil, **"iki süreç aynı
bütçeyi aşamıyor"**. Testler o iddiayı hedefliyor.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yt_automation import kota


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "veri" / "test.db"


def test_harcama_yeni_ornekte_gorunur(db: Path):
    """Asıl senaryo: ayrı süreçler ayrı nesne kurar, aynı defteri görmeli."""
    kota.KaliciSayac(db).harca("videos.insert")

    # İkinci "süreç" — sıfırdan kurulan bağımsız bir sayaç.
    ikinci = kota.KaliciSayac(db)
    assert ikinci.harcanan == 1_600
    assert ikinci.kalan == kota.GUNLUK_BUTCE - 1_600


def test_butce_asiminda_deftere_yazilmaz(db: Path):
    s = kota.KaliciSayac(db, butce=100)
    with pytest.raises(kota.KotaAsimi, match="videos.insert"):
        s.harca("videos.insert")
    # Reddedilen istek hiç gönderilmedi — harcama sayılmamalı.
    assert s.harcanan == 0


def test_rezerve_yuklemenin_payini_korur(db: Path):
    """Trend toplayıcı, bir videoluk yükleme payına dokunamaz."""
    yukleme_payi = kota.video_basina_maliyet()
    s = kota.KaliciSayac(db, butce=yukleme_payi + 40, surec="trend")

    # Rezerve olmadan bakınca 1.691 birim boş görünüyor…
    assert s.yeter_mi("thumbnails.set") is True
    # …ama yükleme payı düşülünce yalnızca 40 birim serbest, 50'lik istek sığmıyor.
    assert s.yeter_mi("thumbnails.set", rezerve=yukleme_payi) is False
    # Ve asıl güvence tavsiyede değil, harcamanın kendisinde:
    with pytest.raises(kota.KotaAsimi, match="rezerve"):
        s.harca("videos.list", rezerve=yukleme_payi + 40)

    assert s.harcanan == 0


def test_rezerve_disindaki_pay_harcanabilir(db: Path):
    yukleme_payi = kota.video_basina_maliyet()
    s = kota.KaliciSayac(db, surec="trend")
    kalan = s.harca("videos.list", rezerve=yukleme_payi)
    assert kalan == kota.GUNLUK_BUTCE - 1


def test_bilinmeyen_islem_kilit_almadan_patlar(db: Path):
    s = kota.KaliciSayac(db)
    with pytest.raises(KeyError, match="bilinmeyen işlem"):
        s.harca("videos.teleport")
    assert s.harcanan == 0


def test_surec_deftere_yazilir(db: Path):
    kota.KaliciSayac(db, surec="trend").harca("videos.list")
    kota.KaliciSayac(db, surec="yukleme").harca("thumbnails.set")

    baglanti = kota.depo.baglan(db)
    try:
        satirlar = baglanti.execute(
            "SELECT surec, islem, birim FROM kota_harcama ORDER BY id"
        ).fetchall()
    finally:
        baglanti.close()

    assert [(s["surec"], s["islem"], s["birim"]) for s in satirlar] == [
        ("trend", "videos.list", 1),
        ("yukleme", "thumbnails.set", 50),
    ]


# --- Kota günü: sınır UTC'de değil, Pasifik'te ---------------------------


def test_kota_gunu_pasifik_takvimine_gore():
    """3 Ocak 05:00 UTC, Pasifik'te hâlâ 2 Ocak — o günün bütçesinden harcar."""
    an = datetime(2026, 1, 3, 5, 0, tzinfo=UTC)
    assert kota.kota_gunu(an) == "2026-01-02"


def test_kota_gunu_pasifik_gece_yarisindan_sonra():
    # 3 Ocak 08:00 UTC = 3 Ocak 00:00 Pasifik (kış, UTC-8) — gün dönmüş.
    an = datetime(2026, 1, 3, 8, 0, tzinfo=UTC)
    assert kota.kota_gunu(an) == "2026-01-03"


def test_kota_gunu_yaz_saatinde_kayar():
    """Yaz saatinde ofset UTC-7 — sabit -8 varsayan kod burada yanılırdı."""
    an = datetime(2026, 7, 3, 7, 30, tzinfo=UTC)
    assert kota.kota_gunu(an) == "2026-07-03"


def test_onceki_gunun_harcamasi_bugune_sayilmaz(db: Path):
    kota.KaliciSayac(db).harca("videos.insert")

    baglanti = kota.depo.baglan(db)
    try:
        baglanti.execute("UPDATE kota_harcama SET gun = '2020-01-01'")
    finally:
        baglanti.close()

    assert kota.KaliciSayac(db).harcanan == 0


# --- Eşzamanlılık: bu modülün var olma sebebi ---------------------------


def test_esZamanli_harcama_butceyi_asmaz(db: Path):
    """Yirmi eşzamanlı yazar, on beş videoluk bütçe.

    Kontrol ile yazma ayrı işlemlerde olsaydı birden fazla yazar aynı
    "kalan" değerini okuyup hepsi harcardı. `BEGIN IMMEDIATE` bunu
    serileştiriyor: tam 15 tanesi geçmeli, 5'i `KotaAsimi` almalı.
    """
    birim = kota.MALIYET["videos.insert"]
    butce = 15 * birim

    def harca() -> bool:
        try:
            kota.KaliciSayac(db, butce=butce, surec="test").harca("videos.insert")
        except kota.KotaAsimi:
            return False
        return True

    with ThreadPoolExecutor(max_workers=20) as havuz:
        sonuclar = list(havuz.map(lambda _: harca(), range(20)))

    assert sum(sonuclar) == 15, "bütçe kadar yazar geçmeliydi"
    assert kota.KaliciSayac(db, butce=butce).harcanan == butce
    assert kota.KaliciSayac(db, butce=butce).kalan == 0


def test_esZamanli_rezerve_korunur(db: Path):
    """Rezerv altına inecek hiçbir yazar geçmemeli — yarış altında da."""
    rezerve = kota.video_basina_maliyet()
    butce = rezerve + 10  # yalnızca 10 birim serbest

    def harca() -> bool:
        try:
            kota.KaliciSayac(db, butce=butce, surec="trend").harca("videos.list", rezerve=rezerve)
        except kota.KotaAsimi:
            return False
        return True

    with ThreadPoolExecutor(max_workers=25) as havuz:
        sonuclar = list(havuz.map(lambda _: harca(), range(25)))

    assert sum(sonuclar) == 10
    # Yükleme payına dokunulmamış olmalı.
    assert kota.KaliciSayac(db, butce=butce).kalan >= rezerve
