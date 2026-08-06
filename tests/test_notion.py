"""Notion aktarımı — sahte HTTP, canlı çağrı yok."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yt_automation import cli, depo
from yt_automation.trend import bosluk, kaynak, notion

SIMDI = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class SahteNotion:
    """`notion._istek` yerine geçer; gönderilen gövdeleri toplar."""

    def __init__(
        self,
        *,
        hata: Exception | None = None,
        her_ikincisi: bool = False,
        mevcut_durum: str = "Yeni",
    ):
        self.govdeler: list[dict] = []
        self.cagrilar: list[tuple[str, str, dict]] = []
        self.hata = hata
        self.her_ikincisi = her_ikincisi
        self.mevcut_durum = mevcut_durum

    def __call__(self, yol: str, govde: dict, token: str, *, yontem: str = "POST") -> dict:
        self.govdeler.append(govde)
        self.cagrilar.append((yontem, yol, govde))
        if yontem == "GET":
            # Güncelleme yolu önce sayfayı okuyor; mevcut durum buradan gelir.
            return {"properties": {"Durum": {"select": {"name": self.mevcut_durum}}}}
        if self.hata and not self.her_ikincisi:
            raise self.hata
        if self.hata and len(self.govdeler) % 2 == 1:
            raise self.hata
        n = len(self.govdeler)
        # URL gerçek biçimde: sonda 32 hane hex kimlik. Sahte "sayfa-1" gibi
        # bir URL üretirse `sayfa_kimligi` onu reddeder ve güncelleme yolu
        # testte sessizce hiç çalışmaz.
        kimlik = f"{n:032x}"
        return {"url": f"https://notion.so/Sayfa-{kimlik}", "id": kimlik}


def govde_yazisi(bloklar: list[dict]) -> str:
    """Blokların düz metni — blok TİPİNDEN bağımsız.

    ⚠️ Testler önce `b["paragraph"]` diye sabit tipe bakıyordu ve gövdeye bir
    `heading_3` eklenince dördü birden `KeyError` verdi. Blok tipi bir sunum
    ayrıntısı; test metnin orada olup olmadığını doğrulamalı.
    """
    return " ".join(
        parca["text"]["content"] for blok in bloklar for parca in blok[blok["type"]]["rich_text"]
    )


@pytest.fixture
def olcum(yol: Path):
    """Trend ölçümü yazar — aktarımın girdisi."""

    def kur(
        video_id: str,
        *,
        izlenme: int = 100_000,
        sinif: str | None = "tarih",
        baslik: str | None = None,
        kosular: int = 3,
    ):
        with depo.yazma_islemi(yol) as baglanti:
            baglanti.execute(
                "INSERT OR REPLACE INTO video (video_id, baslik, kanal_adi, yayin_zamani, "
                "kategori_id, sinif, sinif_kaynagi, ilk_gorulme) "
                "VALUES (?, ?, ?, ?, 27, ?, 'llm', ?)",
                (
                    video_id,
                    baslik or f"Başlık {video_id}",
                    f"Kanal {video_id}",
                    (SIMDI - timedelta(hours=48)).isoformat(),
                    sinif,
                    (SIMDI - timedelta(hours=10)).isoformat(),
                ),
            )
            for i in range(kosular):
                baglanti.execute(
                    "INSERT OR REPLACE INTO olcum (video_id, bolge, an, sira, izlenme) "
                    "VALUES (?, 'TR', ?, 1, ?)",
                    (
                        video_id,
                        (SIMDI - timedelta(hours=(kosular - 1 - i) * 2)).isoformat(),
                        izlenme + i * izlenme // 10,
                    ),
                )

    return kur


# --- Aday seçimi ---------------------------------------------------------


def test_yalnizca_tarih_bilim_aktarilir(yol: Path, olcum):
    """Burası Ömer'in göreceği liste; `trend rapor`'un aksine filtre AÇIK."""
    olcum("tarih1", sinif="tarih", izlenme=100_000)
    olcum("bilim1", sinif="bilim", izlenme=90_000)
    olcum("magazin", sinif="diger", izlenme=900_000)
    olcum("bilinmez", sinif=None, izlenme=800_000)

    kimlikler = {s.video_id for s in notion.aktarilmamis_adaylar(yol)}
    assert kimlikler == {"tarih1", "bilim1"}


def test_ivmeye_gore_siralanir(yol: Path, olcum):
    olcum("yavas", izlenme=10_000)
    olcum("hizli", izlenme=500_000)
    adaylar = notion.aktarilmamis_adaylar(yol)
    assert adaylar[0].video_id == "hizli"


def test_adet_siniri(yol: Path, olcum):
    for i in range(5):
        olcum(f"v{i}", izlenme=10_000 * (i + 1))
    assert len(notion.aktarilmamis_adaylar(yol, adet=2)) == 2


# --- Tekrar yazmama ------------------------------------------------------


def test_aktarilan_aday_ikinci_kez_gonderilmez(yol: Path, olcum, monkeypatch):
    """Kabul ölçütü: aynı video iki kez yazılmıyor."""
    olcum("v1")
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)

    notion.aktar(yol, adaylar=notion.aktarilmamis_adaylar(yol), database="db", token="t", an=SIMDI)
    assert notion.aktarilmamis_adaylar(yol) == []

    ikinci = notion.aktar(
        yol, adaylar=notion.aktarilmamis_adaylar(yol), database="db", token="t", an=SIMDI
    )
    assert ikinci.yazilan == 0
    assert len(sahte.govdeler) == 1, "ikinci koşumda istek gitmemeli"


def test_zorla_tekrar_gonderir(yol: Path, olcum, monkeypatch):
    olcum("v1")
    monkeypatch.setattr(notion, "_istek", SahteNotion())
    notion.aktar(yol, adaylar=notion.aktarilmamis_adaylar(yol), database="db", token="t", an=SIMDI)
    assert [s.video_id for s in notion.aktarilmamis_adaylar(yol, zorla=True)] == ["v1"]


def test_basarisiz_aktarim_defterine_yazilmaz(yol: Path, olcum, monkeypatch):
    """Kayıt başarıdan SONRA yazılmalı.

    Önce yazılsa ve istek patlasa, aday bir daha hiç aktarılmaz ve kimse fark
    etmezdi — sessiz veri kaybı.
    """
    olcum("v1")
    monkeypatch.setattr(notion, "_istek", SahteNotion(hata=notion.NotionHatasi("500")))

    sonuc = notion.aktar(
        yol, adaylar=notion.aktarilmamis_adaylar(yol), database="db", token="t", an=SIMDI
    )
    assert sonuc.yazilan == 0
    assert len(sonuc.hatalar) == 1
    assert [s.video_id for s in notion.aktarilmamis_adaylar(yol)] == ["v1"], (
        "başarısız aday kuyrukta kalmalı"
    )


def test_bir_adayin_hatasi_aktarimi_bitirmez(yol: Path, olcum, monkeypatch):
    olcum("v1", izlenme=500_000)
    olcum("v2", izlenme=100_000)
    monkeypatch.setattr(
        notion, "_istek", SahteNotion(hata=notion.NotionHatasi("429"), her_ikincisi=True)
    )

    sonuc = notion.aktar(
        yol, adaylar=notion.aktarilmamis_adaylar(yol), database="db", token="t", an=SIMDI
    )
    assert sonuc.yazilan == 1
    assert len(sonuc.hatalar) == 1


# --- Gövde ve özellikler ------------------------------------------------


def test_ozellikler_notion_semasina_uyuyor(yol: Path, olcum, monkeypatch):
    olcum("v1", baslik="Cleopatra'nın Ölümü")
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)
    notion.aktar(
        yol, adaylar=notion.aktarilmamis_adaylar(yol), database="db-123", token="t", an=SIMDI
    )

    govde = sahte.govdeler[0]
    p = govde["properties"]
    assert govde["parent"] == {"database_id": "db-123"}
    assert p["Başlık"]["title"][0]["text"]["content"] == "Cleopatra'nın Ölümü"
    assert p["Bağlantı"]["url"] == "https://www.youtube.com/watch?v=v1"
    assert p["Kaynak"]["select"]["name"] == "youtube-chart"
    assert p["Sınıf"]["select"]["name"] == "tarih"
    assert p["Durum"]["select"]["name"] == "Yeni"
    assert p["Tespit tarihi"]["date"]["start"] == "2026-07-30"
    assert p["İzlenme"]["number"] > 0
    # JSON'a serileştirilebilmeli — aksi halde canlı çağrıda patlar.
    json.dumps(govde)


def test_hesaplanamayan_deger_sifir_yazilmaz(yol: Path, olcum, monkeypatch):
    """`None` ile `0` ayrımı Notion'a da taşınmalı: tek ölçümlü videonun hızı
    bilinmiyor, sıfır değil."""
    olcum("v1", kosular=1)
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)
    notion.aktar(
        yol,
        adaylar=notion.aktarilmamis_adaylar(yol, sirala="izlenme"),
        database="db",
        token="t",
        an=SIMDI,
    )

    p = sahte.govdeler[0]["properties"]
    assert p["Hız"]["number"] is None
    assert p["İvme"]["number"] is None


def test_govde_arz_uyarisini_tasiyor(yol: Path, olcum):
    """Bu bir TALEP sinyali. Uyarı olmadan Ömer doymuş bir nişe video üretir."""
    olcum("v1")
    sinyal = notion.aktarilmamis_adaylar(yol)[0]
    metin = govde_yazisi(notion.govde_metni(sinyal))
    assert "TALEP" in metin
    assert "bosluk rapor" in metin
    assert "v1" in metin, "video kimliği izlenebilirlik için gövdede olmalı"
    assert "**" not in metin and "`" not in metin, (
        "Notion markdown yorumlamıyor — işaretler ekranda literal görünür"
    )


def test_govde_ivme_yoksa_sebebini_yaziyor(yol: Path, olcum):
    olcum("v1", kosular=1)
    sinyal = notion.aktarilmamis_adaylar(yol, sirala="izlenme")[0]
    metin = govde_yazisi(notion.govde_metni(sinyal))
    assert "hesaplanamadı" in metin


def test_uzun_baslik_kirpilir(yol: Path, olcum):
    olcum("v1", baslik="A" * 3_000)
    sinyal = notion.aktarilmamis_adaylar(yol)[0]
    icerik = notion.ozellikler(sinyal, bolge=None, gun="2026-07-30")
    assert len(icerik["Başlık"]["title"][0]["text"]["content"]) == notion.BASLIK_SINIRI


# --- Sırlar --------------------------------------------------------------


def test_token_yoksa_anlasilir_hata(monkeypatch):
    monkeypatch.delenv(notion.TOKEN_DEGISKENI, raising=False)
    with pytest.raises(notion.NotionHatasi, match=notion.TOKEN_DEGISKENI):
        notion.token_al()


def test_database_yoksa_anlasilir_hata(monkeypatch):
    monkeypatch.delenv(notion.DATABASE_DEGISKENI, raising=False)
    with pytest.raises(notion.NotionHatasi, match=notion.DATABASE_DEGISKENI):
        notion.database_al()


# --- CLI -----------------------------------------------------------------


def test_kuru_kosum_yazmaz(yol: Path, olcum, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    monkeypatch.setattr(
        notion, "_istek", lambda *a, **k: pytest.fail("kuru koşumda istek gitmemeli")
    )
    monkeypatch.setattr(notion, "token_al", lambda: pytest.fail("kuru koşumda token istenmemeli"))
    olcum("v1")

    assert cli.main(["trend", "aktar", "--kuru", "--kaynak", "youtube-chart"]) == 0
    assert "KURU KOŞUM" in capsys.readouterr().out


def test_cli_aday_yoksa_sirayi_soyluyor(yol: Path, monkeypatch, capsys):
    """ "Aday yok" tek başına yetmez: hangi adımın eksik olduğu söylenmeli.

    Wikipedia yolunda üç adım var (topla → arastir → kaynak); hangisinde
    kaldığı belli olmazsa kullanıcı hepsini deneyerek bulmak zorunda kalır.
    """
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    assert cli.main(["trend", "aktar"]) == 1
    cikti = capsys.readouterr().out
    assert "konu topla" in cikti
    assert "bosluk arastir" in cikti
    assert "konu kaynak" in cikti
    assert "--zorla" in cikti

    assert cli.main(["trend", "aktar", "--kaynak", "youtube-chart"]) == 1
    cart = capsys.readouterr().out
    assert "trend topla" in cart
    assert "trend siniflandir" in cart


def test_cli_token_yoksa_hata_verir(yol: Path, olcum, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    monkeypatch.delenv(notion.TOKEN_DEGISKENI, raising=False)
    olcum("v1")

    assert cli.main(["trend", "aktar", "--kaynak", "youtube-chart"]) == 1
    assert notion.TOKEN_DEGISKENI in capsys.readouterr().err


# --- Wikipedia adayları: asıl devir noktası ------------------------------


@pytest.fixture
def wiki_aday(yol: Path):
    """`makale` + `okunma` + `arz` yazar; istenirse kaynak dosyası da."""

    def kur(
        qid: str,
        baslik: str,
        *,
        dil: str = "en",
        okunma: int = 100_000,
        sinif: str = "tarih",
        medyan_izlenme: int = 5_000,
        dosya: bool = False,
    ):
        with depo.yazma_islemi(yol) as baglanti:
            baglanti.execute(
                "INSERT OR REPLACE INTO makale (dil, baslik, qid, sinif, sinif_kaynagi, "
                "ilk_gorulme) VALUES (?, ?, ?, ?, 'wikidata', ?)",
                (dil, baslik, qid, sinif, SIMDI.isoformat()),
            )
            baglanti.execute(
                "INSERT OR REPLACE INTO okunma (dil, baslik, gun, okunma) "
                "VALUES (?, ?, '2026-07-28', ?)",
                (dil, baslik, okunma),
            )
            baglanti.execute(
                "INSERT OR REPLACE INTO arz (qid, dil, an, sorgu, donen, alakali, "
                "medyan_izlenme, medyan_yas_gun, medyan_abone, harcanan) "
                "VALUES (?, ?, ?, ?, 50, 10, ?, 900, 3000, 102)",
                (qid, dil, SIMDI.isoformat(), baslik.replace("_", " "), medyan_izlenme),
            )
            if dosya:
                for tur, deger, etiket in [
                    ("referans", "https://britishmuseum.org/x", None),
                    ("referans", "https://hathitrust.org/y", None),
                    ("olgu", "MÖ 69", "doğum tarihi"),
                    ("olgu", "İskenderiye", "doğum yeri"),
                ]:
                    baglanti.execute(
                        "INSERT OR REPLACE INTO kaynak (qid, tur, deger, etiket, cekilme) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (qid, tur, deger, etiket, SIMDI.isoformat()),
                    )
                baglanti.execute(
                    "INSERT OR REPLACE INTO kaynak (qid, tur, deger, atif, lisans, cekilme) "
                    "VALUES (?, 'gorsel', 'Kleopatra.jpg', 'Louvre', 'Public domain', ?)",
                    (qid, SIMDI.isoformat()),
                )

    return kur


@pytest.fixture
def pazar(wiki_aday):
    """Bir dilin tabanını kuran sıradan adaylar — kapının çalışması için şart.

    DW-51'den sonra `aktarilmamis_bosluklar` iki kapı uyguluyor ve göreli olan
    dilin **kendi dağılımını** istiyor. Tek aday yazan bir kurulum artık
    "taban güvenilmez" diye elenir; testin ölçmek istediği şey buysa değil.
    """

    def kur(dil: str = "en", *, izlenme: int = 400_000, okunma: int = 4_000, adet: int = 6):
        for i in range(adet):
            # İzlenme katlanarak artıyor: skor log ölçekte, sabit ekleme
            # sıfıra yakın bir MAD üretir ve her sapma devasa z verir.
            wiki_aday(
                f"TABAN{i}",
                f"{dil}_sirade_{i}",
                dil=dil,
                okunma=okunma,
                medyan_izlenme=izlenme * 2**i,
            )

    return kur


def test_bosluk_skoruna_gore_siralanir(yol: Path, wiki_aday):
    """Sıralama testi kapıyı bilerek atlıyor (`zorla`): ölçtüğü şey sıra."""
    wiki_aday("Q1", "Doymus", medyan_izlenme=2_000_000)
    wiki_aday("Q2", "Bos", medyan_izlenme=800)
    kayitlar = notion.aktarilmamis_bosluklar(yol, zorla=True)
    assert [k.baslik for k in kayitlar] == ["Bos", "Doymus"]


def test_wiki_ozellikleri_semaya_uyuyor(yol: Path, wiki_aday, monkeypatch):
    wiki_aday("Q1", "Great_Zimbabwe", dil="en", okunma=27_301, dosya=True)
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)
    notion.bosluklari_aktar(
        yol,
        # Ölçtüğü şey Notion yükünün şekli, kapı değil.
        adaylar=notion.aktarilmamis_bosluklar(yol, zorla=True),
        database="db",
        token="t",
        an=SIMDI,
    )

    p = sahte.govdeler[0]["properties"]
    assert p["Başlık"]["title"][0]["text"]["content"] == "Great Zimbabwe"
    assert p["Kaynak"]["select"]["name"] == "wikipedia"
    assert p["Bağlantı"]["url"] == "https://en.wikipedia.org/wiki/Great_Zimbabwe"
    assert p["Talep (okunma)"]["number"] == 27_301
    assert p["Kaynak sayısı"]["number"] == 5, "2 referans + 2 olgu + 1 görsel"
    assert p["Boşluk skoru"]["number"] is not None
    json.dumps(sahte.govdeler[0])


def test_wiki_govdesi_kaynak_dosyasini_tasiyor(yol: Path, wiki_aday):
    """Kabul ölçütü: Ömer içerik üretimine başlayabilecek kadar bağlam buluyor."""
    wiki_aday("Q1", "Cleopatra", dosya=True)
    kayit = notion.aktarilmamis_bosluklar(yol, zorla=True)[0]
    metin = govde_yazisi(notion.bosluk_govdesi(kayit, kaynak.dosyayi_oku(yol, "Q1")))

    assert "TALEP" in metin and "ARZ" in metin and "BOŞLUK SKORU" in metin
    assert "doğum tarihi: MÖ 69" in metin
    assert "britishmuseum" in metin
    assert "Public domain" in metin, "görselin lisansı olmadan kullanılamaz"
    assert "PAZAR BÜYÜKLÜĞÜNÜ" in metin, "diller arası kıyas uyarısı taşınmalı"
    assert "YAYIN SONUÇLARINDAN DEĞİL" in metin, "eşiklerin geçiciliği taşınmalı"
    assert "**" not in metin and "`" not in metin, (
        "Notion markdown yorumlamıyor — işaretler ekranda literal görünür"
    )


def test_kaynaksiz_aday_acikca_uyariyor(yol: Path, wiki_aday):
    """`dosyayi_oku` boşken de üç boş liste döndürüyor — `if dosya:` her zaman doğru.

    Bu ayrımı kaçırmak "kaynak dosyası yok" uyarısını sessizce yok eder ve
    kaynaksız bir konunun videoya dönmesinin önündeki tek engel o uyarı.
    """
    wiki_aday("Q1", "Kaynaksiz", dosya=False)
    dosya = kaynak.dosyayi_oku(yol, "Q1")
    assert dosya, "sözlük boş değil, listeleri boş"
    assert notion.dosya_dolu(dosya) is False

    kayit = notion.aktarilmamis_bosluklar(yol, zorla=True)[0]
    metin = govde_yazisi(notion.bosluk_govdesi(kayit, dosya))
    assert "videoya dönüşmemeli" in metin


def test_wiki_adayi_ikinci_kez_gonderilmez(yol: Path, wiki_aday, pazar, monkeypatch):
    pazar()
    wiki_aday("Q1", "Cleopatra", okunma=8_000, medyan_izlenme=35_000)
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)

    notion.bosluklari_aktar(
        yol, adaylar=notion.aktarilmamis_bosluklar(yol), database="db", token="t", an=SIMDI
    )
    assert notion.aktarilmamis_bosluklar(yol) == []
    assert len(sahte.govdeler) == 1


def test_wiki_ve_video_defterleri_carpismaz(yol: Path, wiki_aday, olcum, monkeypatch):
    """İkisi aynı `aktarim` tablosunu paylaşıyor; anahtarlar çakışmamalı."""
    wiki_aday("Q1", "Cleopatra")
    olcum("v1")
    monkeypatch.setattr(notion, "_istek", SahteNotion())

    notion.bosluklari_aktar(
        yol, adaylar=notion.aktarilmamis_bosluklar(yol), database="db", token="t", an=SIMDI
    )
    assert len(notion.aktarilmamis_adaylar(yol)) == 1, "video adayı etkilenmemeli"

    notion.aktar(yol, adaylar=notion.aktarilmamis_adaylar(yol), database="db", token="t", an=SIMDI)
    assert notion.aktarilmamis_bosluklar(yol) == []
    assert notion.aktarilmamis_adaylar(yol) == []


def test_cli_varsayilan_kaynak_wikipedia(yol: Path, wiki_aday, pazar, olcum, monkeypatch, capsys):
    """Çartta tarih/bilim olmadığı ölçüldü; varsayılan yol Wikipedia olmalı."""
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    pazar()
    wiki_aday("Q1", "Cleopatra", okunma=8_000, medyan_izlenme=35_000)
    olcum("v1")

    assert cli.main(["trend", "aktar", "--kuru"]) == 0
    cikti = capsys.readouterr().out
    assert "kaynak: wikipedia" in cikti
    assert "Cleopatra" in cikti


def test_cli_cart_kaynagi_secilebilir(yol: Path, olcum, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    olcum("v1")
    assert cli.main(["trend", "aktar", "--kuru", "--kaynak", "youtube-chart"]) == 0
    assert "kaynak: youtube-chart" in capsys.readouterr().out


def test_govde_gecen_formati_ve_kendi_kalibresini_gosterir(yol: Path, wiki_aday, pazar):
    """Kapı format başına çalışıyor (DW-58): aday BİRLEŞİK kalibresi eşiğin
    altındayken de geçmiş olabilir — tek formatta parlıyorsa.

    Yalnızca birleşik değeri göstermek operatöre eşiğin altında bir sayı
    gösterip "bu aday neden burada?" dedirtirdi. Bu test o sapmayı kilitliyor.
    """
    from yt_automation.trend import bosluk

    # Format tabanı: her iki rafta da orta yoğun altı aday.
    for i in range(6):
        wiki_aday(f"T{i}", f"taban_{i}", okunma=40_000)
        _kirilim_yaz(yol, f"T{i}", shorts_izlenme=200_000 * 2**i, uzun_izlenme=100_000 * 2**i)
    wiki_aday("FIRSAT", "Shortsta_Bos", okunma=9_000)
    _kirilim_yaz(yol, "FIRSAT", shorts_izlenme=400, shorts_alakali=2, uzun_izlenme=900_000)

    kayit = next(k for k in bosluk.bosluklar(yol) if k.qid == "FIRSAT")
    metin = govde_yazisi(notion.bosluk_govdesi(kayit, kaynak.dosyayi_oku(yol, "FIRSAT")))

    assert "FORMAT BAŞINA" in metin
    assert "Shorts formatında eşiği geçti" in metin
    assert "kendi taban çizgisine" in metin


def _kirilim_yaz(yol: Path, qid: str, *, shorts_izlenme, uzun_izlenme, shorts_alakali=20):
    from yt_automation.trend import bosluk

    bosluk.olcumu_yaz(
        yol,
        bosluk.ArzOlcumu(
            qid=qid,
            dil="en",
            sorgu="x",
            an=SIMDI.isoformat(),
            donen=50,
            alakali=shorts_alakali + 20,
            medyan_izlenme=(shorts_izlenme + uzun_izlenme) // 2,
            medyan_yas_gun=300,
            medyan_abone=5_000,
            harcanan=102,
            alakali_shorts=shorts_alakali,
            medyan_izlenme_shorts=shorts_izlenme,
            alakali_uzun=20,
            medyan_izlenme_uzun=uzun_izlenme,
        ),
    )


# --- Mevcut sayfaların güncellenmesi (format geri doldurma) -----------------
#
# `Önerilen format` DW-58'de eklendi; ondan önce yazılmış sayfalarda alan boş.
# Aktarım tek yönlü ve bir kez çalıştığı için sayfa kendiliğinden düzelmiyor.


def test_sayfa_kimligi_urlden_okunur():
    url = "https://app.notion.com/p/Lise-Les-vre-3b29bfc93b2e8118bf7fc314cacdee57"
    assert notion.sayfa_kimligi(url) == "3b29bfc93b2e8118bf7fc314cacdee57"


def test_bozuk_url_kimlik_uretmez():
    """Uydurulmuş kimliğe PATCH atmak **başka** bir sayfayı bozar."""
    assert notion.sayfa_kimligi("https://app.notion.com/p/Baslik") is None
    assert notion.sayfa_kimligi("") is None


def _aktarilmis_kur(yol: Path, wiki_aday, pazar, monkeypatch) -> SahteNotion:
    """Bir aday yazılmış hâle getirilir; dönen sahte sonraki testte kullanılır."""
    pazar()
    wiki_aday("FIRSAT", "Firsat", medyan_izlenme=900, okunma=9_000)
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)
    notion.bosluklari_aktar(
        yol,
        adaylar=notion.aktarilmamis_bosluklar(yol, zorla=True),
        database="db",
        token="t",
        an=SIMDI,
    )
    return sahte


def test_guncelleme_format_alanini_yazar(yol: Path, wiki_aday, pazar, monkeypatch):
    _aktarilmis_kur(yol, wiki_aday, pazar, monkeypatch)
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)

    sonuc = notion.bosluklari_guncelle(yol, adaylar=bosluk.bosluklar(yol), token="t", bekleme=0)

    assert sonuc.guncellenen > 0
    yamalar = [g for y, _, g in sahte.cagrilar if y == "PATCH"]
    assert yamalar, "PATCH isteği gitmeli"
    assert "Önerilen format" in yamalar[0]["properties"]
    assert "Hedef kanal" in yamalar[0]["properties"]


def test_guncelleme_govdeyi_yeniden_yazmaz(yol: Path, wiki_aday, pazar, monkeypatch):
    """Gövde güncellemesi insanın sayfaya eklediği notları siler — dokunulmuyor."""
    _aktarilmis_kur(yol, wiki_aday, pazar, monkeypatch)
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)

    notion.bosluklari_guncelle(yol, adaylar=bosluk.bosluklar(yol), token="t", bekleme=0)

    for yontem, _, govde in sahte.cagrilar:
        if yontem == "PATCH":
            assert "children" not in govde


def test_kapiyi_gecemeyen_elendi_olur(yol: Path, wiki_aday, pazar, monkeypatch):
    _aktarilmis_kur(yol, wiki_aday, pazar, monkeypatch)
    # Taban adayları kapıyı geçmiyor; `--ele` onları Elendi'ye çekmeli.
    sahte = SahteNotion(mevcut_durum="Yeni")
    monkeypatch.setattr(notion, "_istek", sahte)

    sonuc = notion.bosluklari_guncelle(
        yol, adaylar=bosluk.bosluklar(yol), token="t", ele=True, bekleme=0
    )

    assert sonuc.elendi > 0
    durumlar = [
        g["properties"]["Durum"]["select"]["name"]
        for y, _, g in sahte.cagrilar
        if y == "PATCH" and "Durum" in g["properties"]
    ]
    assert durumlar and all(d == notion.ELENDI_DURUMU for d in durumlar)


def test_insanin_elledigi_satir_elenmez(yol: Path, wiki_aday, pazar, monkeypatch):
    """`Seçildi` yapılmış bir adayı otomasyon `Elendi`ye çekerse kararı ezer."""
    _aktarilmis_kur(yol, wiki_aday, pazar, monkeypatch)
    sahte = SahteNotion(mevcut_durum="Seçildi")
    monkeypatch.setattr(notion, "_istek", sahte)

    sonuc = notion.bosluklari_guncelle(
        yol, adaylar=bosluk.bosluklar(yol), token="t", ele=True, bekleme=0
    )

    assert sonuc.elendi == 0
    for yontem, _, govde in sahte.cagrilar:
        if yontem == "PATCH":
            assert "Durum" not in govde["properties"]


def test_yazilmamis_aday_atlanir(yol: Path, wiki_aday, pazar, monkeypatch):
    """Notion'a hiç gitmemiş adaya PATCH atılamaz — sayfası yok."""
    pazar()
    wiki_aday("YENI", "Hic_Gitmedi", medyan_izlenme=900, okunma=9_000)
    sahte = SahteNotion()
    monkeypatch.setattr(notion, "_istek", sahte)

    sonuc = notion.bosluklari_guncelle(yol, adaylar=bosluk.bosluklar(yol), token="t", bekleme=0)

    assert sonuc.guncellenen == 0
    assert sonuc.sayfasiz > 0
    assert sahte.cagrilar == []


def test_elenen_adaya_kanal_atanmaz(yol: Path, wiki_aday, pazar):
    """Geçen formatı olsa bile kapıyı geçemeyen adaya kanal yazılmamalı.

    Ölçüldü (2026-08-04): geçen formatı olan 8 adayın 5'i mutlak talep
    kapısında eleniyordu ve yine de `Hedef kanal` alıyordu. Kanal ataması bir
    karar; elenmiş adaya karar yazmak o kararı uydurmaktır. Aktarım yolunda
    görünmüyordu çünkü oraya yalnızca kapıyı geçen aday giriyor — kusur
    `bosluklari_guncelle` elenmişlere de dokununca ortaya çıktı.
    """
    pazar()
    # Talebi eşiğin altında ama arzı bomboş: format kalibresi yüksek çıkar,
    # mutlak talep kapısı yine de eler.
    wiki_aday("ZAYIF", "Talebi_Dusuk", medyan_izlenme=50, okunma=100)
    kayit = next(k for k in bosluk.bosluklar(yol) if k.qid == "ZAYIF")

    assert bosluk.red_gerekcesi(kayit) is not None, "kurulum: aday elenmiş olmalı"
    p = notion.bosluk_ozellikleri(kayit, gun="2026-08-04", kaynak_sayisi=3)
    assert p["Hedef kanal"]["select"] is None
    # Öneri alanı yine dolu: sıralama bilgisi taşıyor, karar taşımıyor.
    assert p["Önerilen format"]["select"]["name"]


def test_copteki_sayfa_guncellenmez(yol: Path, wiki_aday, pazar, monkeypatch):
    """Silinmiş sayfaya PATCH atmak sessiz kayıp — sayılıp raporlanmalı.

    Gerçek vaka (2026-08-04): mükerrer bir sayfa elle silindi ve defter
    silineni gösteriyordu. Kontrol olmadan istek başarılı döner, kimse
    görmez, görünen sayfa bir daha hiç güncellenmezdi.
    """
    _aktarilmis_kur(yol, wiki_aday, pazar, monkeypatch)

    class CopteSahte(SahteNotion):
        def __call__(self, yol_, govde, token, *, yontem="POST"):
            if yontem == "GET":
                self.cagrilar.append((yontem, yol_, govde))
                return {"in_trash": True, "archived": True, "properties": {}}
            return super().__call__(yol_, govde, token, yontem=yontem)

    sahte = CopteSahte()
    monkeypatch.setattr(notion, "_istek", sahte)

    sonuc = notion.bosluklari_guncelle(yol, adaylar=bosluk.bosluklar(yol), token="t", bekleme=0)

    assert sonuc.copte > 0
    assert sonuc.guncellenen == 0
    assert not [y for y, _, _ in sahte.cagrilar if y == "PATCH"], "çöpteki sayfaya yazılmamalı"


# --- Köprünün tüketici ucu (DW-80, ADR-0013) -----------------------------
#
# Kendi test ikizini kullanıyor, `SahteNotion`'ı genişletmiyor. Sebep: oradaki
# ikiz **yazma** yoluna göre şekillenmiş ve GET'te yalnızca `Durum` döndürüyor.
# Tüketici tarafı sayfanın tamamını (id, url, özellikler) okuyor; ikizi ikisine
# birden uydurmak, yirmi mevcut testin dayandığı davranışı da riske atardı.

SAYFA_KIMLIGI = "3b29bfc93b2e814d9886de876f5b3da4"


def _sahte_sayfa(
    *,
    kimlik: str = SAYFA_KIMLIGI,
    durum: str = "Yeni",
    baslik: str = "Fritz Gerlich",
    format_adi: str = "Shorts",
    skor: float | None = 0.32,
    copte: bool = False,
) -> dict:
    return {
        "id": kimlik,
        "url": f"https://app.notion.com/p/Baslik-{kimlik}",
        "in_trash": copte,
        "archived": copte,
        "properties": {
            "Başlık": {"title": [{"plain_text": baslik}]},
            "Durum": {"select": {"name": durum}},
            "Önerilen format": {"select": {"name": format_adi}},
            "Hedef kanal": {"select": {"name": "Shorts kanal"}},
            "Sınıf": {"select": {"name": "tarih"}},
            "Dil": {"rich_text": [{"plain_text": "es"}]},
            "Boşluk skoru": {"number": skor},
            "Talep (okunma)": {"number": 7132},
            "Bağlantı": {"url": "https://es.wikipedia.org/wiki/Fritz_Gerlich"},
        },
    }


class SahteKopru:
    """Tüketici yolunun `notion._istek` ikizi — çağrıları biriktirir."""

    def __init__(self, *, sayfa: dict | None = None, sonuclar: list[dict] | None = None):
        self.sayfa = sayfa if sayfa is not None else _sahte_sayfa()
        self.sonuclar = sonuclar if sonuclar is not None else [_sahte_sayfa()]
        self.cagrilar: list[tuple[str, str, dict | None]] = []

    def __call__(self, yol: str, govde: dict | None, token: str, *, yontem: str = "POST") -> dict:
        self.cagrilar.append((yontem, yol, govde))
        if yontem == "GET":
            return self.sayfa
        if yol.endswith("/query"):
            return {"results": self.sonuclar}
        return self.sayfa

    @property
    def patchler(self) -> list[dict]:
        return [g for y, _, g in self.cagrilar if y == "PATCH" and g]


@pytest.fixture
def kopru(monkeypatch):
    monkeypatch.setenv(notion.TOKEN_DEGISKENI, "t")
    monkeypatch.setenv(notion.DATABASE_DEGISKENI, "db")

    def kur(**kwargs):
        sahte = SahteKopru(**kwargs)
        monkeypatch.setattr(notion, "_istek", sahte)
        monkeypatch.setattr(notion.time, "sleep", lambda _: None)
        return sahte

    return kur


def test_adaylari_getir_durum_suzuyor_ve_skora_gore_siraliyor(kopru):
    sahte = kopru()
    notion.adaylari_getir(token="t")

    _, yol, govde = sahte.cagrilar[0]
    assert yol.endswith("/query")
    assert govde["filter"] == {"property": "Durum", "select": {"equals": "Yeni"}}
    assert govde["sorts"] == [{"property": "Boşluk skoru", "direction": "descending"}]


def test_adaylari_getir_format_suzgeci_ekliyor(kopru):
    sahte = kopru()
    notion.adaylari_getir(token="t", format_adi="shorts")

    filtre = sahte.cagrilar[0][2]["filter"]
    assert filtre["and"][1] == {"property": "Önerilen format", "select": {"equals": "Shorts"}}


def test_bilinmeyen_format_erken_hata(kopru):
    kopru()
    with pytest.raises(notion.NotionHatasi, match="bilinmeyen format"):
        notion.adaylari_getir(token="t", format_adi="dikey")


def test_adaylari_getir_alanlari_cozuyor(kopru):
    kopru()
    (aday,) = notion.adaylari_getir(token="t")

    assert aday.kimlik == SAYFA_KIMLIGI
    assert aday.baslik == "Fritz Gerlich"
    assert aday.durum == "Yeni"
    assert aday.onerilen_format == "Shorts"
    assert aday.bosluk_skoru == 0.32
    assert aday.sozluk()["baglanti"].endswith("Fritz_Gerlich")


def test_sec_yalnizca_durum_yaziyor(kopru):
    """ADR-0011'in salt-okuma sütunu kodla zorlanıyor.

    Bu testin asıl işi bir alanın varlığını değil, **yokluğunu** sınamak:
    ölçüm alanlarından biri gövdeye sızarsa video hattı trend hattının
    ölçümünü ezebilir hale gelir ve bunu kimse fark etmez.
    """
    sahte = kopru()
    notion.adayi_sec(SAYFA_KIMLIGI, token="t")

    (govde,) = sahte.patchler
    assert govde["properties"] == {"Durum": {"select": {"name": "Seçildi"}}}
    for olcum_alani in ("Hız", "İvme", "Boşluk skoru", "Talep (okunma)", "Arz", "Sınıf"):
        assert olcum_alani not in govde["properties"]


@pytest.mark.parametrize("durum", ["Seçildi", "Üretildi", "Elendi", "İnceleniyor"])
def test_sec_beklenmeyen_durumda_yazmiyor(kopru, durum):
    """Çift-kapma yarışı ve insan kararı aynı kontrolle korunuyor."""
    sahte = kopru(sayfa=_sahte_sayfa(durum=durum))

    with pytest.raises(notion.NotionHatasi, match="ezmek yerine durduruldu"):
        notion.adayi_sec(SAYFA_KIMLIGI, token="t")

    assert not sahte.patchler, "beklenmeyen durumda PATCH atılmamalı"


def test_copteki_sayfaya_yazilmiyor(kopru):
    """PATCH başarılı döner ve hiçbir yerde görünmez — 2026-08-04'te ölçüldü."""
    sahte = kopru(sayfa=_sahte_sayfa(copte=True))

    with pytest.raises(notion.NotionHatasi, match="çöpte"):
        notion.adayi_sec(SAYFA_KIMLIGI, token="t")

    assert not sahte.patchler


def test_kuru_kosum_hic_patch_atmiyor(kopru):
    sahte = kopru()
    aday = notion.adayi_sec(SAYFA_KIMLIGI, token="t", kuru=True)

    assert aday.durum == "Yeni"
    assert not sahte.patchler
    assert [y for y, _, _ in sahte.cagrilar] == ["GET"]


def test_bitir_durum_video_ve_notu_yaziyor(kopru):
    sahte = kopru(sayfa=_sahte_sayfa(durum="Seçildi"))
    notion.adayi_bitir(
        SAYFA_KIMLIGI, token="t", video_url="https://youtu.be/abc", uretim_notu="ilk tur"
    )

    (govde,) = sahte.patchler
    ozellikler = govde["properties"]
    assert ozellikler["Durum"] == {"select": {"name": "Üretildi"}}
    assert ozellikler["Video URL"] == {"url": "https://youtu.be/abc"}
    assert "ilk tur" in ozellikler["Üretim notu"]["rich_text"][0]["text"]["content"]
    assert set(ozellikler) == {"Durum", "Video URL", "Üretim notu"}


@pytest.mark.parametrize("durum", ["Seçildi", "Üretiliyor"])
def test_bitir_iki_durumdan_da_kabul_ediyor(kopru, durum):
    """Üretici `Üretiliyor` adımını işaretlemiş de olabilir, atlamış da."""
    sahte = kopru(sayfa=_sahte_sayfa(durum=durum))
    notion.adayi_bitir(SAYFA_KIMLIGI, token="t", video_url="https://youtu.be/abc")

    assert len(sahte.patchler) == 1


def test_bitir_kapilmamis_adayi_reddediyor(kopru):
    """`Yeni` → `Üretildi` atlaması iki hattın aynı konuyu üretmesi demek."""
    sahte = kopru(sayfa=_sahte_sayfa(durum="Yeni"))

    with pytest.raises(notion.NotionHatasi):
        notion.adayi_bitir(SAYFA_KIMLIGI, token="t", video_url="https://youtu.be/abc")

    assert not sahte.patchler


def test_bitir_bos_video_url_reddediyor(kopru):
    """Bağlantısız `Üretildi` köprünün geri dönüş yolunu koparır."""
    sahte = kopru(sayfa=_sahte_sayfa(durum="Seçildi"))

    with pytest.raises(notion.NotionHatasi, match="video_url boş"):
        notion.adayi_bitir(SAYFA_KIMLIGI, token="t", video_url="   ")

    assert not sahte.cagrilar, "doğrulama ağ çağrısından ÖNCE olmalı"


def test_cli_json_cikti_semasi(kopru, capsys):
    kopru()
    assert cli.main(["aday", "listele", "--json"]) == 0

    kayitlar = json.loads(capsys.readouterr().out)
    assert [k["kimlik"] for k in kayitlar] == [SAYFA_KIMLIGI]
    assert set(kayitlar[0]) == {
        "kimlik",
        "baslik",
        "sayfa_url",
        "durum",
        "onerilen_format",
        "hedef_kanal",
        "sinif",
        "dil",
        "bosluk_skoru",
        "talep",
        "baglanti",
    }


def test_cli_aday_yoksa_sifirdan_farkli_donuyor(kopru, capsys):
    """`gunluk-huni.sh` çıkış koduna bakıyor; boş liste sessiz başarı olmamalı."""
    kopru(sonuclar=[])
    assert cli.main(["aday", "listele"]) == 1
    assert "aday yok" in capsys.readouterr().out


def test_cli_url_ve_ciplak_kimlik_ayni_sayfaya_gidiyor(kopru):
    for hedef in (
        f"https://app.notion.com/p/Fritz-Gerlich-{SAYFA_KIMLIGI}",
        SAYFA_KIMLIGI,
        "3b29bfc9-3b2e-814d-9886-de876f5b3da4",
    ):
        sahte = kopru()
        assert cli.main(["aday", "sec", hedef]) == 0
        assert sahte.cagrilar[0][1] == f"/pages/{SAYFA_KIMLIGI}"


def test_cli_bozuk_kimlikte_ag_cagrisi_yapmiyor(kopru, capsys):
    sahte = kopru()
    assert cli.main(["aday", "sec", "bu-bir-kimlik-degil"]) == 1
    assert not sahte.cagrilar
    assert "sayfa kimliği okunamadı" in capsys.readouterr().err


def test_aday_listele_secildi_kuyrugunu_okuyor(kopru, capsys, monkeypatch):
    """Telefondan tetikleme bu kuyruğa dayanıyor (DW-87).

    İnsan Notion mobilden bir adayı `Seçildi` yapıyor; Mac'teki koşum burayı
    sorgulayıp üretimi başlatıyor. Bu kuyruk okunamazsa telefon kumandası
    sessizce çalışmaz — hiçbir hata vermeden hiçbir şey üretilmez.
    """
    sahte = kopru()
    monkeypatch.setenv("NOTION_TOKEN", "t")

    cli.main(["aday", "listele", "--durum", notion.SECILDI_DURUMU, "--json"])

    _, _, govde = sahte.cagrilar[0]
    assert govde["filter"] == {
        "property": "Durum",
        "select": {"equals": notion.SECILDI_DURUMU},
    }
    capsys.readouterr()


def test_aday_listele_varsayilan_yeni_kaliyor(kopru, capsys, monkeypatch):
    """`--durum` verilmezse davranış değişmemeli — mevcut tüketiciler kırılmasın."""
    sahte = kopru()
    monkeypatch.setenv("NOTION_TOKEN", "t")

    cli.main(["aday", "listele", "--json"])

    _, _, govde = sahte.cagrilar[0]
    assert govde["filter"]["select"]["equals"] == notion.DOKUNULMAMIS_DURUM
    capsys.readouterr()
