from datetime import datetime
from pathlib import Path

import pytest

from yt_automation.kanal import Kanal
from yt_automation.kota import KotaAsimi, Sayac
from yt_automation.video import Video
from yt_automation.yukleyici import (
    YuklemeDogrulamaHatasi,
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


def test_zamansiz_video_dogrudan_public_gider(tmp_path: Path):
    govde = yukleme_govdesi(video(tmp_path), KANAL)

    assert govde["status"]["privacyStatus"] == "public"
    assert "publishAt" not in govde["status"]


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
