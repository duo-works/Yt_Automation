"""Wikipedia kaynağı — ağ çağrısı yamalanarak, canlı istek yok."""

from datetime import date
from pathlib import Path

import pytest

from yt_automation import depo
from yt_automation.trend import konu, konu_toplayici, wikipedia


def yanit(*makaleler: tuple[str, int]) -> dict:
    return {
        "items": [
            {
                "articles": [
                    {"article": a, "views": v, "rank": i}
                    for i, (a, v) in enumerate(makaleler, start=1)
                ]
            }
        ]
    }


# --- Gürültü elemesi ----------------------------------------------------


@pytest.mark.parametrize(
    ("baslik", "makale_mi"),
    [
        ("Osmanlı_İmparatorluğu", True),
        ("Main_Page", False),
        ("Ana_Sayfa", False),
        ("Özel:Ara", False),  # ad alanı — dile göre değişiyor, ":" ile yakalanıyor
        ("Special:Search", False),
        ("Kategori:Tarih", False),
        ("-", False),
    ],
)
def test_ad_alani_elenir(baslik, makale_mi):
    assert wikipedia._makale_mi(baslik) is makale_mi


def test_gunluk_liste_gurultuyu_atar(monkeypatch):
    monkeypatch.setattr(
        wikipedia, "_cek", lambda _: yanit(("Ana_Sayfa", 999), ("Osmanlı", 500), ("Özel:Ara", 400))
    )
    sonuc = wikipedia.gunluk_liste("tr", date(2026, 7, 28))
    assert [o.baslik for o in sonuc] == ["Osmanlı"]
    assert sonuc[0].okunma == 500
    assert sonuc[0].gun == "2026-07-28"


def test_adet_siniri_uygulanir(monkeypatch):
    monkeypatch.setattr(
        wikipedia, "_cek", lambda _: yanit(*[(f"M{i}", 100 - i) for i in range(50)])
    )
    assert len(wikipedia.gunluk_liste("tr", date(2026, 7, 28), adet=10)) == 10


def test_veri_yoksa_anlasilir_hata(monkeypatch):
    def patla(_):
        raise wikipedia.WikipediaHatasi("veri yok (HTTP 404)")

    monkeypatch.setattr(wikipedia, "_cek", patla)
    with pytest.raises(wikipedia.WikipediaHatasi, match="404"):
        wikipedia.gunluk_liste("tr", date(2026, 7, 28))


def test_makale_serisi_404te_bos_doner(monkeypatch):
    """Hiç okunmamış makale 404 veriyor — sıfır seri demek, arıza değil."""

    def patla(_):
        raise wikipedia.WikipediaHatasi("veri yok")

    monkeypatch.setattr(wikipedia, "_cek", patla)
    assert wikipedia.makale_serisi("tr", "Yok", date(2026, 7, 1), date(2026, 7, 5)) == []


def test_son_yayimlanan_gun_iki_gun_geride():
    assert wikipedia.son_yayimlanan_gun(date(2026, 7, 29)) == date(2026, 7, 27)


# --- Toplama ------------------------------------------------------------


@pytest.fixture
def sahte_kaynak(monkeypatch):
    """Wikipedia + Wikidata çağrılarını yamalar.

    `tipler` sözlüğü QID → tip listesi; kişi alanları (meslek, ölüm) boş
    varsayılıyor çünkü bu testler sınıflandırmayı değil akışı sınıyor.
    Kişi mantığının kendi testleri `test_konu.py`'de.
    """

    def kur(makaleler, kimlikler, tipler):
        varliklar = {
            q: {"tipler": t, "meslekler": [], "olum": None, "dogum": None}
            for q, t in tipler.items()
        }
        monkeypatch.setattr(wikipedia, "_cek", lambda _: yanit(*makaleler))
        monkeypatch.setattr(konu, "kimlikleri_getir", lambda dil, b: kimlikler)
        monkeypatch.setattr(konu, "varliklari_getir", lambda k: varliklar)

    return kur


def test_toplama_siniflandirip_yazar(yol: Path, sahte_kaynak):
    sahte_kaynak(
        [("Osmanlı_İmparatorluğu", 5000), ("Yeni_Parti", 9000), ("CRISPR", 300)],
        {"Osmanlı_İmparatorluğu": "Q12560", "Yeni_Parti": "Q140644267", "CRISPR": "Q412563"},
        {"Q12560": ["Q3024240"], "Q140644267": ["Q7278"], "Q412563": ["Q336"]},
    )
    sonuc = konu_toplayici.topla(yol, diller=("tr",), gun=date(2026, 7, 28))

    assert sonuc.aday == 3
    assert sonuc.siniflar == {"tarih": 1, "diger": 1, "bilim": 1}

    # En çok okunan "Yeni Parti" ama siyasi parti olduğu için aday değil.
    adaylar = konu_toplayici.adaylar(yol)
    assert [a["baslik"] for a in adaylar] == ["Osmanlı_İmparatorluğu", "CRISPR"]


def test_kimlik_yoksa_belirsiz(yol: Path, sahte_kaynak):
    """Wikidata kimliği olmayan makaleye "diger" demek yanlış — bilinmiyor."""
    sahte_kaynak([("Bilinmeyen", 100)], {}, {})
    sonuc = konu_toplayici.topla(yol, diller=("tr",), gun=date(2026, 7, 28))
    assert sonuc.siniflar == {"belirsiz": 1}


def test_llm_karari_wikidata_tarafindan_ezilmez(yol: Path, sahte_kaynak):
    """DW-30 bir kaydı sınıflandırdıysa sonraki toplama onu geri almamalı."""
    sahte_kaynak([("Semih_Terzi", 100)], {"Semih_Terzi": "Q25934710"}, {"Q25934710": ["Q5"]})
    konu_toplayici.topla(yol, diller=("tr",), gun=date(2026, 7, 28))

    baglanti = depo.baglan(yol)
    try:
        baglanti.execute(
            "UPDATE makale SET sinif = 'tarih', sinif_kaynagi = 'llm' WHERE baslik = 'Semih_Terzi'"
        )
    finally:
        baglanti.close()

    konu_toplayici.topla(yol, diller=("tr",), gun=date(2026, 7, 29))

    baglanti = depo.baglan(yol)
    try:
        satir = baglanti.execute("SELECT sinif, sinif_kaynagi FROM makale").fetchone()
    finally:
        baglanti.close()
    assert satir["sinif"] == "tarih" and satir["sinif_kaynagi"] == "llm"


def test_bir_dilin_hatasi_digerlerini_dusurmez(yol: Path, monkeypatch):
    def cek(url):
        if "/de." in url:
            raise wikipedia.WikipediaHatasi("veri yok")
        return yanit(("Osmanlı", 500))

    monkeypatch.setattr(wikipedia, "_cek", cek)
    monkeypatch.setattr(konu, "kimlikleri_getir", lambda d, b: {"Osmanlı": "Q12560"})
    monkeypatch.setattr(
        konu,
        "varliklari_getir",
        lambda k: {"Q12560": {"tipler": ["Q3024240"], "meslekler": [], "olum": None}},
    )

    sonuc = konu_toplayici.topla(yol, diller=("tr", "de", "en"), gun=date(2026, 7, 28))
    assert sonuc.diller == ["tr", "en"]
    assert len(sonuc.hatalar) == 1


def test_ayni_gun_tekrar_toplanabilir(yol: Path, sahte_kaynak):
    """Aynı gün iki kez çekilirse satır çoğalmamalı, okunma tazelenmeli."""
    sahte_kaynak([("Osmanlı", 500)], {"Osmanlı": "Q12560"}, {"Q12560": ["Q3024240"]})
    konu_toplayici.topla(yol, diller=("tr",), gun=date(2026, 7, 28))
    sahte_kaynak([("Osmanlı", 900)], {"Osmanlı": "Q12560"}, {"Q12560": ["Q3024240"]})
    konu_toplayici.topla(yol, diller=("tr",), gun=date(2026, 7, 28))

    baglanti = depo.baglan(yol)
    try:
        satirlar = baglanti.execute("SELECT okunma FROM okunma").fetchall()
    finally:
        baglanti.close()
    assert [s["okunma"] for s in satirlar] == [900]


# --- Şema göçü ----------------------------------------------------------


def test_eski_veritabani_yeni_tablolari_alir(yol: Path):
    """`user_version` mekanizması gerçekten göç yapıyor mu?

    DW-24'te eklenmişti ama ilk kez burada sınanıyor: sürüm 1'de kalmış bir
    veritabanı açıldığında sürüm 2'nin tabloları eklenmeli.
    """
    baglanti = depo.baglan(yol)
    try:
        baglanti.execute("DROP TABLE makale")
        baglanti.execute("DROP TABLE okunma")
        baglanti.execute("PRAGMA user_version = 1")
    finally:
        baglanti.close()

    baglanti = depo.baglan(yol)
    try:
        adlar = {
            s["name"] for s in baglanti.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        surum = baglanti.execute("PRAGMA user_version").fetchone()[0]
    finally:
        baglanti.close()

    assert {"makale", "okunma"} <= adlar
    assert surum == depo.SEMA_SURUMU
