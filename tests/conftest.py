"""Trend testleri için ortak araçlar.

`SahteIstemci`, `google-api-python-client`'ın çağrı zincirini taklit eder:
`istemci.videos().list(**p).execute()`. Böylece testler hiç ağa çıkmaz —
CI'da canlı çağrı yapmak hem kota harcar hem sonucu tekrarlanamaz kılardı.
"""

from pathlib import Path

import pytest

from yt_automation import depo, kota


class SahteIstemci:
    """`yanitlar`: (bolge, kategori) → öge listesi **ya da** fırlatılacak hata.

    `"_bolgeler"` anahtarı `i18nRegions.list` yanıtını belirler.
    """

    def __init__(self, yanitlar: dict):
        self.yanitlar = yanitlar
        self.cagrilar: list[tuple[str, int]] = []
        self._son: dict = {}

    def videos(self):
        return self

    def i18nRegions(self):  # noqa: N802 — API adını birebir taklit ediyor
        return self

    def list(self, **parametreler):
        self._son = parametreler
        return self

    def execute(self):
        p = self._son
        if "chart" not in p:  # i18nRegions.list
            return {"items": [{"snippet": {"gl": kod}} for kod in self.yanitlar["_bolgeler"]]}
        anahtar = (p["regionCode"], int(p.get("videoCategoryId", 0)))
        self.cagrilar.append(anahtar)
        sonuc = self.yanitlar.get(anahtar, [])
        if isinstance(sonuc, Exception):
            raise sonuc
        return {"items": sonuc}


@pytest.fixture
def sahte_istemci():
    return SahteIstemci


@pytest.fixture
def video_ogesi():
    """`videos.list` yanıtındaki tek bir öğeyi üretir."""

    def yap(video_id: str, *, kategori: str = "27", izlenme: str = "1000", **ek) -> dict:
        oge = {
            "id": video_id,
            "snippet": {
                "title": f"Başlık {video_id}",
                "channelId": f"kanal-{video_id}",
                "channelTitle": f"Kanal {video_id}",
                "publishedAt": "2026-07-28T10:00:00Z",
                "categoryId": kategori,
            },
            "statistics": {"viewCount": izlenme, "likeCount": "10", "commentCount": "5"},
            "contentDetails": {"duration": "PT10M30S"},
            "topicDetails": {"topicCategories": ["https://en.wikipedia.org/wiki/Knowledge"]},
        }
        oge.update(ek)
        return oge

    return yap


@pytest.fixture
def yol(tmp_path: Path) -> Path:
    return tmp_path / "veri" / "test.db"


@pytest.fixture
def sayac(yol: Path) -> kota.KaliciSayac:
    return kota.KaliciSayac(yol, surec="trend")


@pytest.fixture
def satirlar(yol: Path):
    def sorgula(sorgu: str, *p) -> list:
        baglanti = depo.baglan(yol)
        try:
            return baglanti.execute(sorgu, p).fetchall()
        finally:
            baglanti.close()

    return sorgula
