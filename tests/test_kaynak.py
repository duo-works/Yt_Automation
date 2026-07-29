"""Kaynak dosyası — ağ çağrıları yamalanarak.

En kritik test lisans elemesi: lisansı belirsiz bir görselin çıktıya
sızması telif riski demek, ve PRD bunu işaretliyor.
"""

from datetime import date
from pathlib import Path

import pytest

from yt_automation import depo
from yt_automation.trend import kaynak, konu, konu_toplayici, wikipedia


def sayfalar(*sayfa: dict) -> dict:
    return {"query": {"pages": {str(i): s for i, s in enumerate(sayfa)}}}


@pytest.fixture
def aday(yol: Path, monkeypatch):
    """Depoda tarih sınıfında, qid'si olan bir aday bırakır."""

    def kur(baslik: str = "Great_Zimbabwe", qid: str = "Q209217", sinif: str = "tarih"):
        monkeypatch.setattr(
            wikipedia,
            "_cek",
            lambda _: {"items": [{"articles": [{"article": baslik, "views": 5000, "rank": 1}]}]},
        )
        monkeypatch.setattr(konu, "kimlikleri_getir", lambda d, b: {baslik: qid})
        monkeypatch.setattr(
            konu,
            "varliklari_getir",
            lambda k: {qid: {"tipler": ["Q3024240"], "meslekler": [], "olum": None}},
        )
        monkeypatch.setattr(wikipedia, "ozetleri_getir", lambda d, b: {})
        konu_toplayici.topla(yol, diller=("en",), gun=date(2026, 7, 28))
        if sinif != "tarih":
            baglanti = depo.baglan(yol)
            try:
                baglanti.execute("UPDATE makale SET sinif = ?", (sinif,))
            finally:
                baglanti.close()
        return {"dil": "en", "baslik": baslik, "qid": qid}

    return kur


# --- Referanslar --------------------------------------------------------


def test_zayif_alanlar_elenir(monkeypatch):
    """Arşiv linki kaynağın kendisi değil, kopyası."""
    monkeypatch.setattr(
        wikipedia,
        "_cek",
        lambda _: sayfalar(
            {
                "extlinks": [
                    {"*": "https://web.archive.org/web/123/http://x.com"},
                    {"*": "https://en.wikipedia.org/wiki/Foo"},
                    {"*": "https://www.britishmuseum.org/collection/object/1"},
                    {"*": "https://doi.org/10.1000/x"},
                ]
            }
        ),
    )
    assert kaynak.referanslari_getir("en", "X") == [
        "https://www.britishmuseum.org/collection/object/1"
    ]


def test_alt_alan_adlari_da_elenir(monkeypatch):
    """`wikipedia.org` listede ama referanslar `en.wikipedia.org` olarak geliyor.

    Tam eşleşme yeterli sanmıştım; ilk koşumda `en.wikipedia.org` elemeden
    geçti. Wikipedia'yı kaynak göstermek, kaynak göstermemekle aynı şey.
    """
    monkeypatch.setattr(
        wikipedia,
        "_cek",
        lambda _: sayfalar(
            {
                "extlinks": [
                    {"*": "https://tr.wikipedia.org/wiki/X"},
                    {"*": "https://upload.wikimedia.org/a.jpg"},
                    {"*": "https://uni.edu/paper"},
                ]
            }
        ),
    )
    assert kaynak.referanslari_getir("en", "X") == ["https://uni.edu/paper"]


def test_alan_basina_tek_referans(monkeypatch):
    """Aynı sitenin on sayfası tek kaynak."""
    monkeypatch.setattr(
        wikipedia,
        "_cek",
        lambda _: sayfalar(
            {
                "extlinks": [
                    {"*": "https://museum.org/a"},
                    {"*": "https://museum.org/b"},
                    {"*": "https://uni.edu/c"},
                ]
            }
        ),
    )
    assert kaynak.referanslari_getir("en", "X") == ["https://museum.org/a", "https://uni.edu/c"]


def test_referans_hatasi_bos_doner(monkeypatch):
    def patla(_):
        raise wikipedia.WikipediaHatasi("404")

    monkeypatch.setattr(wikipedia, "_cek", patla)
    assert kaynak.referanslari_getir("en", "X") == []


# --- Olgular ------------------------------------------------------------


@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [
        ({"time": "+1450-01-01T00:00:00Z"}, "1450"),
        ({"time": "-0500-01-01T00:00:00Z"}, "MÖ 500"),  # işaret kaybolmamalı
        ({"time": "+0079-08-24T00:00:00Z"}, "79"),  # baştaki sıfırlar kırpılır
        ({"id": "Q954"}, "Q954"),
        ({"latitude": -20.27, "longitude": 30.933}, "-20.2700, 30.9330"),
        ({"amount": "+1200"}, "1200"),
        ("düz metin", "düz metin"),
        (None, None),
    ],
)
def test_olgu_degeri_cevrimi(ham, beklenen):
    assert kaynak._olgu_degeri(ham) == beklenen


def test_olgular_etiketle_gelir(monkeypatch):
    monkeypatch.setattr(
        konu,
        "_cek",
        lambda _: {
            "entities": {
                "Q1": {
                    "claims": {
                        "P571": [
                            {"mainsnak": {"datavalue": {"value": {"time": "+1100-01-01T0:0:0Z"}}}}
                        ],
                        "P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q954"}}}}],
                        "P9999": [{"mainsnak": {"datavalue": {"value": "ilgisiz"}}}],
                    }
                }
            }
        },
    )
    olgular = kaynak.olgulari_getir("Q1")
    assert ("ortaya çıkışı", "1100") in olgular
    assert ("ülkesi", "Q954") in olgular
    assert not any(d == "ilgisiz" for _, d in olgular), "listede olmayan özellik alınmamalı"


def test_kimlikler_etikete_cevrilir(monkeypatch):
    """İlk canlı koşumda `ölüm nedeni: Q114953` çıktı — üretim tarafına gönderilemez."""

    def cek(url):
        if "props=labels" in url:
            return {"entities": {"Q114953": {"labels": {"tr": {"value": "yılan sokması"}}}}}
        return {
            "entities": {
                "Q1": {
                    "claims": {"P509": [{"mainsnak": {"datavalue": {"value": {"id": "Q114953"}}}}]}
                }
            }
        }

    monkeypatch.setattr(konu, "_cek", cek)
    assert kaynak.olgulari_getir("Q1") == [("ölüm nedeni", "yılan sokması")]


def test_turkce_etiket_yoksa_ingilizceye_dusulur(monkeypatch):
    def cek(url):
        if "props=labels" in url:
            return {"entities": {"Q1": {"labels": {"en": {"value": "asp"}}}}}
        return {
            "entities": {
                "Q1": {"claims": {"P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q1"}}}}]}}
            }
        }

    monkeypatch.setattr(konu, "_cek", cek)
    assert kaynak.olgulari_getir("Q1") == [("ülkesi", "asp")]


def test_etiket_cozulemezse_kimlik_kalir(monkeypatch):
    """Çözüm başarısızsa olguyu düşürmek yerine ham kimlikle tutmak yeğdir."""

    def cek(url):
        if "props=labels" in url:
            raise konu.WikidataHatasi("503")
        return {
            "entities": {
                "Q1": {"claims": {"P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q954"}}}}]}}
            }
        }

    monkeypatch.setattr(konu, "_cek", cek)
    assert kaynak.olgulari_getir("Q1") == [("ülkesi", "Q954")]


def test_ozellik_basina_tek_deger(monkeypatch):
    monkeypatch.setattr(
        konu,
        "_cek",
        lambda _: {
            "entities": {
                "Q1": {
                    "claims": {
                        "P17": [
                            {"mainsnak": {"datavalue": {"value": {"id": "Q1"}}}},
                            {"mainsnak": {"datavalue": {"value": {"id": "Q2"}}}},
                        ]
                    }
                }
            }
        },
    )
    assert kaynak.olgulari_getir("Q1") == [("ülkesi", "Q1")]


# --- Görseller: lisans elemesi ------------------------------------------


def gorsel_yaniti(dosyalar, ustveriler):
    def cek(url):
        if "prop=images" in url:
            return sayfalar({"images": [{"title": d} for d in dosyalar]})
        return sayfalar(*[{"title": d, "imageinfo": [{"extmetadata": u}]} for d, u in ustveriler])

    return cek


def test_lisanssiz_gorsel_elenir(monkeypatch):
    """En kritik test: telif riski PRD'de işaretli, görseller elle kontrol edilmiyor."""
    monkeypatch.setattr(
        wikipedia,
        "_cek",
        gorsel_yaniti(
            ["File:a.jpg", "File:b.jpg"],
            [
                ("File:a.jpg", {}),  # lisans alanı hiç yok
                ("File:b.jpg", {"LicenseShortName": {"value": "CC BY-SA 4.0"}}),
            ],
        ),
    )
    sonuc = kaynak.gorselleri_getir("en", "X")
    assert [g["dosya"] for g in sonuc] == ["File:b.jpg"]


@pytest.mark.parametrize("lisans", ["", "?", "unknown", "bilinmiyor", "UNKNOWN"])
def test_belirsiz_lisans_degerleri_elenir(monkeypatch, lisans):
    monkeypatch.setattr(
        wikipedia,
        "_cek",
        gorsel_yaniti(["File:a.jpg"], [("File:a.jpg", {"LicenseShortName": {"value": lisans}})]),
    )
    assert kaynak.gorselleri_getir("en", "X") == []


def test_atif_html_den_arindirilir(monkeypatch):
    monkeypatch.setattr(
        wikipedia,
        "_cek",
        gorsel_yaniti(
            ["File:a.jpg"],
            [
                (
                    "File:a.jpg",
                    {
                        "LicenseShortName": {"value": "CC BY 2.0"},
                        "Artist": {"value": '<a href="https://x.com/u">Ada  Lovelace</a>'},
                    },
                )
            ],
        ),
    )
    assert kaynak.gorselleri_getir("en", "X")[0]["atif"] == "Ada Lovelace"


def test_gorsel_olmayan_dosyalar_atlanir(monkeypatch):
    monkeypatch.setattr(
        wikipedia,
        "_cek",
        gorsel_yaniti(
            ["File:ses.ogg", "File:a.jpg"],
            [("File:a.jpg", {"LicenseShortName": {"value": "CC0"}})],
        ),
    )
    assert [g["dosya"] for g in kaynak.gorselleri_getir("en", "X")] == ["File:a.jpg"]


@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [
        ('<a href="x">Ad</a>', "Ad"),
        ("Ad   Soyad", "Ad Soyad"),
        ("", ""),
        (None, ""),
    ],
)
def test_metne_cevir(ham, beklenen):
    assert kaynak.metne_cevir(ham) == beklenen


# --- Depo ---------------------------------------------------------------


def test_cek_uc_turu_de_yazar(yol: Path, aday, monkeypatch):
    a = aday()
    monkeypatch.setattr(kaynak, "referanslari_getir", lambda d, b, adet=12: ["https://m.org/1"])
    monkeypatch.setattr(kaynak, "olgulari_getir", lambda q: [("ortaya çıkışı", "1100")])
    monkeypatch.setattr(
        kaynak,
        "gorselleri_getir",
        lambda d, b, adet=4: [{"dosya": "File:a.jpg", "lisans": "CC0", "atif": "X"}],
    )
    sonuc = kaynak.cek(yol, a["dil"], a["baslik"], a["qid"])

    assert (sonuc.referans, sonuc.olgu, sonuc.gorsel) == (1, 1, 1)
    dosya = kaynak.dosyayi_oku(yol, a["qid"])
    assert dosya["referans"][0]["deger"] == "https://m.org/1"
    assert dosya["olgu"][0]["etiket"] == "ortaya çıkışı"
    assert dosya["gorsel"][0]["lisans"] == "CC0"


def test_yeterlilik_esigi():
    az = kaynak.KaynakSonucu(qid="Q1", referans=2, olgu=9)
    assert not az.yeterli and "YETERSİZ" in az.ozet()
    tam = kaynak.KaynakSonucu(qid="Q1", referans=3, olgu=5)
    assert tam.yeterli and "YETERSİZ" not in tam.ozet()


def test_cekilen_aday_tekrar_gelmez(yol: Path, aday, monkeypatch):
    """Önbellek: kaynaklar qid bazlı, bir kez çekilir."""
    a = aday()
    assert [k["qid"] for k in kaynak.cekilmemis_adaylar(yol)] == [a["qid"]]

    monkeypatch.setattr(kaynak, "referanslari_getir", lambda d, b, adet=12: ["https://m.org/1"])
    monkeypatch.setattr(kaynak, "olgulari_getir", lambda q: [])
    monkeypatch.setattr(kaynak, "gorselleri_getir", lambda d, b, adet=4: [])
    kaynak.cek(yol, a["dil"], a["baslik"], a["qid"])

    assert kaynak.cekilmemis_adaylar(yol) == []


def test_diger_sinifi_aday_degil(yol: Path, aday):
    """544 `diger` için kaynak çekmek anlamsız."""
    aday(sinif="diger")
    assert kaynak.cekilmemis_adaylar(yol) == []


def test_ayni_kaynak_iki_kez_yazilmaz(yol: Path, aday, monkeypatch):
    a = aday()
    monkeypatch.setattr(kaynak, "referanslari_getir", lambda d, b, adet=12: ["https://m.org/1"])
    monkeypatch.setattr(kaynak, "olgulari_getir", lambda q: [])
    monkeypatch.setattr(kaynak, "gorselleri_getir", lambda d, b, adet=4: [])
    kaynak.cek(yol, a["dil"], a["baslik"], a["qid"])
    kaynak.cek(yol, a["dil"], a["baslik"], a["qid"])

    assert len(kaynak.dosyayi_oku(yol, a["qid"])["referans"]) == 1


def test_json_disa_aktarim(yol: Path, aday, monkeypatch):
    a = aday()
    monkeypatch.setattr(kaynak, "referanslari_getir", lambda d, b, adet=12: [])
    monkeypatch.setattr(kaynak, "olgulari_getir", lambda q: [("ülkesi", "Q954")])
    monkeypatch.setattr(kaynak, "gorselleri_getir", lambda d, b, adet=4: [])
    kaynak.cek(yol, a["dil"], a["baslik"], a["qid"])

    assert '"ülkesi"' in kaynak.json_disa_aktar(yol, a["qid"])


# --- Şema göçü ----------------------------------------------------------


def test_surum_2_veritabani_kaynak_tablosunu_alir(yol: Path):
    baglanti = depo.baglan(yol)
    try:
        baglanti.execute("DROP TABLE kaynak")
        baglanti.execute("PRAGMA user_version = 2")
    finally:
        baglanti.close()

    baglanti = depo.baglan(yol)
    try:
        adlar = {
            s["name"] for s in baglanti.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        baglanti.close()
    assert "kaynak" in adlar
