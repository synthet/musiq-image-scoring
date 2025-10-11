#!/usr/bin/env python3
"""
Analyze JSON results from MUSIQ batch processing to find best and worst images.
Searches through all JSON files in a directory and creates a comprehensive summary.
"""

import argparse
import json
import os
import glob
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class JSONResultsAnalyzer:
    """Analyze JSON results from MUSIQ batch processing."""
    
    def __init__(self, directory: str):
        self.directory = directory
        self.json_files = []
        self.results = []
        self.summary = {}
        
    def find_json_files(self) -> List[str]:
        """Find all JSON files in the directory."""
        pattern = os.path.join(self.directory, "*.json")
        json_files = glob.glob(pattern)
        
        # Filter out batch summary files
        json_files = [f for f in json_files if not os.path.basename(f).startswith('batch_summary_')]
        
        return sorted(json_files)
    
    def load_json_data(self, json_file: str) -> Optional[Dict]:
        """Load and validate JSON data from a file."""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate required fields
            if not all(key in data for key in ['image_name', 'models', 'summary']):
                print(f"Warning: Invalid JSON structure in {json_file}")
                return None
            
            # Add file path for reference
            data['json_file'] = json_file
            return data
            
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
            return None
    
    def analyze_all_results(self):
        """Analyze all JSON files and create comprehensive summary."""
        print(f"Scanning directory: {self.directory}")
        
        # Find all JSON files
        self.json_files = self.find_json_files()
        print(f"Found {len(self.json_files)} JSON files")
        
        if not self.json_files:
            print("No JSON files found!")
            return
        
        # Load all results
        print("Loading JSON data...")
        for json_file in self.json_files:
            data = self.load_json_data(json_file)
            if data:
                self.results.append(data)
        
        print(f"Successfully loaded {len(self.results)} valid results")
        
        if not self.results:
            print("No valid results to analyze!")
            return
        
        # Create comprehensive analysis
        self._create_summary()
    
    def _create_summary(self):
        """Create comprehensive summary of all results."""
        print("Analyzing results...")
        
        # Initialize summary structure
        self.summary = {
            "analysis_date": datetime.now().isoformat(),
            "directory": self.directory,
            "total_images": len(self.results),
            "overall_statistics": {},
            "model_statistics": {},
            "best_worst_images": {
                "overall": {},
                "by_model": {}
            }
        }
        
        # Calculate overall statistics
        self._calculate_overall_statistics()
        
        # Calculate model-specific statistics
        self._calculate_model_statistics()
        
        # Find best and worst images
        self._find_best_worst_images()
    
    def _calculate_overall_statistics(self):
        """Calculate overall statistics across all images."""
        avg_scores = []
        successful_predictions = 0
        failed_predictions = 0
        
        for result in self.results:
            summary = result.get('summary', {})
            if summary.get('average_normalized_score') is not None:
                avg_scores.append(summary['average_normalized_score'])
            
            successful_predictions += summary.get('successful_predictions', 0)
            failed_predictions += summary.get('failed_predictions', 0)
        
        if avg_scores:
            self.summary["overall_statistics"] = {
                "average_score": round(sum(avg_scores) / len(avg_scores), 3),
                "min_score": round(min(avg_scores), 3),
                "max_score": round(max(avg_scores), 3),
                "score_range": round(max(avg_scores) - min(avg_scores), 3),
                "total_successful_predictions": successful_predictions,
                "total_failed_predictions": failed_predictions
            }
    
    def _calculate_model_statistics(self):
        """Calculate statistics for each model."""
        models = ['spaq', 'ava', 'koniq', 'paq2piq']
        
        for model in models:
            scores = []
            normalized_scores = []
            successful = 0
            failed = 0
            
            for result in self.results:
                model_data = result.get('models', {}).get(model, {})
                if model_data.get('status') == 'success':
                    scores.append(model_data.get('score'))
                    normalized_scores.append(model_data.get('normalized_score'))
                    successful += 1
                else:
                    failed += 1
            
            if scores:
                self.summary["model_statistics"][model] = {
                    "successful_predictions": successful,
                    "failed_predictions": failed,
                    "raw_scores": {
                        "average": round(sum(scores) / len(scores), 2),
                        "min": round(min(scores), 2),
                        "max": round(max(scores), 2)
                    },
                    "normalized_scores": {
                        "average": round(sum(normalized_scores) / len(normalized_scores), 3),
                        "min": round(min(normalized_scores), 3),
                        "max": round(max(normalized_scores), 3)
                    }
                }
    
    def _find_best_worst_images(self):
        """Find best and worst images overall and by model."""
        # Overall best and worst
        valid_results = [r for r in self.results if r.get('summary', {}).get('average_normalized_score') is not None]
        
        if valid_results:
            best_overall = max(valid_results, key=lambda x: x['summary']['average_normalized_score'])
            worst_overall = min(valid_results, key=lambda x: x['summary']['average_normalized_score'])
            
            self.summary["best_worst_images"]["overall"] = {
                "best": {
                    "image_name": best_overall['image_name'],
                    "average_normalized_score": best_overall['summary']['average_normalized_score'],
                    "individual_scores": self._extract_individual_scores(best_overall)
                },
                "worst": {
                    "image_name": worst_overall['image_name'],
                    "average_normalized_score": worst_overall['summary']['average_normalized_score'],
                    "individual_scores": self._extract_individual_scores(worst_overall)
                }
            }
        
        # Best and worst by model
        models = ['spaq', 'ava', 'koniq', 'paq2piq']
        
        for model in models:
            model_results = []
            for result in self.results:
                model_data = result.get('models', {}).get(model, {})
                if model_data.get('status') == 'success':
                    model_results.append({
                        'result': result,
                        'score': model_data.get('score'),
                        'normalized_score': model_data.get('normalized_score')
                    })
            
            if model_results:
                best_model = max(model_results, key=lambda x: x['normalized_score'])
                worst_model = min(model_results, key=lambda x: x['normalized_score'])
                
                self.summary["best_worst_images"]["by_model"][model] = {
                    "best": {
                        "image_name": best_model['result']['image_name'],
                        "score": best_model['score'],
                        "normalized_score": best_model['normalized_score']
                    },
                    "worst": {
                        "image_name": worst_model['result']['image_name'],
                        "score": worst_model['score'],
                        "normalized_score": worst_model['normalized_score']
                    }
                }
    
    def _extract_individual_scores(self, result: Dict) -> Dict:
        """Extract individual model scores from a result."""
        scores = {}
        for model, model_data in result.get('models', {}).items():
            if model_data.get('status') == 'success':
                scores[model] = {
                    "score": model_data.get('score'),
                    "normalized_score": model_data.get('normalized_score')
                }
        return scores
    
    def save_summary(self, output_file: str = None):
        """Save analysis summary to JSON file."""
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(self.directory, f"analysis_summary_{timestamp}.json")
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.summary, f, indent=2, ensure_ascii=False)
            
            print(f"Analysis summary saved to: {output_file}")
            return output_file
            
        except Exception as e:
            print(f"Error saving summary: {e}")
            return None
    
    def print_summary(self):
        """Print a formatted summary to console."""
        if not self.summary:
            print("No analysis data available!")
            return
        
        print("\n" + "=" * 80)
        print("MUSIQ BATCH ANALYSIS SUMMARY")
        print("=" * 80)
        
        # Overall statistics
        overall = self.summary.get('overall_statistics', {})
        print(f"\n📊 OVERALL STATISTICS")
        print(f"Total Images Analyzed: {self.summary.get('total_images', 0)}")
        print(f"Average Score: {overall.get('average_score', 'N/A')}")
        print(f"Score Range: {overall.get('min_score', 'N/A')} - {overall.get('max_score', 'N/A')}")
        print(f"Score Spread: {overall.get('score_range', 'N/A')}")
        
        # Best and worst overall
        best_worst = self.summary.get('best_worst_images', {}).get('overall', {})
        if best_worst:
            print(f"\n🏆 BEST OVERALL IMAGE")
            best = best_worst.get('best', {})
            print(f"  Image: {best.get('image_name', 'N/A')}")
            print(f"  Average Score: {best.get('average_normalized_score', 'N/A')}")
            
            print(f"\n📉 WORST OVERALL IMAGE")
            worst = best_worst.get('worst', {})
            print(f"  Image: {worst.get('image_name', 'N/A')}")
            print(f"  Average Score: {worst.get('average_normalized_score', 'N/A')}")
        
        # Model statistics
        print(f"\n📈 MODEL STATISTICS")
        model_stats = self.summary.get('model_statistics', {})
        for model, stats in model_stats.items():
            print(f"\n  {model.upper()}:")
            print(f"    Successful: {stats.get('successful_predictions', 0)}")
            print(f"    Failed: {stats.get('failed_predictions', 0)}")
            raw_scores = stats.get('raw_scores', {})
            norm_scores = stats.get('normalized_scores', {})
            print(f"    Raw Score Range: {raw_scores.get('min', 'N/A')} - {raw_scores.get('max', 'N/A')}")
            print(f"    Normalized Range: {norm_scores.get('min', 'N/A')} - {norm_scores.get('max', 'N/A')}")
        
        # Best and worst by model
        print(f"\n🎯 BEST & WORST BY MODEL")
        by_model = self.summary.get('best_worst_images', {}).get('by_model', {})
        for model, best_worst in by_model.items():
            print(f"\n  {model.upper()}:")
            best = best_worst.get('best', {})
            worst = best_worst.get('worst', {})
            print(f"    Best: {best.get('image_name', 'N/A')} (score: {best.get('normalized_score', 'N/A')})")
            print(f"    Worst: {worst.get('image_name', 'N/A')} (score: {worst.get('normalized_score', 'N/A')})")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Analyze JSON results from MUSIQ batch processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze_json_results.py --directory "D:/Projects/image-scoring"
  python analyze_json_results.py --directory "D:/Photos/Export/2025" --output "my_analysis.json"
        """
    )
    
    parser.add_argument('--directory', required=True, help='Directory containing JSON files')
    parser.add_argument('--output', help='Output file for analysis summary (default: auto-generated)')
    
    args = parser.parse_args()
    
    # Validate directory
    if not os.path.exists(args.directory):
        print(f"Error: Directory not found: {args.directory}")
        return 1
    
    if not os.path.isdir(args.directory):
        print(f"Error: Path is not a directory: {args.directory}")
        return 1
    
    # Create analyzer and run analysis
    analyzer = JSONResultsAnalyzer(args.directory)
    analyzer.analyze_all_results()
    
    if not analyzer.results:
        print("No valid results found to analyze!")
        return 1
    
    # Save and print summary
    output_file = analyzer.save_summary(args.output)
    analyzer.print_summary()
    
    if output_file:
        print(f"\nDetailed analysis saved to: {output_file}")
    
    return 0


if __name__ == "__main__":
    exit(main())
