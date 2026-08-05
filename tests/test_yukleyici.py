from datetime import datetime
from pathlib import Path

import pytest

from yt_automation.kanal import Kanal
from yt_automation.kota import KotaAsimi, Sayac
from yt_automation.video import Video
from yt_automation.yukleyici import (
    YanlisKanalHatasi,
    YuklemeDogrulamaHatasi,
    kanali_dogrula,
    yukle_ve_dogrula,
    yukleme_govdesi,
)

KANAL = Kanal(kimlik="egitim", ad="Eğitim", cocuk_icerigi=False)


def video(tmp_path: Path, *, zamanli: bool = False, sentetik: bool = True) -> Video:
    dosya = tmp_path / "video.mp4"
    dosya.write_bytes(b"video")
    return Video(
        dosya=dosya,
        baslik="Roma su kemerleri",
        aciklama="Açıklama",
        etiketler=("history", "shorts"),
        yayin_tarihi=datetime(2026, 8, 1, 18, 0) if zamanli else None,
        sentetik_medya=sentetik,
        cocuk_icerigi=False,
        thumbnail=None,
    )


def test_zamanli_video_private_ve_utc_publish_at_ile_gider(tmp_path: Path):
    govde = yukleme_govdesi(video(tmp_path, zamanli=True), KANAL)

    assert govde["status"] == {
        "privacyStatus": "private",
        "publishAt": "2026-08-01T15:00:00Z",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }


def test_zamansiz_video_yayina_cikmaz(tmp_path: Path):
    """Yayın tarihi yoksa video yüklenir ama **private** kalır.

    Bu test eskiden tersini kilitliyordu (`== "public"`), yani kusuru
    koruyordu. PRD'nin *v1'de OLMAYACAKLAR* listesinde "otomatik yayın kararı"
    açıkça yazılı; tarihsiz bir videoyu anında herkese açmak tam olarak o karar
    ve üstelik varsayılan yoldu — metadata'da bir satırı unutmanın cezası
    "yayında" oluyordu.

    Yön asimetrik: erken yayınlanan videoyu geri almak izlenme, öneri sinyali
    ve çocuk içeriğinde uyum riski demek; geç yayınlanan videoyu yayınlamak
    bir tık.
    """
    govde = yukleme_govdesi(video(tmp_path), KANAL)

    assert govde["status"]["privacyStatus"] == "private"
    assert "publishAt" not in govde["status"]
    # Zamanlanmış hâl zaten `test_zamanli_video_private_ve_utc_publish_at_ile_gider`
    # ile kilitli: orada da gizlilik `private`, yayını açan şey `publishAt`.


class Calistir:
    def __init__(self, sonuc):
        self.sonuc = sonuc

    def execute(self):
        return self.sonuc


class DevamEdenYukleme:
    def __init__(self):
        self.cagrilar: list[int] = []
        self.adim = 0

    def next_chunk(self, *, num_retries: int):
        self.cagrilar.append(num_retries)
        self.adim += 1
        if self.adim == 1:
            return object(), None
        return object(), {"id": "video123"}


class SahteVideolar:
    def __init__(self, dogrulama_statusu):
        self.dogrulama_statusu = dogrulama_statusu
        self.insert_cagrisi = None
        self.list_cagrisi = None
        self.yukleme = DevamEdenYukleme()

    def insert(self, **kwargs):
        self.insert_cagrisi = kwargs
        return self.yukleme

    def list(self, **kwargs):
        self.list_cagrisi = kwargs
        return Calistir({"items": [{"id": "video123", "status": self.dogrulama_statusu}]})


class SahteServis:
    def __init__(self, dogrulama_statusu):
        self.videolar = SahteVideolar(dogrulama_statusu)

    def videos(self):
        return self.videolar


class MedyaFabrikasi:
    def __init__(self):
        self.cagri = None

    def __call__(self, *args, **kwargs):
        self.cagri = (args, kwargs)
        return object()


def test_resumable_yukleme_kotayi_once_harcar_ve_bayraklari_dogrular(tmp_path: Path):
    v = video(tmp_path, sentetik=True)
    beklenen = yukleme_govdesi(v, KANAL)["status"]
    servis = SahteServis(beklenen)
    sayac = Sayac()
    medya = MedyaFabrikasi()

    sonuc = yukle_ve_dogrula(v, KANAL, servis, sayac, medya_fabrikasi=medya)

    assert sonuc == "video123"
    assert sayac.harcanan == 1601
    assert sayac.kayit == [("videos.insert", 1600), ("videos.list", 1)]
    assert servis.videolar.insert_cagrisi["body"]["status"] == beklenen
    assert servis.videolar.yukleme.cagrilar == [3, 3]
    assert medya.cagri[1]["resumable"] is True
    assert servis.videolar.list_cagrisi == {"part": "status", "id": "video123"}


def test_kota_yetmezse_api_istegi_hic_olusturulmaz(tmp_path: Path):
    v = video(tmp_path)
    servis = SahteServis(yukleme_govdesi(v, KANAL)["status"])

    with pytest.raises(KotaAsimi):
        yukle_ve_dogrula(v, KANAL, servis, Sayac(butce=1599))

    assert servis.videolar.insert_cagrisi is None


def test_beyan_bayragi_yanlissa_dogrulama_hatasi(tmp_path: Path):
    v = video(tmp_path, sentetik=True)
    yanlis = dict(yukleme_govdesi(v, KANAL)["status"])
    yanlis["containsSyntheticMedia"] = False

    with pytest.raises(YuklemeDogrulamaHatasi, match="containsSyntheticMedia"):
        yukle_ve_dogrula(v, KANAL, SahteServis(yanlis), Sayac())


def test_donmeyen_alan_hata_sayilmaz_ama_raporlanir(tmp_path: Path):
    """YouTube alanı hiç döndürmezse "doğrulanamadı" demek gerekir, "başarısız" değil.

    Ölçüldü (2026-08-05, videos.list?part=status): `containsSyntheticMedia`,
    `selfDeclaredMadeForKids` ve `publishAt` yanıtta yok. Ayrım yapılmazsa
    `gercek.get(alan)` None verir, beklenen True ile eşleşmez ve HER BAŞARILI
    yüklemeden sonra hata atılır — video YouTube'da, 1.651 birim harcanmış,
    çağıran taraf başarısız sandığı için tekrar dener.
    """
    sayac = Sayac()
    uyarilar: list[str] = []
    # YouTube yalnızca privacyStatus döndürüyor; diğer üç beyan geri okunamıyor.
    servis = SahteServis({"privacyStatus": "private"})

    video_id = yukle_ve_dogrula(
        video(tmp_path),
        KANAL,
        servis,
        sayac,
        medya_fabrikasi=MedyaFabrikasi(),
        uyar=uyarilar.append,
    )

    assert video_id == "video123"
    assert len(uyarilar) == 1
    assert "selfDeclaredMadeForKids" in uyarilar[0]
    assert "containsSyntheticMedia" in uyarilar[0]


def test_donen_ama_tutmayan_alan_hala_hata(tmp_path: Path):
    """Ayrım gevşetilirken gerçek denetim kaybedilmemeli.

    Alan DÖNDÜ ve beklenenden farklıysa beyan tutmamış demektir — bu hâlâ
    hata. Kaybedilseydi, `private` gönderip `public` çıkan bir video sessizce
    kabul edilirdi.
    """
    sayac = Sayac()
    servis = SahteServis({"privacyStatus": "public"})

    with pytest.raises(YuklemeDogrulamaHatasi, match="privacyStatus"):
        yukle_ve_dogrula(
            video(tmp_path),
            KANAL,
            servis,
            sayac,
            medya_fabrikasi=MedyaFabrikasi(),
        )


class SahteKanallar:
    """`channels.list?mine=true` yanıtı."""

    def __init__(self, kanal_id: str | None, ad: str = "Bir Kanal"):
        self.cagri = None
        self.kanal_id = kanal_id
        self.ad = ad

    def list(self, **kwargs):
        self.cagri = kwargs
        ogeler = [{"id": self.kanal_id, "snippet": {"title": self.ad}}] if self.kanal_id else []
        return Calistir({"items": ogeler})


class KanalliServis(SahteServis):
    def __init__(self, dogrulama_statusu, kanal_id: str | None, ad: str = "Bir Kanal"):
        super().__init__(dogrulama_statusu)
        self.kanallar = SahteKanallar(kanal_id, ad)

    def channels(self):
        return self.kanallar


KIMLIKLI = Kanal(
    kimlik="egitim",
    ad="Eğitim",
    cocuk_icerigi=False,
    youtube_kanal_id="UCbeklenen",
)


def test_yanlis_kanalda_hicbir_sey_yuklenmez():
    """Ölçülmüş kusur (2026-08-05): token beklenen kanal yerine kişisel kanala bağlandı.

    Kullanıcı kendi Google hesabıyla giriş yaptı, Google onun kanalını seçti ve
    kod bunu göremedi — hangi kanalda olduğunu hiç sormuyordu. Yükleme
    yapılsaydı video yanlış kanala giderdi; geri alması YouTube tarafında elle
    iş. Elle bir `channels.list` çağrısı yakaladı, kod yakalamadı.
    """
    servis = KanalliServis({}, "UCbaskasi", ad="Kişisel Kanal")
    sayac = Sayac()

    with pytest.raises(YanlisKanalHatasi, match="Kişisel Kanal"):
        kanali_dogrula(servis, KIMLIKLI, sayac)

    # Hata mesajı ne yapılacağını söylemeli.
    try:
        kanali_dogrula(servis, KIMLIKLI, sayac)
    except YanlisKanalHatasi as hata:
        assert "UCbeklenen" in str(hata), "beklenen kanal da yazılmalı"
        assert "yeniden yetkilendir" in str(hata).lower()


def test_dogru_kanalda_gecer_ve_bir_birim_harcar():
    servis = KanalliServis({}, "UCbeklenen")
    sayac = Sayac()

    assert kanali_dogrula(servis, KIMLIKLI, sayac) == "UCbeklenen"
    assert sayac.kayit == [("channels.list", 1)]
    assert servis.kanallar.cagri == {"part": "snippet", "mine": True}


def test_kimliksiz_profilde_dogrulama_atlanir_ama_uyarilir():
    """Sessiz atlama, korumanın hiç olmamasıyla aynı şey olurdu."""
    servis = KanalliServis({}, "UCherhangi")
    sayac = Sayac()
    uyarilar: list[str] = []

    assert kanali_dogrula(servis, KANAL, sayac, uyar=uyarilar.append) is None
    assert sayac.kayit == [], "doğrulama yapılmadıysa kota da harcanmamalı"
    assert len(uyarilar) == 1
    assert "youtube_kanal_id" in uyarilar[0]


def test_kanal_bulunamazsa_durulur():
    """Boş yanıt 'doğrulandı' sayılmamalı — token yanlış hesapla alınmış olabilir."""
    servis = KanalliServis({}, None)

    with pytest.raises(YanlisKanalHatasi, match="bulunamadı"):
        kanali_dogrula(servis, KIMLIKLI, Sayac())
