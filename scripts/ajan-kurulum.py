"""Ajan kurulumunu yapar ve **doğrular** — Claude Code ve Codex için.

    python3 scripts/ajan-kurulum.py          # doğrula, eksikleri raporla
    python3 scripts/ajan-kurulum.py --kur    # eksikleri gidermeyi de dene

## Neden betik

`AGENTS.md` dört önkoşulu sayıyor (Notion erişimi, git kimliği, hook onayı,
Codex kopyası) ama elle yapılınca atlanıyor: bu betik yazılırken ölçüldü —
`~/.codex/prompts/` **hiç yoktu**, yani Codex tarafında komutların hiçbiri
kurulu değildi ve kimse fark etmemişti.

Asıl mesele "kurmak" değil **"kurulduğunu doğrulamak"**: dört önkoşulun üçü
sessizce bozuluyor. Komut hata vermez, yanlış iş yapar.

## Platform

Saf Python + stdlib. Ömer Windows'ta çalıştığı için bilinçli tercih: aynı
komut iki platformda da çalışır, Git Bash gerekmez. (`scripts/zamanlama-kur.sh`
yalnızca macOS; oradaki ders bu.)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KOMUT_KAYNAGI = KOK / "docs" / "ajan" / "komutlar"
CODEX_PROMPTS = Path.home() / ".codex" / "prompts"

# Git kimliği → Notion `Kişi` alanı. `oturum-basla.md` ile aynı tablo;
# ikisi ayrışırsa kayıtlar yanlış kişiye açılır.
KIMLIKLER = {
    "Mirza Sarıbıyık": "Mirza",
    "Ömer Faruk Güleç": "Ömer",
    "ofgworks": "Ömer",
}

# NFKD'nin **ayrıştırmadığı** harfler. `ü → u + ¨` ayrışıyor ama `ı` ayrı bir
# harf olduğu için ayrışmıyor: "Sarıbıyık" → "Sarbyk" olurdu.
#
# Aynı tablo `trend/bosluk.py`'de de var (orada alaka ölçümü için). Burada
# kopyalanmasının sebebi bu betiğin **kurulumdan önce** çalışması: paket
# kurulu olmayabilir, `src/` içinden import edilemez.
_AYRISMAYAN = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "ğ": "g"})


def _sadelestir(ad: str) -> str:
    """Aksanları düşürür, küçük harfe indirir.

    ⚠️ Git kimliği ASCII'ye düşebiliyor: Ömer'in makinesinde ölçülen değer
    `Omer Faruk Gulec` idi ve tabloda `Ömer Faruk Güleç` yazdığı için kimlik
    "tabloda yok" sayılıyordu. Windows kurulumları bu değeri tekrar
    üretebiliyor, yani tabloya ASCII satırı eklemek kalıcı çözüm değil —
    karşılaştırmanın kendisi aksana duyarsız olmalı.
    """
    sade = unicodedata.normalize("NFKD", ad.casefold().translate(_AYRISMAYAN))
    return "".join(k for k in sade if not unicodedata.combining(k)).strip()


# Aksana duyarsız arama tablosu — yukarıdakinden türetilir, elle tutulmaz.
_ARAMA = {_sadelestir(ad): kisi for ad, kisi in KIMLIKLER.items()}

YESIL, KIRMIZI, SARI, SIFIRLA = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def isaret(durum: str) -> str:
    return {
        "ok": f"{YESIL}✅{SIFIRLA}",
        "hata": f"{KIRMIZI}🔴{SIFIRLA}",
        "uyari": f"{SARI}⚠️{SIFIRLA} ",
    }[durum]


class Rapor:
    def __init__(self) -> None:
        self.satirlar: list[tuple[str, str, str]] = []

    def ekle(self, durum: str, baslik: str, detay: str = "") -> None:
        self.satirlar.append((durum, baslik, detay))
        print(f"  {isaret(durum)} {baslik}")
        for parca in filter(None, detay.split("\n")):
            print(f"       {parca}")

    @property
    def hatali(self) -> int:
        return sum(1 for d, _, _ in self.satirlar if d == "hata")


def git_kimligi(rapor: Rapor) -> None:
    """`Kişi` alanının tek kaynağı. Yanlışsa kayıt yanlış kişiye açılır."""
    try:
        ad = subprocess.run(
            ["git", "config", "user.name"], cwd=KOK, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as hata:
        rapor.ekle("hata", "Git kimliği okunamadı", str(hata))
        return

    if not ad:
        rapor.ekle(
            "hata",
            "Git kimliği boş",
            'git config user.name "Ömer Faruk Güleç"   ← kendi adınızla',
        )
    elif kisi := _ARAMA.get(_sadelestir(ad)):
        rapor.ekle("ok", f"Git kimliği: {ad} → Notion `Kişi` = {kisi}")
    else:
        rapor.ekle(
            "hata",
            f"Git kimliği tabloda yok: {ad!r}",
            "Oturum kaydı yanlış kişiye açılır ve bu FARK EDİLMEZ.\n"
            f"Tanınanlar: {', '.join(KIMLIKLER)} (aksansız yazımları da geçerli).",
        )


def notion_erisimi(rapor: Rapor) -> None:
    """Yedek yolu gerçekten çalıştırır — 'token var' demek yetmez."""
    betik = KOK / "scripts" / "oturum-sorgula.py"
    if not betik.is_file():
        rapor.ekle("hata", "scripts/oturum-sorgula.py yok")
        return
    sonuc = subprocess.run([sys.executable, str(betik)], capture_output=True, text=True, timeout=60)
    if sonuc.returncode == 0:
        rapor.ekle("ok", "Notion yedek yolu çalışıyor (kanarya göründü)")
    elif sonuc.returncode == 2:
        rapor.ekle(
            "hata",
            "Notion sorgusu çalıştı ama KANARYA YOK",
            "Kanal bozuk olabilir. Çoklu-ajan işine başlamayın.",
        )
    else:
        ilk = (sonuc.stdout.strip().splitlines() or ["-"])[0]
        rapor.ekle("hata", "Notion yedek yolu çalışmıyor", ilk)


def hook_yapilandirmasi(rapor: Rapor) -> None:
    """Hook'un **tanımlı** olduğunu doğrular; onaylandığını doğrulayamaz."""
    ayar = KOK / ".claude" / "settings.json"
    if not ayar.is_file():
        rapor.ekle("hata", ".claude/settings.json yok")
        return
    try:
        veri = json.loads(ayar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as hata:
        # Bozuk JSON o dosyadaki TÜM ayarları sessizce devre dışı bırakır.
        rapor.ekle("hata", ".claude/settings.json bozuk JSON", str(hata))
        return
    olaylar = [o for o in ("SessionStart", "Stop") if o in veri.get("hooks", {})]
    if len(olaylar) == 2:
        rapor.ekle(
            "ok",
            "Hook'lar tanımlı (SessionStart + Stop)",
            "⚠️ Tanımlı olması çalıştığı anlamına gelmez: Claude Code proje"
            "\nhook'ları için bir kez onay ister. Yeni oturumda protokol"
            "\nhatırlatması gelmiyorsa `/hooks` menüsünü bir kez açın.",
        )
    else:
        rapor.ekle("hata", f"Hook eksik — bulunan: {olaylar or 'hiçbiri'}")


def codex_komutlari(rapor: Rapor, kur: bool) -> None:
    """Codex'te repo bazında slash komut yok; dosyalar kişisel dizine kopyalanır."""
    if not KOMUT_KAYNAGI.is_dir():
        rapor.ekle("hata", f"Komut kaynağı yok: {KOMUT_KAYNAGI}")
        return
    kaynaklar = sorted(KOMUT_KAYNAGI.glob("*.md"))

    if kur:
        CODEX_PROMPTS.mkdir(parents=True, exist_ok=True)
        for dosya in kaynaklar:
            shutil.copy2(dosya, CODEX_PROMPTS / dosya.name)

    if not CODEX_PROMPTS.is_dir():
        rapor.ekle(
            "hata",
            "Codex komutları kurulu değil (~/.codex/prompts yok)",
            "`--kur` ile çalıştırın. Codex kullanmıyorsanız bu satırı yok sayın.",
        )
        return

    eksik = [d.name for d in kaynaklar if not (CODEX_PROMPTS / d.name).is_file()]
    if eksik:
        rapor.ekle("hata", f"Codex'te eksik komut: {', '.join(eksik)}", "`--kur` ile giderilir.")
        return

    # ⚠️ Kopya bayatlayabilir: kanonik dosya değişince Codex eskisini çalıştırır
    # ve bunu söylemez. Bu, "komut davranışı beklenmedik" şikâyetinin ilk sebebi.
    bayat = [d.name for d in kaynaklar if (CODEX_PROMPTS / d.name).read_bytes() != d.read_bytes()]
    if bayat:
        rapor.ekle(
            "uyari",
            f"Codex kopyası bayat: {', '.join(bayat)}",
            "Kanonik dosya değişmiş. `--kur` ile tazeleyin.",
        )
    else:
        rapor.ekle("ok", f"Codex komutları güncel ({len(kaynaklar)} dosya)")


def claude_komutlari(rapor: Rapor) -> None:
    sarmalayicilar = sorted((KOK / ".claude" / "commands").glob("*.md"))
    kanonik = sorted(KOMUT_KAYNAGI.glob("*.md"))
    eksik = {d.stem for d in kanonik} - {d.stem for d in sarmalayicilar}
    if eksik:
        rapor.ekle("hata", f"Claude Code sarmalayıcısı eksik: {', '.join(sorted(eksik))}")
    else:
        rapor.ekle("ok", f"Claude Code komutları yerinde ({len(sarmalayicilar)} adet)")


def main() -> int:
    ayrist = argparse.ArgumentParser(description="Ajan kurulumunu doğrula (ve iste, kur)")
    ayrist.add_argument("--kur", action="store_true", help="Eksikleri gidermeyi de dene")
    args = ayrist.parse_args()

    print(f"\n=== AJAN KURULUMU {'(kur + doğrula)' if args.kur else '(yalnızca doğrula)'} ===\n")
    rapor = Rapor()
    git_kimligi(rapor)
    claude_komutlari(rapor)
    codex_komutlari(rapor, args.kur)
    hook_yapilandirmasi(rapor)
    notion_erisimi(rapor)

    print()
    if rapor.hatali:
        print(f"{KIRMIZI}{rapor.hatali} eksik var — komutlar güvenilir çalışmaz.{SIFIRLA}")
        if not args.kur:
            print("Bir kısmı otomatik giderilebilir:  python3 scripts/ajan-kurulum.py --kur")
        return 1
    print(f"{YESIL}Kurulum tam. `/oturum-basla` ile başlayabilirsiniz.{SIFIRLA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
