#!/bin/bash
# Ortak önyükleme — `saatlik-tarama.sh` ve `gunluk-huni.sh` bunu `source` ediyor.
#
# Kendi başına çalıştırılmaz; tek işi iki betiğin de aynı ortamı aynı biçimde
# kurması. Ayrı bir dosya olmasının sebebi kopyala-yapıştır değil **sapma**:
# `.env` yükleme sırası ve kota koruması iki yerde ayrı ayrı durursa biri
# düzeltilip diğeri unutulur.
#
# Üç yol birbirinden bağımsız ve bu ayrım bilinçli (ADR-0008):
#   · KOD  → `YT_OTOMASYON_KOK`   — sabit ref'e iğnelenmiş worktree
#   · VERİ → `YT_OTOMASYON_VERI`  — geliştirme ağacının `veri/` dizini
#   · SIR  → `YT_OTOMASYON_ENV`   — geliştirme ağacının `.env` dosyası

PROJE="${YT_OTOMASYON_KOK:-$HOME/Projects/Yt_Automation}"
cd "$PROJE" || { echo "proje dizini yok: $PROJE" >&2; exit 1; }

ENV_DOSYA="${YT_OTOMASYON_ENV:-$PROJE/.env}"

# ⚠️ `.env` bu değişkenleri BOŞ değerle taşıyor (`.env.example`'da öyle yazıyor).
# `set -a` ile kaynaklandığında o boş değer, `launchd`'ın plist üzerinden
# verdiği gerçek yolu **ezer** — sonuç, deponun geliştirme ağacı yerine
# worktree'nin içine yazılması ve iki ayrı veritabanının sessizce oluşması.
# Bu yüzden ortamdan gelen dolu değerler önce saklanıyor, sonra geri konuyor.
_KOK_ONCE="${YT_OTOMASYON_KOK:-}"
_VERI_ONCE="${YT_OTOMASYON_VERI:-}"
_GUNLUK_ONCE="${YT_OTOMASYON_GUNLUK:-}"

if [ -f "$ENV_DOSYA" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_DOSYA"
    set +a
fi

if [ -n "$_KOK_ONCE" ]; then export YT_OTOMASYON_KOK="$_KOK_ONCE"; fi
if [ -n "$_VERI_ONCE" ]; then export YT_OTOMASYON_VERI="$_VERI_ONCE"; fi
if [ -n "$_GUNLUK_ONCE" ]; then export YT_OTOMASYON_GUNLUK="$_GUNLUK_ONCE"; fi

PY="$PROJE/.venv/bin/python"
VERI_DIZIN="${YT_OTOMASYON_VERI:-$PROJE/veri}"
GUNLUK_DIZIN="${YT_OTOMASYON_GUNLUK:-$VERI_DIZIN/gunluk}"
mkdir -p "$GUNLUK_DIZIN" 2>/dev/null
GUNLUK="$GUNLUK_DIZIN/tarama-$(date +%Y-%m-%d).log"
NOBET="$GUNLUK_DIZIN/.son-basarili"

kaydet() { printf '%s  %s\n' "$(date '+%H:%M:%S')" "$*" >> "$GUNLUK"; }

# macOS bildirimi. `launchd.hata.log`'a yazmak yetmiyor — kimse okumuyor.
# 2026-07-30: görev dal değişimi yüzünden beş saat boyunca çıkış kodu 127 ile
# öldü, hata günlüğüne beş satır düştü ve tesadüfen fark edildi. Sessiz
# başarısızlığı bitiren şey günlük değil, ekrana çıkan bildirim.
bildir() {
    local mesaj="${1//\"/\\\"}"
    osascript -e "display notification \"$mesaj\" with title \"YT trend otomasyonu\"" \
        >/dev/null 2>&1 || true
}

# Önuçuş kontrolü — çıplak `127` yerine ne eksik olduğunu söyler.
onucus() {
    local hata=0
    if [ ! -x "$PY" ]; then
        kaydet "HATA: sanal ortam yok: $PY"
        hata=1
    elif ! "$PY" -c 'import yt_automation' >/dev/null 2>&1; then
        kaydet "HATA: yt_automation import edilemiyor — worktree'de 'pip install -e .' eksik"
        hata=1
    fi
    [ -f "$ENV_DOSYA" ] || kaydet "UYARI: .env yok: $ENV_DOSYA"
    if [ -z "${YOUTUBE_API_KEY:-}" ]; then
        kaydet "HATA: YOUTUBE_API_KEY boş — tarama kota çağrısı yapamaz"
        hata=1
    fi
    if ! mkdir -p "$VERI_DIZIN" 2>/dev/null || [ ! -w "$VERI_DIZIN" ]; then
        kaydet "HATA: veri dizini yazılabilir değil: $VERI_DIZIN"
        hata=1
    fi
    return $hata
}
