#!/bin/bash
# Saatlik trend taramasını `launchd`'a kurar, durumunu gösterir ya da kaldırır.
#
#   scripts/zamanlama-kur.sh kur
#   scripts/zamanlama-kur.sh durum
#   scripts/zamanlama-kur.sh kaldir
#
# ⚠️ Yalnızca macOS. Ömer Windows'ta çalışıyor; oradaki karşılığı Görev
# Zamanlayıcı ve henüz yazılmadı — ihtiyaç doğduğunda ayrı görev açılacak.
# Trend hattı Mirza'nın makinesinde çalıştığı için bu bir engel değil.

set -uo pipefail

ETIKET="works.duo.yt-trend"
PROJE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SABLON="$PROJE/scripts/$ETIKET.plist"
BETIK="$PROJE/scripts/saatlik-tarama.sh"
HEDEF="$HOME/Library/LaunchAgents/$ETIKET.plist"

komut="${1:-durum}"

case "$komut" in
kur)
    [ "$(uname)" = "Darwin" ] || { echo "bu betik yalnızca macOS'ta çalışır" >&2; exit 1; }
    [ -x "$PROJE/.venv/bin/python" ] || {
        echo "sanal ortam yok. Önce: python3.13 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
        exit 1
    }
    [ -f "$PROJE/.env" ] || echo "⚠️  .env yok — YOUTUBE_API_KEY olmadan tarama başarısız olur"

    mkdir -p "$HOME/Library/LaunchAgents" "$PROJE/veri/gunluk"
    # Şablondaki yer tutucular burada dolduruluyor: plist'in kendisi mutlak
    # yol içermiyor, yani commit edilebiliyor ve iki makinede de çalışıyor.
    sed -e "s|__PROJE__|$PROJE|g" -e "s|__BETIK__|$BETIK|g" "$SABLON" > "$HEDEF"
    chmod +x "$BETIK"

    launchctl unload "$HEDEF" 2>/dev/null
    if launchctl load "$HEDEF"; then
        echo "✅ kuruldu: $HEDEF"
        echo "   saat başı çalışacak; ilk koşum şimdi başladı (RunAtLoad)"
        echo "   günlük: $PROJE/veri/gunluk/tarama-\$(date +%Y-%m-%d).log"
    else
        echo "❌ launchctl load başarısız" >&2
        exit 1
    fi
    ;;
durum)
    # ⚠️ `launchctl list | grep -q` KULLANMA. `grep -q` ilk eşleşmede çıkıyor,
    # `launchctl list` SIGPIPE alıyor ve `pipefail` yüzünden boru başarısız
    # sayılıyor — sonuç, yüklü bir görev için "yüklü değil" demek. Bu fiilen
    # oldu: görev saat 15:04'te çalıştı, `durum` ❌ gösterdi.
    #
    # Çıktı önce değişkene alınıyor; boru yok, SIGPIPE yok.
    kayit="$(launchctl list 2>/dev/null || true)"
    satir="$(printf '%s\n' "$kayit" | grep -F "$ETIKET" || true)"
    if [ -n "$satir" ]; then
        echo "✅ yüklü:"
        printf '%s\n' "$satir" | sed 's/^/   /'
        echo "   (sütunlar: PID  son çıkış kodu  etiket — PID '-' ise şu an koşmuyor, normal)"
        cikis="$(printf '%s\n' "$satir" | awk '{print $2}')"
        [ "$cikis" = "0" ] || echo "   ⚠️  son koşum sıfırdan farklı çıkış kodu verdi: $cikis"
    else
        echo "❌ yüklü değil. Kurmak için: scripts/zamanlama-kur.sh kur"
    fi
    son="$(ls -t "$PROJE"/veri/gunluk/tarama-*.log 2>/dev/null | head -1)"
    [ -n "$son" ] && { echo; echo "son günlük ($son):"; tail -8 "$son" | sed 's/^/   /'; }
    ;;
kaldir)
    launchctl unload "$HEDEF" 2>/dev/null
    rm -f "$HEDEF"
    echo "✅ kaldırıldı (günlükler ve veri korundu)"
    ;;
*)
    echo "kullanım: $0 {kur|durum|kaldir}" >&2
    exit 1
    ;;
esac
