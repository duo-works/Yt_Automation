# 0001 — Görev takibinin tek kaynağı Notion olacak

- **Durum:** Kabul
- **Tarih:** 2026-07-25
- **Karar verenler:** duo-works çekirdek ekip
- **İlgili görev:** DW-1

## Bağlam

İki kişilik ekipte görev takibi için iki aday vardı: GitHub Issues + Projects, ve Notion. Önceki çalışma düzeninde dokümantasyon Obsidian'da tutuluyordu ve plan dosyaları repo köküne dağılmıştı (`*_PLAN.md`); aynı bilginin iki yerde farklı hallerde bulunması en sık yaşanan karışıklık kaynağıydı.

Kritik gözlem: sorun hangi aracın seçildiği değil, **iki aracın aynı anda kullanılması**. İki görev listesi olduğu anda hangisinin güncel olduğu belirsizleşir.

## Değerlendirilen seçenekler

1. **GitHub Issues + Projects** — Kod akışına en yakın, PR'dan otomatik kapanma, ek araç yok. Buna karşılık PRD, toplantı notu, bilgi bankası gibi uzun form içerik için zayıf; ekip zaten Notion kullanıyor, ikinci bir yüzey açılırdı.
2. **Notion tek kaynak** — Görev, doküman, sprint, karar tek yerde; ilişkisel database'ler (Görev ↔ Proje ↔ Sprint) ile güçlü raporlama. Buna karşılık kod ile otomatik bağ yok, bağ elle kurulmalı.
3. **İkisi birden, çift yönlü senkron** — En zengin görünüm, ama senkron çakışmaları ve bakım maliyeti iki kişilik ekip için orantısız.

## Karar

**Notion tek görev kaynağıdır.** GitHub Issues tüm repo'larda kapatılır (`.github/ISSUE_TEMPLATE/config.yml` ile Notion'a yönlendirilir).

Kod ile bağ, otomasyon yerine **konvansiyonla** kurulur: her görevin `DW-<numara>` biçiminde bir ID'si vardır; bu ID branch adında, commit gövdesinde ve PR başlığında zorunludur. `pr-title.yml` iş akışı bunu CI'da doğrular — yani konvansiyon "umut" değil, zorunluluktur.

## Sonuçlar

**Kolaylaştırdı:** Tek yere bakılır. Görev, PRD, sprint ve karar aynı ilişkisel yapıda. Yeni katılan biri tek aracı öğrenir.

**Zorlaştırdı:** Görev durumu elle güncellenir — PR merge edilince Notion kendiliğinden kapanmaz. Bunu telafi eden şey PR şablonundaki kontrol listesi ve akışın 6. adımıdır.

**Kabul edilen kısıt:** GitHub üzerinde görev geçmişi tutulmaz. Bir PR'ın neden yapıldığını anlamak için Notion'a gitmek gerekir; bu yüzden PR başlığındaki `[DW-<numara>]` zorunluluğundan taviz verilmez.

**Yeniden değerlendirme koşulu:** Ekip üçüncü kişiyle büyür ve elle durum güncelleme aksamaya başlarsa, Notion API + GitHub Actions ile tek yönlü (PR merge → görev "Bitti") otomasyon değerlendirilir. Çift yönlü senkron o durumda da tercih edilmez.
