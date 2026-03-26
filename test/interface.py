#!/usr/bin/env python3
"""
Interface utilisateur pour DocCore
Gère les fichiers uniques et les dossiers avec conversion parallèle automatique
"""

import sys
import time
import logging
import argparse
from pathlib import Path
from typing import List, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from document_converter import DocumentConverter
from datamodel.base_models import InputFormat
from datamodel.settings import settings

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
_log = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    """Résultat simplifié pour l'interface"""
    file: str
    status: str
    pages: int
    error: str = None
    time: float = 0
    output_file: str = None


class DocCoreInterface:
    """Interface utilisateur pour DocCore"""
    
    def __init__(self, max_workers: int = 4):
        """
        Initialise l'interface
        
        Args:
            max_workers: Nombre maximum de conversions en parallèle
        """
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF, InputFormat.IMAGE]
        )
        self.max_workers = max_workers
        
        # Configurer les paramètres de parallélisation
        settings.perf.doc_batch_size = max_workers
        settings.perf.doc_batch_concurrency = max_workers
        
        _log.info(f"Interface initialisée avec {max_workers} workers parallèles")
    
    def process_file(self, file_path: Path, output_dir: Path = None) -> ConversionResult:
        """
        Traite un fichier unique
        
        Args:
            file_path: Chemin du fichier
            output_dir: Dossier de sortie (optionnel)
        
        Returns:
            ConversionResult: Résultat de la conversion
        """
        start_time = time.time()
        output_file = None
        
        try:
            # Générer le nom du fichier de sortie
            if output_dir:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{file_path.stem}_result.json"
            else:
                output_file = file_path.parent / f"{file_path.stem}_result.json"
            
            # Convertir
            result = self.converter.convert(
                source=file_path,
                raises_on_error=False
            )
            
            elapsed = time.time() - start_time
            
            return ConversionResult(
                file=str(file_path),
                status=result.status.value,
                pages=len(result.pages) if result.pages else 0,
                time=elapsed,
                output_file=str(output_file)
            )
            
        except Exception as e:
            elapsed = time.time() - start_time
            return ConversionResult(
                file=str(file_path),
                status="FAILURE",
                pages=0,
                error=str(e),
                time=elapsed
            )
    
    def process_folder(self, folder_path: Path, output_dir: Path = None) -> List[ConversionResult]:
        """
        Traite un dossier EN PARALLÈLE
        
        Args:
            folder_path: Chemin du dossier
            output_dir: Dossier de sortie (optionnel)
        
        Returns:
            List[ConversionResult]: Liste des résultats
        """
        # Récupérer tous les fichiers supportés
        supported_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.bmp'}
        
        files = []
        for ext in supported_extensions:
            files.extend(folder_path.glob(f"*{ext}"))
            files.extend(folder_path.glob(f"*{ext.upper()}"))
        
        # Enlever les doublons
        files = list(set(files))
        
        if not files:
            _log.warning(f"Aucun fichier supporté trouvé dans {folder_path}")
            return []
        
        _log.info(f"📁 {len(files)} fichiers trouvés dans {folder_path}")
        _log.info(f"⚡ Conversion en parallèle avec {self.max_workers} workers...")
        
        # ✅ CONVERSION PARALLÈLE AUTOMATIQUE
        results = []
        
        # Méthode 1: Utiliser convert_all (recommandé)
        start_time = time.time()
        
        for result in self.converter.convert_all(files, raises_on_error=False):
            elapsed = time.time() - start_time
            
            # Sauvegarder le résultat si output_dir est spécifié
            output_file = None
            if output_dir and result.status == ConversionStatus.SUCCESS:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{Path(result.input.file).stem}_result.json"
                # Sauvegarde déjà faite dans main.py, ou à faire ici
            
            results.append(ConversionResult(
                file=str(result.input.file),
                status=result.status.value,
                pages=len(result.pages) if result.pages else 0,
                time=elapsed,
                output_file=str(output_file) if output_file else None
            ))
        
        total_time = time.time() - start_time
        _log.info(f"✅ Conversion terminée en {total_time:.2f}s")
        
        return results
    
    def process(self, path: str, output_dir: str = None, recursive: bool = False) -> List[ConversionResult]:
        """
        Point d'entrée principal - détecte automatiquement si c'est un fichier ou dossier
        
        Args:
            path: Chemin du fichier ou dossier
            output_dir: Dossier de sortie (optionnel)
            recursive: Traiter les sous-dossiers (si dossier)
        
        Returns:
            List[ConversionResult]: Liste des résultats
        """
        input_path = Path(path)
        output_path = Path(output_dir) if output_dir else None
        
        if not input_path.exists():
            raise FileNotFoundError(f"Le chemin n'existe pas: {path}")
        
        # ✅ DÉTECTION AUTOMATIQUE
        if input_path.is_file():
            _log.info(f"📄 Traitement d'un fichier unique: {input_path.name}")
            result = self.process_file(input_path, output_path)
            return [result]
        
        elif input_path.is_dir():
            _log.info(f"📁 Traitement d'un dossier: {input_path}")
            
            if recursive:
                # Traiter tous les sous-dossiers récursivement
                all_results = []
                for subdir in input_path.rglob("*"):
                    if subdir.is_dir():
                        results = self.process_folder(subdir, output_path)
                        all_results.extend(results)
                return all_results
            else:
                return self.process_folder(input_path, output_path)
        
        else:
            raise ValueError(f"Le chemin n'est ni un fichier ni un dossier: {path}")


def print_results(results: List[ConversionResult]):
    """Affiche les résultats de manière lisible"""
    
    if not results:
        print("\n❌ Aucun résultat")
        return
    
    print("\n" + "=" * 80)
    print("📊 RÉSULTATS DE LA CONVERSION")
    print("=" * 80)
    
    success = [r for r in results if r.status == "success"]
    failed = [r for r in results if r.status != "success"]
    
    print(f"\n✅ Succès: {len(success)}")
    print(f"❌ Échecs: {len(failed)}")
    print(f"⏱️  Temps total: {sum(r.time for r in results):.2f}s")
    
    if success:
        print("\n" + "-" * 50)
        print("📄 FICHIERS CONVERTIS AVEC SUCCÈS:")
        print("-" * 50)
        for r in success[:10]:  # Afficher les 10 premiers
            print(f"   ✓ {Path(r.file).name}")
            print(f"     - Pages: {r.pages}")
            print(f"     - Temps: {r.time:.2f}s")
            if r.output_file:
                print(f"     - Sortie: {Path(r.output_file).name}")
    
    if failed:
        print("\n" + "-" * 50)
        print("❌ FICHIERS EN ÉCHEC:")
        print("-" * 50)
        for r in failed[:10]:
            print(f"   ✗ {Path(r.file).name}")
            print(f"     - Erreur: {r.error}")


def main():
    parser = argparse.ArgumentParser(
        description='DocCore - Interface utilisateur',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
EXEMPLES:
  # Fichier unique
  python interface.py facture.pdf -o resultats/
  
  # Dossier (conversion parallèle automatique)
  python interface.py d:/factures/ -o resultats/
  
  # Dossier avec sous-dossiers
  python interface.py d:/factures/ -o resultats/ -r
  
  # Avec plus de parallélisme
  python interface.py d:/factures/ -o resultats/ -w 8
        """
    )
    
    parser.add_argument('input', help='Chemin du fichier ou dossier')
    parser.add_argument('-o', '--output', help='Dossier de sortie (optionnel)')
    parser.add_argument('-r', '--recursive', action='store_true', 
                        help='Traiter les sous-dossiers récursivement')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='Nombre de conversions en parallèle (défaut: 4)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Afficher les logs détaillés')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Créer l'interface
        interface = DocCoreInterface(max_workers=args.workers)
        
        # Traiter (détection automatique fichier/dossier)
        results = interface.process(args.input, args.output, args.recursive)
        
        # Afficher les résultats
        print_results(results)
        
        # Sauvegarder un rapport récapitulatif
        if args.output:
            output_path = Path(args.output)
            output_path.mkdir(parents=True, exist_ok=True)
            report_file = output_path / f"rapport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("RAPPORT DE CONVERSION DOCORE\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Fichiers traités: {len(results)}\n")
                f.write(f"Succès: {len([r for r in results if r.status == 'success'])}\n")
                f.write(f"Échecs: {len([r for r in results if r.status != 'success'])}\n\n")
                
                for r in results:
                    f.write(f"- {Path(r.file).name}: {r.status}\n")
            
            print(f"\n📝 Rapport sauvegardé: {report_file}")
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()