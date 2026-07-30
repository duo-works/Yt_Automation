#!/bin/bash
# Saatlik trend taramasını `launchd`'a kurar, tazeler, durumunu gösterir ya da
# kaldırır.
#
#   scripts/zamanlama-kur.sh kur [--ref <ref>]
#   scripts/zamanlama-kur.sh tazele [--ref <ref>]
#   scripts/zamanlama-kur.sh durum
#   scripts/zamanlama-kur.sh kaldir
#
# ⚠️ Yalnızca macOS. Ömer Windows'ta çalışıyor; oradaki karşılığı Görev
# Zamanlayıcı ve henüz yazılmadı — ihtiyaç doğduğunda ayrı görev açılacak.
# Trend hattı Mirza'nın makinesinde çalıştığı için bu bir engel değil.
#
# ⚠️ Zamanlanmış iş geliştirme ağacından KOŞMUYOR (ADR-0008). Kendi worktree'si
# var ve sabit bir ref'e iğneli. Sebebi ölçüldü: 2026-07-30'da geliştirme ağacı
# `main`'e geçince `saatlik-tarama.sh` ortadan kayboldu (o dosya yalnızca
# DW-32'den sonraki dallarda var) ve görev beş saat boyunca çıkış kodu 127 ile
# öldü; beş derin tarama örneği kayboldu. Otomasyonu yeni koda taşımak artık
# `tazele` ile BİLİNÇLİ bir eylem, dal değiştirmenin yan etkisi değil.

set -uo pipefail

ETIKET="works.duo.yt-trend"
KAYNAK="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Kod worktree'de; veri ve sırlar geliştirme ağacında kalıyor. İkisi de
# gitignore'da olduğu için dal değişiminden zaten etkilenmiyorlar.
CALISMA="${YT_OTOMASYON_CALISMA:-$HOME/.yt-otomasyon/calisan}"
VERI="${YT_OTOMASYON_VERI:-$KAYNAK/veri}"
ENV_DOSYA="${YT_OTOMASYON_ENV:-$KAYNAK/.env}"

SABLON="$KAYNAK/scripts/$ETIKET.plist"
BETIK="$CALISMA/scripts/saatlik-tarama.sh"
HEDEF="$HOME/Library/LaunchAgents/$ETIKET.plist"
NOBET="$VERI/gunluk/.son-basarili"

# Nöbet bu yaştan eskiyse görev "yüklü ama çalışmıyor" sayılır. Saatlik bir iş
# için iki saat, tek bir kaçırılmış koşumu hata saymayacak kadar geniş.
NOBET_TAZELIK=7200

komut="${1:-durum}"
[ $# -gt 0 ] && shift

REF=""
while [ $# -gt 0 ]; do
    case "$1" in
    --ref)
        REF="${2:-}"
        [ -n "$REF" ] || { echo "--ref bir değer istiyor" >&2; exit 1; }
        shift 2
        ;;
    *)
        echo "bilinmeyen seçenek: $1" >&2
        exit 1
        ;;
    esac
done

macos_ol() {
    [ "$(uname)" = "Darwin" ] || { echo "bu betik yalnızca macOS'ta çalışır" >&2; exit 1; }
}

# Worktree'yi kurar ya da mevcut olanı bırakır. Ref verilmezse geliştirme
# ağacının o anki HEAD'i iğnelenir.
worktree_hazirla() {
    local ref="${REF:-$(git -C "$KAYNAK" rev-parse HEAD 2>/dev/null)}"
    [ -n "$ref" ] || { echo "git deposu bulunamadı: $KAYNAK" >&2; return 1; }

    if [ -e "$CALISMA/.git" ]; then
        echo "ℹ️  worktree zaten var: $CALISMA"
        echo "   başka bir ref'e taşımak için: $0 tazele --ref <ref>"
        return 0
    fi

    mkdir -p "$(dirname "$CALISMA")"
    # `--detach`: dal checkout etmiyoruz. Aksi hâlde aynı dal iki worktree'de
    # birden checkout edilemez ve geliştirme ağacı o dala geçemez olurdu.
    git -C "$KAYNAK" worktree add --detach "$CALISMA" "$ref" || return 1
    echo "✅ worktree kuruldu: $CALISMA"
}

venv_hazirla() {
    if [ -x "$CALISMA/.venv/bin/python" ]; then
        return 0
    fi
    local py
    py="$(command -v python3.13 2>/dev/null || command -v python3 2>/dev/null || true)"
    [ -n "$py" ] || { echo "python3.13 bulunamadı" >&2; return 1; }

    echo "   sanal ortam kuruluyor (bir kerelik)…"
    "$py" -m venv "$CALISMA/.venv" || return 1
    "$CALISMA/.venv/bin/pip" install --quiet --upgrade pip || return 1
    "$CALISMA/.venv/bin/pip" install --quiet -e "$CALISMA" || return 1
}

plist_yaz() {
    mkdir -p "$HOME/Library/LaunchAgents" "$VERI/gunluk"
    # Şablondaki yer tutucular burada dolduruluyor: plist'in kendisi mutlak
    # yol içermiyor, yani commit edilebiliyor ve iki makinede de çalışıyor.
    sed -e "s|__CALISMA__|$CALISMA|g" \
        -e "s|__BETIK__|$BETIK|g" \
        -e "s|__VERI__|$VERI|g" \
        -e "s|__ENV__|$ENV_DOSYA|g" \
        "$SABLON" > "$HEDEF"
    chmod +x "$CALISMA"/scripts/*.sh 2>/dev/null
}

yeniden_yukle() {
    launchctl unload "$HEDEF" 2>/dev/null
    launchctl load "$HEDEF"
}

case "$komut" in
kur)
    macos_ol
    [ -f "$ENV_DOSYA" ] || echo "⚠️  .env yok ($ENV_DOSYA) — YOUTUBE_API_KEY olmadan tarama başarısız olur"

    worktree_hazirla || exit 1
    venv_hazirla || exit 1

    # İğnelenen ref DW-32'den eskiyse betikler orada yoktur. Bunu kurulum
    # anında söylemek, saat başı 127 almaktan iyi.
    [ -f "$BETIK" ] || {
        echo "❌ $BETIK yok — iğnelenen ref betikleri içermiyor." >&2
        echo "   Betikleri içeren bir ref ile deneyin: $0 tazele --ref <ref>" >&2
        exit 1
    }

    plist_yaz
    if yeniden_yukle; then
        echo "✅ kuruldu: $HEDEF"
        echo "   kod   : $CALISMA ($(git -C "$CALISMA" rev-parse --short HEAD 2>/dev/null))"
        echo "   veri  : $VERI"
        echo "   sırlar: $ENV_DOSYA"
        echo "   saat başı çalışacak; ilk koşum şimdi başladı (RunAtLoad)"
        echo "   günlük: $VERI/gunluk/tarama-\$(date +%Y-%m-%d).log"
    else
        echo "❌ launchctl load başarısız" >&2
        exit 1
    fi
    ;;
tazele)
    macos_ol
    [ -e "$CALISMA/.git" ] || { echo "worktree yok. Önce: $0 kur" >&2; exit 1; }

    ref="${REF:-$(git -C "$KAYNAK" rev-parse HEAD 2>/dev/null)}"
    git -C "$CALISMA" fetch --quiet origin 2>/dev/null
    git -C "$CALISMA" checkout --detach "$ref" 2>/dev/null || {
        echo "❌ ref checkout edilemedi: $ref" >&2
        exit 1
    }
    [ -f "$BETIK" ] || { echo "❌ $BETIK yok — bu ref betikleri içermiyor" >&2; exit 1; }

    # Bağımlılıklar değişmiş olabilir; kod değişimi editable kurulumda zaten
    # otomatik yansıyor.
    "$CALISMA/.venv/bin/pip" install --quiet -e "$CALISMA" 2>/dev/null

    plist_yaz
    yeniden_yukle >/dev/null 2>&1
    echo "✅ tazelendi: $(git -C "$CALISMA" rev-parse --short HEAD) — $(git -C "$CALISMA" log -1 --format=%s)"
    ;;
durum)
    saglikli=0

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
        if [ "$cikis" != "0" ]; then
            echo "   ⚠️  son koşum sıfırdan farklı çıkış kodu verdi: $cikis"
            saglikli=1
        fi
    else
        echo "❌ yüklü değil. Kurmak için: $0 kur"
        saglikli=1
    fi

    echo
    if [ -e "$CALISMA/.git" ]; then
        echo "kod: $CALISMA"
        echo "   $(git -C "$CALISMA" rev-parse --short HEAD) — $(git -C "$CALISMA" log -1 --format=%s 2>/dev/null)"
        [ -f "$BETIK" ] || { echo "   ❌ saatlik-tarama.sh bu ref'te yok"; saglikli=1; }
    else
        echo "❌ worktree yok: $CALISMA"
        saglikli=1
    fi

    # Nöbet tazeliği — "yüklü" görünüp hiç koşmayan görevi yakalayan tek şey.
    echo
    if [ -f "$NOBET" ]; then
        yas=$(( $(date +%s) - $(stat -f %m "$NOBET" 2>/dev/null || echo 0) ))
        if [ "$yas" -gt "$NOBET_TAZELIK" ]; then
            echo "❌ son başarılı koşum $((yas / 60)) dakika önce — görev yüklü ama çalışmıyor"
            saglikli=1
        else
            echo "✅ son başarılı koşum $((yas / 60)) dakika önce"
        fi
    else
        echo "⚠️  hiç başarılı koşum yok (nöbet dosyası: $NOBET)"
        saglikli=1
    fi

    son="$(ls -t "$VERI"/gunluk/tarama-*.log 2>/dev/null | head -1)"
    [ -n "$son" ] && { echo; echo "son günlük ($son):"; tail -8 "$son" | sed 's/^/   /'; }
    exit "$saglikli"
    ;;
kaldir)
    launchctl unload "$HEDEF" 2>/dev/null
    rm -f "$HEDEF"
    echo "✅ kaldırıldı (günlükler, veri ve worktree korundu)"
    echo "   worktree'yi de silmek için: git -C $KAYNAK worktree remove $CALISMA"
    ;;
*)
    echo "kullanım: $0 {kur|tazele|durum|kaldir} [--ref <ref>]" >&2
    exit 1
    ;;
esac
