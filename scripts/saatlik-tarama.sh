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

set -uo pipefail

PROJE="${YT_OTOMASYON_KOK:-$HOME/Projects/Yt_Automation}"
cd "$PROJE" || { echo "proje dizini yok: $PROJE" >&2; exit 1; }

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

PY="$PROJE/.venv/bin/python"
[ -x "$PY" ] || { echo "sanal ortam yok: $PY" >&2; exit 1; }

GUNLUK_DIZIN="${YT_OTOMASYON_GUNLUK:-$PROJE/veri/gunluk}"
mkdir -p "$GUNLUK_DIZIN"
GUNLUK="$GUNLUK_DIZIN/tarama-$(date +%Y-%m-%d).log"

kaydet() { printf '%s  %s\n' "$(date '+%H:%M:%S')" "$*" >> "$GUNLUK"; }

# Geniş taramayı günde bir kez: bugünün damgası dosyada yoksa çalıştır.
# `kosu` tablosuna sormak daha doğru olurdu ama bu kontrol kabuğun içinde
# kalabildiği sürece betik tek başına anlaşılır kalıyor.
NOBET="$GUNLUK_DIZIN/.genis-$(date +%Y-%m-%d)"
if [ ! -f "$NOBET" ]; then
    kaydet "geniş tarama başlıyor"
    if "$PY" -m yt_automation.cli trend topla --genis >> "$GUNLUK" 2>&1; then
        touch "$NOBET"
        kaydet "geniş tarama tamam"
    else
        kaydet "geniş tarama BAŞARISIZ (çıkış $?)"
    fi
fi

kaydet "derin tarama başlıyor"
"$PY" -m yt_automation.cli trend topla --derin >> "$GUNLUK" 2>&1 \
    && kaydet "derin tarama tamam" \
    || kaydet "derin tarama BAŞARISIZ (çıkış $?)"

# Ücretsiz adımlar: kota harcamıyorlar, her koşumda çalışabilirler.
"$PY" -m yt_automation.cli trend siniflandir >> "$GUNLUK" 2>&1 || kaydet "sınıflandırma başarısız"

# Eski günlükleri temizle — 30 günden fazlasını tutmanın faydası yok.
find "$GUNLUK_DIZIN" -name 'tarama-*.log' -mtime +30 -delete 2>/dev/null
find "$GUNLUK_DIZIN" -name '.genis-*' -mtime +2 -delete 2>/dev/null
