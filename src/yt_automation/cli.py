"""Komut satırı arayüzü.

v1 elle tetikleniyor (PRD kararı), bu yüzden giriş noktası bir CLI.
Zamanlanmış çalışma faz 2'de — o zaman aynı fonksiyonlar bir zamanlayıcıdan
çağrılır, CLI değişmez.

Şu an yalnızca `dogrula` gerçek: kuyruğu okur ve kota tahminini verir.
Yükleme komutları OAuth görevinden sonra eklenir.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, kanal, kota, oauth
from .kota import KotaAsimi
from .video import MetadataHatasi, kuyrugu_oku
from .yukleyici import YuklemeDogrulamaHatasi, yukle_ve_dogrula


def _dogrula(dizin: Path, kanal_kimligi: str) -> int:
    try:
        profil = kanal.getir(kanal_kimligi)
        kuyruk = kuyrugu_oku(dizin, profil)
    except (KeyError, MetadataHatasi) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1

    if not kuyruk:
        print(f"{dizin} içinde yüklenecek video yok.")
        return 0

    tahmin = sum(kota.video_basina_maliyet(thumbnail=v.thumbnail is not None) for v in kuyruk)

    print(f"Kanal: {profil.ad} (cocuk_icerigi={profil.cocuk_icerigi})")
    print(f"Kuyruk: {len(kuyruk)} video\n")
    for v in kuyruk:
        zaman = v.yayin_tarihi.isoformat() if v.yayin_tarihi else "planlanmamış"
        kapak = "kapak var" if v.thumbnail else "kapak YOK"
        print(f"  · {v.dosya.name}")
        print(f"    {v.baslik}")
        print(f"    {len(v.etiketler)} etiket · {zaman} · {kapak}")

    print(f"\nTahmini kota: {tahmin}/{kota.GUNLUK_BUTCE} birim")
    if tahmin > kota.GUNLUK_BUTCE:
        print(
            f"UYARI: kuyruk günlük bütçeyi {tahmin - kota.GUNLUK_BUTCE} birim aşıyor. "
            "Birden fazla güne bölün.",
            file=sys.stderr,
        )
        return 1
    return 0


def _yukle(dizin: Path, kanal_kimligi: str) -> int:
    try:
        profil = kanal.getir(kanal_kimligi)
        kuyruk = kuyrugu_oku(dizin, profil)
        servis = oauth.servis_olustur()
        sayac = kota.Sayac()
        for video in kuyruk:
            video_id = yukle_ve_dogrula(video, profil, servis, sayac)
            print(f"Yüklendi ve doğrulandı: {video.baslik} — {video_id}")
        print(f"Kota: {sayac.ozet()}")
        return 0
    except (KeyError, MetadataHatasi, KotaAsimi, YuklemeDogrulamaHatasi) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(
        prog="ytoto",
        description="YouTube yükleme otomasyonu",
    )
    ayristirici.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    altlar = ayristirici.add_subparsers(dest="komut", required=True)

    dogrula = altlar.add_parser(
        "dogrula",
        help="Kuyruktaki metadata dosyalarını doğrula ve kota tahmini ver",
    )
    dogrula.add_argument("dizin", type=Path, help="Video ve metadata dosyalarının bulunduğu dizin")
    dogrula.add_argument("--kanal", default="cocuk", help="Kanal kimliği (varsayılan: cocuk)")

    yukle = altlar.add_parser("yukle", help="Kuyruktaki videoları yükle ve bayrakları doğrula")
    yukle.add_argument("dizin", type=Path, help="Video ve metadata dosyalarının bulunduğu dizin")
    yukle.add_argument("--kanal", default="cocuk", help="Kanal kimliği (varsayılan: cocuk)")

    args = ayristirici.parse_args(argv)
    if args.komut == "dogrula":
        return _dogrula(args.dizin, args.kanal)
    if args.komut == "yukle":
        return _yukle(args.dizin, args.kanal)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
