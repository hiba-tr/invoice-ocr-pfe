"""
test_preprocess.py - Test complet du pipeline de preprocessing
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image
from backend.extraction.engine.models.utils.image_preprocessing import (
    ImagePreprocessor,
    InvoiceEnhancer,
    PreprocessingPipeline,
    assess_image_quality,
)

image_path = "test/12.png"
image = Image.open(image_path)

print("=" * 60)
print("TEST COMPLET DU PIPELINE DE PREPROCESSING")
print("=" * 60)
print()

# 1. Qualite originale
quality = assess_image_quality(image)
print(f" 1. Qualite originale :")
print(f"   Blur      : {quality['blur_score']:.1f}")
print(f"   Luminosite: {quality['brightness']:.1f}")
print(f"   Contraste : {quality['contrast']:.1f}")
print()

# 2. InvoiceEnhancer
print("2. InvoiceEnhancer (deskew + CLAHE + binarisation)...")
enhancer = InvoiceEnhancer()
enhanced = enhancer.enhance_for_ocr(image)
enhanced.save("test/12_invoice_enhanced.png")
quality2 = assess_image_quality(enhanced)
print(f"   Apres  : blur={quality2['blur_score']:.1f}, contraste={quality2['contrast']:.1f}")
print("   Sauvegarde : test/12_invoice_enhanced.png")
print()

# 3. ImagePreprocessor
print("3. ImagePreprocessor (adaptatif)...")
preprocessor = ImagePreprocessor()
preprocessed = preprocessor.get_enhanced_image(image)
preprocessed.save("test/12_preprocessed.png")
quality3 = assess_image_quality(preprocessed)
print(f"   Apres  : blur={quality3['blur_score']:.1f}, contraste={quality3['contrast']:.1f}")
print("   Sauvegarde : test/12_preprocessed.png")
print()

# 4. Pipeline complet image
print("4. Pipeline complet (InvoiceEnhancer + ImagePreprocessor)...")
enhanced2 = enhancer.enhance_for_ocr(image)
final = preprocessor.get_enhanced_image(enhanced2)
final.save("test/12_final.png")
quality4 = assess_image_quality(final)
print(f"   Apres  : blur={quality4['blur_score']:.1f}, contraste={quality4['contrast']:.1f}")
print("   Sauvegarde : test/12_final.png")
print()

# 5. Test du pipeline texte (OCR corrector)
print("5. Test du pipeline de correction texte...")
pipeline = PreprocessingPipeline()

# Simuler un texte OCR bruite
sample_text = """Facilities
CIHEROUQ Concession-WAHA PROD F
ESDV Valves location as per firefighting rating (IGRR)
Camp upgrade (148.271.43) (148.271.43) (74.135.72) (74.135.72)
Salt water well disposal FCLT
Waha CPF TA 20.132.69 20.132.69 10.066.35 10.066.35
Overhaul Rotating Equipment (137.254.60) (137.254.60) (68.627.30) (68.627.30)"""

result = pipeline.process_text(sample_text, learn=True)

print(f"   Vocabulaire appris : {result['vocabulary_size']} mots")
print(f"   Lignes fusionnees  : {len(result['lines'])}")
print(f"   Items extraits     : {len(result['items'])}")
print()

print("6. Items extraits :")
print("-" * 60)
for item in result['items']:
    valeurs = item.get('valeurs', [])
    valeurs_str = " | ".join(f"{v:,.2f}" for v in valeurs) if valeurs else ""
    section = f" [{item.get('section', '')}]" if item.get('section') else ""
    print(f"  {item['description']}{section}")
    if valeurs_str:
        print(f"    -> {valeurs_str}")
print("-" * 60)
print()

print("7. Fichiers generes :")
print("   test/12_invoice_enhanced.png")
print("   test/12_preprocessed.png")
print("   test/12_final.png")
print()
print("Comparez visuellement ces 3 images avec l'originale (test/12.png)")
print("La meilleure pour l'OCR devrait etre test/12_final.png")