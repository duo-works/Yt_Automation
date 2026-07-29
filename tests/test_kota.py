import pytest

from yt_automation import kota


def test_gunluk_tavan_alti_video():
    """Uçtan uca maliyetle günlük tavan 6 video; 7'nci bütçeyi aşar.

    PRD ilk yazımında "tavan fiilen 5" diyordu — bu test onu yanlışladı.
    6 × 1.651 = 9.906, yani sığıyor ama geriye yalnızca 94 birim kalıyor.
    """
    birim = kota.video_basina_maliyet()
    assert 6 * birim <= kota.GUNLUK_BUTCE
    assert 7 * birim > kota.GUNLUK_BUTCE
    # 6 video sığıyor ama raporlamaya nefes bırakmıyor.
    assert kota.GUNLUK_BUTCE - 6 * birim < 100


def test_harcama_kalani_dusurur():
    s = kota.Sayac()
    kalan = s.harca("videos.insert")
    assert s.harcanan == 1_600
    assert kalan == kota.GUNLUK_BUTCE - 1_600


def test_butce_asiminda_istek_gonderilmez():
    s = kota.Sayac(butce=100)
    with pytest.raises(kota.KotaAsimi, match="videos.insert"):
        s.harca("videos.insert")
    # Reddedilen istek harcamaya yazılmamalı — hiç gönderilmedi.
    assert s.harcanan == 0
    assert s.kayit == []


def test_yeter_mi_sinirda_dogru():
    s = kota.Sayac(butce=kota.MALIYET["thumbnails.set"])
    assert s.yeter_mi("thumbnails.set") is True
    assert s.yeter_mi("videos.insert") is False


def test_bilinmeyen_islem_anlasilir_hata():
    s = kota.Sayac()
    with pytest.raises(KeyError, match="bilinmeyen işlem"):
        s.harca("videos.teleport")


def test_video_basina_maliyet():
    assert kota.video_basina_maliyet() == 1_600 + 50 + 1
    assert kota.video_basina_maliyet(thumbnail=False) == 1_600 + 1
    assert kota.video_basina_maliyet(thumbnail=False, dogrulama=False) == 1_600


def test_gunde_bir_video_iki_kanal_rahat():
    """PRD: iki kanal aynı 10.000 birimi paylaşır."""
    assert 2 * kota.video_basina_maliyet() < kota.GUNLUK_BUTCE


def test_kayit_tutulur():
    s = kota.Sayac()
    s.harca("videos.insert")
    s.harca("thumbnails.set")
    assert s.kayit == [("videos.insert", 1_600), ("thumbnails.set", 50)]
    assert "1650/10000" in s.ozet()
