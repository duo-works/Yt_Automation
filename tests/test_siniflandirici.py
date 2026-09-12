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


def test_okunur_bicimde_donen_baslik_yazilir(yol: Path, belirsiz_kuyruk):
    """Model, `_istem()`'in gösterdiği alt çizgisiz biçimi döndürebilir.

    Canlı koşumda 300 makalenin 273'ü tam bu yüzden düştü: istem başlığı
    `Bill Oddie` diye gösterip kod `Bill_Oddie` bekliyordu. Eski testler
    yakalayamadı çünkü fixture başlıklarının hepsi tek kelimeydi — tek
    kelimede iki biçim aynı ve hata görünmüyor.
    """
    belirsiz_kuyruk([("Bill_Oddie", 5000), ("Tim_Brooke-Taylor", 3000)])
    llm = SahteLLM(
        [
            SahteYanit(
                [
                    {"baslik": "Bill Oddie", "sinif": "diger", "gerekce": "komedyen"},
                    {"baslik": "Tim Brooke-Taylor", "sinif": "diger", "gerekce": "komedyen"},
                ]
            )
        ]
    )
    sonuc = siniflandirici.siniflandir(llm, yol)

    assert sonuc.hatalar == []
    assert sonuc.sorulan == 2
    assert sinif_oku(yol, "Bill_Oddie") == ("diger", "llm")
    assert sinif_oku(yol, "Tim_Brooke-Taylor") == ("diger", "llm")


def test_alt_cizgili_bicimde_donen_baslik_da_yazilir(yol: Path, belirsiz_kuyruk):
    """Model bazen depo biçimini döndürüyor; ikisi de kabul edilmeli.

    Hata nondeterministikti: eski istem "alt çizgiler dahil" diyordu ama
    alt çizgiyi hiç göstermiyordu, model bazen ekliyor bazen eklemiyordu.
    """
    belirsiz_kuyruk([("Bill_Oddie", 5000)])
    llm = SahteLLM([SahteYanit([{"baslik": "Bill_Oddie", "sinif": "diger", "gerekce": "x"}])])
    sonuc = siniflandirici.siniflandir(llm, yol)

    assert sonuc.hatalar == []
    assert sinif_oku(yol, "Bill_Oddie") == ("diger", "llm")


def test_dil_oneki_ile_donen_baslik_yazilir(yol: Path, belirsiz_kuyruk):
    """Model satır başındaki `[de]` etiketini başlığa katabiliyor.

    İlk düzeltmeden sonra kalan 40 hatanın tamamı buydu: istem satırları
    `- [de] Dean Reed` biçimindeydi. İstem artık dili bir kez üstte söylüyor,
    ama gelen önek yine de hoş görülüyor.
    """
    belirsiz_kuyruk([("Dean_Reed", 5000)], dil="de")
    llm = SahteLLM([SahteYanit([{"baslik": "[de] Dean Reed", "sinif": "diger", "gerekce": "x"}])])
    sonuc = siniflandirici.siniflandir(llm, yol)

    assert sonuc.hatalar == []
    assert sinif_oku(yol, "Dean_Reed") == ("diger", "llm")


def test_istem_dili_satir_basina_tekrarlamaz(yol: Path):
    """Dil bir kez üstte; satırlar yalnızca başlık taşır."""
    kayitlar = [{"dil": "de", "baslik": "Dean_Reed", "okunma": 100}]
    istem = siniflandirici._istem(kayitlar, {})

    assert "de.wikipedia" in istem
    assert "- Dean Reed" in istem
    assert "[de]" not in istem


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
    monkeypatch.delenv(siniflandirici.OPENROUTER_ANAHTAR_DEGISKENI, raising=False)
    monkeypatch.delenv(siniflandirici.SAGLAYICI_DEGISKENI, raising=False)
    with pytest.raises(siniflandirici.SiniflandirmaHatasi, match="ANTHROPIC_API_KEY"):
        siniflandirici.istemci_kur()


# --- Sağlayıcı seçimi (DW-138) ---------------------------------------------


@pytest.mark.parametrize(
    "ortam,beklenen",
    [
        ({"LLM_SAGLAYICI": "openrouter", "ANTHROPIC_API_KEY": "a"}, "openrouter"),
        ({"LLM_SAGLAYICI": "anthropic", "OPENROUTER_API_KEY": "o"}, "anthropic"),
        ({"ANTHROPIC_API_KEY": "a", "OPENROUTER_API_KEY": "o"}, "anthropic"),
        ({"OPENROUTER_API_KEY": "o"}, "openrouter"),
        ({}, "anthropic"),
    ],
)
def test_saglayici_secimi(ortam, beklenen):
    """Açık seçim her şeyi ezer; boşsa eldeki anahtar; Anthropic önce —
    mevcut kurulumlar (yalnızca ANTHROPIC_API_KEY) hiç değişmesin."""
    assert siniflandirici.saglayici_sec(ortam) == beklenen


def test_taninmayan_saglayici_HATA_verir_sessizce_dusmez():
    """ "OpenRouter'a geçtim" sanılan hat Anthropic'te koşup 400 almasın."""
    with pytest.raises(siniflandirici.SiniflandirmaHatasi, match="LLM_SAGLAYICI"):
        siniflandirici.saglayici_sec({"LLM_SAGLAYICI": "openai"})


def test_openrouter_modeli_env_den_yoksa_varsayilan():
    assert siniflandirici.saglayici_ve_model({"LLM_SAGLAYICI": "openrouter"}) == (
        "openrouter",
        siniflandirici.OPENROUTER_VARSAYILAN_MODEL,
    )
    assert siniflandirici.saglayici_ve_model(
        {"LLM_SAGLAYICI": "openrouter", "OPENROUTER_MODEL": "x/y"}
    ) == ("openrouter", "x/y")


def test_openrouter_anahtari_yoksa_anlasilir_hata(monkeypatch):
    monkeypatch.setenv(siniflandirici.SAGLAYICI_DEGISKENI, "openrouter")
    monkeypatch.delenv(siniflandirici.OPENROUTER_ANAHTAR_DEGISKENI, raising=False)
    with pytest.raises(siniflandirici.SiniflandirmaHatasi, match="OPENROUTER_API_KEY"):
        siniflandirici.istemci_kur()


def test_openrouter_istemcisi_kuruluyor(monkeypatch):
    monkeypatch.setenv(siniflandirici.SAGLAYICI_DEGISKENI, "openrouter")
    monkeypatch.setenv(siniflandirici.OPENROUTER_ANAHTAR_DEGISKENI, "sk-or-test")
    istemci = siniflandirici.istemci_kur()
    assert isinstance(istemci, siniflandirici.OpenRouterIstemci)
    assert istemci.model == siniflandirici.OPENROUTER_VARSAYILAN_MODEL


# --- OpenRouter istemcisi — sahte taşıma, canlı çağrı yok ------------------


def _openrouter_cevap(icerik, maliyet=None):
    veri = {"choices": [{"message": {"content": icerik}}]}
    if maliyet is not None:
        veri["usage"] = {"cost": maliyet}
    return veri


def test_openrouter_json_citini_soyuyor_ve_maliyeti_topluyor(monkeypatch):
    """MPT'de ölçüldü: Kimi cevabı ```json çitiyle dönüyor; çıplak
    `json.loads` patlar. `usage.cost` özete taşınır."""
    istemci = siniflandirici.OpenRouterIstemci("k", "m")
    gonderilen = []

    def sahte(govde):
        gonderilen.append(govde)
        ic = json.dumps({"sonuclar": [{"baslik": "Frida Kahlo", "sinif": "diger", "gerekce": "r"}]})
        return _openrouter_cevap(f"```json\n{ic}\n```", maliyet=0.0021)

    monkeypatch.setattr(istemci, "_gonder", sahte)

    sonuc = istemci.sor("yönerge", "istem")

    assert sonuc["sonuclar"][0]["sinif"] == "diger"
    assert istemci.maliyet_usd == pytest.approx(0.0021)
    govde = gonderilen[0]
    # ⚠️ Akıl yürütme KAPALI olmalı — Kimi bütçeyi düşünmeye harcayıp boş dönüyor.
    assert govde["reasoning"] == {"enabled": False}
    assert govde["usage"] == {"include": True}
    assert govde["response_format"] == {"type": "json_object"}
    assert govde["messages"][0] == {"role": "system", "content": "yönerge"}


def test_openrouter_bos_cevap_sessiz_gecmiyor(monkeypatch):
    istemci = siniflandirici.OpenRouterIstemci("k", "m")
    monkeypatch.setattr(istemci, "_gonder", lambda g: _openrouter_cevap(None))
    with pytest.raises(siniflandirici.SiniflandirmaHatasi, match="boş cevap"):
        istemci.sor("y", "i")


def test_openrouter_402_metni_hataya_giriyor(monkeypatch):
    """`gunluk-huni.sh` bütçe hâlini bu metinden tanıyor (`kredi_bitti_mi`);
    yutulursa kredisi bitmiş hat yine "bozuk" görünür (DW-136)."""
    import io
    import urllib.error

    istemci = siniflandirici.OpenRouterIstemci("k", "m")

    def patla(istek, timeout):
        raise urllib.error.HTTPError(
            istek.full_url,
            402,
            "Payment Required",
            {},
            io.BytesIO(
                b'{"error":{"message":"This request requires more credits, or fewer '
                b'max_tokens. You requested up to 8000 tokens, but can only afford 12."}}'
            ),
        )

    monkeypatch.setattr("urllib.request.urlopen", patla)
    with pytest.raises(siniflandirici.SiniflandirmaHatasi, match="402.*requires more credits"):
        istemci.sor("y", "i")


def test_siniflandir_openrouter_istemcisiyle_yaziyor(yol: Path, belirsiz_kuyruk, monkeypatch):
    """`_grubu_sor` iki yüzeyi ayırt ediyor: `sor()` olan istemci OpenAI
    uyumlu yoldan gider, sonuç yine aynı `_yaz`dan geçer."""
    belirsiz_kuyruk([("Frida_Kahlo", 500), ("Marie_Curie", 300)])
    istemci = siniflandirici.OpenRouterIstemci("k", "m")
    monkeypatch.setattr(
        istemci,
        "_gonder",
        lambda g: _openrouter_cevap(
            json.dumps(
                {
                    "sonuclar": [
                        {"baslik": "Frida Kahlo", "sinif": "diger", "gerekce": "ressam"},
                        {"baslik": "Marie Curie", "sinif": "bilim", "gerekce": "fizikçi"},
                    ]
                }
            ),
            maliyet=0.003,
        ),
    )

    sonuc = siniflandirici.siniflandir(istemci, yol)

    assert sinif_oku(yol, "Frida_Kahlo") == ("diger", "llm")
    assert sinif_oku(yol, "Marie_Curie") == ("bilim", "llm")
    assert sonuc.cagri_sayisi == 1
    assert sonuc.maliyet_usd == pytest.approx(0.003)
    assert "$0.0030" in sonuc.ozet()


def test_anthropic_yolu_ozete_maliyet_yazmiyor(yol: Path, belirsiz_kuyruk):
    """Anthropic cevabı maliyet taşımıyor; özet satırı değişmemeli."""
    belirsiz_kuyruk([("Frida_Kahlo", 500)])
    llm = SahteLLM([SahteYanit([{"baslik": "Frida Kahlo", "sinif": "diger", "gerekce": "r"}])])

    sonuc = siniflandirici.siniflandir(llm, yol)

    assert sonuc.maliyet_usd == 0.0
    assert "$" not in sonuc.ozet()
