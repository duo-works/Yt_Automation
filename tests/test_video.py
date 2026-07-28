from datetime import datetime
from pathlib import Path

import pytest

from yt_automation.kanal import Kanal
from yt_automation.video import (
    ACIKLAMA_MAKS,
    BASLIK_MAKS,
    MetadataHatasi,
    kuyrugu_oku,
    oku,
)

COCUK = Kanal(
    kimlik="cocuk",
    ad="Çocuk içeriği",
    cocuk_icerigi=True,
    varsayilan_etiketler=("çocuk", "çizgi film"),
)
EGITIM = Kanal(kimlik="egitim", ad="Eğitim", cocuk_icerigi=False)


def yaz(dizin: Path, ad: str, metadata: str, *, video: bool = True) -> Path:
    yol = dizin / f"{ad}.yaml"
    yol.write_text(metadata, encoding="utf-8")
    if video:
        (dizin / f"{ad}.mp4").write_bytes(b"sahte video")
    return yol


def test_gecerli_metadata_okunur(tmp_path: Path):
    yol = yaz(
        tmp_path,
        "bolum-01",
        """
baslik: İlk bölüm
aciklama: Açıklama metni
etiketler: ["masal", "çocuk"]
yayin_tarihi: 2026-08-01T18:00:00
sentetik_medya: true
""",
    )
    v = oku(yol, COCUK)

    assert v.baslik == "İlk bölüm"
    assert v.dosya.name == "bolum-01.mp4"
    assert v.sentetik_medya is True
    assert v.cocuk_icerigi is True
    assert v.yayin_tarihi == datetime(2026, 8, 1, 18, 0)
    assert v.zamanlanmis is True
    assert v.thumbnail is None


def test_kanal_etiketleri_once_gelir_ve_tekrarlar_atilir(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", 'baslik: X\netiketler: ["çocuk", "masal"]\n')
    v = oku(yol, COCUK)
    # "çocuk" hem kanalda hem metadata'da — bir kez görünmeli, sıra korunmalı.
    assert v.etiketler == ("çocuk", "çizgi film", "masal")


def test_video_dosyasi_yoksa_hata(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", "baslik: X\n", video=False)
    with pytest.raises(MetadataHatasi, match="video dosyası yok"):
        oku(yol, COCUK)


def test_baslik_zorunlu(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", "aciklama: sadece açıklama\n")
    with pytest.raises(MetadataHatasi, match="baslik: zorunlu"):
        oku(yol, COCUK)


def test_baslik_sinirini_asamaz(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", f"baslik: {'a' * (BASLIK_MAKS + 1)}\n")
    with pytest.raises(MetadataHatasi, match="baslik:"):
        oku(yol, COCUK)


def test_aciklama_sinirini_asamaz(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", f"baslik: X\naciklama: {'a' * (ACIKLAMA_MAKS + 1)}\n")
    with pytest.raises(MetadataHatasi, match="aciklama:"):
        oku(yol, COCUK)


def test_etiket_toplam_siniri(tmp_path: Path):
    # Etiketler **farklı** olmalı; aynısı tekrarlanırsa tekilleştirme sınırı gizler.
    uzun = ", ".join(f'"{i:02d}{"e" * 58}"' for i in range(10))
    yol = yaz(tmp_path, "bolum-01", f"baslik: X\netiketler: [{uzun}]\n")
    with pytest.raises(MetadataHatasi, match="toplam"):
        oku(yol, COCUK)


def test_cocuk_icerigi_kanalla_celisirse_hata(tmp_path: Path):
    """Yanlış klasöre konmuş video sessizce yanlış bayrakla yüklenmemeli."""
    yol = yaz(tmp_path, "bolum-01", "baslik: X\ncocuk_icerigi: false\n")
    with pytest.raises(MetadataHatasi, match="çelişiyor"):
        oku(yol, COCUK)


def test_cocuk_icerigi_verilmezse_kanaldan_gelir(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", "baslik: X\n")
    assert oku(yol, COCUK).cocuk_icerigi is True

    yol2 = yaz(tmp_path, "bolum-02", "baslik: Y\n")
    assert oku(yol2, EGITIM).cocuk_icerigi is False


def test_sentetik_medya_varsayilani_false(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", "baslik: X\n")
    assert oku(yol, COCUK).sentetik_medya is False


def test_thumbnail_yoksa_hata(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", "baslik: X\nthumbnail: yok.jpg\n")
    with pytest.raises(MetadataHatasi, match="thumbnail:"):
        oku(yol, COCUK)


def test_thumbnail_cozulur(tmp_path: Path):
    (tmp_path / "kapak.jpg").write_bytes(b"sahte")
    yol = yaz(tmp_path, "bolum-01", "baslik: X\nthumbnail: kapak.jpg\n")
    assert oku(yol, COCUK).thumbnail.name == "kapak.jpg"


def test_bozuk_tarih_anlasilir_hata_verir(tmp_path: Path):
    yol = yaz(tmp_path, "bolum-01", 'baslik: X\nyayin_tarihi: "yarın"\n')
    with pytest.raises(MetadataHatasi, match="yayin_tarihi:"):
        oku(yol, COCUK)


def test_kuyruk_dosya_adina_gore_siralanir(tmp_path: Path):
    yaz(tmp_path, "bolum-02", "baslik: İkinci\n")
    yaz(tmp_path, "bolum-01", "baslik: Birinci\n")
    kuyruk = kuyrugu_oku(tmp_path, COCUK)
    assert [v.baslik for v in kuyruk] == ["Birinci", "İkinci"]


def test_bos_dizin_bos_kuyruk(tmp_path: Path):
    assert kuyrugu_oku(tmp_path, COCUK) == []
