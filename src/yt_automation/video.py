"""Video metadata dosyasının okunması ve doğrulanması.

Girdi biçimi PRD'de karara bağlandı: her videonun yanında aynı adlı bir
`.yaml` durur.

    videolar/2026-08-01-bolum-01.mp4
    videolar/2026-08-01-bolum-01.yaml

Metadata örneği::

    baslik: İlk bölüm
    # Offset yoksa Europe/Istanbul kabul edilir; açık offset korunur.
    yayin_tarihi: 2026-08-01T18:00:00

Doğrulama **yüklemeden önce** yapılır. Sebebi kota: `videos.insert` 1.600
birim ve reddedilen bir istek de bu birimi harcar. Biçim hatasını API'ye
sordurmak, günlük 10.000 birimin altıda birini bir yazım hatasına vermek olur.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .kanal import Kanal

# YouTube Data API'nin dayattığı sınırlar.
BASLIK_MAKS = 100
ACIKLAMA_MAKS = 5000
ETIKET_TOPLAM_MAKS = 500

VIDEO_UZANTILARI = (".mp4", ".mov", ".mkv", ".webm", ".avi")
VARSAYILAN_SAAT_DILIMI = ZoneInfo("Europe/Istanbul")


class MetadataHatasi(ValueError):
    """Metadata dosyası eksik veya geçersiz."""


@dataclass(frozen=True)
class Video:
    """Yüklemeye hazır tek bir video."""

    dosya: Path
    baslik: str
    aciklama: str
    etiketler: tuple[str, ...]
    yayin_tarihi: datetime | None
    sentetik_medya: bool
    cocuk_icerigi: bool
    thumbnail: Path | None

    @property
    def zamanlanmis(self) -> bool:
        """Yayın tarihi verilmişse video `private` yüklenip o tarihe planlanır."""
        return self.yayin_tarihi is not None


def _yol_coz(kok: Path, deger: object, alan: str) -> Path:
    """Metadata'daki göreli yolu metadata dosyasının bulunduğu dizine göre çözer."""
    if not isinstance(deger, str) or not deger.strip():
        raise MetadataHatasi(f"{alan}: dosya adı bekleniyordu, {deger!r} geldi")
    yol = (kok / deger).resolve()
    if not yol.is_file():
        raise MetadataHatasi(f"{alan}: dosya bulunamadı — {yol}")
    return yol


def _etiketleri_coz(deger: object, kanal: Kanal) -> tuple[str, ...]:
    if deger is None:
        ham: list[str] = []
    elif isinstance(deger, list) and all(isinstance(e, str) for e in deger):
        ham = list(deger)
    else:
        raise MetadataHatasi("etiketler: dizi bekleniyordu")

    # Kanalın varsayılanları önce gelir; sıra korunarak tekrarlar atılır.
    birlesik = list(kanal.varsayilan_etiketler) + ham
    return tuple(dict.fromkeys(e.strip() for e in birlesik if e.strip()))


def _tarih_coz(deger: object) -> datetime | None:
    if deger is None:
        return None
    if isinstance(deger, datetime):
        return deger
    raise MetadataHatasi(
        f"yayin_tarihi: tarih-saat bekleniyordu, {deger!r} geldi "
        "— YAML'de tırnaksız ISO biçimi kullanın (2026-08-01T18:00:00)"
    )


def yayin_tarihini_utc(deger: datetime) -> datetime:
    """Yayın tarihini UTC'ye çevirir.

    Offset içermeyen YAML tarihleri Europe/Istanbul kabul edilir. Açık offset
    verilmişse o offset korunarak UTC'ye çevrilir. YouTube ``publishAt`` için
    RFC 3339 ve UTC bekler.
    """
    if deger.tzinfo is None:
        deger = deger.replace(tzinfo=VARSAYILAN_SAAT_DILIMI)
    return deger.astimezone(UTC)


def oku(metadata_yolu: Path, kanal: Kanal) -> Video:
    """Metadata dosyasını okur, doğrular ve `Video` üretir.

    Video dosyası, metadata ile **aynı adı** taşıyan ve tanınan bir uzantısı
    olan dosyadır. `thumbnail` alanı verilmişse o da doğrulanır.
    """
    if not metadata_yolu.is_file():
        raise MetadataHatasi(f"metadata dosyası yok: {metadata_yolu}")

    ham = yaml.safe_load(metadata_yolu.read_text(encoding="utf-8"))
    if not isinstance(ham, dict):
        raise MetadataHatasi(f"{metadata_yolu.name}: en üstte anahtar-değer eşlemesi bekleniyordu")

    kok = metadata_yolu.parent

    video_dosyasi = next(
        (a for u in VIDEO_UZANTILARI if (a := metadata_yolu.with_suffix(u)).is_file()),
        None,
    )
    if video_dosyasi is None:
        beklenen = ", ".join(VIDEO_UZANTILARI)
        raise MetadataHatasi(
            f"{metadata_yolu.stem}: yanında video dosyası yok (aranan uzantılar: {beklenen})"
        )

    baslik = str(ham.get("baslik", "")).strip()
    if not baslik:
        raise MetadataHatasi("baslik: zorunlu")
    if len(baslik) > BASLIK_MAKS:
        raise MetadataHatasi(f"baslik: {len(baslik)} karakter, sınır {BASLIK_MAKS}")

    aciklama = str(ham.get("aciklama", "") or "")
    if len(aciklama) > ACIKLAMA_MAKS:
        raise MetadataHatasi(f"aciklama: {len(aciklama)} karakter, sınır {ACIKLAMA_MAKS}")

    etiketler = _etiketleri_coz(ham.get("etiketler"), kanal)
    # YouTube etiketleri tek tek değil, toplam uzunlukla sınırlar.
    toplam = sum(len(e) for e in etiketler)
    if toplam > ETIKET_TOPLAM_MAKS:
        raise MetadataHatasi(f"etiketler: toplam {toplam} karakter, sınır {ETIKET_TOPLAM_MAKS}")

    # `cocuk_icerigi` metadata'da verilmemişse kanal profilinden gelir. Verilmişse
    # kanalla çelişmemeli — çelişki, yanlış klasöre konmuş bir video demektir ve
    # yanlış işaretleme FTC yaptırımına giriyor.
    cocuk_icerigi = ham.get("cocuk_icerigi", kanal.cocuk_icerigi)
    if not isinstance(cocuk_icerigi, bool):
        raise MetadataHatasi("cocuk_icerigi: true/false bekleniyordu")
    if cocuk_icerigi != kanal.cocuk_icerigi:
        raise MetadataHatasi(
            f"cocuk_icerigi ({cocuk_icerigi}) kanal profiliyle çelişiyor "
            f"({kanal.kimlik} → {kanal.cocuk_icerigi}). Video yanlış kanalda olabilir."
        )

    sentetik_medya = ham.get("sentetik_medya", False)
    if not isinstance(sentetik_medya, bool):
        raise MetadataHatasi("sentetik_medya: true/false bekleniyordu")

    thumbnail = _yol_coz(kok, ham["thumbnail"], "thumbnail") if ham.get("thumbnail") else None

    return Video(
        dosya=video_dosyasi,
        baslik=baslik,
        aciklama=aciklama,
        etiketler=etiketler,
        yayin_tarihi=_tarih_coz(ham.get("yayin_tarihi")),
        sentetik_medya=sentetik_medya,
        cocuk_icerigi=cocuk_icerigi,
        thumbnail=thumbnail,
    )


def kuyrugu_oku(dizin: Path, kanal: Kanal) -> list[Video]:
    """Bir dizindeki tüm metadata dosyalarını okur, dosya adına göre sıralar."""
    if not dizin.is_dir():
        raise MetadataHatasi(f"dizin yok: {dizin}")
    return [oku(y, kanal) for y in sorted(dizin.glob("*.yaml"))]
