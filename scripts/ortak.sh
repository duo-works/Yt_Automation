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

# Bir adımın çıktısı "günlük kota tavanı doldu" mu diyor?
#
# Tavan tam olarak durdurmak için var; dolması bütçe hâli, arıza DEĞİL. Kota
# biten adım sıfırdan farklı dönüyor ve bunu hata sayan betik, tavanın dolduğu
# her saat bildirim gönderir — DW-47'nin bitirdiği yanlış alarm düzenine dönüş.
#
# Ölçüldü (2026-08-04): geri doldurma işi günlük kotayı bitirdi ve saatlik
# derin tarama 12:08'den itibaren 5 kez "düştü", her seferinde bildirim gitti.
# Daha kötüsü nöbet damgası yazılmadı, yani nöbetçi otomasyonu sağlıksız
# gösterdi — gerçekten bozulmuş bir hatla kotası dolmuş bir hat aynı göründü.
#
# ⚠️ `grep -i` KULLANMA. Türkçe'de ASCII "I" ile dotless "ı" ayrı harfler ve
# `grep -i` ikisini katlamaz; "kota tavanında durdu" deseni "KOTA TAVANINDA
# DURDU" çıktısını hiç tutmaz. Tam literal aranıyor, testle kilitli.
#
# Desen tek yerde: aynı kontrol `gunluk-huni.sh` ve `saatlik-tarama.sh`'ta
# ayrı ayrı dursaydı biri düzeltilip diğeri unutulurdu — bu kusur zaten öyle
# doğdu (huni tarafı düzeltildi, saatlik taraf gözden kaçtı).
KOTA_TAVANI_METNI="KOTA TAVANINDA DURDU"

kota_tavani_mi() { printf '%s' "$1" | grep -q "$KOTA_TAVANI_METNI"; }

# LLM kredisinin bitmesi de bütçe hâli — yukarıdaki kota tavanının ikizi.
#
# Ölçüldü (2026-08-19): `konu siniflandir` 7 Ağustos'tan beri HER koşumda
# 400 dönüyor ("Your credit balance is too low to access the Anthropic API").
# Son 7 günde 655 hata satırı. Adım hata sayıldığı için `gunluk-huni.sh`
# `exit 1` ile bitiyor, `saatlik-tarama.sh` nöbet dosyasını yazmıyor ve
# günlük huni ERTESİ SAAT baştan koşuyor. Kanıt: `veri/gunluk/` içinde
# `.genis-*` damgaları var, `.huni-*` HİÇ YOK.
#
# Bedeli iki katlı: sondaj kotası günün ilk koşumunda tükeniyor (sonraki
# koşumlar `0 sondaj`), ve her saat "huni düştü" bildirimi gidiyor — yani
# kredisi bitmiş bir hat ile gerçekten bozulmuş bir hat yine aynı görünüyor.
# Bu, yukarıdaki yorumun 2026-08-04'te kota için tarif ettiği kusurun aynısı.
#
# ⚠️ Bu satır krediyi geri getirmez, YANLIŞ ALARMI bitirir: adım atlandı
# diye kaydediliyor ve `belirsiz` kuyruğunun biriktiği zaten ayrıca
# uyarılıyor (`gunluk-huni.sh`, "belirsiz kuyruğu birikiyor").
#
# Desen sağlayıcının hata metnine dayanıyor ve testle kilitli. `grep -i`
# yok: metin ASCII ve yukarıdaki dotless-ı gerekçesi burada da geçerli.
#
# İki sağlayıcı, iki metin (DW-138 ile sınıflandırıcı OpenRouter'a da
# gidebiliyor). OpenRouter 402'si birebir (MPT `hata-20260912-111250.log`):
# "This request requires more credits, or fewer max_tokens". Sabit tek desen
# kalırsa OpenRouter'da kredi bitince huni yine saat başı baştan koşar.
KREDI_BITTI_METNI="credit balance is too low"
KREDI_BITTI_METNI_OPENROUTER="requires more credits"

kredi_bitti_mi() {
    printf '%s' "$1" | grep -q -e "$KREDI_BITTI_METNI" -e "$KREDI_BITTI_METNI_OPENROUTER"
}

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
