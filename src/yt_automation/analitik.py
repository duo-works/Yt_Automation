"""YouTube Analytics performans verisini normalize eder ve raporlar.

OAuth kimlik bilgisi üretmek bu modülün sorumluluğu değildir (DW-21). Bu
modül geçerli bir ``Credentials`` nesnesi alır, Data/Analytics API verilerini
çeker ve API yanıtından bağımsız, test edilebilir kayıtlar üretir.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

VARSAYILAN_SAAT_DILIMI = "Europe/Istanbul"
VARSAYILAN_YAYIN_SAATLERI = [2, 8, 14, 20]


def sureyi_saniyeye_cevir(deger: str) -> int:
    """ISO-8601 video süresini saniyeye çevirir; geçersiz girdide sıfır döner."""
    eslesme = re.fullmatch(
        r"P(?:(?P<gun>\d+)D)?T(?:(?P<saat>\d+)H)?(?:(?P<dakika>\d+)M)?"
        r"(?:(?P<saniye>\d+)S)?",
        deger or "",
    )
    if not eslesme:
        return 0
    parcalar = {ad: int(ham or 0) for ad, ham in eslesme.groupdict().items()}
    return (
        parcalar["gun"] * 86_400
        + parcalar["saat"] * 3_600
        + parcalar["dakika"] * 60
        + parcalar["saniye"]
    )


def _tam_sayi(deger: Any) -> int:
    try:
        return int(deger or 0)
    except (TypeError, ValueError):
        return 0


def _ondalik(deger: Any) -> float:
    try:
        sonuc = float(deger or 0)
        return sonuc if math.isfinite(sonuc) else 0.0
    except (TypeError, ValueError):
        return 0.0


def video_kayitlari_olustur(
    videolar: list[dict[str, Any]],
    video_analytics: dict[str, dict[str, Any]],
    *,
    simdi: datetime | None = None,
    saat_dilimi: str = "UTC",
) -> list[dict[str, Any]]:
    """Data API videolarını Analytics metrikleriyle birleştirip Shorts'u sıralar."""
    simdi = simdi or datetime.now(UTC)
    yerel = ZoneInfo(saat_dilimi)
    kayitlar: list[dict[str, Any]] = []

    for video in videolar:
        sure = sureyi_saniyeye_cevir(video.get("contentDetails", {}).get("duration", ""))
        if not 0 < sure <= 180:
            continue

        video_id = str(video.get("id", ""))
        snippet = video.get("snippet", {})
        istatistik = video.get("statistics", {})
        analytics = video_analytics.get(video_id, {})
        yayin = datetime.fromisoformat(
            snippet.get("publishedAt", "1970-01-01T00:00:00Z").replace("Z", "+00:00")
        )
        yas_gun = max((simdi - yayin).total_seconds() / 86_400, 1.0)

        herkese_acik_goruntulenme = _tam_sayi(istatistik.get("viewCount"))
        goruntulenme = _tam_sayi(analytics.get("views", herkese_acik_goruntulenme))
        begeni = _tam_sayi(analytics.get("likes", istatistik.get("likeCount")))
        yorum = _tam_sayi(analytics.get("comments", istatistik.get("commentCount")))
        izlenme_yuzdesi = _ondalik(analytics.get("averageViewPercentage"))
        kazanilan_abone = _tam_sayi(analytics.get("subscribersGained"))

        analytics_etkilesimi_var = "likes" in analytics or "comments" in analytics
        etkilesim_tabani = goruntulenme if analytics_etkilesimi_var else herkese_acik_goruntulenme
        etkilesim = (begeni + yorum) / etkilesim_tabani if etkilesim_tabani else 0.0
        gunluk_goruntulenme = goruntulenme / yas_gun
        tutma_carpani = 0.5 + min(izlenme_yuzdesi, 150.0) / 100.0
        performans = gunluk_goruntulenme * tutma_carpani * (1 + etkilesim * 5)

        kayitlar.append(
            {
                "video_id": video_id,
                "baslik": snippet.get("title", ""),
                "yayin_tarihi": yayin.isoformat(),
                "yerel_yayin_saati": yayin.astimezone(yerel).hour,
                "sure_saniye": sure,
                "goruntulenme": goruntulenme,
                "begeni": begeni,
                "yorum": yorum,
                "etkilesim_orani": etkilesim,
                "ortalama_izlenme_suresi": _ondalik(analytics.get("averageViewDuration")),
                "ortalama_izlenme_yuzdesi": izlenme_yuzdesi,
                "kazanilan_abone": kazanilan_abone,
                "gunluk_goruntulenme": gunluk_goruntulenme,
                "performans_puani": performans,
                "url": f"https://youtube.com/shorts/{video_id}",
            }
        )

    return sorted(kayitlar, key=lambda kayit: kayit["performans_puani"], reverse=True)


def yayin_saatlerini_oner(kayitlar: list[dict[str, Any]], adet: int = 4) -> list[int]:
    """Az veride deney saatleri, yeterli veride gözlenen performans saatleri döndürür."""
    if len(kayitlar) < 8:
        return VARSAYILAN_YAYIN_SAATLERI[:adet]

    saatler: dict[int, list[float]] = defaultdict(list)
    for kayit in kayitlar:
        saat = _tam_sayi(kayit.get("yerel_yayin_saati")) % 24
        saatler[saat].append(_ondalik(kayit.get("performans_puani")))

    sirali = sorted(
        saatler,
        key=lambda saat: (sum(saatler[saat]) / len(saatler[saat]), len(saatler[saat])),
        reverse=True,
    )
    secilen: list[int] = []
    for saat in [*sirali, *VARSAYILAN_YAYIN_SAATLERI]:
        if saat not in secilen:
            secilen.append(saat)
        if len(secilen) == adet:
            break
    return secilen


def kanal_ve_videolari_getir(
    kimlik: Credentials,
    *,
    servis_olustur: Callable[..., Any] = build,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Yetkili hesaptaki kanalı ve en fazla 200 yüklemenin Data API kaydını getirir."""
    youtube = servis_olustur("youtube", "v3", credentials=kimlik)
    cevap = youtube.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
    kanallar = cevap.get("items", [])
    if not kanallar:
        raise RuntimeError("yetkili hesapta YouTube kanalı bulunamadı")
    kanal = kanallar[0]
    yuklemeler = kanal["contentDetails"]["relatedPlaylists"]["uploads"]

    video_kimlikleri: list[str] = []
    sayfa = None
    while True:
        cevap = (
            youtube.playlistItems()
            .list(
                part="contentDetails",
                playlistId=yuklemeler,
                maxResults=50,
                pageToken=sayfa,
            )
            .execute()
        )
        video_kimlikleri.extend(oge["contentDetails"]["videoId"] for oge in cevap.get("items", []))
        sayfa = cevap.get("nextPageToken")
        if not sayfa or len(video_kimlikleri) >= 200:
            break

    videolar: list[dict[str, Any]] = []
    for baslangic in range(0, len(video_kimlikleri), 50):
        cevap = (
            youtube.videos()
            .list(
                part="snippet,contentDetails,statistics",
                id=",".join(video_kimlikleri[baslangic : baslangic + 50]),
                maxResults=50,
            )
            .execute()
        )
        videolar.extend(cevap.get("items", []))
    return kanal, videolar


def analytics_verisini_getir(
    kimlik: Credentials,
    gun: int = 90,
    *,
    servis_olustur: Callable[..., Any] = build,
) -> dict[str, dict[str, Any]]:
    """Video bazlı son ``gun`` günlük Analytics metriklerini getirir."""
    analytics = servis_olustur("youtubeAnalytics", "v2", credentials=kimlik)
    bitis = datetime.now(UTC).date() - timedelta(days=1)
    baslangic = bitis - timedelta(days=gun - 1)
    cevap = (
        analytics.reports()
        .query(
            ids="channel==MINE",
            startDate=baslangic.isoformat(),
            endDate=bitis.isoformat(),
            metrics=(
                "views,likes,comments,estimatedMinutesWatched,averageViewDuration,"
                "averageViewPercentage,subscribersGained"
            ),
            dimensions="video",
            sort="-views",
            maxResults=200,
        )
        .execute()
    )
    basliklar = [baslik["name"] for baslik in cevap.get("columnHeaders", [])]
    return {
        str(satir[0]): dict(zip(basliklar[1:], satir[1:], strict=False))
        for satir in cevap.get("rows", [])
    }


def rapor_olustur(
    kanal: dict[str, Any],
    kayitlar: list[dict[str, Any]],
    yayin_saatleri: list[int],
    saat_dilimi: str,
) -> dict[str, Any]:
    """API yanıtlarını kalıcı olarak saklanabilir rapor sözlüğüne dönüştürür."""
    istatistik = kanal.get("statistics", {})
    return {
        "olusturulma_tarihi": datetime.now(UTC).isoformat(),
        "saat_dilimi": saat_dilimi,
        "kanal": {
            "id": kanal.get("id", ""),
            "ad": kanal.get("snippet", {}).get("title", ""),
            "abone": _tam_sayi(istatistik.get("subscriberCount")),
            "toplam_goruntulenme": _tam_sayi(istatistik.get("viewCount")),
            "video_sayisi": _tam_sayi(istatistik.get("videoCount")),
        },
        "incelenen_shorts": len(kayitlar),
        "veri_guveni": "dusuk" if len(kayitlar) < 8 else "orta",
        "onerilen_yayin_saatleri": yayin_saatleri,
        "en_iyi_shorts": kayitlar[:10],
        "tum_shorts": kayitlar,
    }
