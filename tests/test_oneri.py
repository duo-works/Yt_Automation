"""YouTube arama önerileri kaynağı (DW-111).

Bu dosyada canlı çağrı yok: uç ücretsiz ama gayriresmî, CI'da ona bağlanmak
testleri Google'ın o günkü keyfine bağlar. Ağ katmanı sahte yanıtla
sürülüyor; kilitlenen şey **ayrıştırma, kodlama ve yumuşak düşme.**
"""

import json
from pathlib import Path

import pytest

from yt_automation import depo
from yt_automation.trend import gtrends, oneri


def _govde(sorgu: str, oneriler: list[str], kodlama: str = "utf-8") -> bytes:
    """Ucun gerçek gövde biçimi — ölçüldü 2026-08-09."""
    return json.dumps([sorgu, oneriler, [], {}], ensure_ascii=False).encode(kodlama)


class _SahteBaslik:
    def __init__(self, kodlama: str | None):
        self._kodlama = kodlama

    def get_content_charset(self) -> str | None:
        return self._kodlama


class _SahteYanit:
    def __init__(self, ham: bytes, kodlama: str | None = "utf-8"):
        self._ham = ham
        self.headers = _SahteBaslik(kodlama)

    def read(self) -> bytes:
        return self._ham

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture(autouse=True)
def beklemesiz(monkeypatch):
    """Testler ucun nezaket beklemesini ödemesin."""
    monkeypatch.setattr(oneri.time, "sleep", lambda _: None)


@pytest.fixture(autouse=True)
def tohum_dosyasi_yok(monkeypatch):
    """Geliştiricinin kendi `YT_ONERI_TOHUM`'u testleri kaydırmasın."""
    monkeypatch.delenv(oneri.TOHUM_DEGISKENI, raising=False)


def _ucu_sabitle(
    monkeypatch, ham: bytes, kaydet: list | None = None, kodlama: str | None = "utf-8"
):
    def sahte(istek, timeout=None):
        if kaydet is not None:
            kaydet.append(istek.full_url)
        return _SahteYanit(ham, kodlama)

    monkeypatch.setattr(oneri.urllib.request, "urlopen", sahte)


def test_geo_dile_ve_ulkeye_ayrilir():
    assert oneri._coz("en-US") == ("en", "US")
    assert oneri._coz("es-MX") == ("es", "MX")
    # Ülkesiz tohum dosyası ya da elle verilen değer çökmemeli.
    assert oneri._coz("tr") == ("tr", "TR")


def test_oneriler_ayristirilir(monkeypatch):
    _ucu_sabitle(monkeypatch, _govde("ancient", ["ancient", "ancient rome", "ancient egypt"]))
    assert oneri.onerileri_cek("ancient", "en-US") == ["ancient rome", "ancient egypt"]


def test_tohumun_kendisi_terim_sayilmaz(monkeypatch):
    """İlk öğe genelde tohumun yankısı — bilinen şeyi boruya yazmanın değeri yok."""
    _ucu_sabitle(monkeypatch, _govde("who was", ["who was", "who was cleopatra"]))
    assert oneri.onerileri_cek("who was", "en-US") == ["who was cleopatra"]


def test_utf8_govde_okunur(monkeypatch):
    _ucu_sabitle(monkeypatch, _govde("imperio", ["imperio romano para niños"]))
    assert oneri.onerileri_cek("imperio", "es-ES") == ["imperio romano para niños"]


def test_latin1_govde_de_okunur(monkeypatch):
    """⚠️ Kodlama User-Agent'a göre değişiyor (ölçüldü 2026-08-09).

    Repo'nun kimlikli UA'sıyla uç `charset=iso-8859-1` dönüyor; UTF-8
    sabitleyen ilk sürüm "quién fue"yi "qui�n fue" yapıyordu ve bu sessiz
    bir bozulma — terim yazılır, yalnızca Wikipedia'da hiç eşleşmez.
    """
    _ucu_sabitle(
        monkeypatch,
        _govde("quién fue", ["quién fue cleopatra"], kodlama="latin-1"),
        kodlama="iso-8859-1",
    )
    assert oneri.onerileri_cek("quién fue", "es-ES") == ["quién fue cleopatra"]


def test_kodlama_beyan_edilmezse_utf8_varsayilir(monkeypatch):
    _ucu_sabitle(monkeypatch, _govde("imperio", ["imperio romano niños"]), kodlama=None)
    assert oneri.onerileri_cek("imperio", "es-ES") == ["imperio romano niños"]


def test_taninmayan_kodlama_hata_verir(monkeypatch):
    """Uydurma charset sessizce boş dönmemeli."""
    _ucu_sabitle(monkeypatch, _govde("q", ["bir şey"]), kodlama="yok-boyle-kodlama")
    with pytest.raises(oneri.OneriHatasi):
        oneri.onerileri_cek("q", "es-ES")


def test_dil_ve_ulke_istege_gecer(monkeypatch):
    cagrilar: list[str] = []
    _ucu_sabitle(monkeypatch, _govde("q", ["bir sonuç"]), kaydet=cagrilar)
    oneri.onerileri_cek("q", "es-MX")
    assert "hl=es" in cagrilar[0]
    assert "gl=MX" in cagrilar[0]
    assert "ds=yt" in cagrilar[0], "Google Web değil YouTube önerileri istenmeli"


def test_bozuk_govde_hata_verir(monkeypatch):
    _ucu_sabitle(monkeypatch, b"<html>hata</html>")
    with pytest.raises(oneri.OneriHatasi):
        oneri.onerileri_cek("ancient", "en-US")


def test_beklenmeyen_bicim_hata_verir(monkeypatch):
    """Geçerli JSON ama beklenen şekil değil — sessizce boş dönmemeli."""
    _ucu_sabitle(monkeypatch, json.dumps({"suggestions": []}).encode())
    with pytest.raises(oneri.OneriHatasi):
        oneri.onerileri_cek("ancient", "en-US")


def test_ag_hatasi_oneri_hatasina_cevrilir(monkeypatch):
    def patlat(istek, timeout=None):
        raise TimeoutError("zaman aşımı")

    monkeypatch.setattr(oneri.urllib.request, "urlopen", patlat)
    with pytest.raises(oneri.OneriHatasi):
        oneri.onerileri_cek("ancient", "en-US")


def test_terimler_tekrarsiz(monkeypatch):
    """İki tohum aynı öneriyi döndürebilir; boruya bir kez girmeli."""
    _ucu_sabitle(monkeypatch, _govde("x", ["Ancient Rome", "ancient rome", "Pompeii"]))
    terimler = oneri.terimleri_cek("en-US")
    metinler = [t.terim for t in terimler]
    assert metinler.count("Ancient Rome") == 1
    assert "ancient rome" not in metinler, "büyük/küçük harf farkı tekrar sayılmamalı"
    assert "Pompeii" in metinler


def test_tohumsuz_pazar_bos_doner(monkeypatch):
    """Tanımsız pazar hata değil — kaynak o pazarda sessizce yok."""
    _ucu_sabitle(monkeypatch, _govde("x", ["bir şey"]))
    assert oneri.terimleri_cek("fr-FR") == []


def test_tum_tohumlar_duserse_hata(monkeypatch):
    """Kırık uç "bugün öneri yokmuş" gibi görünmemeli."""

    def patlat(istek, timeout=None):
        raise TimeoutError("uç kapalı")

    monkeypatch.setattr(oneri.urllib.request, "urlopen", patlat)
    with pytest.raises(oneri.OneriHatasi):
        oneri.terimleri_cek("en-US")


def test_tek_tohumun_hatasi_digerlerini_dusurmez(monkeypatch):
    cagri = {"n": 0}

    def sahte(istek, timeout=None):
        cagri["n"] += 1
        if cagri["n"] == 1:
            raise TimeoutError("ilk tohum düştü")
        return _SahteYanit(_govde("x", ["Pompeii"]))

    monkeypatch.setattr(oneri.urllib.request, "urlopen", sahte)
    terimler = oneri.terimleri_cek("en-US")
    assert [t.terim for t in terimler] == ["Pompeii"]


def test_tohum_dosyasi_varsayilanin_yerine_gecer(tmp_path: Path, monkeypatch):
    dosya = tmp_path / "tohum.txt"
    dosya.write_text("kayıp şehir\n// yorum\n\nunutulmuş imparatorluk\n", encoding="utf-8")
    monkeypatch.setenv(oneri.TOHUM_DEGISKENI, str(dosya))
    assert oneri.tohumlar("en") == ("kayıp şehir", "unutulmuş imparatorluk")


def test_var_olmayan_tohum_dosyasi_varsayilana_duser(monkeypatch):
    monkeypatch.setenv(oneri.TOHUM_DEGISKENI, "/yok/boyle/bir/dosya.txt")
    assert oneri.dosya_yolu() is None
    assert oneri.tohumlar("en") == oneri.VARSAYILAN_TOHUMLAR["en"]


def test_terimler_ayni_boruya_girer(yol: Path, monkeypatch):
    """ADR-0010: kaynak çoğalır, boru tektir — kendi yazma kodu yok."""
    monkeypatch.setattr(gtrends, "_siniflandir", lambda dil, baslik: ("tarih", "Q1"))
    monkeypatch.setattr(
        gtrends.wikipedia,
        "makale_serisi",
        lambda dil, baslik, bas, son: [
            gtrends.wikipedia.Okunma(dil=dil, baslik=baslik, gun="2026-08-02", okunma=4_000)
        ],
    )

    sonuc = oneri.isle(
        yol,
        pazarlar=("en",),
        terim_getir=lambda geo: [gtrends.TrendTerimi(terim="Pompeii", geo=geo, trafik="")],
        makale_bul=lambda dil, terim: terim.replace(" ", "_"),
    )

    # en → ("en-US", "en-GB"): iki coğrafya, aynı terim. İkincisi zaten
    # `makale`'de olduğu için yeniden yazılmamalı.
    assert sonuc.terim == 2
    assert sonuc.yazilan == 1

    baglanti = depo.baglan(yol)
    try:
        satir = baglanti.execute("SELECT dil, baslik, sinif FROM makale").fetchall()
    finally:
        baglanti.close()
    assert [tuple(s) for s in satir] == [("en", "Pompeii", "tarih")]


def test_youtube_kotasina_dokunmaz(yol: Path, monkeypatch):
    """Sondaj bütçesiyle yarışmamalı: hiçbir YouTube API çağrısı yok."""
    monkeypatch.setattr(gtrends, "_siniflandir", lambda dil, baslik: ("belirsiz", None))
    monkeypatch.setattr(gtrends.wikipedia, "makale_serisi", lambda *a, **k: [])

    oneri.isle(
        yol,
        pazarlar=("en",),
        terim_getir=lambda geo: [gtrends.TrendTerimi(terim="Pompeii", geo=geo, trafik="")],
        makale_bul=lambda dil, terim: terim,
    )

    baglanti = depo.baglan(yol)
    try:
        harcama = baglanti.execute("SELECT COALESCE(SUM(birim), 0) FROM kota_harcama").fetchone()[0]
    finally:
        baglanti.close()
    assert harcama == 0
