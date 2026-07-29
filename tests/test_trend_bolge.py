"""Bölge seçimi — derin taramanın kapsamı ölçülerek belirlenir, varsayılmaz."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yt_automation import depo
from yt_automation.trend import bolge, toplayici


def test_genis_kosu_yoksa_anlasilir_hata(yol: Path):
    with pytest.raises(bolge.BolgeHatasi, match="--genis"):
        bolge.derin_bolgeler(yol)


def test_ilgili_kategori_yoksa_uyarir(yol: Path, sayac, sahte_istemci, video_ogesi):
    """Tarama çalışmış ama hiç eğitim/bilim çıkmamışsa sessizce boş dönmemeli."""
    istemci = sahte_istemci({("TR", 0): [video_ogesi("v1", kategori="10")]})  # Music
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR"], yol=yol)

    with pytest.raises(bolge.BolgeHatasi, match="eğitim/bilim"):
        bolge.derin_bolgeler(yol)


def test_yogunluga_gore_siralanir(yol: Path, sayac, sahte_istemci, video_ogesi):
    """Sıralama eğitim/bilim video sayısına göre — toplam hacme göre değil."""
    istemci = sahte_istemci(
        {
            # DE: 3 eğitim
            ("DE", 27): [video_ogesi(f"de{i}", kategori="27") for i in range(3)],
            # TR: 1 eğitim + 2 müzik → yoğunluk 1, hacim 3
            ("TR", 27): [video_ogesi("tr1", kategori="27")],
            ("TR", 0): [video_ogesi("trm1", kategori="10"), video_ogesi("trm2", kategori="10")],
            # FR: 2 bilim
            ("FR", 28): [video_ogesi(f"fr{i}", kategori="28") for i in range(2)],
        }
    )
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR", "DE", "FR"], yol=yol)

    assert bolge.derin_bolgeler(yol) == ["DE", "FR", "TR"]
    assert bolge.derin_bolgeler(yol, adet=2) == ["DE", "FR"]


def test_yalnizca_son_genis_kosu_sayilir(yol: Path, sayac, sahte_istemci, video_ogesi):
    """Eski koşular sıralamayı kirletmemeli — bölge tercihi güncel veriye dayanır."""
    toplayici.topla(
        sahte_istemci({("TR", 27): [video_ogesi(f"t{i}", kategori="27") for i in range(5)]}),
        sayac,
        tur="genis",
        bolgeler=["TR"],
        yol=yol,
        an=datetime(2026, 7, 1, tzinfo=UTC),
    )
    toplayici.topla(
        sahte_istemci({("DE", 27): [video_ogesi("d1", kategori="27")]}),
        sayac,
        tur="genis",
        bolgeler=["DE"],
        yol=yol,
        an=datetime(2026, 7, 29, tzinfo=UTC),
    )

    assert bolge.derin_bolgeler(yol) == ["DE"]


def test_derin_kosu_siralamayi_kaydirmaz(yol: Path, sayac, sahte_istemci, video_ogesi):
    """Bölge tercihi yalnızca geniş taramadan türetilir.

    Aksi halde geri besleme kendi kendini besler: derin tarama zaten seçilmiş
    bölgeleri okur, onlar daha da öne çıkar ve kapsam bir daha genişlemez.
    """
    toplayici.topla(
        sahte_istemci({("DE", 27): [video_ogesi("d1", kategori="27")]}),
        sayac,
        tur="genis",
        bolgeler=["DE"],
        yol=yol,
        an=datetime(2026, 7, 29, 9, tzinfo=UTC),
    )
    toplayici.topla(
        sahte_istemci({("FR", 27): [video_ogesi(f"f{i}", kategori="27") for i in range(9)]}),
        sayac,
        tur="derin",
        bolgeler=["FR"],
        yol=yol,
        an=datetime(2026, 7, 29, 10, tzinfo=UTC),
    )

    baglanti = depo.baglan(yol)
    try:
        assert bolge.son_genis_kosu(baglanti) == "2026-07-29T09:00:00+00:00"
    finally:
        baglanti.close()
    assert bolge.derin_bolgeler(yol) == ["DE"]


def test_bolgeleri_getir_sirali(sahte_istemci):
    assert bolge.bolgeleri_getir(sahte_istemci({"_bolgeler": ["TR", "DE", "US"]})) == [
        "DE",
        "TR",
        "US",
    ]
