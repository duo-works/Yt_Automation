"""Talep-arz boşluğu — sondaj, skorlama ve kota koruması.

Hiç canlı çağrı yok: `search.list` 100 birim ve CI'da tekrarlanamaz.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yt_automation import cli, depo, kota
from yt_automation.trend import bosluk

SIMDI = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class SahteYT:
    """`search`/`videos`/`channels` zincirlerini taklit eder.

    `arama`: `(video_id, başlık, kanal_id)` üçlüleri.
    `izlenmeler`: `video_id → izlenme` (yok = istatistik gizli).
    `yaslar`: `video_id → gün` (son andan geriye).
    `aboneler`: `kanal_id → abone` (`None` = gizlenmiş).
    """

    def __init__(self, *, arama=(), izlenmeler=None, yaslar=None, aboneler=None, hatalar=None):
        self.arama = list(arama)
        self.izlenmeler = izlenmeler or {}
        self.yaslar = yaslar or {}
        self.aboneler = aboneler or {}
        self.hatalar = hatalar or {}
        self.cagrilar: list[str] = []
        self.parametreler: list[dict] = []
        self._tur = ""
        self._p: dict = {}

    def search(self):
        self._tur = "search"
        return self

    def videos(self):
        self._tur = "videos"
        return self

    def channels(self):
        self._tur = "channels"
        return self

    def list(self, **p):
        self._p = p
        return self

    def execute(self):
        self.cagrilar.append(self._tur)
        self.parametreler.append(dict(self._p))
        if self._tur in self.hatalar:
            raise self.hatalar[self._tur]
        if self._tur == "search":
            return {
                "items": [
                    {"id": {"videoId": vid}, "snippet": {"title": baslik}}
                    for vid, baslik, _ in self.arama
                ]
            }
        if self._tur == "videos":
            istenen = self._p["id"].split(",")
            ogeler = []
            for vid, _, kanal in self.arama:
                if vid not in istenen:
                    continue
                yas = self.yaslar.get(vid, 100)
                oge = {
                    "id": vid,
                    "snippet": {
                        # `publishedAt` API'de ISO metin gelir.
                        "publishedAt": (SIMDI - timedelta(days=yas)).isoformat(),
                        "channelId": kanal,
                    },
                    "statistics": {},
                }
                if vid in self.izlenmeler:
                    oge["statistics"]["viewCount"] = str(self.izlenmeler[vid])
                ogeler.append(oge)
            return {"items": ogeler}
        istenen = self._p["id"].split(",")
        ogeler = []
        for kanal in istenen:
            abone = self.aboneler.get(kanal, 1_000)
            istatistik = (
                {"hiddenSubscriberCount": True}
                if abone is None
                else {"subscriberCount": str(abone), "hiddenSubscriberCount": False}
            )
            ogeler.append({"id": kanal, "statistics": istatistik})
        return {"items": ogeler}


@pytest.fixture
def aday(yol: Path):
    """`makale` + `okunma` satırı yazar — sondajın girdisi."""

    def kur(qid: str, baslik: str, *, dil: str = "en", okunma: int = 100_000, sinif="tarih"):
        with depo.yazma_islemi(yol) as baglanti:
            baglanti.execute(
                "INSERT OR REPLACE INTO makale (dil, baslik, qid, sinif, sinif_kaynagi, "
                "ilk_gorulme) VALUES (?, ?, ?, ?, 'wikidata', ?)",
                (dil, baslik, qid, sinif, SIMDI.isoformat()),
            )
            baglanti.execute(
                "INSERT OR REPLACE INTO okunma (dil, baslik, gun, okunma, sira) "
                "VALUES (?, ?, '2026-07-28', ?, 1)",
                (dil, baslik, okunma),
            )

    return kur


@pytest.fixture
def bosluk_sayac(yol: Path) -> kota.KaliciSayac:
    return kota.KaliciSayac(yol, surec=bosluk.SUREC)


# --- Sorgu ve alaka ------------------------------------------------------


def test_ayrim_eki_sorgudan_atilir(yol: Path):
    """Kimse "Cleopatra (1963 film)" diye aramıyor — parantez Wikipedia'nın eki."""
    assert bosluk.sorguya_cevir("Cleopatra_(1963_film)") == "Cleopatra"
    assert bosluk.sorguya_cevir("Battle_of_Actium") == "Battle of Actium"


def test_kisa_belirtecler_atilir(yol: Path):
    """ "of", "the", "ve" her başlıkta var ve alaka hakkında hiçbir şey söylemez."""
    assert bosluk.belirtecler("Battle of Actium") == {"battle", "actium"}


def test_aksanlar_duserek_esitlenir(yol: Path):
    """Diller arası çalışmalı: "Süleyman" ile "Suleyman" aynı belirteç."""
    assert bosluk.belirtecler("Süleyman") == bosluk.belirtecler("Suleyman")
    assert bosluk.belirtecler("Ægypt") == bosluk.belirtecler("Aegypt")


def test_turkce_noktasiz_i_sozcugu_kesmiyor(yol: Path):
    """NFKD `ı`'yı ayrıştırmıyor; tablosuz "Osmanlı" → "osmanl" oluyordu.

    Türkçe birincil hedef dil: sessizce yanlış eşleşen bir alaka ölçümü,
    Türkçe adaylarda arzı sistematik olarak eksik gösterirdi.
    """
    assert bosluk.belirtecler("Osmanlı İmparatorluğu") == {"osmanli", "imparatorlugu"}
    assert bosluk.belirtecler("Osmanlı") == bosluk.belirtecler("Osmanli")

    hedef = bosluk.belirtecler("Fatih Sultan Mehmet")
    assert bosluk.alakali_mi(hedef, "FATİH SULTAN MEHMET Belgesel")


def test_alaka_yarim_esikle_olculur(yol: Path):
    hedef = bosluk.belirtecler("Battle of Actium")
    assert bosluk.alakali_mi(hedef, "The Actium Disaster Explained")
    assert bosluk.alakali_mi(hedef, "Actium: Rome's Turning Point")
    assert not bosluk.alakali_mi(hedef, "Top 10 Roman Emperors")


def test_anlamli_belirtec_yoksa_alakali_sayilir(yol: Path):
    """Hata yönü asimetrik: fazla arz saymak, az saymaktan güvenli."""
    assert bosluk.alakali_mi(set(), "Herhangi bir başlık")


# --- Sondaj maliyeti -----------------------------------------------------


def test_tam_sondaj_102_birim(yol: Path, aday, bosluk_sayac):
    aday("Q1", "Cleopatra")
    istemci = SahteYT(
        arama=[("v1", "Cleopatra Documentary", "k1"), ("v2", "Cleopatra Explained", "k2")],
        izlenmeler={"v1": 5_000, "v2": 9_000},
        aboneler={"k1": 20_000, "k2": 40_000},
    )
    olcum = bosluk.sondala(istemci, bosluk_sayac, qid="Q1", dil="en", baslik="Cleopatra", an=SIMDI)

    assert istemci.cagrilar == ["search", "videos", "channels"]
    assert olcum.harcanan == 102 == bosluk.SONDAJ_MALIYETI
    assert bosluk_sayac.surec_harcamasi == 102


def test_bos_arama_iki_cagriyi_atlar(yol: Path, aday, bosluk_sayac):
    """Sonuç yoksa istatistik ve kanal çağrısı 2 birimi çöpe atmak olurdu."""
    istemci = SahteYT(arama=[])
    olcum = bosluk.sondala(istemci, bosluk_sayac, qid="Q1", dil="en", baslik="Xyzzy", an=SIMDI)

    assert istemci.cagrilar == ["search"]
    assert olcum.harcanan == 100
    assert olcum.gecerli is False, "boş arama 'arzı yok' değil 'sorgu şüpheli'"


def test_alakali_sonuc_yoksa_istatistik_istenmez(yol: Path, aday, bosluk_sayac):
    """50 sonuç var ama hiçbiri konuyu karşılamıyor — gerçek boşluk, geçerli ölçüm."""
    istemci = SahteYT(arama=[(f"v{i}", "Alakasiz Baska Konu", f"k{i}") for i in range(50)])
    olcum = bosluk.sondala(istemci, bosluk_sayac, qid="Q1", dil="en", baslik="Cleopatra", an=SIMDI)

    assert istemci.cagrilar == ["search"]
    assert olcum.donen == 50
    assert olcum.alakali == 0
    assert olcum.gecerli is True


def test_sorgu_dogru_parametrelerle_gonderilir(yol: Path, bosluk_sayac):
    istemci = SahteYT(arama=[])
    bosluk.sondala(
        istemci, bosluk_sayac, qid="Q1", dil="tr", baslik="Fatih_Sultan_Mehmet", an=SIMDI
    )
    p = istemci.parametreler[0]

    assert p["q"] == "Fatih Sultan Mehmet"
    assert p["type"] == "video"
    assert p["relevanceLanguage"] == "tr"
    assert p["maxResults"] == 50, "maliyet aynı olduğu için hep 50 istenmeli"


# --- Ölçüm doğruluğu -----------------------------------------------------


def test_medyanlar_alakali_videolardan_hesaplanir(yol: Path, bosluk_sayac):
    istemci = SahteYT(
        arama=[
            ("v1", "Cleopatra Full Documentary", "k1"),
            ("v2", "Cleopatra in 10 Minutes", "k2"),
            ("v3", "Cleopatra Biography", "k3"),
            ("alakasiz", "Ancient Rome Top 10", "k9"),
        ],
        izlenmeler={"v1": 1_000, "v2": 5_000, "v3": 9_000, "alakasiz": 9_000_000},
        yaslar={"v1": 100, "v2": 200, "v3": 300},
        aboneler={"k1": 1_000, "k2": 3_000, "k3": 5_000},
    )
    olcum = bosluk.sondala(istemci, bosluk_sayac, qid="Q1", dil="en", baslik="Cleopatra", an=SIMDI)

    assert olcum.alakali == 3
    assert olcum.medyan_izlenme == 5_000, "alakasız videonun 9M izlenmesi girmemeli"
    assert olcum.ust_izlenme == 9_000
    assert olcum.medyan_yas_gun == 200
    assert olcum.medyan_abone == 3_000


def test_gizli_abone_medyana_girmez(yol: Path, bosluk_sayac):
    """Gizlenmiş aboneyi sıfır saymak, büyük bir kanalı küçük göstermek olurdu."""
    istemci = SahteYT(
        arama=[("v1", "Cleopatra A", "k1"), ("v2", "Cleopatra B", "gizli")],
        izlenmeler={"v1": 1_000, "v2": 1_000},
        aboneler={"k1": 7_000, "gizli": None},
    )
    olcum = bosluk.sondala(istemci, bosluk_sayac, qid="Q1", dil="en", baslik="Cleopatra", an=SIMDI)
    assert olcum.medyan_abone == 7_000


def test_istatistigi_olmayan_video_izlenmeye_karismaz(yol: Path, bosluk_sayac):
    istemci = SahteYT(
        arama=[("v1", "Cleopatra A", "k1"), ("v2", "Cleopatra B", "k1")],
        izlenmeler={"v1": 4_000},  # v2'nin istatistiği gizli
        aboneler={"k1": 1_000},
    )
    olcum = bosluk.sondala(istemci, bosluk_sayac, qid="Q1", dil="en", baslik="Cleopatra", an=SIMDI)
    assert olcum.medyan_izlenme == 4_000


def test_ayni_kanal_her_video_icin_sayilir(yol: Path, bosluk_sayac):
    """Ölçtüğümüz "karşımdaki kanal ne büyüklükte", "kaç ayrı kanal var" değil.

    Tek bir dev kanal listeyi doldurmuşsa arz güçlüdür; bunu bir kez saymak
    rekabeti olduğundan zayıf gösterirdi.
    """
    istemci = SahteYT(
        arama=[
            ("v1", "Cleopatra A", "dev"),
            ("v2", "Cleopatra B", "dev"),
            ("v3", "Cleopatra C", "kucuk"),
        ],
        izlenmeler={"v1": 1_000, "v2": 1_000, "v3": 1_000},
        aboneler={"dev": 5_000_000, "kucuk": 100},
    )
    olcum = bosluk.sondala(istemci, bosluk_sayac, qid="Q1", dil="en", baslik="Cleopatra", an=SIMDI)
    assert olcum.medyan_abone == 5_000_000, "iki dev videosu medyanı yukarı çekmeli"


# --- Skorlama: 10 iyi / 10 kötü boşluk ----------------------------------

# Kabul ölçütü. Örnekler gerçek kalıplardan türetildi: iyi boşluk = talep
# yüksek, mevcut içerik az / eski / düşük izlenmeli / küçük kanallardan.
# Kötü boşluk = talep yüksek ama liste yeni, çok izlenen, dev kanallardan dolu.
#
# Değerler `(talep, dönen, alakalı, medyan_izlenme, medyan_yaş_gün, medyan_abone)`.
IYI_BOSLUKLAR = [
    ("çok eski içerik, küçük kanallar", (250_000, 50, 2, 1_500, 2_500, 3_000)),
    ("50 sonuç, hiçbiri konuyu karşılamıyor", (180_000, 48, 0, None, None, None)),
    ("orta talep, zayıf ve bayat arz", (90_000, 50, 5, 8_000, 1_800, 12_000)),
    ("az sonuç, hepsi 8 yıllık", (120_000, 30, 3, 4_000, 3_000, 2_000)),
    ("mikro kanallar, düşük izlenme", (60_000, 50, 4, 2_000, 2_200, 800)),
    ("tek alakalı sonuç, 900 izlenme", (45_000, 20, 1, 900, 2_800, 500)),
    ("yüksek talep, orta arz", (150_000, 50, 6, 5_000, 2_000, 9_000)),
    ("dengeli ama eski", (75_000, 40, 3, 3_500, 2_000, 5_000)),
    ("çok yüksek talep, kısıtlı arz", (220_000, 50, 4, 6_000, 2_600, 15_000)),
    ("iki alakalı sonuç, küçük kanallar", (110_000, 35, 2, 2_500, 2_400, 1_500)),
]

KOTU_BOSLUKLAR = [
    ("doymuş: dev kanallar, yeni içerik", (250_000, 50, 45, 800_000, 60, 2_000_000)),
    ("tamamen doymuş", (180_000, 50, 50, 1_200_000, 90, 5_000_000)),
    ("orta talep ama güçlü arz", (90_000, 50, 30, 300_000, 120, 800_000)),
    ("herkesin yaptığı konu", (500_000, 50, 40, 2_000_000, 45, 10_000_000)),
    ("düşük talep, yine de doymuş", (60_000, 50, 25, 150_000, 200, 400_000)),
    ("viral konu, imkânsız rekabet", (1_000_000, 50, 48, 5_000_000, 30, 20_000_000)),
    ("küçük talep, oturmuş arz", (45_000, 50, 35, 90_000, 180, 250_000)),
    ("yüksek talep, taze dev içerik", (150_000, 50, 42, 600_000, 75, 1_500_000)),
    ("milyonluk kanallar hâkim", (220_000, 50, 38, 1_000_000, 100, 3_000_000)),
    ("orta ölçek ama kalabalık", (110_000, 50, 33, 250_000, 150, 600_000)),
]


def _skor(veri: tuple) -> float:
    talep, donen, alakali, izlenme, yas, abone = veri
    olcum = bosluk.ArzOlcumu(
        qid="Q",
        dil="en",
        sorgu="x",
        an=SIMDI.isoformat(),
        donen=donen,
        alakali=alakali,
        medyan_izlenme=izlenme,
        medyan_yas_gun=yas,
        medyan_abone=abone,
    )
    skor = bosluk.skorla(olcum, talep)
    assert skor is not None
    return skor


@pytest.mark.parametrize(("etiket", "veri"), IYI_BOSLUKLAR)
def test_iyi_bosluk_pozitif_skor(etiket: str, veri: tuple):
    assert _skor(veri) > 0, f"iyi boşluk negatif skor aldı: {etiket}"


@pytest.mark.parametrize(("etiket", "veri"), KOTU_BOSLUKLAR)
def test_kotu_bosluk_negatif_skor(etiket: str, veri: tuple):
    assert _skor(veri) < 0, f"kötü boşluk pozitif skor aldı: {etiket}"


def test_iyi_ve_kotu_bosluklar_tamamen_ayrilir():
    """Kabul ölçütünün özü: en kötü "iyi", en iyi "kötü"nün üstünde olmalı.

    Sıfır işareti yorumlanabilir bir sınır: artı = talep arzı aşıyor.
    """
    iyi = [_skor(v) for _, v in IYI_BOSLUKLAR]
    kotu = [_skor(v) for _, v in KOTU_BOSLUKLAR]

    assert min(iyi) > max(kotu)
    assert min(iyi) > 0 > max(kotu)
    # Aralık en az 2 puan olmalı: log ölçekte 100 kat fark. Bu kadar geniş bir
    # marj, ağırlıklar biraz değişse de ayrımın ayakta kalacağını gösteriyor.
    assert min(iyi) - max(kotu) > 2.0


def test_canli_sondaj_siralamasi_korunur():
    """İlk canlı sondajın (2026-07-30) gerçek sayıları — sıralama regresyonu.

    Sentetik kümenin doğrulamadığı şey: gerçek Wikipedia okunması bu konularda
    25 bin civarında, sentetik kümede 45 bin–1 milyon. Bu yüzden üç ölçümün
    hepsi negatif çıkıyor ve **işaret kalibre değil**. Korunması gereken şey
    işaret değil, sıralama: Great Zimbabwe gerçekten en az doymuş olan.
    """
    great_zimbabwe = (27_301, 50, 49, 22_125, 858, 41_700)
    abdul_kalam = (24_116, 50, 50, 1_462_458, 1_073, 407_000)
    cleopatra = (25_020, 50, 47, 1_129_928, 519, 474_000)

    assert _skor(great_zimbabwe) > _skor(abdul_kalam)
    assert _skor(great_zimbabwe) > _skor(cleopatra)
    assert _skor(great_zimbabwe) - _skor(cleopatra) > 2.0, "ayrım belirgin olmalı"
    # Ölçülen gerçek: hepsi negatif. Bu bir hata değil, kalibrasyon eksiği —
    # test bunu **kayda geçiriyor** ki ileride sessizce değişmesin.
    assert max(_skor(v) for v in (great_zimbabwe, abdul_kalam, cleopatra)) < 0


def test_gecersiz_olcum_skorlanmaz(yol: Path):
    """Sorgusu bozuk bir konuyu "arzı hiç yok" diye zirveye koymak en pahalı hata."""
    olcum = bosluk.ArzOlcumu(qid="Q", dil="en", sorgu="x", an=SIMDI.isoformat(), donen=0)
    assert bosluk.skorla(olcum, 500_000) is None


def test_yas_arzi_zayiflatir():
    """Aynı izlenme, aynı kanal — tek fark yaş. Eski içerik boşluk demek."""
    yeni = (100_000, 50, 5, 50_000, 30, 100_000)
    eski = (100_000, 50, 5, 50_000, 2_000, 100_000)
    assert _skor(eski) > _skor(yeni)


def test_kanal_buyuklugu_arzi_gucledirir():
    """102. birimin gerekçesi: aynı izlenme, farklı kanal büyüklüğü."""
    kucuk = (100_000, 50, 5, 50_000, 365, 2_000)
    dev = (100_000, 50, 5, 50_000, 365, 5_000_000)
    assert _skor(kucuk) > _skor(dev)


# --- Kota koruması ------------------------------------------------------


def test_yukleme_rezervi_korunur(yol: Path, aday, bosluk_sayac):
    """Araştırma hiçbir koşulda yayını bloke etmemeli."""
    bir_video = kota.video_basina_maliyet()
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO kota_harcama (gun, an, islem, birim, surec) VALUES (?, ?, ?, ?, ?)",
            (
                kota.kota_gunu(),
                SIMDI.isoformat(),
                "videos.list",
                kota.GUNLUK_BUTCE - bir_video - 50,
                "yukleme",
            ),
        )

    with pytest.raises(kota.KotaAsimi, match="rezerve"):
        bosluk.sondala(
            SahteYT(arama=[]), bosluk_sayac, qid="Q1", dil="en", baslik="Cleopatra", an=SIMDI
        )


def test_gunluk_tavan_asilmaz(yol: Path, aday, bosluk_sayac):
    """Tavan sondaj **başlamadan** kontrol ediliyor: yarım sondaj 100 birim çöp."""
    for i in range(30):
        aday(f"Q{i}", f"Konu_{i}", okunma=100_000 - i)
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO kota_harcama (gun, an, islem, birim, surec) VALUES (?, ?, ?, ?, ?)",
            (kota.kota_gunu(), SIMDI.isoformat(), "search.list", 2_950, bosluk.SUREC),
        )

    sonuc = bosluk.arastir(
        SahteYT(arama=[]), bosluk_sayac, yol, limit=30, tavan=bosluk.SONDAJ_KOTA_TAVANI
    )

    assert sonuc.sondaj == 0
    assert sonuc.kota_bitti is True
    assert bosluk_sayac.surec_harcamasi == 2_950, "tek birim bile harcanmamalı"


def test_tavan_dolunca_durur_kalan_adaylar_beklemede(yol: Path, aday, bosluk_sayac):
    for i in range(5):
        aday(f"Q{i}", f"Konu_{i}", okunma=100_000 - i)

    sonuc = bosluk.arastir(SahteYT(arama=[]), bosluk_sayac, yol, limit=5, tavan=250)

    assert sonuc.sondaj == 2, "250 / 102 = 2 sondaj sığar"
    assert sonuc.kota_bitti is True


# --- Aday seçimi ve araştırma döngüsü -----------------------------------


def test_sondajlanmis_aday_tekrar_sorulmaz(yol: Path, aday, bosluk_sayac):
    """Huninin en önemli tasarrufu: her tekrar 102 birim."""
    aday("Q1", "Cleopatra", okunma=200_000)
    aday("Q2", "Hannibal", okunma=100_000)

    bosluk.arastir(SahteYT(arama=[]), bosluk_sayac, yol, limit=1)
    kalan = [a["baslik"] for a in bosluk.sondajlanmamis_adaylar(yol, 10)]

    assert kalan == ["Hannibal"]


def test_diger_sinif_sondalanmaz(yol: Path, aday):
    aday("Q1", "Tarihi_Konu", okunma=100_000, sinif="tarih")
    aday("Q2", "Magazin", okunma=900_000, sinif="diger")
    aday("Q3", "Belirsiz", okunma=800_000, sinif="belirsiz")

    assert [a["baslik"] for a in bosluk.sondajlanmamis_adaylar(yol, 10)] == ["Tarihi_Konu"]


def test_qidsiz_aday_sondalanmaz(yol: Path, aday):
    """`arz` qid üzerinden anahtarlanıyor; kimliksiz makale yazılamaz."""
    aday("Q1", "Kimlikli", okunma=100_000)
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO makale (dil, baslik, qid, sinif, sinif_kaynagi, ilk_gorulme) "
            "VALUES ('en', 'Kimliksiz', NULL, 'tarih', 'llm', ?)",
            (SIMDI.isoformat(),),
        )
        baglanti.execute(
            "INSERT INTO okunma (dil, baslik, gun, okunma) VALUES "
            "('en', 'Kimliksiz', '2026-07-28', 999999)"
        )

    assert [a["baslik"] for a in bosluk.sondajlanmamis_adaylar(yol, 10)] == ["Kimlikli"]


def test_bir_adayin_hatasi_arastirmayi_bitirmez(yol: Path, aday, bosluk_sayac):
    aday("Q1", "Patlayan", okunma=200_000)
    aday("Q2", "Calisan", okunma=100_000)

    cagri = {"n": 0}

    class Kararsiz(SahteYT):
        def execute(self):
            if self._tur == "search":
                cagri["n"] += 1
                if cagri["n"] == 1:
                    raise RuntimeError("503 backend error")
            return super().execute()

    sonuc = bosluk.arastir(Kararsiz(arama=[]), bosluk_sayac, yol, limit=2)

    assert len(sonuc.hatalar) == 1
    assert sonuc.sondaj == 1, "ikinci aday yine işlenmeli"


def test_olcum_diske_yazilir(yol: Path, aday, bosluk_sayac):
    aday("Q1", "Cleopatra")
    istemci = SahteYT(
        arama=[("v1", "Cleopatra Documentary", "k1")],
        izlenmeler={"v1": 4_242},
        aboneler={"k1": 8_000},
    )
    bosluk.arastir(istemci, bosluk_sayac, yol, limit=1)

    baglanti = depo.baglan(yol)
    try:
        satir = baglanti.execute("SELECT * FROM arz").fetchone()
    finally:
        baglanti.close()

    assert satir["qid"] == "Q1"
    assert satir["sorgu"] == "Cleopatra"
    assert satir["medyan_izlenme"] == 4_242
    assert satir["harcanan"] == 102


# --- Rapor ---------------------------------------------------------------


def test_rapor_skora_gore_sirali(yol: Path, aday, bosluk_sayac):
    aday("Q1", "Doymus_Konu", okunma=200_000)
    aday("Q2", "Bos_Konu", okunma=200_000)

    for qid, baslik, istemci in [
        (
            "Q1",
            "Doymus_Konu",
            SahteYT(
                arama=[(f"v{i}", "Doymus Konu Belgesel", "dev") for i in range(20)],
                izlenmeler={f"v{i}": 900_000 for i in range(20)},
                yaslar={f"v{i}": 40 for i in range(20)},
                aboneler={"dev": 4_000_000},
            ),
        ),
        (
            "Q2",
            "Bos_Konu",
            SahteYT(
                arama=[("v1", "Bos Konu Kisa", "mikro")],
                izlenmeler={"v1": 600},
                yaslar={"v1": 2_400},
                aboneler={"mikro": 300},
            ),
        ),
    ]:
        olcum = bosluk.sondala(istemci, bosluk_sayac, qid=qid, dil="en", baslik=baslik, an=SIMDI)
        bosluk.olcumu_yaz(yol, olcum)

    kayitlar = bosluk.bosluklar(yol)
    assert [k.baslik for k in kayitlar] == ["Bos_Konu", "Doymus_Konu"]
    assert kayitlar[0].skor > 0 > kayitlar[1].skor


def test_gecersiz_olcum_sona_gider(yol: Path, aday, bosluk_sayac):
    aday("Q1", "Iyi", okunma=200_000)
    aday("Q2", "Bozuk", okunma=900_000)

    bosluk.olcumu_yaz(
        yol,
        bosluk.sondala(
            SahteYT(
                arama=[("v1", "Iyi Konu", "k1")],
                izlenmeler={"v1": 900},
                yaslar={"v1": 2_000},
                aboneler={"k1": 400},
            ),
            bosluk_sayac,
            qid="Q1",
            dil="en",
            baslik="Iyi",
            an=SIMDI,
        ),
    )
    bosluk.olcumu_yaz(
        yol,
        bosluk.sondala(
            SahteYT(arama=[]), bosluk_sayac, qid="Q2", dil="en", baslik="Bozuk", an=SIMDI
        ),
    )

    kayitlar = bosluk.bosluklar(yol)
    assert [k.baslik for k in kayitlar] == ["Iyi", "Bozuk"]
    assert kayitlar[1].skor is None, "geçersiz ölçüm skorlanmamalı"


# --- CLI -----------------------------------------------------------------


def test_kuru_kosum_sondaj_sayisini_ve_maliyeti_bildirir(yol: Path, aday, monkeypatch, capsys):
    """Kabul ölçütü: kuru koşum sondaj sayısını ve maliyeti ÖNCEDEN bildirir."""
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    for i in range(3):
        aday(f"Q{i}", f"Konu_{i}", okunma=100_000 - i)

    assert cli.main(["bosluk", "arastir", "--kuru"]) == 0
    cikti = capsys.readouterr().out

    assert "3 aday hazır" in cikti
    assert "3 sondaj" in cikti
    assert "306 birim" in cikti, "3 × 102"
    assert f"{kota.video_basina_maliyet()} birim (dokunulmaz)" in cikti


def test_kuru_kosum_tavani_hesaba_katar(yol: Path, aday, monkeypatch, capsys):
    """ "10 istedim, 2 oldu" sürprizini koşum sırasında değil öncesinde görmeli."""
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    for i in range(10):
        aday(f"Q{i}", f"Konu_{i}", okunma=100_000 - i)
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO kota_harcama (gun, an, islem, birim, surec) VALUES (?, ?, ?, ?, ?)",
            (kota.kota_gunu(), SIMDI.isoformat(), "search.list", 2_800, bosluk.SUREC),
        )

    assert cli.main(["bosluk", "arastir", "--kuru", "--limit", "10"]) == 0
    cikti = capsys.readouterr().out

    assert "tavana 1 sondaj sığıyor → 1 sondaj" in cikti
    assert "102 birim" in cikti


def test_kuru_kosum_hic_cagri_yapmaz(yol: Path, aday, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    monkeypatch.setattr(
        cli, "_istemci_kur", lambda: pytest.fail("kuru koşumda istemci kurulmamalı")
    )
    aday("Q1", "Konu")

    assert cli.main(["bosluk", "arastir", "--kuru"]) == 0
    baglanti = depo.baglan(yol)
    try:
        assert baglanti.execute("SELECT COUNT(*) n FROM kota_harcama").fetchone()["n"] == 0
    finally:
        baglanti.close()


def test_cli_rapor_olcum_yoksa_uyarir(yol: Path, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    assert cli.main(["bosluk", "rapor"]) == 1
    assert "bosluk arastir" in capsys.readouterr().out


def test_cli_aday_yoksa_uyarir(yol: Path, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    assert cli.main(["bosluk", "arastir", "--kuru"]) == 1
    assert "konu topla" in capsys.readouterr().out
