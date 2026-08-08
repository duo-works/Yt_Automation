"""Drive yayını — çıktılar için YouTube'dan bağımsız ikinci kopya.

Testler gerçek Drive'a çıkmıyor; servis nesnesi taklit ediliyor.
"""

from pathlib import Path

import pytest

from yt_automation import drive


class SahteIstek:
    def __init__(self, sonuc):
        self._sonuc = sonuc

    def execute(self):
        return self._sonuc


class SahteDosyalar:
    def __init__(self, mevcut_klasor=None, klasor_icerigi=()):
        self.mevcut_klasor = mevcut_klasor
        self.klasor_icerigi = list(klasor_icerigi)
        self.olusturulanlar = []
        self.sorgular = []

    def list(self, *, q, fields, pageSize=None):  # noqa: N803 — Google API imzası
        self.sorgular.append(q)
        if "mimeType" in q:
            dosyalar = [{"id": self.mevcut_klasor, "name": "klasor"}] if self.mevcut_klasor else []
        else:
            dosyalar = [{"name": ad} for ad in self.klasor_icerigi]
        return SahteIstek({"files": dosyalar})

    def create(self, *, body, fields, media_body=None):  # noqa: N803
        self.olusturulanlar.append(body)
        return SahteIstek(
            {
                "id": f"kimlik-{len(self.olusturulanlar)}",
                "name": body.get("name", ""),
                "webViewLink": "https://drive.google.com/file/d/x/view",
            }
        )


class SahteIzinler:
    def __init__(self, hata=None):
        self.verilenler = []
        self._hata = hata

    def create(self, *, fileId, body, fields):  # noqa: N803
        self.verilenler.append((fileId, body))
        if self._hata is not None:
            raise self._hata
        return SahteIstek({"id": "izin-1"})


def _http_hatasi(durum: int):
    """`googleapiclient.errors.HttpError` — gerçek sınıf, gerçek `resp.status`."""
    from googleapiclient.errors import HttpError

    class _Yanit:
        status = durum
        reason = "test"

    return HttpError(_Yanit(), b"{}")


class SahteServis:
    def __init__(self, dosyalar, izinler=None):
        self._dosyalar = dosyalar
        self._izinler = izinler or SahteIzinler()

    def files(self):
        return self._dosyalar

    def permissions(self):
        return self._izinler


@pytest.fixture
def videolar(tmp_path):
    yollar = []
    for ad in ("01-bir.mp4", "02-iki.mp4"):
        p = tmp_path / ad
        p.write_bytes(b"video")
        yollar.append(p)
    return yollar


@pytest.fixture
def baglanti_kur(monkeypatch):
    """`videolari_yukle`'yi ağa çıkmadan koşturur."""

    def kur(dosyalar_sahtesi, izinler=None):
        servis = SahteServis(dosyalar_sahtesi, izinler)
        monkeypatch.setattr(drive, "kimlik_al", lambda **_kwargs: object())
        monkeypatch.setattr(drive, "_servis", lambda _kimlik: servis)
        monkeypatch.setattr(drive, "MediaFileUpload", None, raising=False)
        return servis

    return kur


def test_kapsam_yalnizca_kendi_dosyalari():
    """`drive` (tam erişim) değil `drive.file` — geri alınması zor yetki istenmiyor."""
    assert drive.KAPSAMLAR == ["https://www.googleapis.com/auth/drive.file"]


def test_token_youtube_tokenindan_ayri():
    """Ölçüldü (2026-08-06): paylaşılan token dosyası kapsamı daraltıp
    kanal doğrulamasını sessizce bozdu."""
    assert drive.VARSAYILAN_TOKEN.name == "drive-token.json"
    assert drive.VARSAYILAN_TOKEN.name != "token.json"


def test_mevcut_klasor_yeniden_kullaniliyor(videolar, baglanti_kur, monkeypatch):
    """Her koşumda yeni klasör açmak stoğu ikiye böler."""
    dosyalar = SahteDosyalar(mevcut_klasor="klasor-1")
    baglanti_kur(dosyalar)
    monkeypatch.setattr(drive, "videolari_yukle", drive.videolari_yukle)

    import sys
    from types import ModuleType

    sahte_http = ModuleType("googleapiclient.http")
    sahte_http.MediaFileUpload = lambda *a, **k: object()
    sahte_hata = ModuleType("googleapiclient.errors")

    class SahteHttpError(Exception):
        pass

    sahte_hata.HttpError = SahteHttpError
    monkeypatch.setitem(sys.modules, "googleapiclient.http", sahte_http)
    monkeypatch.setitem(sys.modules, "googleapiclient.errors", sahte_hata)

    drive.videolari_yukle(videolar, klasor_adi="Test", client_secret=Path("/yok"), paylas=False)

    klasor_olusturmalari = [
        o for o in dosyalar.olusturulanlar if o.get("mimeType") == drive.KLASOR_TURU
    ]
    assert klasor_olusturmalari == [], "mevcut klasör varken yenisi açılmamalı"


def test_klasor_sorgusu_coptekileri_disliyor():
    """Çöpteki klasöre yükleme görünmez bir yere yükleme demek."""
    dosyalar = SahteDosyalar(mevcut_klasor=None)
    servis = SahteServis(dosyalar)

    drive.klasor_bul_ya_da_ac(servis, "Test")

    assert "trashed = false" in dosyalar.sorgular[0]


def test_klasor_adindaki_tirnak_kaciriliyor():
    """Sorgu tek tırnakla sınırlı; kaçırılmazsa sorgu bozulur."""
    dosyalar = SahteDosyalar(mevcut_klasor=None)
    servis = SahteServis(dosyalar)

    drive.klasor_bul_ya_da_ac(servis, "Ali'nin klasörü")

    assert "\\'" in dosyalar.sorgular[0]


def test_paylasim_yalnizca_okuma_veriyor():
    """Yazma yetkisi verilmiyor — bağlantı inceleme içindir."""
    izinler = SahteIzinler()
    servis = SahteServis(SahteDosyalar(), izinler)

    baglanti = drive.baglanti_ac(servis, "klasor-9")

    ((_, govde),) = izinler.verilenler
    assert govde["role"] == "reader"
    assert govde["type"] == "anyone"
    assert baglanti.endswith("klasor-9")


def test_paylasim_reddedilse_bile_baglanti_donuyor():
    """⚠️ Ölçüldü (2026-08-08): yükleme başarılıyken koşum HATA ile düşüyordu.

    Klasörde uygulamamızın oluşturmadığı bir dosya varsa `drive.file` kapsamı
    izin çağrısını 403 `appNotAuthorizedToChild` ile reddediyor — klasörün
    izni çocuğu da etkileyeceği için. Bu hata yüklemeden SONRA geldiği için
    video Drive'a çıkmış oluyor ama çağıran taraf bağlantıyı alamıyordu.

    Paylaşım bir yan iş: klasör zaten paylaşılmış olabilir ve bağlantı her
    hâlükârda geçerli.
    """
    izinler = SahteIzinler(hata=_http_hatasi(403))
    servis = SahteServis(SahteDosyalar(), izinler)

    assert drive.baglanti_ac(servis, "klasor-9").endswith("klasor-9")


def test_paylasimdaki_baska_hatalar_yutulmuyor():
    """403 dışındaki hatalar gerçek arıza — sessizce geçilmemeli."""
    izinler = SahteIzinler(hata=_http_hatasi(500))
    servis = SahteServis(SahteDosyalar(), izinler)

    with pytest.raises(Exception, match="500"):
        drive.baglanti_ac(servis, "klasor-9")


def test_olmayan_dosya_erken_hata(tmp_path):
    with pytest.raises(drive.DriveHatasi, match="dosya bulunamadı"):
        drive.videolari_yukle(
            [tmp_path / "yok.mp4"],
            klasor_adi="Test",
            client_secret=Path("/yok"),
        )
