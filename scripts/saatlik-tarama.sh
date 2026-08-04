#!/bin/bash
# Saatlik trend taraması — `launchd` bunu çağırıyor.
#
# Neden ayrı bir kabuk betiği: `launchd` bir ortam devralmıyor (ne PATH, ne
# `.env`, ne çalışma dizini). Bunları plist içine gömmek yerine tek bir yerde
# toplamak, hem plist'i sabit tutuyor hem elle çalıştırıp aynı davranışı
# görmeyi sağlıyor.
#
# ⚠️ İki tür koşum var ve sırası önemli:
#   · Geniş tarama (222 birim) günde BİR kez — bölge sıralamasını besliyor.
#   · Derin tarama (40 birim) saat başı — zaman serisini besliyor.
# Geniş taramayı saat başı yapmak günlük bütçenin yarısını yer ve `mostPopular`
# yaklaşık saatlik tazelendiği için hiçbir ek bilgi getirmez.
#
# ⚠️ Bu betik artık geliştirme ağacından değil, sabit bir ref'e iğnelenmiş
# worktree'den koşuyor (ADR-0008). Sebebi ölçüldü: 2026-07-30'da geliştirme
# ağacı `main`'e geçince betik ortadan kayboldu ve görev beş saat boyunca
# çıkış kodu 127 ile öldü. Yolları `scripts/zamanlama-kur.sh` yönetiyor.

set -uo pipefail

# shellcheck source=scripts/ortak.sh
. "$(dirname "${BASH_SOURCE[0]}")/ortak.sh"

if ! onucus; then
    bildir "Tarama başlayamadı — önuçuş kontrolü düştü. Günlük: $GUNLUK"
    exit 1
fi

basarisiz=0

# Geniş taramayı günde bir kez: bugünün damgası dosyada yoksa çalıştır.
# `kosu` tablosuna sormak daha doğru olurdu ama bu kontrol kabuğun içinde
# kalabildiği sürece betik tek başına anlaşılır kalıyor.
GENIS_NOBET="$GUNLUK_DIZIN/.genis-$(date +%Y-%m-%d)"
if [ ! -f "$GENIS_NOBET" ]; then
    kaydet "geniş tarama başlıyor"
    if "$PY" -m yt_automation.cli trend topla --genis >> "$GUNLUK" 2>&1; then
        touch "$GENIS_NOBET"
        kaydet "geniş tarama tamam"
    else
        kaydet "HATA: geniş tarama başarısız (çıkış $?)"
        basarisiz=1
    fi
fi

kaydet "derin tarama başlıyor"
if "$PY" -m yt_automation.cli trend topla --derin >> "$GUNLUK" 2>&1; then
    kaydet "derin tarama tamam"
else
    kaydet "HATA: derin tarama başarısız (çıkış $?)"
    basarisiz=1
fi

# Ücretsiz adımlar: kota harcamıyorlar, her koşumda çalışabilirler.
if ! "$PY" -m yt_automation.cli trend siniflandir >> "$GUNLUK" 2>&1; then
    kaydet "HATA: sınıflandırma başarısız (çıkış $?)"
    basarisiz=1
fi

# Google Trends keşfi — saatlik olması bilinçli (DW-55): Wikipedia günlük
# yayımlıyor, gün-içi tazeliği veren tek kaynak bu. YouTube kotası 0.
#
# ⚠️ Bu adım koşumu düşürmüyor ve `basarisiz` işaretlemiyor. Gerekçe: dış bir
# RSS ucu bizim hattımızın sağlığı değil. Kırıldığında bildirim göndermek,
# DW-47'nin bitirdiği yanlış alarm düzenine geri dönmek olurdu; günlükte
# görünür kalıyor ve keşif kaynağı olmadan huni yine çalışıyor.
if ! "$PY" -m yt_automation.cli konu gtrends >> "$GUNLUK" 2>&1; then
    kaydet "UYARI: Google Trends keşfi başarısız (çıkış $?) — huni etkilenmedi"
fi

# Günlük aday hunisi — günde bir kez, geniş taramayla aynı nöbet deseniyle.
#
# ⚠️ Nöbet dosyası yalnızca BAŞARIDA konuyor, yani düşen bir huni ertesi saat
# yeniden deneniyor. Bu güvenli: tek pahalı adım olan sondaj
# `bosluk.SONDAJ_KOTA_TAVANI` (3.000 birim/gün) ile ayrıca sınırlı, tekrar
# denemeler bütçeyi süpüremez.
HUNI_NOBET="$GUNLUK_DIZIN/.huni-$(date +%Y-%m-%d)"
if [ ! -f "$HUNI_NOBET" ]; then
    if bash "$PROJE/scripts/gunluk-huni.sh"; then
        touch "$HUNI_NOBET"
    else
        basarisiz=1
    fi
fi

# Eski günlükleri temizle — 30 günden fazlasını tutmanın faydası yok.
find "$GUNLUK_DIZIN" -name 'tarama-*.log' -mtime +30 -delete 2>/dev/null
find "$GUNLUK_DIZIN" -name '.genis-*' -mtime +2 -delete 2>/dev/null
find "$GUNLUK_DIZIN" -name '.huni-*' -mtime +2 -delete 2>/dev/null

if [ "$basarisiz" = "1" ]; then
    bildir "Saatlik tarama bir veya daha fazla adımda düştü. Günlük: $GUNLUK"
    exit 1
fi

# Nöbet damgası: `zamanlama-kur.sh durum` bunun tazeliğine bakıyor. Görevin
# "yüklü" görünüp aslında hiç koşmaması bu dosya olmadan anlaşılmıyordu.
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$NOBET"
exit 0
