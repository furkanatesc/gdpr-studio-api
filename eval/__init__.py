"""Hukuki-doğruluk değerlendirme harness'i (golden set).

Amaç: prompt/model/grounding değişince üretilen dokümanların hukuki doğruluğunun
REGRESYONA uğramadığını kanıtlamak. İki katman:
  - Deterministik (modelsiz, ücretsiz): grounding çözümleme doğru mu → pytest'te koşar.
  - Model çağrılı (on-demand): madde atıfları, zorunlu bölümler, m.6 özel nitelikli veri
    işlenişi, saklama süresi uydurma yasağı, disclaimer → `python -m eval.runner`.
"""
