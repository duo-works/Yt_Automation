"""LLM sınıflandırma katmanı — Wikidata'nın karar veremediği kuyruk.

DW-34 Wikidata tipleriyle ücretsiz bir ön eleme kurdu ve kuyruğu 600'den
50'ye indirdi. Ama canlı koşum yetmediğini kanıtladı:

    Paul Newman   → "tarih" çıktı. Oyuncu; İspanyolca Wikidata kaydında
                    `Q189290` (subay) var, çünkü askerlik yapmış.
    Frida Kahlo   → belirsiz. Ölmüş bir ressam; kültür konusu, tarih değil.
    Q5 + tanınmayan meslek → belirsiz. Karar verilemiyor.

Meslek listesini genişletmek yanlış pozitifi artırıyor, daraltmak kuyruğu
büyütüyor. Bu katman o kuyruğu kapatıyor — Wikidata'nın yerine geçmiyor,
**kalanını** çözüyor.

Maliyet önbellekle sınırlanıyor: bir makale bir kez sorulur, sonuç
`sinif_kaynagi = 'llm'` ile kalıcı olur ve sonraki toplamalar onu ezmez
(`konu_toplayici._sinifi_yaz`). Aynı makale her gün listede görünse de tek
çağrı. Determinizm kaybı da böyle sınırlanıyor: karar bir kez veriliyor.

YouTube kotasına dokunmuyor.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .. import depo
from . import wikipedia

ANAHTAR_DEGISKENI = "ANTHROPIC_API_KEY"
MODEL = "claude-opus-5"

# ⚠️ SAĞLAYICI SEÇİLEBİLİR (DW-138). Ölçüldü (2026-09-12): sınıflandırıcı
# `claude-opus-5`'e sabitti, Anthropic hesabında kredi yoktu ve huni 7
# Ağustos'tan beri hiç besleme yapamadı (`konu siniflandir` her koşumda 400).
# Üretim hattı zaten OpenRouter'da ve orada bakiye var; Opus sınıfı fiyatla
# günde 5 çağrı × 8k token, video üretiminin kendisinden pahalıya geliyordu.
#
# Seçim: `LLM_SAGLAYICI` (anthropic | openrouter). Boşsa eski davranış —
# `ANTHROPIC_API_KEY` varsa Anthropic; yoksa `OPENROUTER_API_KEY` varsa
# OpenRouter. Yani mevcut kurulumlar değişmez, geçiş `.env`'den yapılır.
SAGLAYICI_DEGISKENI = "LLM_SAGLAYICI"
SAGLAYICILAR = ("anthropic", "openrouter")
OPENROUTER_ANAHTAR_DEGISKENI = "OPENROUTER_API_KEY"
OPENROUTER_MODEL_DEGISKENI = "OPENROUTER_MODEL"
OPENROUTER_VARSAYILAN_MODEL = "moonshotai/kimi-k2.6"
OPENROUTER_UCU = "https://openrouter.ai/api/v1/chat/completions"
# Grup başına 20 makale × (özet ≤400 karakter) ≈ 4-6k giriş; çıktı ≤ 2k.
# 180 sn, MPT'nin Shorts metin sınırının (360) yarısı — burada görü yok.
OPENROUTER_ZAMAN_ASIMI = 180
AZAMI_CIKTI_TOKEN = 8_000

# Tek istekteki makale sayısı. 20 bilinçli: istem başına sabit maliyet
# (yönerge metni) makale sayısına bölünüyor, ama grup büyüdükçe modelin
# tek bir makaleye ayırdığı dikkat azalıyor ve bir hata tüm grubu etkiliyor.
GRUP_BOYUTU = 20

SINIFLAR = ("tarih", "bilim", "diger")

# Modelin başlığa katabildiği `[en] ` / `[de] ` biçimli dil öneki.
_ONEK = re.compile(r"^\[[a-z]{2,3}\]\s*")

YONERGE = """Sen bir YouTube kanalı için konu seçen bir sınıflandırıcısın.
Kanal **tarih** ve **bilim** içeriği üretiyor.

Her Wikipedia makalesini üç sınıftan birine ata:

- `tarih` — geçmişteki olaylar, dönemler, medeniyetler, tarihî figürler,
  arkeoloji, savaşlar. Konu **kendisi tarihsel** olmalı.
- `bilim` — doğa bilimleri, matematik, tıp, teknoloji, keşifler,
  bilim insanları ve çalışmaları.
- `diger` — geri kalan her şey.

Ayrım kuralları:

1. **Ölmüş olmak tarihî yapmaz.** Bir ressam, besteci, oyuncu veya sporcu
   öldüğünde tarih konusu değil kültür/spor konusu olur. Frida Kahlo,
   Richard Wagner, Paul Newman → `diger`.
2. **Kurgu eser, işlediği konunun sınıfına girmez.** Bir savaş filmi
   `diger`; anlattığı savaş `tarih`.
3. **Güncel siyaset tarih değil.** Yaşayan siyasetçiler, seçimler,
   partiler → `diger`. Tarihî devlet adamları → `tarih`.
4. **Emin değilsen `diger` seç.** Yanlış aday listeyi kirletir; kaçırılan
   aday yalnızca bir fırsat kaybıdır."""

SEMA = {
    "type": "object",
    "properties": {
        "sonuclar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "baslik": {"type": "string"},
                    "sinif": {"type": "string", "enum": list(SINIFLAR)},
                    "gerekce": {"type": "string", "description": "En fazla bir cümle"},
                },
                "required": ["baslik", "sinif", "gerekce"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sonuclar"],
    "additionalProperties": False,
}


class SiniflandirmaHatasi(RuntimeError):
    """LLM sınıflandırması yapılamadı."""


@dataclass
class SiniflandirmaSonucu:
    sorulan: int = 0
    cagri_sayisi: int = 0
    siniflar: dict[str, int] = field(default_factory=dict)
    hatalar: list[str] = field(default_factory=list)

    maliyet_usd: float = 0.0

    def ozet(self) -> str:
        dagilim = " · ".join(f"{k}:{v}" for k, v in sorted(self.siniflar.items()))
        satir = f"{self.sorulan} makale · {self.cagri_sayisi} çağrı · {dagilim or 'sonuç yok'}"
        if self.maliyet_usd:
            # Yalnızca sağlayıcı maliyeti cevaba yazıyorsa (OpenRouter
            # `usage.include`); Anthropic yazmıyor, satır değişmiyor.
            satir += f" · ${self.maliyet_usd:.4f}"
        if self.hatalar:
            satir += f" · {len(self.hatalar)} hata"
        return satir


def saglayici_sec(ortam: dict[str, str] | None = None) -> str:
    """Hangi sağlayıcı — `LLM_SAGLAYICI`, yoksa eldeki anahtara göre.

    Açık seçim tanınmayan bir değerse HATA: sessizce Anthropic'e düşmek,
    kullanıcının "OpenRouter'a geçtim" sandığı hattı Anthropic'te
    çalıştırırdı — ve o hesapta kredi yoksa yine 400.
    """
    ortam = os.environ if ortam is None else ortam
    secim = ortam.get(SAGLAYICI_DEGISKENI, "").strip().lower()
    if secim in SAGLAYICILAR:
        return secim
    if secim:
        raise SiniflandirmaHatasi(
            f"{SAGLAYICI_DEGISKENI}={secim!r} tanınmıyor; seçenekler: " + " | ".join(SAGLAYICILAR)
        )
    if ortam.get(ANAHTAR_DEGISKENI):
        return "anthropic"
    if ortam.get(OPENROUTER_ANAHTAR_DEGISKENI):
        return "openrouter"
    return "anthropic"


def saglayici_ve_model(ortam: dict[str, str] | None = None) -> tuple[str, str]:
    """Kuru koşum çıktısı ve loglar için: ("openrouter", "moonshotai/kimi-k2.6")."""
    ortam = os.environ if ortam is None else ortam
    secim = saglayici_sec(ortam)
    if secim == "openrouter":
        model = ortam.get(OPENROUTER_MODEL_DEGISKENI, "").strip() or OPENROUTER_VARSAYILAN_MODEL
        return secim, model
    return secim, MODEL


def istemci_kur():
    """Seçilen sağlayıcının istemcisi.

    Ağır içe aktarım fonksiyonun içinde: `anthropic` yalnızca bu komut
    çalıştırıldığında yükleniyor, `ytoto dogrula` gibi komutlar etkilenmiyor.
    OpenRouter yolu yeni bağımlılık getirmiyor (`urllib`).
    """
    secim, model = saglayici_ve_model()
    if secim == "openrouter":
        anahtar = os.environ.get(OPENROUTER_ANAHTAR_DEGISKENI, "").strip()
        if not anahtar:
            raise SiniflandirmaHatasi(
                f"{OPENROUTER_ANAHTAR_DEGISKENI} tanımlı değil. openrouter.ai/settings/keys"
                "'den alın, `.env`'e koyun ve kabuğa aktarın: set -a; source .env; set +a"
            )
        return OpenRouterIstemci(anahtar, model)
    if not os.environ.get(ANAHTAR_DEGISKENI):
        raise SiniflandirmaHatasi(
            f"{ANAHTAR_DEGISKENI} tanımlı değil. console.anthropic.com'dan alın, "
            "`.env`'e koyun ve kabuğa aktarın: set -a; source .env; set +a"
        )
    import anthropic

    return anthropic.Anthropic()


def _json_govdesi(icerik: str | None) -> dict:
    """Modelin metnini JSON'a çevirir; ```json çitini soyar.

    ⚠️ `response_format=json_object` her sağlayıcıda tutulan bir söz değil:
    MPT'de ölçüldü (2026-08-15), OpenRouter üzerinden Kimi cevabı ```json
    çitiyle döndürüyor ve çıplak `json.loads` patlıyor. Boş cevap da sessiz
    geçmemeli — akıl yürütme bütçeyi yediğinde tam böyle görünüyor.
    """
    metin = (icerik or "").strip()
    if metin.startswith("```"):
        metin = re.sub(r"^```[a-zA-Z]*\s*", "", metin)
        metin = re.sub(r"\s*```$", "", metin)
    if not metin:
        raise SiniflandirmaHatasi("model boş cevap döndürdü (akıl yürütme bütçeyi yemiş olabilir)")
    return json.loads(metin)


class OpenRouterIstemci:
    """OpenAI uyumlu sohbet ucu — `sor(yonerge, istem) -> dict`.

    ⚠️ `reasoning: enabled=false` ZORUNLU: `moonshotai/kimi-k2.6` bir akıl
    yürütme modeli ve MPT'de ölçüldü — bütün çıktı bütçesini düşünmeye
    harcayıp `content` boş dönüyor (`max_tokens 16000 -> reasoning 16000`).
    `usage.include` bedava ve maliyeti cevaba yazıyor; özet satırı onu
    gösteriyor ki "sınıflandırma ne tuttu" sorusu ölçüsüz kalmasın.
    """

    def __init__(self, anahtar: str, model: str, *, uc: str = OPENROUTER_UCU):
        self.anahtar = anahtar
        self.model = model
        self.uc = uc
        self.maliyet_usd = 0.0

    def _gonder(self, govde: dict) -> dict:
        import urllib.error
        import urllib.request

        istek = urllib.request.Request(
            self.uc,
            data=json.dumps(govde).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.anahtar}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/duo-works/Yt_Automation",
                "X-Title": "Yt_Automation konu siniflandir",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(istek, timeout=OPENROUTER_ZAMAN_ASIMI) as cevap:
                return json.loads(cevap.read().decode("utf-8"))
        except urllib.error.HTTPError as hata:
            # ⚠️ Gövde metni HATAYA GİRİYOR: `gunluk-huni.sh` bütçe hâlini
            # (`kredi_bitti_mi`) bu metinden tanıyor. Yutulursa kredisi
            # bitmiş hat yine "bozuk" görünür — DW-136'nın kapattığı kusur.
            govde_metni = hata.read().decode("utf-8", "replace")[:400]
            raise SiniflandirmaHatasi(f"Error code: {hata.code} - {govde_metni}") from hata

    def sor(self, yonerge: str, istem: str) -> dict:
        veri = self._gonder(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": yonerge},
                    {"role": "user", "content": istem},
                ],
                "max_tokens": AZAMI_CIKTI_TOKEN,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
                "reasoning": {"enabled": False},
                "usage": {"include": True},
            }
        )
        maliyet = (veri.get("usage") or {}).get("cost")
        if isinstance(maliyet, (int, float)):
            self.maliyet_usd += float(maliyet)
        secenekler = veri.get("choices") or []
        icerik = (secenekler[0].get("message") or {}).get("content") if secenekler else None
        return _json_govdesi(icerik)


def bekleyenler(yol: Path, limit: int = 200) -> list[dict]:
    """Sınıflandırılmayı bekleyen makaleler — en çok okunanlar önce.

    Sıra önemli: kuyruk bütçeden büyükse en çok okunanı sormak, rastgele
    birini sormaktan değerli.
    """
    baglanti = depo.baglan(yol)
    try:
        return [
            dict(s)
            for s in baglanti.execute(
                """
                SELECT m.dil, m.baslik, MAX(o.okunma) AS okunma
                FROM makale m
                JOIN okunma o ON o.dil = m.dil AND o.baslik = m.baslik
                WHERE m.sinif = 'belirsiz'
                GROUP BY m.dil, m.baslik
                ORDER BY okunma DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
    finally:
        baglanti.close()


def _istem(kayitlar: list[dict], ozetler: dict[str, str]) -> str:
    # ⚠️ Dil satır başına yazılmıyor, bir kez üstte söyleniyor. Eskiden her
    # satır `- [de] Dean Reed` biçimindeydi ve model dil etiketini başlığın
    # parçası sanıp `baslik` alanında geri döndürüyordu — canlı koşumda 40
    # makale bu yüzden eşleşmedi. Zaten `siniflandir()` grupları dile göre
    # ayırıyor, yani satır başına tekrarlamanın bilgi değeri de yoktu.
    dil = kayitlar[0]["dil"] if kayitlar else ""
    satirlar = []
    for k in kayitlar:
        baslik = k["baslik"].replace("_", " ")
        ozet = ozetler.get(k["baslik"], "")
        parca = f"- {baslik}"
        if ozet:
            # Giriş paragrafı uzun olabiliyor; ilk cümleler ayrımı zaten veriyor.
            parca += f"\n  {ozet[:400]}"
        satirlar.append(parca)
    return (
        f"Aşağıdaki makaleler {dil}.wikipedia'dan geliyor. Her birini sınıflandır "
        "ve `baslik` alanını **listede yazdığı gibi** geri döndür.\n\n" + "\n".join(satirlar)
    )


def _grubu_sor(istemci, kayitlar: list[dict], ozetler: dict[str, str]) -> list[dict]:
    istem = _istem(kayitlar, ozetler)
    # İki istemci yüzeyi: OpenRouter `sor()`, Anthropic `messages.create()`.
    # Ayrım burada, tek yerde — çağıran taraf sağlayıcıyı bilmiyor.
    if hasattr(istemci, "sor"):
        # Şema OpenAI uyumlu uçta `json_object` ile gidiyor; alan adları ve
        # sınıf listesi yönergede yazılı olduğu için model aynı yapıyı
        # döndürüyor, `_yaz` tanınmayan sınıfı zaten reddediyor.
        return istemci.sor(YONERGE + "\n\n" + _sema_metni(), istem).get("sonuclar", [])
    yanit = istemci.messages.create(
        model=MODEL,
        max_tokens=AZAMI_CIKTI_TOKEN,
        system=YONERGE,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SEMA}},
        messages=[{"role": "user", "content": istem}],
    )
    # Reddedilen istek boş `content` döndürüyor — indekslemeden önce bak.
    if yanit.stop_reason == "refusal":
        raise SiniflandirmaHatasi("model isteği reddetti")
    metin = next((b.text for b in yanit.content if b.type == "text"), "")
    return json.loads(metin).get("sonuclar", [])


def _sema_metni() -> str:
    """OpenAI uyumlu uçta `json_schema` zorlaması yerine şema yönergeye gömülür."""
    return "Yalnızca şu JSON nesnesini döndür, başka metin yazma:\n" + json.dumps(
        {
            "sonuclar": [
                {
                    "baslik": "<listede yazdığı gibi>",
                    "sinif": "<" + " | ".join(SINIFLAR) + ">",
                    "gerekce": "<en fazla bir cümle>",
                }
            ]
        },
        ensure_ascii=False,
    )


def siniflandir(
    istemci,
    yol: Path,
    *,
    limit: int = 200,
) -> SiniflandirmaSonucu:
    """Belirsiz kuyruğunu LLM'e sorar ve sonucu kalıcı yazar."""
    sonuc = SiniflandirmaSonucu()
    kuyruk = bekleyenler(yol, limit)
    if not kuyruk:
        return sonuc

    # Başlıklar dile göre gruplanıyor: özet API'si tek dilde sorgulanıyor.
    dile_gore: dict[str, list[dict]] = {}
    for kayit in kuyruk:
        dile_gore.setdefault(kayit["dil"], []).append(kayit)

    for dil, kayitlar in dile_gore.items():
        ozetler = wikipedia.ozetleri_getir(dil, [k["baslik"] for k in kayitlar])
        for i in range(0, len(kayitlar), GRUP_BOYUTU):
            grup = kayitlar[i : i + GRUP_BOYUTU]
            try:
                yanitlar = _grubu_sor(istemci, grup, ozetler)
            except Exception as hata:  # noqa: BLE001 — bir grup diğerlerini düşürmemeli
                sonuc.hatalar.append(f"{dil}[{i}]: {hata}")
                continue
            sonuc.cagri_sayisi += 1
            _yaz(yol, dil, grup, yanitlar, sonuc)
    # Sağlayıcı maliyeti biriktiriyorsa (OpenRouter) özete taşınır; yoksa 0.
    sonuc.maliyet_usd = float(getattr(istemci, "maliyet_usd", 0.0) or 0.0)
    return sonuc


def _yaz(yol: Path, dil: str, grup: list[dict], yanitlar: list[dict], sonuc) -> None:
    # ⚠️ Başlık iki biçimde dolaşıyor ve ikisi de eşleşmeye kabul edilmeli:
    # depoda Wikipedia'nın alt çizgili biçimi (`Bill_Oddie`, birincil anahtar),
    # modele ise `_istem()` okunur biçimi gösteriyor (`Bill Oddie`).
    #
    # Yalnızca depo biçimini beklemek canlı veride hattı fiilen durdurdu:
    # 300 makalenin 273'ü "tanınmayan yanıt" ile düştü (%91). Model gördüğünü
    # döndürüyordu; kod göstermediği biçimi arıyordu. Testler yakalayamadı
    # çünkü fixture başlıklarının hepsi tek kelimeydi ve tek kelimede iki
    # biçim aynı.
    esleme: dict[str, str] = {}
    for k in grup:
        esleme[k["baslik"]] = k["baslik"]
        esleme[k["baslik"].replace("_", " ")] = k["baslik"]

    with depo.yazma_islemi(yol) as baglanti:
        for kayit in yanitlar:
            ham = kayit.get("baslik", "")
            # Eski istem biçiminden kalma `[dil] ` önekini de hoş gör: model
            # satır başındaki etiketi başlığa katabiliyor. İstem düzeltildi
            # ama tolerans ucuz ve aynı hatanın tekrarını sessizce yutmuyor.
            ham = _ONEK.sub("", ham, count=1)
            # Model başlığı büsbütün değiştirmiş olabilir; grupta yoksa yazma —
            # yanlış satırı güncellemektense atlamak yeğdir.
            baslik = esleme.get(ham, "")
            if not baslik or kayit.get("sinif") not in SINIFLAR:
                sonuc.hatalar.append(f"{dil}: tanınmayan yanıt {ham!r}")
                continue
            # ⚠️ `dil` yazılmıyor: `makale`'nin birincil anahtarı (dil, baslik)
            # ve `dil` makalenin geldiği **Wikipedia sürümü**. Modelden ayrıca
            # "içerik dili" istemenin de anlamı yok — bir konunun tr.wikipedia'da
            # yükselmesi zaten Türkçe talep demek. Sürüm kodu sorunun cevabı.
            baglanti.execute(
                "UPDATE makale SET sinif = ?, sinif_kaynagi = 'llm' WHERE dil = ? AND baslik = ?",
                (kayit["sinif"], dil, baslik),
            )
            sonuc.sorulan += 1
            sonuc.siniflar[kayit["sinif"]] = sonuc.siniflar.get(kayit["sinif"], 0) + 1
