from datetime import UTC, datetime

import pytest

from yt_automation.analitik import (
    rapor_olustur,
    sureyi_saniyeye_cevir,
    video_kayitlari_olustur,
    yayin_saatlerini_oner,
)


def test_iso8601_suresi_saniyeye_cevrilir():
    assert sureyi_saniyeye_cevir("PT38S") == 38
    assert sureyi_saniyeye_cevir("PT1M2S") == 62
    assert sureyi_saniyeye_cevir("PT1H2M3S") == 3723
    assert sureyi_saniyeye_cevir("bozuk") == 0


def test_video_ve_analytics_kayitlari_birlestirilir_uzun_video_elenir():
    videolar = [
        {
            "id": "short1",
            "snippet": {
                "title": "A short history fact",
                "publishedAt": "2026-07-20T10:00:00Z",
            },
            "contentDetails": {"duration": "PT39S"},
            "statistics": {"viewCount": "1000", "likeCount": "80", "commentCount": "20"},
        },
        {
            "id": "long1",
            "snippet": {
                "title": "A long documentary",
                "publishedAt": "2026-07-19T10:00:00Z",
            },
            "contentDetails": {"duration": "PT8M"},
            "statistics": {"viewCount": "5000"},
        },
    ]
    analytics = {
        "short1": {
            "views": 900,
            "averageViewPercentage": 82.5,
            "subscribersGained": 12,
        }
    }

    kayitlar = video_kayitlari_olustur(
        videolar,
        analytics,
        simdi=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert [kayit["video_id"] for kayit in kayitlar] == ["short1"]
    assert kayitlar[0]["sure_saniye"] == 39
    assert kayitlar[0]["etkilesim_orani"] == pytest.approx(0.10)
    assert kayitlar[0]["ortalama_izlenme_yuzdesi"] == 82.5
    assert kayitlar[0]["kazanilan_abone"] == 12


def test_analytics_views_yokken_data_api_sayisi_kullanilir():
    videolar = [
        {
            "id": "short1",
            "snippet": {"title": "X", "publishedAt": "2026-07-20T10:00:00Z"},
            "contentDetails": {"duration": "PT39S"},
            "statistics": {"viewCount": "321"},
        }
    ]

    kayitlar = video_kayitlari_olustur(
        videolar,
        {},
        simdi=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert kayitlar[0]["goruntulenme"] == 321


def test_az_veride_esit_aralikli_global_test_saatleri_onerilir():
    kayitlar = [
        {"yerel_yayin_saati": 19, "performans_puani": 100.0},
        {"yerel_yayin_saati": 13, "performans_puani": 50.0},
        {"yerel_yayin_saati": 22, "performans_puani": 25.0},
    ]

    assert yayin_saatlerini_oner(kayitlar, adet=4) == [2, 8, 14, 20]


def test_rapor_kanal_ozetini_ve_veri_guvenini_icerir():
    kanal = {
        "id": "kanal1",
        "snippet": {"title": "muezza"},
        "statistics": {"subscriberCount": "1", "viewCount": "964", "videoCount": "3"},
    }

    rapor = rapor_olustur(kanal, [], [2, 8, 14, 20], "Europe/Istanbul")

    assert rapor["kanal"]["ad"] == "muezza"
    assert rapor["kanal"]["toplam_goruntulenme"] == 964
    assert rapor["veri_guveni"] == "dusuk"
    assert rapor["onerilen_yayin_saatleri"] == [2, 8, 14, 20]
