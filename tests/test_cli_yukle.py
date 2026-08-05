from pathlib import Path

from yt_automation import cli


def test_yukle_komutu_dizin_ve_kanali_aktarir(monkeypatch, tmp_path: Path):
    cagrilar = []

    def sahte_yukle(dizin: Path, kanal: str) -> int:
        cagrilar.append((dizin, kanal))
        return 0

    monkeypatch.setattr(cli, "_yukle", sahte_yukle)

    sonuc = cli.main(["yukle", str(tmp_path), "--kanal", "cocuk"])

    assert sonuc == 0
    assert cagrilar == [(tmp_path, "cocuk")]


def test_yukleme_kalici_sayaci_kullanir(monkeypatch, tmp_path: Path):
    """Yükleme hattı kota defterine yazmalı — bellekteki sayaç yetmez.

    Bu hat projenin en büyük kota tüketicisi (video başına 1.651 birim) ve tek
    muhasebe tutmayan tüketiciydi. `Sayac` her çalıştırmada sıfırdan başlıyor
    ve diğer süreçleri göremiyor: gün içinde 897 birim harcanmışken 10.000
    kalan görür, altı videoya izin verir, bütçe beşe yeter ve altıncı
    `videos.insert` 1.600 birim harcayıp 403 alır — reddedilen istek de
    kotadan yediği için bedel iki kez ödenir. DW-24 tam bunun için yazıldı.
    """
    from yt_automation import kanal as kanal_modulu
    from yt_automation import kota, oauth

    monkeypatch.setenv("YT_OTOMASYON_VERI", str(tmp_path))
    monkeypatch.setattr(oauth, "servis_olustur", lambda: object())
    monkeypatch.setattr(cli, "kuyrugu_oku", lambda dizin, profil: [])
    monkeypatch.setattr(
        kanal_modulu,
        "getir",
        lambda k: kanal_modulu.Kanal(kimlik=k, ad=k, cocuk_icerigi=False),
    )

    gorulen: list[object] = []
    gercek = kota.KaliciSayac

    def izleyen(*args, **kwargs):
        sayac = gercek(*args, **kwargs)
        gorulen.append((sayac, kwargs.get("surec")))
        return sayac

    monkeypatch.setattr(kota, "KaliciSayac", izleyen)

    assert cli._yukle(tmp_path, "egitim") == 0
    assert gorulen, "yükleme hattı KaliciSayac kurmadı — bellekteki sayaç kota defterini görmez"
    assert gorulen[0][1] == "yukleme", "harcama kendi `surec` etiketiyle yazılmalı"
