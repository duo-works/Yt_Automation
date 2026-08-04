"""Aktif oturum kayıtlarını **MCP olmadan** sorgular — protokolün yedek yolu.

    python3 scripts/oturum-sorgula.py

`/oturum-basla`'nın 2. adımı normalde Notion MCP üzerinden sorgulanır. MCP
kopabiliyor: bu betik yazılırken de kopuktu (`Needs authentication`) ve
protokolün **tek** güvencesi o sorgu. Yedek yol olmadan tek seçenek "çoklu-ajan
işine başlama" oluyordu; bu betik ikinci bir yol açıyor.

## Neden doğrudan API

`ntn` (Notion CLI) kurulu olsa bile `ntn login` ya da `NOTION_WORKSPACE_ID`
istiyor — yani ayrı bir kurulum adımı. `NOTION_TOKEN` ise `.env`'de zaten var
(trend hattı Notion'a yazıyor), dolayısıyla bu yol **ek kurulum istemiyor**.

## Çıkış kodları

`/oturum-basla` bunlara göre davranmalı:

    0  sorgu çalıştı ve kanarya göründü  → sonuç güvenilir
    2  sorgu çalıştı ama kanarya YOK     → kanal bozuk, çoklu-ajan işine başlama
    1  sorgu çalışmadı                   → hatayı "kayıt yok" diye yorumlama

⚠️ 2 ile 0'ı ayırmak bu betiğin asıl işi. Boş sonuç "kimse çalışmıyor" da
olabilir "göremiyorum" da; ikisini ayıran tek şey kanaryanın görünmesi.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

TABAN = "https://api.notion.com/v1"
# ⚠️ 2025-09-03 sürümü `data_sources` uç noktasını getiriyor; daha eski
# sürümlerde `databases/<id>/query` kullanılır ve şema alanları farklıdır.
SURUM = "2025-09-03"
OTURUM_KAYDI = "280e2fd0-a14a-4d2d-ac25-24585472348e"
TOKEN_DEGISKENI = "NOTION_TOKEN"


def _env_oku(env: Path) -> str | None:
    if not env.is_file():
        return None
    for satir in env.read_text(encoding="utf-8").splitlines():
        satir = satir.strip()
        if satir.startswith(f"{TOKEN_DEGISKENI}="):
            return satir.split("=", 1)[1].strip().strip("\"'") or None
    return None


def token_bul() -> str | None:
    """Ortam değişkeni → bu kopyanın `.env`'i → **ana çalışma dizininin** `.env`'i.

    Üçüncüsü şart: `.env` git'e girmiyor, yani `git worktree` ile açılan bir
    kopyada **yok**. AGENTS.md ajanları worktree'de çalışmaya yönlendiriyor,
    dolayısıyla yedek yol orada da çalışmazsa hiç yok demektir.

    `--git-common-dir` worktree'den çağrıldığında ana repo'nun `.git` yolunu
    verir; onun üst dizini ana çalışma dizinidir.
    """
    if deger := os.environ.get(TOKEN_DEGISKENI):
        return deger

    kok = Path(__file__).resolve().parent.parent
    if deger := _env_oku(kok / ".env"):
        return deger

    try:
        ortak = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=kok,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not ortak:
        return None
    return _env_oku((kok / ortak).resolve().parent / ".env")


def _metin(ozellik: dict, tur: str) -> str:
    return "".join(p.get("plain_text", "") for p in (ozellik.get(tur) or []))


def _secim(ozellikler: dict, ad: str) -> str:
    return ((ozellikler.get(ad) or {}).get("select") or {}).get("name", "")


def aktif_kayitlar(token: str) -> list[dict]:
    """`Durum = Devam ediyor` olan tüm kayıtlar (sayfalama dahil)."""
    kayitlar: list[dict] = []
    imlec = None
    while True:
        # ⚠️ `Durum` bir **select**, `status` değil. `status` filtresiyle
        # sorulursa Notion `validation_error` döner — sessiz boş sonuç değil,
        # ama hata "kayıt yok" diye yorumlanırsa protokol çöker.
        govde: dict = {
            "filter": {"property": "Durum", "select": {"equals": "Devam ediyor"}},
            "page_size": 100,
        }
        if imlec:
            govde["start_cursor"] = imlec
        istek = urllib.request.Request(
            f"{TABAN}/data_sources/{OTURUM_KAYDI}/query",
            data=json.dumps(govde).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": SURUM,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(istek, timeout=30) as yanit:
            veri = json.load(yanit)
        kayitlar += veri.get("results", [])
        if not veri.get("has_more"):
            return kayitlar
        imlec = veri.get("next_cursor")


def main() -> int:
    token = token_bul()
    if not token:
        print(f"🔴 {TOKEN_DEGISKENI} bulunamadı (ortamda da `.env`'de de yok).")
        print("   `.env.example`'a bakın; token Notion → Settings → Integrations'tan alınır.")
        return 1

    try:
        kayitlar = aktif_kayitlar(token)
    except urllib.error.HTTPError as hata:
        govde = hata.read().decode("utf-8", "replace")[:300]
        print(f"🔴 Notion API hatası (HTTP {hata.code}): {govde}")
        print("   ⚠️ Bunu 'aktif kayıt yok' diye YORUMLAMAYIN — sorgu hiç çalışmadı.")
        return 1
    except OSError as hata:
        print(f"🔴 Ağ hatası: {hata}")
        print("   ⚠️ Bunu 'aktif kayıt yok' diye YORUMLAMAYIN — sorgu hiç çalışmadı.")
        return 1

    kanarya = [k for k in kayitlar if _secim(k["properties"], "Tür") == "Kanarya"]
    calisan = [k for k in kayitlar if _secim(k["properties"], "Tür") != "Kanarya"]

    print(f"=== AKTİF OTURUM KAYITLARI ({len(calisan)} çalışan + {len(kanarya)} kanarya) ===\n")
    for kayit in calisan:
        o = kayit["properties"]
        tur, kisi, ajan = (
            _secim(o, "Tür") or "-",
            _secim(o, "Kişi") or "?",
            _secim(o, "Ajan") or "?",
        )
        print(f"  [{tur}] {kisi} · {ajan}")
        print(f"      {_metin(o.get('Kayıt', {}), 'title')}")
        if dal := _metin(o.get("Branch", {}), "rich_text"):
            print(f"      dal   : {dal}")
        if alan := _metin(o.get("Dokunulan alanlar", {}), "rich_text"):
            print(f"      alanlar: {alan}")
        print(f"      url   : {kayit['url']}")
        print()

    if not calisan:
        print("  (kanarya dışında aktif kayıt yok)\n")

    if not kanarya:
        print("🚦 KANARYA GÖRÜNMEDİ — kanal bozuk olabilir.")
        print("   Sorgu çalıştı ama kanarya satırı dönmedi: eksik paylaşım, yanlış")
        print("   data source ya da bozuk filtre olabilir. Boş sonucun 'kimse")
        print("   çalışmıyor' mu 'göremiyorum' mu olduğu ayırt EDİLEMEZ.")
        print("   Çoklu-ajan işine başlamayın.")
        return 2

    print("🚦 Kanarya göründü — sonuç güvenilir.")
    if calisan:
        print("\n⚠️ Yukarıdaki kayıtların `alanlar` değerini kendi dokunacağın")
        print("   dosyalarla karşılaştır. Ölçüt 'başkasına ait' değil,")
        print("   **'bu oturuma ait değil'** — kendi kardeş ajanınla da çakışabilirsin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
