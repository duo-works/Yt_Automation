"""Niş kanal izleme — taban çizgisi, aşırı performans ve kota koruması."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yt_automation import cli, depo, kota
from yt_automation.trend import hiz, nis

SIMDI = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


class SahteYT:
    """`channels`/`playlistItems`/`videos` zincirlerini taklit eder.

    `kanallar`: `handle → (kanal_id, ad, abone)`; handle yoksa boş yanıt.
    `listeler`: `liste_id → [video_id, …]`.
    `videolar`: `video_id → (baslik, kanal_id, izlenme, yas_gun)`.
    """

    def __init__(self, *, kanallar=None, listeler=None, videolar=None, hatalar=None):
        self.kanallar = kanallar or {}
        self.listeler = listeler or {}
        self.videolar = videolar or {}
        self.hatalar = hatalar or {}
        self.cagrilar: list[str] = []
        self._tur = ""
        self._p: dict = {}

    def channels(self):
        self._tur = "channels"
        return self

    def playlistItems(self):  # noqa: N802 — API adını birebir taklit ediyor
        self._tur = "playlistItems"
        return self

    def videos(self):
        self._tur = "videos"
        return self

    def list(self, **p):
        self._p = p
        return self

    def execute(self):
        self.cagrilar.append(self._tur)
        if self._tur in self.hatalar:
            raise self.hatalar[self._tur]
        if self._tur == "channels":
            handle = self._p["forHandle"]
            if handle not in self.kanallar:
                return {"items": []}
            kanal_id, ad, abone = self.kanallar[handle]
            return {
                "items": [
                    {
                        "id": kanal_id,
                        "snippet": {"title": ad},
                        "contentDetails": {
                            "relatedPlaylists": {"uploads": kanal_id.replace("UC", "UU", 1)}
                        },
                        "statistics": {
                            "subscriberCount": str(abone),
                            "hiddenSubscriberCount": False,
                            "videoCount": "100",
                        },
                    }
                ]
            }
        if self._tur == "playlistItems":
            return {
                "items": [
                    {"contentDetails": {"videoId": vid}}
                    for vid in self.listeler.get(self._p["playlistId"], [])
                ]
            }
        istenen = self._p["id"].split(",")
        ogeler = []
        for vid in istenen:
            if vid not in self.videolar:
                continue
            baslik, kanal_id, izlenme, yas = self.videolar[vid]
            ogeler.append(
                {
                    "id": vid,
                    "snippet": {
                        "title": baslik,
                        "channelId": kanal_id,
                        "channelTitle": f"Kanal {kanal_id}",
                        "publishedAt": (SIMDI - timedelta(days=yas)).isoformat(),
                        "categoryId": "27",
                    },
                    "statistics": {"viewCount": str(izlenme)},
                    "contentDetails": {"duration": "PT12M"},
                }
            )
        return {"items": ogeler}


@pytest.fixture
def nis_sayac(yol: Path) -> kota.KaliciSayac:
    return kota.KaliciSayac(yol, surec=nis.SUREC)


@pytest.fixture
def kanal_kur(yol: Path):
    """`nis_kanal` satırı yazar — çözüm adımını atlamak için."""

    def kur(kanal_id: str, *, handle: str | None = None, ad: str = "Kanal", abone: int = 100_000):
        with depo.yazma_islemi(yol) as baglanti:
            baglanti.execute(
                "INSERT OR REPLACE INTO nis_kanal (kanal_id, handle, ad, sinif, "
                "yukleme_listesi, abone, guncelleme) VALUES (?, ?, ?, 'tarih', ?, ?, ?)",
                (
                    kanal_id,
                    handle or f"@{kanal_id}",
                    ad,
                    kanal_id.replace("UC", "UU", 1),
                    abone,
                    SIMDI.isoformat(),
                ),
            )

    return kur


@pytest.fixture
def olcum_kur(yol: Path):
    """Doğrudan `video` + `nis_olcum` yazar — API'den geçmeden."""

    def kur(video_id: str, kanal_id: str, *, izlenme: int, yas_gun: float, baslik: str = ""):
        with depo.yazma_islemi(yol) as baglanti:
            baglanti.execute(
                "INSERT OR REPLACE INTO video (video_id, baslik, kanal_id, kanal_adi, "
                "yayin_zamani, ilk_gorulme) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    video_id,
                    baslik or f"Başlık {video_id}",
                    kanal_id,
                    f"Kanal {kanal_id}",
                    (SIMDI - timedelta(days=yas_gun)).isoformat(),
                    SIMDI.isoformat(),
                ),
            )
            baglanti.execute(
                "INSERT OR REPLACE INTO nis_olcum (video_id, kanal_id, an, izlenme) "
                "VALUES (?, ?, ?, ?)",
                (video_id, kanal_id, SIMDI.isoformat(), izlenme),
            )

    return kur


# --- Kimlik çözümü -------------------------------------------------------


def test_handle_kimlige_cozulur(yol: Path, nis_sayac):
    istemci = SahteYT(
        kanallar={"@kurzgesagt": ("UCsXVk37bltHxD1rDPwtNM8Q", "Kurzgesagt", 24_000_000)}
    )
    sonuc = nis.kanallari_coz(istemci, nis_sayac, yol, kanallar=(("@kurzgesagt", "bilim"),))

    assert sonuc.cozulen == 1
    assert sonuc.harcanan == 1, "channels.list 1 birim"
    baglanti = depo.baglan(yol)
    try:
        satir = baglanti.execute("SELECT * FROM nis_kanal").fetchone()
    finally:
        baglanti.close()
    assert satir["kanal_id"] == "UCsXVk37bltHxD1rDPwtNM8Q"
    assert satir["yukleme_listesi"] == "UUsXVk37bltHxD1rDPwtNM8Q"
    assert satir["abone"] == 24_000_000


def test_kayitli_handle_tekrar_sorulmaz(yol: Path, nis_sayac, kanal_kur):
    """Tekrarlanan koşum bedava olmalı — kimlik değişmiyor."""
    kanal_kur("UC1", handle="@zaten")
    istemci = SahteYT(kanallar={"@zaten": ("UC1", "Zaten", 1_000)})
    sonuc = nis.kanallari_coz(istemci, nis_sayac, yol, kanallar=(("@zaten", "tarih"),))

    assert sonuc.zaten_vardi == 1
    assert sonuc.harcanan == 0
    assert istemci.cagrilar == []


def test_bulunamayan_handle_digerlerini_dusurmez(yol: Path, nis_sayac):
    """Handle yanlışsa açık hata; sessiz bozulma yok."""
    istemci = SahteYT(kanallar={"@var": ("UC1", "Var", 1_000)})
    sonuc = nis.kanallari_coz(
        istemci, nis_sayac, yol, kanallar=(("@yok", "tarih"), ("@var", "bilim"))
    )

    assert sonuc.cozulen == 1
    assert sonuc.bulunamayan == ["@yok"]
    assert sonuc.harcanan == 2, "bulunamayan handle da birim harcar"


def test_katalogdaki_handleler_tekil(yol: Path):
    handleler = [h for h, _ in nis.IZLENEN_KANALLAR]
    assert len(handleler) == len(set(handleler)), "aynı kanal iki kez izlenmemeli"


# --- İzleme --------------------------------------------------------------


def test_kanal_basina_iki_birim(yol: Path, nis_sayac, kanal_kur):
    kanal_kur("UC1")
    istemci = SahteYT(
        listeler={"UU1": ["v1", "v2"]},
        videolar={"v1": ("A", "UC1", 5_000, 60), "v2": ("B", "UC1", 8_000, 90)},
    )
    sonuc = nis.izle(istemci, nis_sayac, yol, an=SIMDI)

    assert istemci.cagrilar == ["playlistItems", "videos"]
    assert sonuc.harcanan == 2
    assert sonuc.video_sayisi == 2


def test_bos_liste_istatistik_istemez(yol: Path, nis_sayac, kanal_kur):
    kanal_kur("UC1")
    istemci = SahteYT(listeler={"UU1": []})
    sonuc = nis.izle(istemci, nis_sayac, yol, an=SIMDI)

    assert istemci.cagrilar == ["playlistItems"]
    assert sonuc.harcanan == 1


def test_olcum_olcum_tablosunu_kirletmez(yol: Path, nis_sayac, kanal_kur):
    """Niş ölçümü `olcum`'a yazılırsa DW-29'un bölge yayılım hesabı bozulur.

    `olcum`'da `bolge` anahtarın parçası; yapay bir kod koymak
    `COUNT(DISTINCT bolge)`'yi bir fazla saydırırdı.
    """
    kanal_kur("UC1")
    istemci = SahteYT(listeler={"UU1": ["v1"]}, videolar={"v1": ("A", "UC1", 5_000, 60)})
    nis.izle(istemci, nis_sayac, yol, an=SIMDI)

    baglanti = depo.baglan(yol)
    try:
        assert baglanti.execute("SELECT COUNT(*) n FROM olcum").fetchone()["n"] == 0
        assert baglanti.execute("SELECT COUNT(*) n FROM nis_olcum").fetchone()["n"] == 1
        # Metadata ortak tabloda: başlığı iki yerde tutmak ayrışma demek.
        assert baglanti.execute("SELECT baslik FROM video").fetchone()["baslik"] == "A"
    finally:
        baglanti.close()
    assert hiz.hesapla(yol) == [], "niş ölçümü trend raporuna sızmamalı"


def test_bir_kanalin_hatasi_izlemeyi_bitirmez(yol: Path, nis_sayac, kanal_kur):
    kanal_kur("UC1", handle="@a")
    kanal_kur("UC2", handle="@b")

    class Kararsiz(SahteYT):
        def execute(self):
            if self._tur == "playlistItems" and self._p["playlistId"] == "UU1":
                raise RuntimeError("404 playlistNotFound")
            return super().execute()

    istemci = Kararsiz(listeler={"UU2": ["v1"]}, videolar={"v1": ("A", "UC2", 5_000, 60)})
    sonuc = nis.izle(istemci, nis_sayac, yol, an=SIMDI)

    assert len(sonuc.hatalar) == 1
    assert sonuc.kanal_sayisi == 1


def test_gunluk_tavan_asilmaz(yol: Path, nis_sayac, kanal_kur):
    for i in range(5):
        kanal_kur(f"UC{i}", handle=f"@k{i}")
    istemci = SahteYT(
        listeler={f"UU{i}": ["v"] for i in range(5)},
        videolar={"v": ("A", "UC0", 1_000, 60)},
    )
    sonuc = nis.izle(istemci, nis_sayac, yol, tavan=4, an=SIMDI)

    assert sonuc.kanal_sayisi == 2, "4 / 2 = 2 kanal sığar"
    assert sonuc.kota_bitti is True


def test_yukleme_rezervi_korunur(yol: Path, nis_sayac, kanal_kur):
    kanal_kur("UC1")
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO kota_harcama (gun, an, islem, birim, surec) VALUES (?, ?, ?, ?, ?)",
            (
                kota.kota_gunu(),
                SIMDI.isoformat(),
                "videos.insert",
                kota.GUNLUK_BUTCE - kota.video_basina_maliyet(),
                "yukleme",
            ),
        )
    sonuc = nis.izle(SahteYT(), nis_sayac, yol, an=SIMDI)

    assert sonuc.kota_bitti is True
    assert sonuc.kanal_sayisi == 0


# --- Taban çizgisi -------------------------------------------------------


def test_taban_olgun_videolarin_medyani(yol: Path, olcum_kur):
    """Taban medyan, ortalama değil: tek viral video ortalamayı ikiye katlar."""
    for i, izlenme in enumerate([1_000, 2_000, 3_000, 4_000, 900_000]):
        olcum_kur(f"v{i}", "UC1", izlenme=izlenme, yas_gun=60)
    kayitlar = nis.asiri_performans(yol, an=SIMDI, asgari_oran=0.0)

    assert kayitlar[0].taban == 3_000, "medyan; ortalama 182.000 olurdu"


def test_olgunlasmamis_video_tabana_girmez(yol: Path, olcum_kur):
    """Tırmanan video tabanı aşağı çeker, o kanalda her şey aşırı görünür."""
    for i in range(5):
        olcum_kur(f"olgun{i}", "UC1", izlenme=100_000, yas_gun=60)
    for i in range(5):
        olcum_kur(f"yeni{i}", "UC1", izlenme=100, yas_gun=1)

    kayitlar = nis.asiri_performans(yol, an=SIMDI, asgari_oran=0.0)
    assert kayitlar[0].taban == 100_000


def test_yetersiz_olgun_video_kanali_atar(yol: Path, olcum_kur):
    """Yanlış taban, yanlış zirve demek — hiç sıralamamak yeğ."""
    for i in range(nis.ASGARI_OLGUN_VIDEO - 1):
        olcum_kur(f"v{i}", "UC1", izlenme=1_000, yas_gun=60)
    assert nis.asiri_performans(yol, an=SIMDI, asgari_oran=0.0) == []


# --- Kanal büyüklüğünden bağımsızlık ------------------------------------


def test_kucuk_kanalin_patlamasi_devin_siradan_videosunu_geride_birakir(yol: Path, olcum_kur):
    """Kabul ölçütünün özü.

    Dev kanal: taban 2.000.000; 2.400.000 izlenen videosu sıradan (1,2×).
    Küçük kanal: taban 50.000; 400.000 izlenen videosu sinyal (8×).
    Ham izlenmeye bakan bir sıralama devi öne koyardı.
    """
    for i in range(5):
        olcum_kur(f"dev{i}", "UCdev", izlenme=2_000_000, yas_gun=60)
    olcum_kur("dev_yeni", "UCdev", izlenme=2_400_000, yas_gun=45, baslik="Devin sıradan videosu")
    for i in range(5):
        olcum_kur(f"kucuk{i}", "UCkucuk", izlenme=50_000, yas_gun=60)
    olcum_kur("kucuk_patlama", "UCkucuk", izlenme=400_000, yas_gun=45, baslik="Küçüğün patlaması")

    kayitlar = nis.asiri_performans(yol, an=SIMDI, asgari_oran=1.1)
    assert [k.baslik for k in kayitlar] == ["Küçüğün patlaması", "Devin sıradan videosu"]
    assert kayitlar[0].izlenme < kayitlar[1].izlenme, "ham izlenmede dev önde"


# --- Yeni yükleme yanlış pozitifi ---------------------------------------


def test_yeni_yukleme_varsayilan_raporda_yok(yol: Path, olcum_kur):
    """Kabul ölçütü: yeni yüklenen video yanlış pozitif üretmiyor.

    Günlük hıza normalize edilen 2 saatlik bir video, tabanın 100 katını
    gösterir — DW-29'daki `ASGARI_YAS_SAAT` tuzağının aynısı.
    """
    for i in range(5):
        olcum_kur(f"v{i}", "UC1", izlenme=100_000, yas_gun=60)
    olcum_kur("bebek", "UC1", izlenme=8_000, yas_gun=0.08, baslik="İki saatlik video")

    varsayilan = nis.asiri_performans(yol, an=SIMDI, asgari_oran=0.0)
    assert "İki saatlik video" not in [k.baslik for k in varsayilan]


def test_erken_kipte_yeni_yukleme_isaretli_gelir(yol: Path, olcum_kur):
    for i in range(5):
        olcum_kur(f"v{i}", "UC1", izlenme=100_000, yas_gun=60)
    olcum_kur("bebek", "UC1", izlenme=8_000, yas_gun=0.08, baslik="İki saatlik video")

    erken = nis.asiri_performans(yol, an=SIMDI, erken=True, asgari_oran=0.0)
    bebek = next(k for k in erken if k.baslik == "İki saatlik video")

    assert bebek.olgun is False
    assert "HENÜZ OTURMADI" in bebek.satir(erken=True)
    # Bölen tabanlandı: 0,08 güne bölünmedi, 1 güne bölündü.
    assert bebek.gunluk_oran == pytest.approx(8_000 / (100_000 / nis.OLGUNLASMA_GUN))


def test_satir_siralama_sayisini_basar(yol: Path, olcum_kur):
    """Canlı koşumda bulundu: `--erken` `gunluk_oran`a göre sıralayıp `oran` basıyordu.

    Sonuç, 15,03× bir satırın 1,94× ile 2,12× arasında durmasıydı — rapor
    kendi sıralamasını yanlış gösteriyordu.
    """
    for i in range(5):
        olcum_kur(f"v{i}", "UC1", izlenme=100_000, yas_gun=60)
    olcum_kur("hedef", "UC1", izlenme=50_000, yas_gun=5, baslik="Hedef")

    kayit = next(
        k
        for k in nis.asiri_performans(yol, an=SIMDI, erken=True, asgari_oran=0.0)
        if k.baslik == "Hedef"
    )
    assert kayit.oran != pytest.approx(kayit.gunluk_oran)
    assert f"{kayit.oran:.2f}×" in kayit.satir()
    assert f"{kayit.gunluk_oran:.2f}×" in kayit.satir(erken=True)


# --- Yaş penceresi -------------------------------------------------------


def test_pencere_eski_hitleri_disarida_birakir(yol: Path, olcum_kur):
    """Canlı koşumda bulundu: pencere olmadan tepede 1.428 günlük bir video vardı.

    Ölçüm doğruydu ama soruya cevap değildi — 4 yıllık bir tüm zamanlar hiti
    "şimdi ne yapmalıyım" sorusuna bir şey söylemiyor.
    """
    for i in range(5):
        olcum_kur(f"v{i}", "UC1", izlenme=100_000, yas_gun=200)
    olcum_kur("eski_hit", "UC1", izlenme=3_000_000, yas_gun=1_428, baslik="Dört yıllık hit")
    olcum_kur("yeni_hit", "UC1", izlenme=500_000, yas_gun=45, baslik="Bu ayın hiti")

    pencereli = nis.asiri_performans(yol, an=SIMDI, asgari_oran=1.1)
    assert [k.baslik for k in pencereli] == ["Bu ayın hiti"]

    tum_zamanlar = nis.asiri_performans(yol, an=SIMDI, asgari_oran=1.1, pencere_gun=0)
    assert [k.baslik for k in tum_zamanlar] == ["Dört yıllık hit", "Bu ayın hiti"]


def test_taban_pencereden_etkilenmez(yol: Path, olcum_kur):
    """Pencere yalnızca sıralanan kümeyi daraltıyor; taban geniş kalmalı.

    Taban da pencereye sıkışsa 30–90 gün bandındaki 1–2 videodan hesaplanır ve
    gürültü olurdu.
    """
    for i in range(5):
        olcum_kur(f"eski{i}", "UC1", izlenme=100_000, yas_gun=400)
    olcum_kur("yeni", "UC1", izlenme=300_000, yas_gun=45)

    kayitlar = nis.asiri_performans(yol, an=SIMDI, asgari_oran=0.0)
    assert len(kayitlar) == 1
    assert kayitlar[0].taban == 100_000
    assert kayitlar[0].oran == pytest.approx(3.0)


def test_yayin_zamani_olmayan_video_atlanir(yol: Path, olcum_kur):
    for i in range(5):
        olcum_kur(f"v{i}", "UC1", izlenme=100_000, yas_gun=60)
    olcum_kur("tarihsiz", "UC1", izlenme=999_999, yas_gun=45)
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute("UPDATE video SET yayin_zamani = NULL WHERE video_id = 'tarihsiz'")

    assert "tarihsiz" not in [k.video_id for k in nis.asiri_performans(yol, an=SIMDI)]


def test_en_son_olcum_kullanilir(yol: Path, olcum_kur):
    for i in range(5):
        olcum_kur(f"v{i}", "UC1", izlenme=100_000, yas_gun=60)
    olcum_kur("hedef", "UC1", izlenme=200_000, yas_gun=45)
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO nis_olcum (video_id, kanal_id, an, izlenme) VALUES (?, ?, ?, ?)",
            ("hedef", "UC1", (SIMDI + timedelta(hours=6)).isoformat(), 500_000),
        )

    hedef = next(k for k in nis.asiri_performans(yol, an=SIMDI) if k.video_id == "hedef")
    assert hedef.izlenme == 500_000


# --- CLI -----------------------------------------------------------------


def test_kuru_kosum_maliyeti_bildirir(yol: Path, monkeypatch, capsys, kanal_kur):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    monkeypatch.setattr(
        cli, "_istemci_kur", lambda: pytest.fail("kuru koşumda istemci kurulmamalı")
    )
    kanal_kur("UC1", handle=nis.IZLENEN_KANALLAR[0][0])

    assert cli.main(["nis", "izle", "--kuru"]) == 0
    cikti = capsys.readouterr().out

    assert f"katalogda {len(nis.IZLENEN_KANALLAR)} kanal · 1 tanesi çözülmüş" in cikti
    assert f"niş bugün: 0/{nis.NIS_KOTA_TAVANI} birim" in cikti


def test_cli_rapor_kapsami_yazar(yol: Path, olcum_kur, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    for i in range(5):
        olcum_kur(f"v{i}", "UC1", izlenme=100_000, yas_gun=60)
    olcum_kur("hit", "UC1", izlenme=500_000, yas_gun=45, baslik="Hit")

    assert cli.main(["nis", "rapor"]) == 0
    cikti = capsys.readouterr().out
    assert f"son {nis.PENCERE_GUN:g} gün" in cikti
    assert "Hit" in cikti

    assert cli.main(["nis", "rapor", "--pencere", "0"]) == 0
    assert "tüm zamanlar" in capsys.readouterr().out


def test_cli_rapor_taban_yoksa_sebebi_soyler(yol: Path, olcum_kur, monkeypatch, capsys):
    """ "Sonuç yok" yetmez: ölçüm mü yok, taban mı kurulamadı — ikisi farklı iş."""
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    olcum_kur("v1", "UC1", izlenme=1_000, yas_gun=60)

    assert cli.main(["nis", "rapor"]) == 1
    assert f"{nis.ASGARI_OLGUN_VIDEO} olgun video" in capsys.readouterr().out
