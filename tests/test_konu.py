"""Wikidata tabanlı konu sınıflandırma.

Kimlikler 2026-07-29'da Wikidata'dan tek tek doğrulandı; buradaki testler
eşleme mantığını koruyor, kimliklerin doğruluğunu değil (o `konu.py`
yorumlarında kayıtlı).
"""

import pytest

from yt_automation.trend import konu


@pytest.mark.parametrize(
    ("tipler", "beklenen"),
    [
        (["Q3024240", "Q48349"], "tarih"),  # Osmanlı İmparatorluğu
        (["Q178561"], "tarih"),  # muharebe
        (["Q336"], "bilim"),
        (["Q12136"], "bilim"),  # hastalık
        (["Q7278"], "diger"),  # siyasi parti
        (["Q11424"], "diger"),  # film
        (["Q5"], "belirsiz"),  # insan — LLM'e gider
        ([], "diger"),
        (["Q999999"], "diger"),  # tanımadığımız tip
    ],
)
def test_siniflandirma(tipler, beklenen):
    assert konu.siniflandir(tipler) == beklenen


def test_dislama_tarihten_once_gelir():
    """ "Gladyatör (film)" tarihî bir konuyu işler ama bizim için filmdir.

    Sıra ters olsaydı kurgu eserler tarih diye sınıflanır ve aday listesi
    film önerileriyle dolardı.
    """
    assert konu.siniflandir(["Q11424", "Q3024240"]) == "diger"
    assert konu.siniflandir(["Q482994", "Q336"]) == "diger"


def test_belirsiz_tarihe_yenilir():
    """Kişi **ve** tarihî olay etiketi varsa tarih kazanmalı — belirsiz değil."""
    assert konu.siniflandir(["Q5", "Q13418847"]) == "tarih"


# --- Kişiler ------------------------------------------------------------
#
# İlk canlı koşumda 400 makalenin 193'ü Q5 (insan) çıktı. Bu katman olmadan
# belirsiz kuyruğu neredeyse tüm listeyi kapsıyordu.


@pytest.mark.parametrize(
    ("varlik", "beklenen", "kim"),
    [
        ({"meslekler": ["Q116"], "olum": 1481}, "tarih", "Mehmed II — hükümdar, ö.1481"),
        ({"meslekler": ["Q901"], "olum": 1955}, "bilim", "Einstein — bilim insanı"),
        ({"meslekler": ["Q901"], "olum": None}, "bilim", "yaşayan bilim insanı da konudur"),
        ({"meslekler": ["Q937857"], "olum": None}, "diger", "Ronaldo — futbolcu, yaşıyor"),
        ({"meslekler": ["Q177220"], "olum": None}, "diger", "Taylor Swift — şarkıcı, yaşıyor"),
        ({"meslekler": ["Q1097498"], "olum": None}, "diger", "yaşayan devlet başkanı → güncel"),
        ({"meslekler": ["Q33999"], "olum": 2010}, "belirsiz", "ölmüş oyuncu → LLM"),
    ],
)
def test_kisi_siniflandirma(varlik, beklenen, kim):
    assert konu.siniflandir(["Q5"], varlik) == beklenen, kim


@pytest.mark.parametrize(
    ("varlik", "kim"),
    [
        ({"meslekler": ["Q1028181"], "olum": 1954}, "Frida Kahlo — ressam"),
        ({"meslekler": ["Q36834"], "olum": 1883}, "Richard Wagner — besteci"),
        ({"meslekler": ["Q33999"], "olum": 2008}, "Paul Newman — oyuncu"),
    ],
)
def test_olmus_sanatci_tarih_degil(varlik, kim):
    """İlk canlı koşumda üçü de "tarih" çıkmıştı.

    Sebep "1975'ten önce ölen herkes tarihîdir" kuralıydı. Ölmüş bir ressam
    tarih konusu değil, kültür konusu — kural kaldırıldı, meslek zorunlu oldu.
    """
    assert konu.siniflandir(["Q5"], varlik) == "belirsiz", kim


def test_hekimlik_bilim_garantisi_degil():
    """Graeme Garden — yaşayan komedyen, tıp okuduğu için `Q39631` taşıyor.

    İlk canlı koşumda listenin en tepesinde "bilim" olarak çıktı.
    """
    assert konu.siniflandir(["Q5"], {"meslekler": ["Q39631"], "olum": None}) == "diger"


def test_kisi_verisi_yoksa_belirsiz_kalir():
    """Varlık bilgisi gelmezse karar verilemez — LLM'e gitmeli."""
    assert konu.siniflandir(["Q5"]) == "belirsiz"


def test_kisi_tipi_ozel_tipe_yenilir():
    """Hem Q5 hem tarihî olay etiketi varsa özel tip kazanır."""
    assert konu.siniflandir(["Q5", "Q3024240"], {"meslekler": [], "olum": None}) == "tarih"


def test_tip_kumeleri_cakismiyor():
    """Bir kimlik iki kümede olursa sınıf sıraya bağlı ve sessizce kırılgan olur."""
    kumeler = [
        set(konu.TARIH_TIPLERI),
        set(konu.BILIM_TIPLERI),
        set(konu.DISLANAN_TIPLERI),
        set(konu.BELIRSIZ_TIPLERI),
    ]
    for i, a in enumerate(kumeler):
        for b in kumeler[i + 1 :]:
            assert not (a & b), f"çakışan kimlik: {a & b}"
