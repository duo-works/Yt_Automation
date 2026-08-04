"""LLM sınıflandırma katmanı — sahte istemciyle, canlı çağrı yok."""

import json
from datetime import date
from pathlib import Path

import pytest

from yt_automation import depo
from yt_automation.trend import konu, konu_toplayici, siniflandirici, wikipedia


class SahteYanit:
    def __init__(self, sonuclar, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        govde = json.dumps({"sonuclar": sonuclar}, ensure_ascii=False)
        self.content = [type("Blok", (), {"type": "text", "text": govde})()]


class SahteLLM:
    """`istemci.messages.create(...)` zincirini taklit eder."""

    def __init__(self, yanitlar, hata=None):
        self.yanitlar = list(yanitlar)
        self.hata = hata
        self.istemler: list[str] = []
        self.messages = self

    def create(self, **p):
        self.istemler.append(p["messages"][0]["content"])
        if self.hata:
            raise self.hata
        return self.yanitlar.pop(0) if self.yanitlar else SahteYanit([])


@pytest.fixture
def belirsiz_kuyruk(yol: Path, monkeypatch):
    """Belirsiz sınıfta makaleler bırakan bir toplama yapar."""

    def kur(makaleler: list[tuple[str, int]], dil: str = "en"):
        monkeypatch.setattr(
            wikipedia,
            "_cek",
            lambda _: {
                "items": [
                    {
                        "articles": [
                            {"article": a, "views": v, "rank": i}
                            for i, (a, v) in enumerate(makaleler, start=1)
                        ]
                    }
                ]
            },
        )
        monkeypatch.setattr(
            konu,
            "kimlikleri_getir",
            lambda d, b: {a: f"Q{i}" for i, (a, _) in enumerate(makaleler)},
        )
        # Ölmüş, mesleği tanınmayan kişi → Wikidata `belirsiz` diyor.
        # Bu tam olarak Frida Kahlo vakası: bu katmanın var olma sebebi.
        monkeypatch.setattr(
            konu,
            "varliklari_getir",
            lambda k: {q: {"tipler": ["Q5"], "meslekler": ["Q1028181"], "olum": 1954} for q in k},
        )
        monkeypatch.setattr(wikipedia, "ozetleri_getir", lambda d, b: {})
        konu_toplayici.topla(yol, diller=(dil,), gun=date(2026, 7, 28))

    return kur


def sinif_oku(yol: Path, baslik: str) -> tuple[str, str]:
    baglanti = depo.baglan(yol)
    try:
        s = baglanti.execute(
            "SELECT sinif, sinif_kaynagi FROM makale WHERE baslik = ?", (baslik,)
        ).fetchone()
    finally:
        baglanti.close()
    return (s["sinif"], s["sinif_kaynagi"])


# --- Kuyruk -------------------------------------------------------------


def test_bekleyenler_okunmaya_gore_siralanir(yol: Path, belirsiz_kuyruk):
    """Kuyruk bütçeden büyükse en çok okunanı sormak rastgele birini sormaktan değerli."""
    belirsiz_kuyruk([("Az", 100), ("Cok", 9000), ("Orta", 3000)])
    assert [k["baslik"] for k in siniflandirici.bekleyenler(yol)] == ["Cok", "Orta", "Az"]


def test_bekleyenler_yalnizca_belirsizleri_alir(yol: Path, belirsiz_kuyruk):
    belirsiz_kuyruk([("A", 100), ("B", 200)])
    baglanti = depo.baglan(yol)
    try:
        baglanti.execute("UPDATE makale SET sinif = 'tarih' WHERE baslik = 'A'")
    finally:
        baglanti.close()
    assert [k["baslik"] for k in siniflandirici.bekleyenler(yol)] == ["B"]


# --- Sınıflandırma ------------------------------------------------------


def test_sonuc_kalici_yazilir(yol: Path, belirsiz_kuyruk):
    belirsiz_kuyruk([("Homer", 5000), ("Paul_Newman", 3000)])
    llm = SahteLLM(
        [
            SahteYanit(
                [
                    {"baslik": "Homer", "sinif": "tarih", "gerekce": "antik Yunan şairi"},
                    {"baslik": "Paul_Newman", "sinif": "diger", "gerekce": "oyuncu"},
                ]
            )
        ]
    )
    sonuc = siniflandirici.siniflandir(llm, yol)

    assert sonuc.sorulan == 2
    assert sonuc.siniflar == {"tarih": 1, "diger": 1}
    assert sinif_oku(yol, "Homer") == ("tarih", "llm")
    assert sinif_oku(yol, "Paul_Newman") == ("diger", "llm")


def test_siniflandirilan_makale_kuyruktan_cikar(yol: Path, belirsiz_kuyruk):
    """Önbelleğin özü: aynı makale ikinci kez LLM'e gitmemeli."""
    belirsiz_kuyruk([("Homer", 5000)])
    llm = SahteLLM([SahteYanit([{"baslik": "Homer", "sinif": "tarih", "gerekce": "şair"}])])
    siniflandirici.siniflandir(llm, yol)

    assert siniflandirici.bekleyenler(yol) == []
    ikinci = SahteLLM([])
    assert siniflandirici.siniflandir(ikinci, yol).cagri_sayisi == 0
    assert ikinci.istemler == [], "ikinci kez sorulmamalıydı"


def test_llm_karari_sonraki_toplamada_korunur(yol: Path, belirsiz_kuyruk):
    """DW-34'ün koruması bu katmanla birlikte çalışmalı."""
    belirsiz_kuyruk([("Homer", 5000)])
    siniflandirici.siniflandir(
        SahteLLM([SahteYanit([{"baslik": "Homer", "sinif": "tarih", "gerekce": "şair"}])]), yol
    )
    belirsiz_kuyruk([("Homer", 6000)])  # ertesi gün yeniden toplandı
    assert sinif_oku(yol, "Homer") == ("tarih", "llm")


def test_gruplar_halinde_sorulur(yol: Path, belirsiz_kuyruk, monkeypatch):
    monkeypatch.setattr(siniflandirici, "GRUP_BOYUTU", 2)
    belirsiz_kuyruk([(f"M{i}", 100 - i) for i in range(5)])
    llm = SahteLLM([SahteYanit([]) for _ in range(3)])
    sonuc = siniflandirici.siniflandir(llm, yol)
    assert sonuc.cagri_sayisi == 3, "5 makale / 2'lik grup = 3 çağrı"


def test_bir_grubun_hatasi_digerlerini_dusurmez(yol: Path, belirsiz_kuyruk, monkeypatch):
    monkeypatch.setattr(siniflandirici, "GRUP_BOYUTU", 1)
    belirsiz_kuyruk([("A", 200), ("B", 100)])

    cagri = {"n": 0}

    class Kararsiz(SahteLLM):
        def create(self, **p):
            cagri["n"] += 1
            if cagri["n"] == 1:
                raise RuntimeError("529 overloaded")
            return SahteYanit([{"baslik": "B", "sinif": "bilim", "gerekce": "x"}])

    sonuc = siniflandirici.siniflandir(Kararsiz([]), yol)
    assert len(sonuc.hatalar) == 1
    assert sonuc.sorulan == 1, "ikinci grup yine de işlenmeli"


# --- Bozuk yanıtlar -----------------------------------------------------


def test_gruba_ait_olmayan_baslik_yazilmaz(yol: Path, belirsiz_kuyruk):
    """Model başlığı değiştirirse yanlış satırı güncellemektense atlamak yeğdir."""
    belirsiz_kuyruk([("Homer", 5000)])
    llm = SahteLLM([SahteYanit([{"baslik": "Homer Simpson", "sinif": "diger", "gerekce": "x"}])])
    sonuc = siniflandirici.siniflandir(llm, yol)

    assert sonuc.sorulan == 0
    assert len(sonuc.hatalar) == 1
    assert sinif_oku(yol, "Homer") == ("belirsiz", "wikidata"), "dokunulmamalıydı"


def test_tanimsiz_sinif_reddedilir(yol: Path, belirsiz_kuyruk):
    belirsiz_kuyruk([("Homer", 5000)])
    llm = SahteLLM([SahteYanit([{"baslik": "Homer", "sinif": "edebiyat", "gerekce": "x"}])])
    sonuc = siniflandirici.siniflandir(llm, yol)

    assert sonuc.sorulan == 0
    assert sinif_oku(yol, "Homer")[0] == "belirsiz"


def test_reddedilen_istek_cokmez(yol: Path, belirsiz_kuyruk):
    """`stop_reason == "refusal"` boş content döndürür — indekslemeden önce bakılmalı."""
    belirsiz_kuyruk([("Homer", 5000)])
    llm = SahteLLM([SahteYanit([], stop_reason="refusal")])
    sonuc = siniflandirici.siniflandir(llm, yol)

    assert len(sonuc.hatalar) == 1
    assert "reddetti" in sonuc.hatalar[0]


def test_bos_kuyruk_cagri_yapmaz(yol: Path):
    llm = SahteLLM([])
    assert siniflandirici.siniflandir(llm, yol).cagri_sayisi == 0
    assert llm.istemler == []


# --- İstem --------------------------------------------------------------


def test_istem_ozet_icerir(yol: Path, belirsiz_kuyruk, monkeypatch):
    """Başlık tek başına yetmiyor — "Homer" şair mi Simpson mı?"""
    belirsiz_kuyruk([("Homer", 5000)])
    monkeypatch.setattr(
        wikipedia, "ozetleri_getir", lambda d, b: {"Homer": "was an ancient Greek poet"}
    )
    llm = SahteLLM([SahteYanit([])])
    siniflandirici.siniflandir(llm, yol)
    assert "ancient Greek poet" in llm.istemler[0]


def test_istem_ozet_olmadan_da_calisir(yol: Path, belirsiz_kuyruk, monkeypatch):
    belirsiz_kuyruk([("Homer", 5000)])
    monkeypatch.setattr(wikipedia, "ozetleri_getir", lambda d, b: {})
    llm = SahteLLM([SahteYanit([])])
    siniflandirici.siniflandir(llm, yol)
    assert "Homer" in llm.istemler[0]


def test_yonerge_ayrim_kurallarini_tasiyor():
    """Canlı koşumda bulunan üç hata istemde açıkça karşılanmalı."""
    for isim in ("Frida Kahlo", "Richard Wagner", "Paul Newman"):
        assert isim in siniflandirici.YONERGE
    assert "Emin değilsen `diger`" in siniflandirici.YONERGE


def test_anahtar_yoksa_anlasilir_hata(monkeypatch):
    monkeypatch.delenv(siniflandirici.ANAHTAR_DEGISKENI, raising=False)
    with pytest.raises(siniflandirici.SiniflandirmaHatasi, match="ANTHROPIC_API_KEY"):
        siniflandirici.istemci_kur()
