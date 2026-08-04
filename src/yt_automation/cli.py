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
from .trend import (
    bolge,
    bosluk,
    gtrends,
    hiz,
    kaynak,
    konu_toplayici,
    nis,
    notion,
    sicrama,
    siniflandirici,
    toplayici,
    video_sinif,
    wikipedia,
)
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


def _trend_rapor(*, bolge_kodu: str | None, siniflar: str | None, sirala: str, limit: int) -> int:
    """Türetilmiş sinyaller — kota harcamaz, yalnızca depoyu okur."""
    yol = depo.varsayilan_yol()
    secilen = tuple(s.strip() for s in siniflar.split(",") if s.strip()) if siniflar else None

    try:
        # Limit sonda uygulanıyor: özet **bütün** kümeyi anlatmalı, ekrana
        # basılan ilk N'i değil. Kaç videonun ivmesi olduğunu bilmek, listenin
        # ne kadar olgunlaştığını gösteren tek sayı.
        sinyaller = hiz.hesapla(yol, bolge_kodu=bolge_kodu, siniflar=secilen, sirala=sirala)
    except ValueError as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1

    if not sinyaller:
        print("Ölçüm yok — önce `ytoto trend topla` çalıştırın.")
        return 1

    ozet = hiz.rapor_ozeti(yol, sinyaller)
    print(f"{ozet.ozet()} · sıralama: {sirala}\n")
    for sira, sinyal in enumerate(sinyaller[:limit], start=1):
        print(f"  {sira:>3}. {sinyal.satir()}")

    if ozet.kosu_sayisi < 2:
        print(
            "\n⚠️ Tek koşu var: hız ve ivme hesaplanamıyor, sıralama izlenmeye düşüyor. "
            f"En az {hiz.ASGARI_ARALIK_SAAT * 60:.0f} dakika arayla ikinci bir "
            "`ytoto trend topla` gerekiyor.",
            file=sys.stderr,
        )
    elif ozet.ivmesi_olan == 0:
        print(
            "\n⚠️ Hiçbir videonun ivmesi yok: ivme üç ölçüm istiyor. Üçüncü koşumdan sonra dolacak.",
            file=sys.stderr,
        )
    return 0


def _bosluk_arastir(*, limit: int, kuru: bool) -> int:
    """Talep-arz sondajı — huninin tek pahalı adımı, sondaj başına 102 birim."""
    yol = depo.varsayilan_yol()
    # Sıçrama detektörü (DW-54): patlayan konu kuyruğun başına geçer. Kota
    # harcamaz — girdisi zaten toplanmış okunma serileri.
    sicramalar = sicrama.tespit_et(yol)
    oncelikli = {s.qid for s in sicramalar if s.qid}
    if sicramalar:
        print(f"🔥 {len(sicramalar)} sıçrama tespit edildi — kuyruğun başına alındı:")
        for s in sicramalar[:5]:
            print(f"    {s.satir()}")
    adaylar = bosluk.sondajlanmamis_adaylar(yol, limit, oncelikli_qidler=oncelikli)
    sayac = kota.KaliciSayac(yol, surec=bosluk.SUREC)

    if not adaylar:
        print("Sondajlanmamış aday yok — önce `ytoto konu topla` çalıştırın.")
        return 1

    if kuru:
        # Kabul ölçütü: kuru koşum sondaj sayısını ve maliyeti ÖNCEDEN bildirir.
        # Tavana takılacak sondaj sayısı da burada hesaplanıyor — "10 istedim,
        # 4 oldu" sürprizini koşum sırasında değil öncesinde görmek gerekiyor.
        kalan_tavan = bosluk.SONDAJ_KOTA_TAVANI - sayac.surec_harcamasi
        sigan = max(kalan_tavan // bosluk.SONDAJ_MALIYETI, 0)
        yapilacak = min(len(adaylar), sigan)
        print("KURU KOŞUM — talep-arz sondajı")
        print(f"  {len(adaylar)} aday hazır, tavana {sigan} sondaj sığıyor → {yapilacak} sondaj")
        print(
            f"  sondaj başına {bosluk.SONDAJ_MALIYETI} birim "
            f"({kota.MALIYET['search.list']} + {kota.MALIYET['videos.list']} + "
            f"{kota.MALIYET['channels.list']})"
        )
        print(f"  tahmini maliyet: {yapilacak * bosluk.SONDAJ_MALIYETI} birim")
        print(f"  boşluk bugün: {sayac.surec_harcamasi}/{bosluk.SONDAJ_KOTA_TAVANI} birim")
        print(f"  yükleme rezervi: {kota.video_basina_maliyet()} birim (dokunulmaz)")
        print(f"  ortak kota: {sayac.ozet()}")
        for aday in adaylar[: max(yapilacak, 1)][:5]:
            kopru = (
                f" ← köprü: {aday['kaynak_dil']}"
                if aday.get("kaynak_dil") and aday["kaynak_dil"] != aday["dil"]
                else ""
            )
            print(
                f"    · [{aday['sinif']}] {aday['dil']}: "
                f"{aday['baslik'].replace('_', ' ')} ({aday['okunma']:,} okunma{kopru})"
                f' → "{bosluk.sorguya_cevir(aday["baslik"])}"'
            )
        return 0

    try:
        istemci = _istemci_kur()
    except RuntimeError as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1

    sonuc = bosluk.arastir(istemci, sayac, yol, limit=limit, oncelikli_qidler=oncelikli)
    print(sonuc.ozet())
    for hata in sonuc.hatalar[:5]:
        print(f"  hata: {hata}", file=sys.stderr)
    if sonuc.gecersiz:
        print(
            f"⚠️ {sonuc.gecersiz} sondajda arama boş döndü. Bunlar 'arzı yok' "
            "değil 'sorgu şüpheli' demek ve skorlanmıyor.",
            file=sys.stderr,
        )
    return 1 if sonuc.sondaj == 0 else 0


def _bosluk_rapor(*, limit: int) -> int:
    kayitlar = bosluk.bosluklar(depo.varsayilan_yol(), limit=limit)
    if not kayitlar:
        print("Ölçüm yok — önce `ytoto bosluk arastir` çalıştırın.")
        return 1
    gecen = sum(1 for k in kayitlar if bosluk.red_gerekcesi(k) is None)
    print(
        f"{len(kayitlar)} ölçülmüş aday · {gecen} tanesi kapıları geçiyor\n"
        f"skor = log(talep) − arz gücü · MAD = skorun kendi dilinin tabanına uzaklığı\n"
    )
    for kayit in kayitlar:
        gerekce = bosluk.red_gerekcesi(kayit)
        isaret = "  " if gerekce is None else "· "
        satir = kayit.satir()
        if gerekce:
            satir += f"\n           ↳ elendi: {gerekce}"
        print(f"{isaret}{satir}")
    print(
        f"\nℹ️ Kapılar: kalibre skor ≥ {bosluk.ESIK_KALIBRE:.1f} MAD **ve** talep ≥ "
        f"{bosluk.ASGARI_TALEP:,} okunma/gün. Ham skorun mutlak seviyesi fırsatı değil "
        "pazar büyüklüğünü kodluyor, o yüzden sıralama dile göre normalize ediliyor. "
        "Eşikler gözlenen dağılımdan seçildi, yayın sonuçlarından değil — tek video "
        "yayınlanınca revize edilmeli.",
        file=sys.stderr,
    )
    return 0


def _nis_izle(*, kuru: bool) -> int:
    """Niş kanalların son yüklemelerini çeker. Kanal başına 2 birim."""
    yol = depo.varsayilan_yol()
    sayac = kota.KaliciSayac(yol, surec=nis.SUREC)
    kayitli = nis.kayitli_handleler(yol)
    cozulecek = [h for h, _ in nis.IZLENEN_KANALLAR if h not in kayitli]

    if kuru:
        izlenecek = len(kayitli) + len(cozulecek)
        print("KURU KOŞUM — niş kanal izleme")
        print(f"  katalogda {len(nis.IZLENEN_KANALLAR)} kanal · {len(kayitli)} tanesi çözülmüş")
        print(
            f"  çözülecek: {len(cozulecek)} handle × {kota.MALIYET['channels.list']} birim "
            f"= {len(cozulecek)} birim (bir kereye mahsus)"
        )
        print(f"  izlenecek: {izlenecek} kanal × 2 birim = {izlenecek * 2} birim")
        print(f"  tahmini toplam: {len(cozulecek) + izlenecek * 2} birim")
        print(f"  niş bugün: {sayac.surec_harcamasi}/{nis.NIS_KOTA_TAVANI} birim")
        print(f"  ortak kota: {sayac.ozet()}")
        return 0

    try:
        istemci = _istemci_kur()
    except RuntimeError as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1

    if cozulecek:
        cozum = nis.kanallari_coz(istemci, sayac, yol)
        print(cozum.ozet())
        for eksik in cozum.bulunamayan:
            print(f"  ⚠️ handle bulunamadı: {eksik}", file=sys.stderr)

    sonuc = nis.izle(istemci, sayac, yol)
    print(sonuc.ozet())
    for hata in sonuc.hatalar[:5]:
        print(f"  hata: {hata}", file=sys.stderr)
    return 1 if sonuc.kanal_sayisi == 0 else 0


def _nis_rapor(*, erken: bool, limit: int, asgari: float, pencere: float) -> int:
    kayitlar = nis.asiri_performans(
        depo.varsayilan_yol(),
        erken=erken,
        asgari_oran=asgari,
        pencere_gun=pencere,
        limit=limit,
    )
    if not kayitlar:
        print(
            "Sıralanacak video yok. Sebep ya ölçüm yok (`ytoto nis izle`) ya da "
            f"hiçbir kanalda taban için gereken {nis.ASGARI_OLGUN_VIDEO} olgun video yok."
        )
        return 1
    olcut = "günlük hız oranı (erken sinyal)" if erken else "izlenme oranı (olgun videolar)"
    kapsam = f"son {pencere:g} gün" if pencere else "tüm zamanlar"
    print(f"{len(kayitlar)} video · {kapsam} · ölçüt: {olcut} · taban = kanalın olgun medyanı\n")
    for kayit in kayitlar:
        print(f"  {kayit.satir(erken=erken)}")
    print(
        "\nℹ️ Bu sinyal takipçi yapar, lider değil: burada zirveye çıkan konu "
        "tanımı gereği arzı VAR olan konudur. `ytoto bosluk rapor` ile birlikte okunmalı.",
        file=sys.stderr,
    )
    return 0


def _trend_bolgeler(*, adet: int, pencere: int) -> int:
    """Bölge seçimini ve gerekçesini gösterir. Kota harcamaz.

    Seçim otomatik ama **denetlenebilir** olmalı: "neden TR listede yok"
    sorusunun cevabı koda bakmadan görülebilmeli.
    """
    yol = depo.varsayilan_yol()
    satirlar = bolge.secim_raporu(yol, adet, pencere_gun=pencere)
    if not satirlar:
        print("Veri yok — önce `ytoto trend topla --genis` çalıştırın.")
        return 1

    secilen = [s for s in satirlar if s["durum"] == "seçildi"]
    kopya = [s for s in satirlar if s["durum"].startswith("kopya")]
    print(
        f"{len(satirlar)} bölge ölçüldü · {len(secilen)} seçildi · "
        f"{len(kopya)} kopya elendi · son {pencere} gün\n"
    )
    for s in satirlar[: adet + len(kopya) + 5]:
        isaret = "→" if s["durum"] == "seçildi" else " "
        print(f"  {isaret} {s['bolge']}  {s['adet']:>4} ilgili video  {s['durum']}")

    if kopya:
        print(
            f"\nℹ️ {len(kopya)} bölge aynı çartı döndürdüğü için elendi "
            f"(≥%{bolge.ORTUSME_ESIGI * 100:.0f} örtüşme). Ölçülmüş örnek: "
            "LI, CH çartının birebir kopyası — ayrı çağrı yeni veri getirmiyor.",
            file=sys.stderr,
        )
    return 0


def _trend_siniflandir(*, yeniden: bool) -> int:
    """Videoları kategori ve konu etiketiyle sınıflandırır. Hiç çağrı yapmaz."""
    sonuc = video_sinif.uygula(depo.varsayilan_yol(), yeniden=yeniden)
    print(sonuc.ozet())
    ilgili = sonuc.siniflar.get("tarih", 0) + sonuc.siniflar.get("bilim", 0)
    if sonuc.islenen and ilgili == 0:
        print(
            "\nℹ️ Hiç tarih/bilim videosu çıkmadı. Bu beklenen: çartta bu etiketler "
            "pratikte yok (4.905 videoda en yakın etiket 'Knowledge', 19 kez). "
            "Aday üretimi `ytoto konu topla` üzerinden yürüyor.",
            file=sys.stderr,
        )
    return 0


def _trend_aktar(*, adet: int, kuru: bool, zorla: bool, kaynak_turu: str) -> int:
    """Günlük ilk-N adayı Notion'a yazar — Ömer'e devir noktası.

    Varsayılan kaynak **wikipedia**, çart değil. Sebebi ölçülmüş: 4.905 çart
    videosunda sıfır tarih, 19 bilim ve o 19'un hepsi yazılım dersi / cihaz
    incelemesi. Huninin gerçekten ürettiği aday listesi Wikipedia tarafında.
    """
    yol = depo.varsayilan_yol()
    wiki = kaynak_turu == "wikipedia"

    adaylar = (
        notion.aktarilmamis_bosluklar(yol, adet=adet, zorla=zorla)
        if wiki
        else notion.aktarilmamis_adaylar(yol, adet=adet, zorla=zorla)
    )

    # Kapıların ne elediği hem dolu hem boş günde raporlanıyor: eşikleri revize
    # edecek olan tek şey bu sayı ve sessiz eleme onu görünmez yapardı.
    gecen_sayisi, eleme = notion.bosluk_kapi_ozeti(yol) if wiki and not zorla else (0, {})

    if not adaylar:
        # ⚠️ "Aday yok"un iki ayrı sebebi var ve karıştırmak operatörü yanlış
        # yere bakmaya gönderir: kapı hepsini elediyse huni bilerek boş geçmiş
        # ve yapılacak bir şey yok; kapıyı geçenler zaten gönderilmişse yeni
        # ölçüm gerekiyor. Ayrım `gecen_sayisi` ile yapılıyor.
        if wiki and eleme and gecen_sayisi == 0:
            # ⚠️ "aday yok" ifadesi sözleşme: `gunluk-huni.sh` bu metni görünce
            # koşumu boş gün sayıyor, hata değil (DW-47). Metni değiştirirken
            # betikteki `grep` ile birlikte değiştirin.
            print(
                "Aktarılacak aday yok — ölçülen adayların hiçbiri kapıları geçmedi.\n"
                "Bu bir hata değil: eşiği geçen konu çıkmadığı gün huni bilerek boş geçer."
            )
            for gerekce, sayi in sorted(eleme.items(), key=lambda t: -t[1]):
                print(f"  {sayi:>3} aday · {gerekce}")
            return 0
        if wiki:
            print(
                "Aktarılacak aday yok. Sırayla: `ytoto konu topla` (aday üret), "
                "`ytoto bosluk arastir` (arzı ölç), `ytoto konu kaynak` (dosyayı çek). "
                "Hepsi aktarılmışsa `--zorla` ile tekrar gönderin."
            )
        else:
            print(
                "Aktarılacak çart videosu yok. Sırayla: `ytoto trend topla`, "
                "`ytoto trend siniflandir`. Hepsi aktarılmışsa `--zorla` kullanın."
            )
        return 1

    if eleme:
        toplam = sum(eleme.values())
        ayrinti = " · ".join(f"{sayi} {gerekce}" for gerekce, sayi in sorted(eleme.items()))
        print(f"Kapılar {toplam} adayı eledi — {ayrinti}")

    # Sıçrayanlar 🔥 Acil düşer (DW-54); Notion bildirim aboneliği o durumu
    # telefona taşır. Kota 0 — tespit zaten toplanmış okunma serilerinden.
    acil_qidler = sicrama.sicrayan_qidler(yol) if wiki else set()
    acil_sayisi = sum(1 for a in adaylar if wiki and a.qid in acil_qidler)
    if acil_sayisi:
        print(f"🔥 {acil_sayisi} acil aday — sıçrama tespit edildi, Acil durumuyla düşecek")

    if kuru:
        print(f"KURU KOŞUM — Notion aktarımı · kaynak: {kaynak_turu} · {len(adaylar)} aday")
        print("  YouTube kotası harcanmıyor; Notion yazma tarafı da kotasız.\n")
        for aday in adaylar:
            isaret = "🔥 " if wiki and aday.qid in acil_qidler else "  "
            print(f"{isaret}{aday.satir()}")
        return 0

    try:
        token, database = notion.token_al(), notion.database_al()
    except notion.NotionHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1

    sonuc = (
        notion.bosluklari_aktar(
            yol, adaylar=adaylar, database=database, token=token, acil_qidler=acil_qidler
        )
        if wiki
        else notion.aktar(yol, adaylar=adaylar, database=database, token=token)
    )
    print(sonuc.ozet())
    for url in sonuc.sayfalar[:5]:
        print(f"  {url}")
    for hata in sonuc.hatalar[:5]:
        print(f"  hata: {hata}", file=sys.stderr)
    return 1 if sonuc.yazilan == 0 else 0


def _konu_gtrends(*, kuru: bool) -> int:
    """Google Trends keşfi — YouTube kotası 0, tüm çağrılar ücretsiz API'lere."""
    yol = depo.varsayilan_yol()
    if kuru:
        # Kuru kip yalnızca ağın okuma tarafını kullanır: terimler çekilir,
        # eşleşme aranır, hiçbir şey yazılmaz.
        pazarlar = bosluk.hedef_pazarlar()
        print(f"KURU KOŞUM — Google Trends · pazarlar: {', '.join(pazarlar)}")
        for dil in pazarlar:
            for geo in gtrends.GEO_KODLARI.get(dil, ()):
                try:
                    terimler = gtrends.terimleri_cek(geo)
                except gtrends.GTrendsHatasi as hata:
                    print(f"  {geo}: HATA {hata}", file=sys.stderr)
                    continue
                print(f"  {geo}: {len(terimler)} terim")
                for t in terimler[:5]:
                    # Tek terimin arama hatası raporu bitirmemeli — canlı
                    # koşumda Wikipedia 429 döndürdü ve kuru koşum çöktü.
                    try:
                        eslesme = gtrends.makale_ara(dil, t.terim)
                    except gtrends.GTrendsHatasi as hata:
                        print(f"    · {t.terim} → HATA {hata}", file=sys.stderr)
                        continue
                    ok = f"→ {eslesme.replace('_', ' ')}" if eslesme else "→ eşleşme yok"
                    print(f"    · {t.terim} ({t.trafik or '?'}) {ok}")
        return 0

    sonuc = gtrends.isle(yol)
    print(sonuc.ozet())
    for hata in sonuc.hatalar[:5]:
        print(f"  hata: {hata}", file=sys.stderr)
    # Terim gelmemesi hata (RSS kırık olabilir), eşleşme az olması değil:
    # magazin/spor ağırlıklı listede düşük eşleşme normal gün.
    return 1 if sonuc.terim == 0 else 0


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


def _konu_siniflandir(*, limit: int, kuru: bool) -> int:
    """Wikidata'nın karar veremediği kuyruğu LLM'e sorar. YouTube kotası harcamaz."""
    yol = depo.varsayilan_yol()
    kuyruk = siniflandirici.bekleyenler(yol, limit)

    if kuru:
        grup = -(-len(kuyruk) // siniflandirici.GRUP_BOYUTU)  # tavana yuvarla
        print("KURU KOŞUM — sınıflandırma")
        print(f"  {len(kuyruk)} makale × {siniflandirici.GRUP_BOYUTU}'lik gruplar = {grup} çağrı")
        print(f"  model: {siniflandirici.MODEL}")
        for k in kuyruk[:5]:
            print(f"    · [{k['dil']}] {k['baslik'].replace('_', ' ')} ({k['okunma']:,} okunma)")
        if len(kuyruk) > 5:
            print(f"    … {len(kuyruk) - 5} makale daha")
        return 0

    if not kuyruk:
        print("Belirsiz makale yok — sınıflandırılacak bir şey kalmamış.")
        return 0

    try:
        istemci = siniflandirici.istemci_kur()
    except siniflandirici.SiniflandirmaHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 1

    sonuc = siniflandirici.siniflandir(istemci, yol, limit=limit)
    print(sonuc.ozet())
    for hata in sonuc.hatalar[:5]:
        print(f"  hata: {hata}", file=sys.stderr)
    return 1 if sonuc.cagri_sayisi == 0 else 0


def _konu_kaynak(*, limit: int, json_cikti: bool, yenile: bool) -> int:
    """Adayların kaynak dosyalarını çeker. Ücretsiz — YouTube kotası harcamaz."""
    yol = depo.varsayilan_yol()
    adaylar = kaynak.cekilmemis_adaylar(yol, limit, yenile=yenile)
    if not adaylar:
        print("Kaynağı çekilmemiş aday yok — önce `ytoto konu topla` çalıştırın.")
        return 1

    yetersiz = 0
    for aday in adaylar:
        sonuc = kaynak.cek(yol, aday["dil"], aday["baslik"], aday["qid"], yenile=yenile)
        baslik = aday["baslik"].replace("_", " ")
        print(f"  {baslik} — {sonuc.ozet()}")
        if not sonuc.yeterli:
            yetersiz += 1
        if json_cikti:
            print(kaynak.json_disa_aktar(yol, aday["qid"]))

    if yetersiz:
        print(
            f"\n⚠️ {yetersiz}/{len(adaylar)} aday yetersiz kaynakla döndü "
            "(en az 3 referans + 5 olgu gerekiyor). Bunlar videoya dönüşmemeli.",
            file=sys.stderr,
        )
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

    bolgeler = trend_altlar.add_parser(
        "bolgeler", help="Derin taramanın bölge seçimini ve gerekçesini göster (ücretsiz)"
    )
    bolgeler.add_argument("--adet", type=int, default=bolge.DERIN_BOLGE_SAYISI)
    bolgeler.add_argument(
        "--pencere",
        type=int,
        default=bolge.SECIM_PENCERESI_GUN,
        help=f"Kaç günlük geçmişe bakılsın (varsayılan: {bolge.SECIM_PENCERESI_GUN})",
    )

    rapor = trend_altlar.add_parser(
        "rapor", help="Hız, ivme ve yaşa göre normalize sinyaller (kota harcamaz)"
    )
    rapor.add_argument("--bolge", help="Yalnızca bu bölgede görünenler (örn. TR)")
    rapor.add_argument("--sinif", help="Virgülle ayrık: tarih,bilim,belirsiz,diger")
    rapor.add_argument(
        "--sirala",
        default="ivme",
        choices=hiz.SIRALAMA_ALANLARI,
        help="Sıralama ölçütü (varsayılan: ivme — asıl trend göstergesi)",
    )
    rapor.add_argument("--limit", type=int, default=25, help="Kaç satır basılsın")

    tsinif = trend_altlar.add_parser(
        "siniflandir", help="Videoları kategori ve konu etiketiyle sınıflandır (ücretsiz)"
    )
    tsinif.add_argument(
        "--yeniden",
        action="store_true",
        help="Daha önce sınıflandırılmışları da yeniden hesapla (LLM kararları korunur)",
    )

    aktar = trend_altlar.add_parser(
        "aktar", help="Günlük ilk-N adayı Notion'a yaz (YouTube kotası harcamaz)"
    )
    aktar.add_argument(
        "--adet",
        type=int,
        default=notion.VARSAYILAN_ADET,
        help=f"Kaç aday aktarılsın (varsayılan: {notion.VARSAYILAN_ADET})",
    )
    aktar.add_argument(
        "--kaynak",
        default="wikipedia",
        choices=("wikipedia", "youtube-chart"),
        help="Hangi aday kümesi aktarılsın (varsayılan: wikipedia — çartta tarih/bilim yok)",
    )
    aktar.add_argument("--kuru", action="store_true", help="Hiç yazma, ne gideceğini göster")
    aktar.add_argument(
        "--zorla", action="store_true", help="Daha önce aktarılmış adayları da gönder"
    )

    bosluk_ay = altlar.add_parser("bosluk", help="Talep-arz boşluğu sondajı ve skorlaması")
    bosluk_altlar = bosluk_ay.add_subparsers(dest="bosluk_komutu", required=True)

    ba = bosluk_altlar.add_parser(
        "arastir", help=f"Adayların arzını ölç (sondaj başına {bosluk.SONDAJ_MALIYETI} birim)"
    )
    ba.add_argument("--limit", type=int, default=10, help="En fazla kaç sondaj")
    ba.add_argument(
        "--kuru", action="store_true", help="Hiç çağrı yapma, sondaj sayısını ve maliyeti bildir"
    )

    br = bosluk_altlar.add_parser("rapor", help="Ölçülmüş adayları skora göre sırala (ücretsiz)")
    br.add_argument("--limit", type=int, default=25)

    nis_ay = altlar.add_parser("nis", help="Niş kanal izleme — kendi ortalamasına göre performans")
    nis_altlar = nis_ay.add_subparsers(dest="nis_komutu", required=True)

    ni = nis_altlar.add_parser(
        "izle", help="Kanalların son yüklemelerini çek (kanal başına 2 birim)"
    )
    ni.add_argument("--kuru", action="store_true", help="Hiç çağrı yapma, maliyeti bildir")

    nr = nis_altlar.add_parser("rapor", help="Aşırı performans oranına göre sırala (ücretsiz)")
    nr.add_argument(
        "--erken",
        action="store_true",
        help="Olgunlaşmamış videoları da kat (gürültülü, her biri işaretlenir)",
    )
    nr.add_argument("--limit", type=int, default=25)
    nr.add_argument("--asgari", type=float, default=1.0, help="Bu oranın altını gösterme")
    nr.add_argument(
        "--pencere",
        type=float,
        default=nis.PENCERE_GUN,
        help=f"Kaç günden yeni videolar sıralansın "
        f"(0 = tüm zamanlar, varsayılan: {nis.PENCERE_GUN})",
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

    kk = konu_altlar.add_parser(
        "kaynak", help="Adayların referans, olgu ve görsel tabanını çek (ücretsiz)"
    )
    kk.add_argument("--limit", type=int, default=10, help="Kaç aday işlensin")
    kk.add_argument("--json", action="store_true", help="Kaynak dosyasını JSON olarak bas")
    kk.add_argument(
        "--yenile",
        action="store_true",
        help="Zaten çekilmiş dosyaları da yeniden çek (toplayıcı düzeldiğinde gerekir)",
    )

    ks = konu_altlar.add_parser(
        "siniflandir", help="Belirsiz kalan makaleleri LLM'e sor (YouTube kotası harcamaz)"
    )
    ks.add_argument("--limit", type=int, default=200, help="En fazla kaç makale sorulsun")
    ks.add_argument("--kuru", action="store_true", help="Hiç çağrı yapma, yalnızca kuyruğu bildir")

    kg = konu_altlar.add_parser(
        "gtrends", help="Google Trends RSS'inden gün-içi konu keşfi (kota harcamaz)"
    )
    kg.add_argument("--kuru", action="store_true", help="Hiç yazma, terim ve eşleşmeleri göster")

    args = ayristirici.parse_args(argv)
    if args.komut == "dogrula":
        return _dogrula(args.dizin, args.kanal)
    if args.komut == "trend":
        if args.trend_komutu == "topla":
            return _trend_topla(derin=args.derin, kuru=args.kuru, adet=args.adet)
        if args.trend_komutu == "bolgeler":
            return _trend_bolgeler(adet=args.adet, pencere=args.pencere)
        if args.trend_komutu == "siniflandir":
            return _trend_siniflandir(yeniden=args.yeniden)
        if args.trend_komutu == "aktar":
            return _trend_aktar(
                adet=args.adet, kuru=args.kuru, zorla=args.zorla, kaynak_turu=args.kaynak
            )
        if args.trend_komutu == "rapor":
            return _trend_rapor(
                bolge_kodu=args.bolge,
                siniflar=args.sinif,
                sirala=args.sirala,
                limit=args.limit,
            )
    if args.komut == "bosluk":
        if args.bosluk_komutu == "arastir":
            return _bosluk_arastir(limit=args.limit, kuru=args.kuru)
        if args.bosluk_komutu == "rapor":
            return _bosluk_rapor(limit=args.limit)
    if args.komut == "nis":
        if args.nis_komutu == "izle":
            return _nis_izle(kuru=args.kuru)
        if args.nis_komutu == "rapor":
            return _nis_rapor(
                erken=args.erken, limit=args.limit, asgari=args.asgari, pencere=args.pencere
            )
    if args.komut == "konu":
        if args.konu_komutu == "topla":
            return _konu_topla(diller=args.diller, gun=args.gun, adet=args.adet)
        if args.konu_komutu == "listele":
            return _konu_listele(limit=args.limit)
        if args.konu_komutu == "siniflandir":
            return _konu_siniflandir(limit=args.limit, kuru=args.kuru)
        if args.konu_komutu == "kaynak":
            return _konu_kaynak(limit=args.limit, json_cikti=args.json, yenile=args.yenile)
        if args.konu_komutu == "gtrends":
            return _konu_gtrends(kuru=args.kuru)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
