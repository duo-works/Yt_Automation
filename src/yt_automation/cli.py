"""Komut satırı arayüzü.

v1 elle tetikleniyor (PRD kararı), bu yüzden giriş noktası bir CLI.
Zamanlanmış çalışma faz 2'de — o zaman aynı fonksiyonlar bir zamanlayıcıdan
çağrılır, CLI değişmez.

`dogrula` kuyruğu okur ve kota tahminini verir. `trend topla` bölgesel
trend listelerini çeker. Yükleme komutları OAuth görevinden sonra eklenir.

Sırlar ortam değişkeninden okunur. `.env` dosyasını okuyan bir bağımlılık
bilerek eklenmedi; değerleri kabuğa siz aktarın:

    set -a; source .env; set +a        # bash/zsh
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__, depo, kanal, kota
from .trend import bolge, konu_toplayici, toplayici, wikipedia
from .video import MetadataHatasi, kuyrugu_oku

ANAHTAR_DEGISKENI = "YOUTUBE_API_KEY"


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


def _istemci_kur():
    """YouTube istemcisi — yalnızca API anahtarı, OAuth yok.

    `chart=mostPopular` genel veri olduğu için kullanıcı yetkilendirmesi
    gerekmiyor. Bu, trend hattının DW-21'i (OAuth) beklememesini sağlıyor.
    """
    anahtar = os.environ.get(ANAHTAR_DEGISKENI)
    if not anahtar:
        raise RuntimeError(
            f"{ANAHTAR_DEGISKENI} tanımlı değil. Google Cloud Console → "
            "APIs & Services → Credentials → API key ile alın, `.env`'e koyun ve "
            "kabuğa aktarın: set -a; source .env; set +a"
        )
    from googleapiclient.discovery import build  # ağır içe aktarım, yalnızca gerektiğinde

    return build("youtube", "v3", developerKey=anahtar, cache_discovery=False)


def _trend_topla(*, derin: bool, kuru: bool, adet: int) -> int:
    yol = depo.varsayilan_yol()
    tur = "derin" if derin else "genis"

    try:
        if derin:
            bolgeler = bolge.derin_bolgeler(yol, adet)
        else:
            bolgeler = bolge.bolgeleri_getir(_istemci_kur()) if not kuru else []
    except (bolge.BolgeHatasi, RuntimeError) as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1

    if kuru:
        # Geniş taramada bölge sayısı API'den geliyor; kuru koşumda çağrı
        # yapmamak için bilinen desteklenen bölge sayısı üzerinden tahmin edilir.
        sayi = len(bolgeler) if bolgeler else bolge.TAHMINI_BOLGE_SAYISI
        cagri = sayi * len(bolge.LISTELER)
        sayac = kota.KaliciSayac(yol, surec="trend")
        print(f"KURU KOŞUM — {tur} tarama")
        print(f"  {sayi} bölge × {len(bolge.LISTELER)} liste = {cagri} çağrı")
        print(f"  tahmini maliyet: {toplayici.maliyet_tahmini(sayi)} birim")
        print(f"  trend bugün: {sayac.surec_harcamasi}/{bolge.TREND_KOTA_TAVANI} birim")
        print(f"  ortak kota: {sayac.ozet()}")
        return 0

    sayac = kota.KaliciSayac(yol, surec="trend")
    sonuc = toplayici.topla(_istemci_kur(), sayac, tur=tur, bolgeler=bolgeler, yol=yol)
    print(sonuc.ozet())
    for hata in sonuc.hatalar[:5]:
        print(f"  hata: {hata}", file=sys.stderr)
    return 1 if sonuc.kota_bitti and sonuc.cagri_sayisi == 0 else 0


def _konu_topla(*, diller: str, gun: str | None, adet: int) -> int:
    """Wikipedia okunma sıçramaları — kota harcamaz, anahtar istemez."""
    yol = depo.varsayilan_yol()
    secilen = tuple(d.strip() for d in diller.split(",") if d.strip())
    hedef = date.fromisoformat(gun) if gun else None

    sonuc = konu_toplayici.topla(yol, diller=secilen, gun=hedef, adet=adet)
    print(sonuc.ozet())
    for hata in sonuc.hatalar[:5]:
        print(f"  hata: {hata}", file=sys.stderr)
    return 1 if not sonuc.diller else 0


def _konu_listele(*, limit: int) -> int:
    kayitlar = konu_toplayici.adaylar(depo.varsayilan_yol(), limit=limit)
    if not kayitlar:
        print("Aday yok — önce `ytoto konu topla` çalıştırın.")
        return 1
    for k in kayitlar:
        print(f"  {k['okunma']:>9,} · [{k['sinif']}] {k['dil']}: {k['baslik'].replace('_', ' ')}")
    return 0


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

    trend = altlar.add_parser("trend", help="Bölgesel trend listeleri")
    trend_altlar = trend.add_subparsers(dest="trend_komutu", required=True)

    topla = trend_altlar.add_parser("topla", help="Trend listelerini çek ve depoya yaz")
    kapsam = topla.add_mutually_exclusive_group(required=True)
    kapsam.add_argument(
        "--genis", action="store_true", help="Desteklenen tüm bölgeler (günde bir kez)"
    )
    kapsam.add_argument("--derin", action="store_true", help="En umut verici bölgeler (saatlik)")
    topla.add_argument(
        "--adet",
        type=int,
        default=bolge.DERIN_BOLGE_SAYISI,
        help=f"Derin taramadaki bölge sayısı (varsayılan: {bolge.DERIN_BOLGE_SAYISI})",
    )
    topla.add_argument(
        "--kuru", action="store_true", help="Hiç çağrı yapma, yalnızca maliyeti bildir"
    )

    konu_ay = altlar.add_parser("konu", help="Wikipedia okunma sıçramaları (kota harcamaz)")
    konu_altlar = konu_ay.add_subparsers(dest="konu_komutu", required=True)

    kt = konu_altlar.add_parser("topla", help="Günlük okunma listelerini çek ve sınıflandır")
    kt.add_argument(
        "--diller",
        default=",".join(wikipedia.VARSAYILAN_DILLER),
        help=f"Virgülle ayrık dil kodları (varsayılan: {','.join(wikipedia.VARSAYILAN_DILLER)})",
    )
    kt.add_argument("--gun", help="YYYY-AA-GG; boşsa verisi hazır olan son gün")
    kt.add_argument("--adet", type=int, default=200, help="Dil başına makale (varsayılan: 200)")

    kl = konu_altlar.add_parser("listele", help="Tarih/bilim adaylarını sıralı göster")
    kl.add_argument("--limit", type=int, default=40)

    args = ayristirici.parse_args(argv)
    if args.komut == "dogrula":
        return _dogrula(args.dizin, args.kanal)
    if args.komut == "trend" and args.trend_komutu == "topla":
        return _trend_topla(derin=args.derin, kuru=args.kuru, adet=args.adet)
    if args.komut == "konu":
        if args.konu_komutu == "topla":
            return _konu_topla(diller=args.diller, gun=args.gun, adet=args.adet)
        if args.konu_komutu == "listele":
            return _konu_listele(limit=args.limit)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
