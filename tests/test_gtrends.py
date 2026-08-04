"""Google Trends kaynağı — gün-içi keşif (DW-55).

Hiç canlı çağrı yok: RSS ve Wikipedia uçları enjekte ediliyor. Testlerin
kilitlediği asıl şey **boru deseni** (ADR-0010): GTrends kendi kuyruğunu
kurmuyor, mevcut hattın girişine yazıyor.
"""

from pathlib import Path

from yt_automation import cli, depo
from yt_automation.trend import gtrends

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0">
  <channel>
    <item>
      <title>pompeii eruption</title>
      <ht:approx_traffic>50000+</ht:approx_traffic>
    </item>
    <item>
      <title>bir dizi oyuncusu</title>
      <ht:approx_traffic>200+</ht:approx_traffic>
    </item>
  </channel>
</rss>"""


def test_rss_ayristirilir_ve_trafik_okunur():
    import xml.etree.ElementTree as ET

    agac = ET.fromstring(RSS)
    ogeler = list(agac.iter("item"))
    assert len(ogeler) == 2
    # Modül `ht:` ad alanını çözebilmeli — çözemezse trafik sessizce boşalır.
    assert ogeler[0].findtext(f"{gtrends._HT}approx_traffic") == "50000+"


def test_cagrisim_eslesme_sayilmaz(monkeypatch):
    """Arama motoru alakasız ama "popüler" bir makale döndürebilir.

    "tarek mansour" → "Kalshi" bir çağrışımdır, eşleşme değil; çağrışımı
    makale saymak boruya çöp doldurur. Alaka ölçümü sondajınkiyle aynı.
    """

    def sahte_ara(dil, terim):
        # Gerçek `makale_ara`nın alaka filtresini test ediyoruz: sahte HTTP
        # katmanı yerine fonksiyonun kendi mantığını çağırıyoruz.
        return gtrends.makale_ara(dil, terim)

    import io
    import json

    def sahte_urlopen(istek, timeout=None):
        return io.BytesIO(json.dumps({"query": {"search": [{"title": "Kalshi"}]}}).encode())

    monkeypatch.setattr(gtrends.urllib.request, "urlopen", sahte_urlopen)
    assert sahte_ara("en", "tarek mansour") is None


def test_eslesen_baslik_dondurulur(monkeypatch):
    import io
    import json

    def sahte_urlopen(istek, timeout=None):
        return io.BytesIO(
            json.dumps({"query": {"search": [{"title": "Pompeii eruption"}]}}).encode()
        )

    monkeypatch.setattr(gtrends.urllib.request, "urlopen", sahte_urlopen)
    assert gtrends.makale_ara("en", "pompeii eruption") == "Pompeii_eruption"


def test_konu_boruya_yazilir_seriyle_birlikte(yol: Path, monkeypatch):
    """Kritik: `okunma` satırı olmayan konu ne sıçrama detektörüne ne sondaj
    kuyruğuna girer. Keşif ancak talep kanıtıyla boruya girerse iş görür."""
    monkeypatch.setattr(
        gtrends,
        "_siniflandir",
        lambda dil, baslik: ("tarih", "Q1234"),
    )
    monkeypatch.setattr(
        gtrends.wikipedia,
        "makale_serisi",
        lambda dil, baslik, bas, son: [
            gtrends.wikipedia.Okunma(dil=dil, baslik=baslik, gun="2026-08-01", okunma=1_200),
            gtrends.wikipedia.Okunma(dil=dil, baslik=baslik, gun="2026-08-02", okunma=9_000),
        ],
    )

    sonuc = gtrends.isle(
        yol,
        pazarlar=("en",),
        terim_getir=lambda geo: [gtrends.TrendTerimi("pompeii", geo, "50000+")],
        makale_bul=lambda dil, terim: "Pompeii",
    )

    assert sonuc.yazilan == 1
    assert sonuc.siniflar == {"tarih": 1}
    baglanti = depo.baglan(yol)
    try:
        makale = baglanti.execute("SELECT * FROM makale WHERE baslik = 'Pompeii'").fetchone()
        assert makale["sinif_kaynagi"] == "gtrends"
        assert makale["qid"] == "Q1234"
        seri = baglanti.execute("SELECT COUNT(*) n FROM okunma WHERE baslik='Pompeii'").fetchone()
        assert seri["n"] == 2, "okunma serisi olmadan konu boruya girmez"
    finally:
        baglanti.close()


def test_bilinen_konu_yeniden_islenmez(yol: Path, monkeypatch):
    """Saatlik koşumda aynı konuyu her seferinde yeniden çekmek, aynı veriyi
    saatte bir indirmek olurdu."""
    with depo.yazma_islemi(yol) as baglanti:
        baglanti.execute(
            "INSERT INTO makale (dil, baslik, qid, sinif, sinif_kaynagi, ilk_gorulme)"
            " VALUES ('en', 'Pompeii', 'Q1', 'tarih', 'wikidata', '2026-08-01')"
        )

    def patlayan(*a, **k):
        raise AssertionError("bilinen konu için sınıflandırma çağrıldı")

    monkeypatch.setattr(gtrends, "_siniflandir", patlayan)
    sonuc = gtrends.isle(
        yol,
        pazarlar=("en",),
        terim_getir=lambda geo: [gtrends.TrendTerimi("pompeii", geo, "1000+")],
        makale_bul=lambda dil, terim: "Pompeii",
    )
    assert sonuc.eslesen == 2, "iki geo (US, GB) — eşleşme sayılır"
    assert sonuc.yazilan == 0


def test_bir_cografyanin_hatasi_digerini_dusurmez(yol: Path):
    def terim_getir(geo):
        if geo == "US":
            raise RuntimeError("503")
        return [gtrends.TrendTerimi("madrid", geo, "5000+")]

    sonuc = gtrends.isle(
        yol,
        pazarlar=("en",),
        terim_getir=terim_getir,
        makale_bul=lambda dil, terim: None,
    )
    assert len(sonuc.hatalar) == 1
    assert sonuc.terim == 1, "GB terimleri yine geldi"


def test_saatlik_betik_gtrends_adimini_kosum_dusurmeden_cagirir():
    """Dış RSS ucu bizim hattımızın sağlığı değil: kırıldığında bildirim
    göndermek DW-47'nin bitirdiği yanlış alarm düzenine dönmek olurdu."""
    betik = (Path(__file__).resolve().parent.parent / "scripts" / "saatlik-tarama.sh").read_text(
        encoding="utf-8"
    )
    assert "konu gtrends" in betik
    bolum = betik.split("konu gtrends")[1].split("fi")[0]
    assert "basarisiz=1" not in bolum, "GTrends hatası koşumu düşürmemeli"
    assert "UYARI" in bolum


def test_cli_kuru_kosum_yazmaz(yol: Path, monkeypatch, capsys):
    monkeypatch.setattr(depo, "varsayilan_yol", lambda: yol)
    monkeypatch.setattr(
        gtrends, "terimleri_cek", lambda geo: [gtrends.TrendTerimi("pompeii", geo, "5000+")]
    )
    monkeypatch.setattr(gtrends, "makale_ara", lambda dil, terim: "Pompeii")

    assert cli.main(["konu", "gtrends", "--kuru"]) == 0
    cikti = capsys.readouterr().out
    assert "KURU KOŞUM" in cikti
    assert "Pompeii" in cikti

    baglanti = depo.baglan(yol)
    try:
        assert baglanti.execute("SELECT COUNT(*) n FROM makale").fetchone()["n"] == 0
    finally:
        baglanti.close()


def test_ilgisiz_konu_icin_seri_cekilmez(yol: Path, monkeypatch):
    """Trend listesi magazin/spor/hava durumu ağırlıklı; hepsine pageviews
    çağrısı yapmak istek sayısını dörde katlar ve hiçbir soruyu cevaplamaz."""
    monkeypatch.setattr(gtrends, "_siniflandir", lambda dil, baslik: ("diger", "Q9"))

    def patlayan(*a, **k):
        raise AssertionError("`diger` konu için okunma serisi çekildi")

    monkeypatch.setattr(gtrends.wikipedia, "makale_serisi", patlayan)
    sonuc = gtrends.isle(
        yol,
        pazarlar=("en",),
        terim_getir=lambda geo: [gtrends.TrendTerimi("jerry jones", geo, "200+")],
        makale_bul=lambda dil, terim: "Jerry_Jones",
    )
    assert sonuc.siniflar == {"diger": 1}


def test_belirsiz_konu_seri_alir_llm_kuyruguna_girsin(yol: Path, monkeypatch):
    """`belirsiz` LLM kuyruğuna girecek ve orada tarih/bilim çıkabilir —
    okunma satırı olmadan `siniflandirici.bekleyenler` onu göremez."""
    monkeypatch.setattr(gtrends, "_siniflandir", lambda dil, baslik: ("belirsiz", "Q9"))
    monkeypatch.setattr(
        gtrends.wikipedia,
        "makale_serisi",
        lambda dil, baslik, bas, son: [
            gtrends.wikipedia.Okunma(dil=dil, baslik=baslik, gun="2026-08-02", okunma=5_000)
        ],
    )
    gtrends.isle(
        yol,
        pazarlar=("en",),
        terim_getir=lambda geo: [gtrends.TrendTerimi("x", geo, "200+")],
        makale_bul=lambda dil, terim: "Belirsiz_Konu",
    )
    baglanti = depo.baglan(yol)
    try:
        n = baglanti.execute(
            "SELECT COUNT(*) n FROM okunma WHERE baslik='Belirsiz_Konu'"
        ).fetchone()["n"]
        assert n == 1
    finally:
        baglanti.close()


def test_hiz_siniri_icin_bekleme_var():
    """İlk canlı koşumda HTTP 429 alındı: 4 coğrafya × 10 terim ardışık istek.
    Bekleme çağrının hemen öncesinde — çağıran unutamaz."""
    import inspect

    kaynak = inspect.getsource(gtrends.makale_ara)
    assert "time.sleep(BEKLEME_SN)" in kaynak
    assert gtrends.BEKLEME_SN > 0


def test_wikimedia_kullanici_ajani_paylasiliyor():
    """Wikimedia tanımlayıcı UA şart koşuyor; ilk sürüm kendi jenerik UA'sını
    gönderiyordu. Tek tanım, tek yerde değişir."""
    import inspect

    for fn in (gtrends.makale_ara, gtrends.terimleri_cek):
        assert "wikipedia.KULLANICI_AJANI" in inspect.getsource(fn)
