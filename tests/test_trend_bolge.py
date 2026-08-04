"""Bölge seçimi — derin taramanın kapsamı ölçülerek belirlenir, varsayılmaz.

⚠️ Zaman damgaları **göreli** kuruluyor. DW-32'de seçim penceresi (7 gün)
eklendiğinde sabit tarihli testler zaman bombasına dönüştü: `2026-07-29`
damgası 2026-08-06'da pencere dışına düşüp testi yanlış sebeple kırardı.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yt_automation import depo
from yt_automation.trend import bolge, toplayici


def once(gun: float = 0.0, saat: float = 0.0) -> datetime:
    """Şu andan `gun` + `saat` kadar önce."""
    return datetime.now(UTC) - timedelta(days=gun, hours=saat)


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
            # DE: 3 eğitim — kısıtsız listeden geliyor, çünkü 27'nin çartı yok
            ("DE", 0): [video_ogesi(f"de{i}", kategori="27") for i in range(3)],
            # TR: 1 eğitim + 2 müzik → yoğunluk 1, hacim 3
            ("TR", 0): [
                video_ogesi("tr1", kategori="27"),
                video_ogesi("trm1", kategori="10"),
                video_ogesi("trm2", kategori="10"),
            ],
            # FR: 2 bilim
            ("FR", 28): [video_ogesi(f"fr{i}", kategori="28") for i in range(2)],
        }
    )
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["TR", "DE", "FR"], yol=yol)

    assert bolge.derin_bolgeler(yol) == ["DE", "FR", "TR"]
    assert bolge.derin_bolgeler(yol, adet=2) == ["DE", "FR"]


def test_pencere_disindaki_kosu_sayilmaz(yol: Path, sayac, sahte_istemci, video_ogesi):
    """Eski koşular sıralamayı kirletmemeli — bölge tercihi güncel veriye dayanır."""
    toplayici.topla(
        sahte_istemci({("TR", 0): [video_ogesi(f"t{i}", kategori="27") for i in range(5)]}),
        sayac,
        tur="genis",
        bolgeler=["TR"],
        yol=yol,
        an=once(gun=30),
    )
    toplayici.topla(
        sahte_istemci({("DE", 0): [video_ogesi("d1", kategori="27")]}),
        sayac,
        tur="genis",
        bolgeler=["DE"],
        yol=yol,
        an=once(saat=1),
    )

    assert bolge.derin_bolgeler(yol) == ["DE"]


def test_pencere_icindeki_kosular_birlesir(yol: Path, sayac, sahte_istemci, video_ogesi):
    """DW-32: tek koşuya bakmak kırılgan.

    Bir bölge son koşumda hata almışsa (ilk canlı taramada 111 bölgenin hepsi
    404 aldı) sıralamadan tamamen düşerdi. Pencere bunu yumuşatıyor.
    """
    toplayici.topla(
        sahte_istemci({("TR", 0): [video_ogesi(f"t{i}", kategori="27") for i in range(5)]}),
        sayac,
        tur="genis",
        bolgeler=["TR"],
        yol=yol,
        an=once(gun=3),
    )
    # Dünkü koşumda TR hiç veri getirmedi; yalnızca DE döndü.
    toplayici.topla(
        sahte_istemci({("DE", 0): [video_ogesi("d1", kategori="27")]}),
        sayac,
        tur="genis",
        bolgeler=["DE"],
        yol=yol,
        an=once(gun=1),
    )

    assert bolge.derin_bolgeler(yol) == ["TR", "DE"], "TR pencereden düşmemeli"


def test_derin_kosu_siralamayi_kaydirmaz(yol: Path, sayac, sahte_istemci, video_ogesi):
    """Bölge tercihi yalnızca geniş taramadan türetilir.

    Aksi halde geri besleme kendi kendini besler: derin tarama zaten seçilmiş
    bölgeleri okur, onlar daha da öne çıkar ve kapsam bir daha genişlemez.
    """
    genis_an = once(saat=2)
    toplayici.topla(
        sahte_istemci({("DE", 0): [video_ogesi("d1", kategori="27")]}),
        sayac,
        tur="genis",
        bolgeler=["DE"],
        yol=yol,
        an=genis_an,
    )
    toplayici.topla(
        sahte_istemci({("FR", 0): [video_ogesi(f"f{i}", kategori="27") for i in range(9)]}),
        sayac,
        tur="derin",
        bolgeler=["FR"],
        yol=yol,
        an=once(saat=1),
    )

    baglanti = depo.baglan(yol)
    try:
        assert bolge.son_genis_kosu(baglanti) == genis_an.isoformat()
    finally:
        baglanti.close()
    assert bolge.derin_bolgeler(yol) == ["DE"]


# --- Kopya bölge eleme (DW-32) -------------------------------------------


def test_ayni_carti_donduren_bolge_elenir(yol: Path, sayac, sahte_istemci, video_ogesi):
    """Ölçülmüş gerçek: LI, CH çartının %100 kopyası.

    Liechtenstein 40 bin nüfuslu ve YouTube ona ayrı çart üretmiyor. Onu ayrı
    bölge saymak derin taramanın 20 yuvasından birini hiç yeni veri getirmeyen
    bir çağrıya harcamak olur.
    """
    ortak = [video_ogesi(f"ch{i}", kategori="27") for i in range(5)]
    istemci = sahte_istemci(
        {
            ("CH", 0): ortak,
            ("LI", 0): ortak,  # birebir aynı
            ("TR", 0): [video_ogesi(f"tr{i}", kategori="27") for i in range(3)],
        }
    )
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["CH", "LI", "TR"], yol=yol)

    secilen = bolge.derin_bolgeler(yol)
    assert "LI" not in secilen
    assert secilen == ["CH", "TR"]


def test_kismi_ortusme_elenmez(yol: Path, sayac, sahte_istemci, video_ogesi):
    """US ∩ GB %62 ölçüldü ve ikisi de listede kalmalı.

    Ortak dil örtüşme üretiyor ama %38'i ayrı ve o kısım bilgi taşıyor.
    Eşiği düşürmek gerçek pazarları elemeye başlar.
    """
    paylasilan = [video_ogesi(f"p{i}", kategori="27") for i in range(5)]
    istemci = sahte_istemci(
        {
            ("US", 0): paylasilan + [video_ogesi(f"us{i}", kategori="27") for i in range(5)],
            ("GB", 0): paylasilan + [video_ogesi(f"gb{i}", kategori="27") for i in range(5)],
        }
    )
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["US", "GB"], yol=yol)

    assert set(bolge.derin_bolgeler(yol)) == {"US", "GB"}


def test_temsilci_siralamada_onde_olan(yol: Path):
    """LI/CH çiftinde hangisinin kaldığı sıralamaya göre belirlenmeli, alfabeye göre değil."""
    kumeler = {"CH": frozenset({"a", "b", "c"}), "LI": frozenset({"a", "b", "c"})}

    assert bolge.kopya_bolgeler(kumeler, ["CH", "LI"]) == {"LI": "CH"}
    assert bolge.kopya_bolgeler(kumeler, ["LI", "CH"]) == {"CH": "LI"}


def test_bos_kumeler_cokmez(yol: Path):
    """Ölçümü olmayan bölge bölme hatası üretmemeli."""
    kumeler = {"TR": frozenset(), "DE": frozenset({"a"})}
    assert bolge.kopya_bolgeler(kumeler, ["TR", "DE"]) == {}


# --- Seçim raporu ---------------------------------------------------------


def test_secim_raporu_gerekce_veriyor(yol: Path, sayac, sahte_istemci, video_ogesi):
    """Seçim otomatik ama denetlenebilir olmalı: "neden TR yok" koda bakmadan görülmeli."""
    ortak = [video_ogesi(f"ch{i}", kategori="27") for i in range(5)]
    istemci = sahte_istemci(
        {
            ("CH", 0): ortak,
            ("LI", 0): ortak,
            ("TR", 0): [video_ogesi("tr1", kategori="27")],
        }
    )
    toplayici.topla(istemci, sayac, tur="genis", bolgeler=["CH", "LI", "TR"], yol=yol)

    rapor = {s["bolge"]: s["durum"] for s in bolge.secim_raporu(yol, adet=1)}
    assert rapor["CH"] == "seçildi"
    assert rapor["LI"] == "kopya → CH"
    assert rapor["TR"] == "sıra dışı", "adet=1 olduğu için sıraya girmedi"


def test_secim_raporu_bos_depoda_patlamaz(yol: Path):
    assert bolge.secim_raporu(yol) == []


def test_bolgeleri_getir_sirali(sahte_istemci):
    assert bolge.bolgeleri_getir(sahte_istemci({"_bolgeler": ["TR", "DE", "US"]})) == [
        "DE",
        "TR",
        "US",
    ]
