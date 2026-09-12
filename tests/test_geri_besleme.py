"""Performans geri beslemesi — sahte HTTP, canlı çağrı yok.

En önemli testler `Video URL` ile `Bağlantı` ayrımını kilitleyenler: ilk
yazımda yanlış sütun okunuyordu ve modül **hata vermeden** dört adayın
dördünü de "eşleşmedi" sayıp boş rapor üretiyordu. Sessiz sıfır, bozuk
ölçümün en tehlikeli hâli — çalışan bir hattan ayırt edilemiyor.
"""

import pytest

from yt_automation import geri_besleme
from yt_automation.trend.notion import Aday


def _aday(baslik, video_url, *, talep=None, skor=None, baglanti=None):
    return Aday(
        kimlik="k" + baslik[:4],
        baslik=baslik,
        sayfa_url="https://notion.example/x",
        durum="Üretildi",
        talep=talep,
        bosluk_skoru=skor,
        baglanti=baglanti,
        video_url=video_url,
    )


def _video(kimlik, izlenme, *, begeni=0, yorum=0, baslik="Video"):
    return {
        "id": kimlik,
        "snippet": {"title": baslik, "publishedAt": "2026-08-10T10:00:00Z"},
        "statistics": {
            "viewCount": str(izlenme),
            "likeCount": str(begeni),
            "commentCount": str(yorum),
        },
    }


# --------------------------------------------------------------------------
# Kimlik çıkarma
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url,beklenen",
    [
        ("https://youtube.com/shorts/vZTMT09Qrpo", "vZTMT09Qrpo"),
        ("https://www.youtube.com/watch?v=MGuqAKqTK3E", "MGuqAKqTK3E"),
        ("https://youtu.be/hC49P3Ar32g", "hC49P3Ar32g"),
    ],
)
def test_video_kimligi_her_iki_bicimden_cikariliyor(url, beklenen):
    """Hat iki biçimde de yükleme yaptı; ikisi de aynı kanalın videosu."""
    assert geri_besleme.video_kimligi(url) == beklenen


def test_bozuk_baglanti_olcumu_durdurmuyor():
    """Tek bozuk satır yüzünden bütün ölçüm durmamalı."""
    assert geri_besleme.video_kimligi("") is None
    assert geri_besleme.video_kimligi("https://example.com/sayfa") is None


# --------------------------------------------------------------------------
# Sütun ayrımı — asıl hata buydu
# --------------------------------------------------------------------------
def test_video_url_okunuyor_baglanti_DEGIL(monkeypatch):
    """⚠️ `baglanti` konunun KAYNAĞI (Wikipedia), `video_url` hattın ÇIKTISI.

    İlk yazımda `baglanti` okunuyordu: dört adayın dördü de eşleşmedi
    sayıldı, hata verilmeden boş rapor üretildi.
    """
    aday = _aday(
        "Tycho Brahe",
        "https://youtube.com/shorts/vZTMT09Qrpo",
        talep=5815.0,
        skor=-1.03,
        baglanti="https://en.wikipedia.org/wiki/Tycho_Brahe",
    )
    monkeypatch.setattr(geri_besleme.notion, "token_al", lambda: "sahte")
    monkeypatch.setattr(geri_besleme.notion, "adaylari_getir", lambda **_k: [aday])
    monkeypatch.setattr(
        geri_besleme,
        "video_istatistikleri",
        lambda kimlikler, **_k: {"vZTMT09Qrpo": _video("vZTMT09Qrpo", 106, begeni=4)},
    )

    rapor = geri_besleme.olc()

    assert rapor.eslesmeyen == []
    assert len(rapor.olcumler) == 1
    olcum = rapor.olcumler[0]
    assert olcum.izlenme == 106
    assert olcum.talep == 5815.0
    # Wikipedia adresi video URL'si olarak sızmamalı.
    assert "wikipedia" not in olcum.video_url


def test_yalnizca_wikipedia_baglantisi_olan_aday_eslesmiyor(monkeypatch):
    aday = _aday("Konu", None, baglanti="https://en.wikipedia.org/wiki/Konu")
    monkeypatch.setattr(geri_besleme.notion, "token_al", lambda: "sahte")
    monkeypatch.setattr(geri_besleme.notion, "adaylari_getir", lambda **_k: [aday])
    monkeypatch.setattr(geri_besleme, "video_istatistikleri", lambda k, **_kw: {})

    rapor = geri_besleme.olc()
    assert rapor.olcumler == []
    assert rapor.eslesmeyen == ["Konu"]


def test_private_video_eslesmeyen_sayiliyor_hata_degil(monkeypatch):
    """Hat videoları private yüklüyor (kanal sahibinin kararı). Data API
    private videoyu döndürmez — bu eksiklik HATA DEĞİL."""
    aday = _aday("Gizli", "https://youtube.com/shorts/AAAAAAAAAAA")
    monkeypatch.setattr(geri_besleme.notion, "token_al", lambda: "sahte")
    monkeypatch.setattr(geri_besleme.notion, "adaylari_getir", lambda **_k: [aday])
    monkeypatch.setattr(geri_besleme, "video_istatistikleri", lambda k, **_kw: {})

    rapor = geri_besleme.olc()
    assert rapor.olcumler == []
    assert rapor.eslesmeyen == ["Gizli"]


# --------------------------------------------------------------------------
# Güven — az örneklemde kesinlik iddia edilmemeli
# --------------------------------------------------------------------------
def test_az_orneklemde_guven_yok_deniyor():
    rapor = geri_besleme.Rapor(
        olcumler=[
            geri_besleme.Olcum(
                baslik=f"k{i}",
                video_kimligi=f"v{i}",
                video_url="",
                talep=float(i),
                bosluk_skoru=0.0,
                sinif=None,
                kaynak=None,
                izlenme=i,
                begeni=0,
                yorum=0,
                yayin_tarihi="",
                video_basligi="",
            )
            for i in range(4)
        ]
    )
    assert rapor.guven == "yok"


def test_uc_altinda_korelasyon_hesaplanmiyor():
    """İki noktadan geçen her sıralama mükemmel uyumlu görünür — anlamsız."""
    rapor = geri_besleme.Rapor(
        olcumler=[
            geri_besleme.Olcum(
                baslik="a",
                video_kimligi="a",
                video_url="",
                talep=10.0,
                bosluk_skoru=None,
                sinif=None,
                kaynak=None,
                izlenme=5,
                begeni=0,
                yorum=0,
                yayin_tarihi="",
                video_basligi="",
            ),
            geri_besleme.Olcum(
                baslik="b",
                video_kimligi="b",
                video_url="",
                talep=20.0,
                bosluk_skoru=None,
                sinif=None,
                kaynak=None,
                izlenme=1,
                begeni=0,
                yorum=0,
                yayin_tarihi="",
                video_basligi="",
            ),
        ]
    )
    assert rapor.talep_izlenme_uyumu() is None


def test_ters_siralama_negatif_korelasyon_veriyor():
    """Tamamen ters sıralamada katsayı −1 olmalı."""
    veriler = [(100.0, 1), (200.0, 2), (300.0, 3), (400.0, 4)]
    rapor = geri_besleme.Rapor(
        olcumler=[
            geri_besleme.Olcum(
                baslik=f"k{i}",
                video_kimligi=f"v{i}",
                video_url="",
                talep=t,
                # izlenme bilerek TERS: en talepli en az izlenen
                bosluk_skoru=None,
                sinif=None,
                kaynak=None,
                izlenme=5 - iz,
                begeni=0,
                yorum=0,
                yayin_tarihi="",
                video_basligi="",
            )
            for i, (t, iz) in enumerate(veriler)
        ]
    )
    assert rapor.talep_izlenme_uyumu() == pytest.approx(-1.0)


def test_2026_08_12_gercek_olcumu_POZITIF_cikiyor():
    """⚠️ İLK OKUMAM YANLIŞTI — kayda geçiyor.

    William Hardham'ın en yüksek talebe (33.862) karşılık en az izlenmelerden
    birini (31) almasına bakıp "huninin sinyali TERS çalışıyor" demiştim.
    Sıralama korelasyonu hesaplanınca çıkan sonuç bunun tersi: **+0,6**.
    İki uç noktaya bakıp genelleme yapmak, ölçüm yerine örüntü uydurmaktı.

    Gerçek veri (2026-08-12, hepsi kanalın ilk üç günü):

        konu                     talep   izlenme
        William Hardham          33862        31
        Tycho Brahe               5815       106
        Second Anglo-Dutch War    2598         0   (private)
        Friedrich Hayek           2305         3

    ⚠️ Bu +0,6 da bir kanıt DEĞİL: n=4, kanal 1 aboneli ve 3 günlük. Doğru
    ifade "huninin öngörüsü henüz doğrulanmadı" — ne doğrulandı ne çürütüldü.
    Testin işi, yanlış okumanın sessizce geri gelmesini engellemek.
    """
    veriler = [(33862.0, 31), (5815.0, 106), (2598.0, 0), (2305.0, 3)]
    rapor = geri_besleme.Rapor(
        olcumler=[
            geri_besleme.Olcum(
                baslik=f"k{i}",
                video_kimligi=f"v{i}",
                video_url="",
                talep=t,
                bosluk_skoru=None,
                sinif=None,
                kaynak=None,
                izlenme=iz,
                begeni=0,
                yorum=0,
                yayin_tarihi="",
                video_basligi="",
            )
            for i, (t, iz) in enumerate(veriler)
        ]
    )
    assert rapor.talep_izlenme_uyumu() == pytest.approx(0.6)


def test_sabit_degerlerde_korelasyon_tanimsiz():
    rapor = geri_besleme.Rapor(
        olcumler=[
            geri_besleme.Olcum(
                baslik=f"k{i}",
                video_kimligi=f"v{i}",
                video_url="",
                talep=5.0,
                bosluk_skoru=None,
                sinif=None,
                kaynak=None,
                izlenme=i,
                begeni=0,
                yorum=0,
                yayin_tarihi="",
                video_basligi="",
            )
            for i in range(4)
        ]
    )
    assert rapor.talep_izlenme_uyumu() is None


# --------------------------------------------------------------------------
# Sıralama ve özet
# --------------------------------------------------------------------------
def test_olcumler_izlenmeye_gore_siralaniyor():
    rapor = geri_besleme.Rapor(
        olcumler=[
            geri_besleme.Olcum(
                baslik=ad,
                video_kimligi=ad,
                video_url="",
                talep=None,
                bosluk_skoru=None,
                sinif=None,
                kaynak=None,
                izlenme=iz,
                begeni=0,
                yorum=0,
                yayin_tarihi="",
                video_basligi="",
            )
            for ad, iz in [("az", 3), ("cok", 546), ("orta", 106)]
        ]
    )
    assert [o.baslik for o in rapor.sirala()] == ["cok", "orta", "az"]


def test_etkilesim_orani_sifir_izlenmede_patlamiyor():
    olcum = geri_besleme.Olcum(
        baslik="x",
        video_kimligi="x",
        video_url="",
        talep=None,
        bosluk_skoru=None,
        sinif=None,
        kaynak=None,
        izlenme=0,
        begeni=0,
        yorum=0,
        yayin_tarihi="",
        video_basligi="",
    )
    assert olcum.etkilesim_orani == 0.0


def test_anahtar_yoksa_acik_hata(monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(geri_besleme.GeriBeslemeHatasi, match="YOUTUBE_API_KEY"):
        geri_besleme.video_istatistikleri(["abc"])


def test_bos_kimlik_listesi_aga_cikmiyor(monkeypatch):
    def patlat(*_a, **_k):  # pragma: no cover - çağrılmamalı
        raise AssertionError("boş listede ağa çıkılmamalı")

    monkeypatch.setattr(geri_besleme.requests, "get", patlat)
    assert geri_besleme.video_istatistikleri([]) == {}
