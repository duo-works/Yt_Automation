#!/bin/bash
# Günlük aday hunisi — Wikipedia okunmalarından Notion adaylarına.
#
#   scripts/gunluk-huni.sh [--kuru]
#
# `saatlik-tarama.sh` bunu günde bir kez, nöbet dosyasıyla çağırıyor.
#
# ⚠️ Neden bu hat zamanlanıyor da çart hattı tek başına yetmiyor: çartın
# tarih/bilim için boş olduğu üç kez ölçüldü — 4.905 çart videosunda **sıfır
# tarih, 19 bilim** ve o 19'un hepsi yazılım dersi ya da cihaz incelemesi.
# Adayı gerçekten üreten hat burası; 2026-07-30'a kadar tamamen elle koşuyordu.
#
# ⚠️ Adım sırası zorunlu, keyfî değil. `notion.aktarilmamis_bosluklar` bir
# adayı ancak **hem** arzı ölçülmüşse **hem** kaynak dosyası çekilmişse
# aktarılabilir sayıyor. Yani 5. adım 3. ve 4. adımdan sonra gelmek zorunda.

set -uo pipefail

# shellcheck source=scripts/ortak.sh
. "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"

kuru=0
[ "${1:-}" = "--kuru" ] && kuru=1

# Ayarlanabilir sayılar. Sondaj huninin tek pahalı adımı: 102 birim/sondaj.
# 20 sondaj = 2.040 birim; çart (~1.182) ve niş (~75) ile birlikte günlük
# toplam ~3.300/10.000 ediyor ve yükleme rezervine (video başına 1.651)
# dokunmuyor. `bosluk.SONDAJ_KOTA_TAVANI` zaten 3.000'de ikinci bir tavan.
MAKALE="${YT_OTOMASYON_MAKALE:-200}"
SINIF="${YT_OTOMASYON_SINIF:-200}"
SONDAJ="${YT_OTOMASYON_SONDAJ:-20}"
KAYNAK="${YT_OTOMASYON_KAYNAK:-20}"
AKTAR="${YT_OTOMASYON_AKTAR:-20}"

basarisiz=0

# adim <ad> <kuru_destekli> <cli argümanları…>
#
# `kuru_destekli` 1 ise adımın kendi `--kuru` kipi var ve kuru koşumda gerçekten
# çalıştırılır (kota harcamaz, ne yapacağını bildirir). 0 ise adım ücretsiz ama
# depoya YAZIYOR — kuru koşumda yalnızca komut basılır, çalıştırılmaz.
adim() {
    local ad="$1"; shift
    local kuru_destekli="$1"; shift

    if [ "$kuru" = "1" ]; then
        if [ "$kuru_destekli" = "1" ]; then
            printf '\n--- %s (kuru) ---\n' "$ad"
            "$PY" -m yt_automation.cli "$@" --kuru
        else
            printf '\n--- %s (atlandı: kuru kipte yazmıyoruz) ---\n' "$ad"
            printf '    ytoto %s\n' "$*"
        fi
        return 0
    fi

    kaydet "huni · $ad başlıyor"

    # Çıktı önce yakalanıyor: "boş gün" ile "gerçek hata" ayrımı buna bakıyor.
    local cikti kod
    cikti="$("$PY" -m yt_automation.cli "$@" 2>&1)"
    kod=$?
    printf '%s\n' "$cikti" >> "$GUNLUK"
    # Son adımın çıktısı adım dışında da okunabilsin: sıçrama bildirimi
    # `trend aktar`ın "acil aday" satırına bakıyor (DW-54).
    SON_CIKTI="$cikti"

    if [ "$kod" = "0" ]; then
        kaydet "huni · $ad tamam"
        return 0
    fi

    # ⚠️ Bu adımların üçü de (`bosluk arastir`, `konu kaynak`, `trend aktar`)
    # işlenecek aday kalmadığında sıfırdan farklı dönüyor. Bu bir hata DEĞİL:
    # sondaj tavanı dolduğunda ya da o günün adayları zaten aktarılmışsa
    # normal hâl. Boş günü hata sayarsak bildirim her gün gelir, kimse bakmaz
    # ve DW-47'nin çözdüğü sessiz başarısızlık bu kez gürültünün içinde
    # kaybolur. Desen CLI'ın kendi metnine dayanıyor ve testle kilitli.
    if printf '%s' "$cikti" | grep -qi "aday yok"; then
        kaydet "huni · $ad — işlenecek aday yok (boş gün, hata değil)"
        return 0
    fi

    kaydet "HATA: huni · $ad başarısız (çıkış $kod)"
    basarisiz=1
}

if [ "$kuru" = "0" ]; then
    onucus || { bildir "Huni başlayamadı — önuçuş kontrolü düştü."; exit 1; }
    kaydet "günlük huni başlıyor"
fi

# 1 · Wikipedia okunma sıçramaları. Ücretsiz, anahtarsız, YouTube kotasız.
adim "konu topla" 0 konu topla --adet "$MAKALE"

# 2 · Wikidata'nın karar veremediği kuyruk LLM'e sorulur.
# Anahtar yoksa huni durmaz: `belirsiz` makaleler kuyrukta bekler, huninin
# geri kalanı `tarih`/`bilim` olarak zaten sınıflanmış adaylarla çalışır.
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    adim "konu siniflandir" 1 konu siniflandir --limit "$SINIF"
else
    if [ "$kuru" = "1" ]; then
        printf '\n--- konu siniflandir (atlandı: ANTHROPIC_API_KEY yok) ---\n'
    else
        kaydet "UYARI: ANTHROPIC_API_KEY yok — 'konu siniflandir' atlandı, belirsiz kuyruğu birikiyor"
    fi
fi

# 3 · Huninin tek pahalı adımı — talep-arz sondajı.
adim "bosluk arastir" 1 bosluk arastir --limit "$SONDAJ"

# 4 · Referans, olgu ve görsel tabanı. YPP "inauthentic content" karşı önlemi.
adim "konu kaynak" 0 konu kaynak --limit "$KAYNAK"

# 5 · Devir noktası: adaylar 📈 Trend Adayları'na düşer.
adim "trend aktar" 1 trend aktar --adet "$AKTAR"

# Sıçrama bildirimi (DW-54): bildirim şimdiye dek yalnızca HATA yolundaydı.
# Acil aday bir fırsat sinyali ve saatler içinde değer kaybediyor — sabah
# Notion kontrolünü beklemesi tespitin anlamını sıfırlar. Desen CLI'ın
# kendi çıktısına dayanıyor ("acil aday", trend aktar basar), testle kilitli.
if [ "$kuru" = "0" ] && printf '%s' "${SON_CIKTI:-}" | grep -qi "acil aday"; then
    bildir "🔥 Sıçrayan konu Notion'a düştü — acil adaylara bakın."
fi

if [ "$kuru" = "1" ]; then
    printf '\nKuru koşum bitti — hiçbir kota harcanmadı, depoya yazılmadı.\n'
    exit 0
fi

if [ "$basarisiz" = "1" ]; then
    kaydet "günlük huni HATALI bitti"
    bildir "Günlük huni bir veya daha fazla adımda düştü. Günlük: $GUNLUK"
    exit 1
fi

kaydet "günlük huni tamam"
exit 0
