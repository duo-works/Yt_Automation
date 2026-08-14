"""Arşiv-önce trend kaynağı — üretilebilirlik başlangıç koşulu.

Bu dosyada canlı çağrı yok: Commons ve Wikidata ücretsiz ama CI'yı onların
o günkü keyfine bağlamak istemiyoruz. Ağ katmanı sahte yanıtla sürülüyor;
kilitlenen şey **eşik, Wikidata köprüsü ve yumuşak düşme.**

⚠️ NEDEN VAR — ölçüldü (2026-08-14). Üretim iki kez durdu ve ikisinde de
sebep hattın kendisi değil, beslenmemesiydi: `Yeni` kuyruğundaki 40 adayın
**40'ı** üretilemezdi (Rogelio Mortimer menü 0, Henry Macandrew 3 — hepsi
kişi). Mevcut kaynaklar talebi ölçüp arzı VARSAYIYOR; bu kaynak yönü
tersine çeviriyor.
"""

import json

import pytest

from yt_automation.trend import arsiv


@pytest.fixture(autouse=True)
def _temiz():
    arsiv.onbellegi_temizle()
    yield
    arsiv.onbellegi_temizle()


def _sahte_iste(monkeypatch, yanitlar: dict):
    """`_iste` ve `_wikidata_iste` yerine sabit yanıtlar."""
    cagrilar: list[dict] = []

    def sahte(parametreler):
        cagrilar.append(parametreler)
        for anahtar, deger in yanitlar.items():
            if anahtar in str(parametreler):
                return deger
        return {}

    monkeypatch.setattr(arsiv, "_iste", sahte)
    monkeypatch.setattr(arsiv, "_wikidata_iste", sahte)
    return cagrilar


def _uyeler(*basliklar: str) -> dict:
    return {"query": {"categorymembers": [{"title": b} for b in basliklar]}}


# --- Eşik -----------------------------------------------------------------


def test_esik_dosya_sayisina_gore_eliyor(monkeypatch):
    def sahte_alt(_tohum, sinir=None):
        return ["Category:Zengin", "Category:Fakir"]

    monkeypatch.setattr(arsiv, "alt_kategoriler", sahte_alt)
    monkeypatch.setattr(
        arsiv, "dosya_sayisi", lambda k, tavan=200: 80 if "Zengin" in k else 3
    )
    monkeypatch.setattr(arsiv, "tohumlar", lambda _dil: ("Category:Tohum",))

    adaylar = arsiv.adaylari_bul("en")

    assert [a.baslik for a in adaylar] == ["Zengin"]
    assert adaylar[0].dosya == 80


def test_esik_URETIM_esigiyle_bagli():
    """⚠️ Bu sayı üretim tarafındaki eşikle AYNI OLAMAZ ama ondan KOPUK da olamaz.

    `huni_besle.ASGARI_MENU = 6 * KARE_YUVASI = 12` **kullanılabilir**
    görsel istiyor (lisans/kadraj elemesinden sonra). Ham kategori sayısı
    her zaman daha yüksek olmalı, yoksa buradan geçen aday orada elenir ve
    kuyruk yine boşalır — bugün yaşanan kusurun bir adım öteye taşınmış hali.
    """
    assert arsiv.ASGARI_DOSYA > 12


def test_ara_kategoriler_dogal_olarak_eleniyor(monkeypatch):
    """"by city"/"by country" kategorilerinde dosya yok; ölçüldü (canlı).

    Ayrı bir ad filtresi yazmaya gerek yok — dosya sayısı sıfır olduğu için
    eşik onları zaten eliyor. Kural sayıya bağlı kalıyor, adlandırmaya değil.
    """
    monkeypatch.setattr(arsiv, "tohumlar", lambda _dil: ("Category:Tohum",))
    monkeypatch.setattr(
        arsiv, "alt_kategoriler", lambda _t, sinir=None: ["Category:Roman architecture by city"]
    )
    monkeypatch.setattr(arsiv, "dosya_sayisi", lambda k, tavan=200: 0)

    assert arsiv.adaylari_bul("en") == []


# --- Wikidata köprüsü -----------------------------------------------------


def test_kategori_P301_ile_MAKALEYE_cevriliyor(monkeypatch):
    """⚠️ Kaynağın en pahalı kusuru buydu, ölçüldü (2026-08-14).

    Commons kategorileri ÇOĞUL, Wikipedia makaleleri TEKİL:

        "Mastabas"                -> arama None  (makale "Mastaba")
        "Ancient Roman aqueducts" -> arama None  (makale "Roman aqueduct")

    11 adayın 6'sı bu yüzden kayboluyordu. Aramayı gevşetmek çözüm değil:
    o zaman çağrışım gelir (`gtrends.makale_ara` docstring'i).
    """
    _sahte_iste(
        monkeypatch,
        {
            "pageprops": {"query": {"pages": {"1": {"pageprops": {"wikibase_item": "Q100"}}}}},
            "claims": {
                "entities": {
                    "Q100": {
                        "claims": {
                            "P301": [
                                {"mainsnak": {"datavalue": {"value": {"id": "Q200"}}}}
                            ]
                        }
                    }
                }
            },
            "sitelinks": {"entities": {"Q200": {"sitelinks": {"enwiki": {"title": "Mastaba"}}}}},
        },
    )
    arsiv._TERIM_KATEGORI["Mastabas"] = "Category:Mastabas"

    assert arsiv.makale_bul("en", "Mastabas") == "Mastaba"


def test_KATEGORI_SAYFASI_makale_sayilmiyor(monkeypatch):
    """⚠️ P301 olmadan köprü Wikipedia'nın KATEGORİ sayfasını döndürüyordu.

    Ölçüldü: `Category:Mastabas` → öğe → enwiki → `Category:Mastabas`.
    Talep ölçümü makale okunmasına dayandığı için bu boruya çöp doldururdu.
    """
    monkeypatch.setattr(arsiv, "ana_konu", lambda _oge: None)
    monkeypatch.setattr(arsiv, "_sitelink", lambda _oge, _dil: "Category:Mastabas")

    assert arsiv.makale_baglantisi("Q100", "en") is None


def test_kopru_kurulamazsa_ARAMAYA_dusuyor(monkeypatch):
    """Kayıp, sessiz kayıptan iyidir."""
    monkeypatch.setattr(
        arsiv, "wikidata_ogesi", lambda _k: (_ for _ in ()).throw(arsiv.ArsivHatasi("yok"))
    )
    monkeypatch.setattr(arsiv.gtrends, "makale_ara", lambda _d, terim: f"aranan-{terim}")
    arsiv._TERIM_KATEGORI["X"] = "Category:X"

    assert arsiv.makale_bul("en", "X") == "aranan-X"


def test_kategorisiz_terim_aramaya_dusuyor(monkeypatch):
    monkeypatch.setattr(arsiv.gtrends, "makale_ara", lambda _d, terim: "bulundu")

    assert arsiv.makale_bul("en", "eslesmeyen") == "bulundu"


# --- Boru hattı sözleşmesi ------------------------------------------------


def test_terimler_gtrends_bicimindeydi(monkeypatch):
    monkeypatch.setattr(
        arsiv,
        "adaylari_bul",
        lambda _dil, asgari=None: [arsiv.KategoriAdayi("Pompeii", "Category:Pompeii", 90)],
    )

    terimler = arsiv.terimleri_cek("en")

    assert terimler[0].terim == "Pompeii"
    assert terimler[0].geo == "en"
    assert "90" in terimler[0].trafik, "dosya sayısı görünür sinyal olmalı"
    # Köprünün kategoriyi bulabilmesi için eşleme yazılmalı.
    assert arsiv._TERIM_KATEGORI["Pompeii"] == "Category:Pompeii"


def test_ayni_dil_iki_kez_taranmiyor(monkeypatch):
    """Commons dilden bağımsız; her coğrafya için yeniden taramak israf."""
    sayac = []
    monkeypatch.setattr(
        arsiv, "adaylari_bul", lambda _dil, asgari=None: sayac.append(1) or []
    )

    arsiv.terimleri_cek("en")
    arsiv.terimleri_cek("en")

    assert len(sayac) == 1


def test_tohum_hatasi_digerlerini_dusurmuyor(monkeypatch):
    """Bir tohumun hatası diğerlerini düşürmez (DW-28'den beri)."""
    monkeypatch.setattr(arsiv, "tohumlar", lambda _dil: ("Category:Patlak", "Category:Saglam"))

    def sahte_alt(tohum, sinir=None):
        if "Patlak" in tohum:
            raise arsiv.ArsivHatasi("uç düştü")
        return ["Category:Iyi"]

    monkeypatch.setattr(arsiv, "alt_kategoriler", sahte_alt)
    monkeypatch.setattr(arsiv, "dosya_sayisi", lambda _k, tavan=200: 99)

    assert [a.baslik for a in arsiv.adaylari_bul("en")] == ["Iyi"]


def test_isle_gtrends_borusunu_KULLANIYOR(monkeypatch, tmp_path):
    """⚠️ ADR-0010: yeni skorlama/kuyruk yazılmıyor.

    İki ayrı skorlama, eşiklerin zamanla birbirinden sapması demektir —
    bugün tam da o sınıf kusur yaşandı (kuyruğun kabul ettiği konuyu
    besleyici reddediyordu).
    """
    gecen = {}

    def sahte_isle(yol, **kwargs):
        gecen.update(kwargs)
        return arsiv.gtrends.IslemeSonucu()

    monkeypatch.setattr(arsiv.gtrends, "isle", sahte_isle)

    arsiv.isle(tmp_path / "depo.db", pazarlar=("en",))

    assert gecen["terim_getir"] is arsiv.terimleri_cek
    assert gecen["makale_bul"] is arsiv.makale_bul
    # Commons ülkeye göre değişmiyor: coğrafya listesi tek elemanlı.
    assert gecen["geo_kodlari"] == {"en": ("en",)}


# --- Tohumlar -------------------------------------------------------------


def test_tohumlar_konuya_capali():
    """⚠️ DW-111'de ölçüldü: cümle kalıbı tohumları 0/24 tarih konusu verdi,
    konu çapalı tohumlar 6/24. Buradaki karşılığı üst kategori seçimi."""
    tohumlar = arsiv.VARSAYILAN_TOHUMLAR["en"]

    assert len(tohumlar) >= 5
    assert all(t.startswith("Category:") for t in tohumlar)


def test_tohum_dosyasi_varsayilanin_YERINE_geciyor(monkeypatch, tmp_path):
    """`oneri.tohumlar` ile aynı sözleşme: genişletmiyor, değiştiriyor."""
    dosya = tmp_path / "tohum.txt"
    dosya.write_text("Category:Ozel\n// yorum\n\n", encoding="utf-8")
    monkeypatch.setenv(arsiv.TOHUM_DEGISKENI, str(dosya))

    assert arsiv.tohumlar("en") == ("Category:Ozel",)


def test_gecersiz_json_ArsivHatasi(monkeypatch):
    class _Yanit:
        def read(self):
            return b"<html>bozuk"

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(arsiv.urllib.request, "urlopen", lambda *_a, **_k: _Yanit())

    with pytest.raises(arsiv.ArsivHatasi):
        arsiv._iste({"action": "query"})


def test_bos_yanit_patlatmiyor(monkeypatch):
    monkeypatch.setattr(arsiv, "_iste", lambda _p: {})

    assert arsiv.alt_kategoriler("Category:X") == []
    assert arsiv.dosya_sayisi("Category:X") == 0
    assert arsiv.wikidata_ogesi("Category:X") is None


def test_dosya_sayisi_uyeleri_sayiyor(monkeypatch):
    monkeypatch.setattr(arsiv, "_iste", lambda _p: _uyeler("File:a.jpg", "File:b.jpg"))

    assert arsiv.dosya_sayisi("Category:X") == 2


def test_baslik_cevrimi():
    assert arsiv._basliga_cevir("Category:Pompeii") == "Pompeii"
    assert arsiv._basliga_cevir("Pompeii") == "Pompeii"


def test_govde_utf8_disi_bozuk_baytta_dusmuyor(monkeypatch):
    """Bozuk tek bayt yüzünden pazarın tamamını kaybetmek istemiyoruz."""

    class _Yanit:
        def read(self):
            return json.dumps({"query": {"categorymembers": []}}).encode("utf-8") + b"\xff"

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(arsiv.urllib.request, "urlopen", lambda *_a, **_k: _Yanit())

    with pytest.raises(arsiv.ArsivHatasi):
        arsiv._iste({"action": "query"})
