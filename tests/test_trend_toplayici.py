"""Trend toplayıcısı — kaydedilmiş yanıtlarla, canlı çağrı yok."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yt_automation import kota
from yt_automation.trend import bolge, toplayici


def test_video_ve_olcum_yazilir(yol: Path, sayac, sahte_istemci, video_ogesi, satirlar):
    istemci = sahte_istemci({("TR", 27): [video_ogesi("v1"), video_ogesi("v2")]})
    sonuc = toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR"], yol=yol)

    assert sonuc.cagri_sayisi == len(bolge.LISTELER)
    assert sonuc.video_sayisi == 2

    v = satirlar("SELECT * FROM video ORDER BY video_id")
    assert [s["video_id"] for s in v] == ["v1", "v2"]
    assert v[0]["kategori_id"] == 27
    assert v[0]["sure_sn"] == 10 * 60 + 30
    assert v[0]["kanal_adi"] == "Kanal v1"
    # DW-30'un dolduracağı alanlar bu görevde boş kalmalı.
    assert v[0]["sinif"] is None and v[0]["dil"] is None

    o = satirlar("SELECT * FROM olcum ORDER BY sira")
    assert [(s["bolge"], s["sira"], s["izlenme"]) for s in o] == [("TR", 1, 1000), ("TR", 2, 1000)]


def test_ayni_video_iki_listede_tek_olcum(yol: Path, sayac, sahte_istemci, video_ogesi, satirlar):
    """Bir video hem kategori listesinde hem kısıtsız listede çıkabilir.

    Tek koşuda iki satır yazılsaydı DW-29 aynı videoyu iki kez sayardı.
    """
    istemci = sahte_istemci(
        {
            ("TR", 27): [video_ogesi("dolgu"), video_ogesi("v1")],  # v1 → 2. sıra
            ("TR", 0): [video_ogesi("v1")],  # v1 → 1. sıra, daha iyi
        }
    )
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR"], yol=yol)

    o = satirlar("SELECT * FROM olcum WHERE video_id = 'v1'")
    assert len(o) == 1
    assert o[0]["sira"] == 1, "daha iyi sıra korunmalı"
    assert o[0]["liste_kategori"] == 0, "sıranın geldiği liste kaydedilmeli"


def test_bos_liste_hata_degil(yol: Path, sayac, sahte_istemci, satirlar):
    istemci = sahte_istemci({})  # her bileşim boş
    sonuc = toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR", "DE"], yol=yol)

    assert sonuc.hatalar == []
    assert sonuc.video_sayisi == 0
    assert len(satirlar("SELECT * FROM kosu")) == 1, "koşu yine de deftere yazılmalı"


def test_bir_bolgenin_hatasi_kosuyu_bitirmez(
    yol: Path, sayac, sahte_istemci, video_ogesi, satirlar
):
    istemci = sahte_istemci(
        {
            ("TR", 27): RuntimeError("403 quotaExceeded"),
            ("DE", 27): [video_ogesi("v1")],
        }
    )
    sonuc = toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR", "DE"], yol=yol)

    assert len(sonuc.hatalar) == 1
    assert sonuc.video_sayisi == 1, "hatalı bölge diğerlerini düşürmemeli"
    assert "1 bölge" in satirlar("SELECT * FROM kosu")[0]["hata"]


def test_tum_cagrilar_ayni_an_damgasini_tasir(
    yol: Path, sayac, sahte_istemci, video_ogesi, satirlar
):
    istemci = sahte_istemci({("TR", 27): [video_ogesi("v1")], ("DE", 28): [video_ogesi("v2")]})
    an = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR", "DE"], yol=yol, an=an)

    anlar = {s["an"] for s in satirlar("SELECT an FROM olcum")}
    assert anlar == {an.isoformat()}, "koşu içindeki tüm ölçümler aynı anı taşımalı"


# --- Kota ---------------------------------------------------------------


def test_cagri_basina_bir_birim(yol: Path, sayac, sahte_istemci, video_ogesi):
    istemci = sahte_istemci({("TR", 27): [video_ogesi("v1")]})
    sonuc = toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR", "DE"], yol=yol)

    beklenen = 2 * len(bolge.LISTELER)
    assert sonuc.cagri_sayisi == beklenen
    assert sonuc.harcanan_kota == beklenen
    assert kota.KaliciSayac(yol, surec="trend").surec_harcamasi == beklenen


def test_trend_tavani_kosuyu_temiz_durdurur(yol: Path, sayac, sahte_istemci, video_ogesi, satirlar):
    istemci = sahte_istemci({("TR", 27): [video_ogesi("v1")]})
    sonuc = toplayici.topla(
        istemci, sayac, tur="genis", bolgeler=["TR", "DE", "FR"], yol=yol, trend_tavani=4
    )

    assert sonuc.kota_bitti is True
    assert sonuc.cagri_sayisi == 4, "tavana kadar harcayıp durmalı"
    # O ana kadarki veri yazılmış olmalı — koşu geri alınmıyor.
    assert satirlar("SELECT * FROM video")


def test_rezerve_yukleme_payini_korur(yol: Path, sahte_istemci, video_ogesi):
    """Ortak bütçe yükleme payına inince trend toplamayı bırakır."""
    butce = kota.video_basina_maliyet() + 2
    sayac = kota.KaliciSayac(yol, butce=butce, surec="trend")
    istemci = sahte_istemci({("TR", 27): [video_ogesi("v1")]})

    sonuc = toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR", "DE"], yol=yol)

    assert sonuc.kota_bitti is True
    assert sonuc.cagri_sayisi == 2, "yalnızca rezerve dışındaki 2 birim harcanmalı"
    assert sayac.kalan >= kota.video_basina_maliyet()


def test_maliyet_tahmini_sayfalama_varsaymaz():
    assert toplayici.maliyet_tahmini(100) == 100 * len(bolge.LISTELER)


# --- Ayrıştırma ---------------------------------------------------------


@pytest.mark.parametrize(
    ("iso", "beklenen"),
    [
        ("PT10M30S", 630),
        ("PT1H2M3S", 3_723),
        ("PT45S", 45),
        ("P1DT2H", 93_600),
        ("P0D", 0),
        (None, None),
        ("", None),
    ],
)
def test_sure_ayristirma(iso, beklenen):
    assert toplayici._sure_saniye(iso) == beklenen


def test_eksik_istatistik_cokmez(yol: Path, sayac, sahte_istemci, video_ogesi, satirlar):
    """Gizli beğeni/yorum sayısında alanlar hiç gelmiyor."""
    oge = video_ogesi("v1")
    oge["statistics"] = {"viewCount": "500"}
    istemci = sahte_istemci({("TR", 27): [oge]})
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR"], yol=yol)

    o = satirlar("SELECT * FROM olcum")[0]
    assert o["izlenme"] == 500
    assert o["begeni"] is None and o["yorum"] is None
