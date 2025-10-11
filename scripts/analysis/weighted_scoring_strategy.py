#!/usr/bin/env python3
"""
Weighted scoring strategy for MUSIQ models based on statistical analysis.
Combines weighted average with outlier detection for robust scoring.
"""

import json
import numpy as np
from typing import Dict, List, Tuple
import argparse
import os
from pathlib import Path


class WeightedScoringStrategy:
    """Advanced scoring strategy combining multiple approaches."""
    
    def __init__(self):
        # Model weights based on statistical analysis
        # Higher weight for models with better discrimination and reliability
        self.model_weights = {
            "koniq": 0.35,      # Best balance of discrimination and reliability
            "spaq": 0.30,       # Best discrimination (widest range)
            "paq2piq": 0.25,    # Most lenient, good for high-quality detection
            "ava": 0.10         # Most conservative, narrow range
        }
        
        # Quality thresholds based on statistical analysis
        self.quality_thresholds = {
            "excellent": 0.75,   # Top 25% (above 75th percentile)
            "good": 0.60,        # Above average (60th percentile)
            "average": 0.45,     # Below average (45th percentile)
            "poor": 0.30         # Bottom 25% (below 30th percentile)
        }
    
    def calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted average score."""
        weighted_sum = 0.0
        total_weight = 0.0
        
        for model, score in scores.items():
            if model in self.model_weights:
                weight = self.model_weights[model]
                weighted_sum += score * weight
                total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def calculate_median_score(self, scores: Dict[str, float]) -> float:
        """Calculate median score (robust to outliers)."""
        valid_scores = [score for score in scores.values() if score is not None]
        return np.median(valid_scores) if valid_scores else 0.0
    
    def calculate_trimmed_mean(self, scores: Dict[str, float], trim_percent: float = 0.1) -> float:
        """Calculate trimmed mean (remove extreme values)."""
        valid_scores = [score for score in scores.values() if score is not None]
        if not valid_scores:
            return 0.0
        
        valid_scores.sort()
        n = len(valid_scores)
        trim_count = int(n * trim_percent)
        
        if trim_count > 0:
            trimmed_scores = valid_scores[trim_count:-trim_count]
        else:
            trimmed_scores = valid_scores
        
        return np.mean(trimmed_scores) if trimmed_scores else 0.0
    
    def detect_outliers(self, scores: Dict[str, float]) -> List[str]:
        """Detect models with outlier scores using IQR method."""
        valid_scores = [(model, score) for model, score in scores.items() if score is not None]
        if len(valid_scores) < 3:
            return []
        
        scores_only = [score for _, score in valid_scores]
        q1 = np.percentile(scores_only, 25)
        q3 = np.percentile(scores_only, 75)
        iqr = q3 - q1
        
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        outliers = []
        for model, score in valid_scores:
            if score < lower_bound or score > upper_bound:
                outliers.append(model)
        
        return outliers
    
    def calculate_robust_score(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Calculate robust score using multiple methods."""
        # Remove outliers
        outliers = self.detect_outliers(scores)
        filtered_scores = {k: v for k, v in scores.items() if k not in outliers}
        
        # Calculate different scoring methods
        weighted = self.calculate_weighted_score(filtered_scores)
        median = self.calculate_median_score(filtered_scores)
        trimmed_mean = self.calculate_trimmed_mean(filtered_scores)
        
        # Combine methods (weighted average of methods)
        final_score = (weighted * 0.5 + median * 0.3 + trimmed_mean * 0.2)
        
        return {
            "final_score": final_score,
            "weighted_score": weighted,
            "median_score": median,
            "trimmed_mean": trimmed_mean,
            "outliers_detected": outliers,
            "outlier_count": len(outliers),
            "models_used": len(filtered_scores)
        }
    
    def get_quality_category(self, score: float) -> str:
        """Categorize quality based on score."""
        if score >= self.quality_thresholds["excellent"]:
            return "excellent"
        elif score >= self.quality_thresholds["good"]:
            return "good"
        elif score >= self.quality_thresholds["average"]:
            return "average"
        else:
            return "poor"
    
    def analyze_image(self, image_data: Dict) -> Dict:
        """Analyze a single image with robust scoring."""
        models = image_data.get("models", {})
        scores = {}
        
        # Extract normalized scores
        for model, data in models.items():
            if data.get("status") == "success":
                scores[model] = data.get("normalized_score")
        
        if not scores:
            return {"error": "No valid scores found"}
        
        # Calculate robust score
        robust_result = self.calculate_robust_score(scores)
        
        # Add quality category
        robust_result["quality_category"] = self.get_quality_category(robust_result["final_score"])
        
        # Add original scores for reference
        robust_result["original_scores"] = scores
        
        return robust_result


def process_json_files(directory: str, output_file: str = None):
    """Process all JSON files in directory with weighted scoring."""
    if output_file is None:
        output_file = os.path.join(directory, "weighted_scoring_results.json")
    
    strategy = WeightedScoringStrategy()
    results = []
    
    # Find all JSON files
    json_files = [f for f in os.listdir(directory) if f.endswith('.json') and not f.startswith('batch_summary_') and not f.startswith('analysis_summary_')]
    
    print(f"Processing {len(json_files)} JSON files...")
    
    for json_file in json_files:
        file_path = os.path.join(directory, json_file)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Analyze image
            analysis = strategy.analyze_image(data)
            
            result = {
                "image_name": data.get("image_name", json_file),
                "image_path": data.get("image_path", file_path),
                "original_average": data.get("summary", {}).get("average_normalized_score"),
                "weighted_analysis": analysis
            }
            
            results.append(result)
            
        except Exception as e:
            print(f"Error processing {json_file}: {e}")
    
    # Sort by final score (descending)
    results.sort(key=lambda x: x["weighted_analysis"].get("final_score", 0), reverse=True)
    
    # Calculate statistics
    final_scores = [r["weighted_analysis"]["final_score"] for r in results if "final_score" in r["weighted_analysis"]]
    
    statistics = {
        "total_images": len(results),
        "scoring_strategy": "Weighted + Median + Trimmed Mean",
        "model_weights": strategy.model_weights,
        "quality_thresholds": strategy.quality_thresholds,
        "score_statistics": {
            "mean": np.mean(final_scores) if final_scores else 0,
            "median": np.median(final_scores) if final_scores else 0,
            "std": np.std(final_scores) if final_scores else 0,
            "min": np.min(final_scores) if final_scores else 0,
            "max": np.max(final_scores) if final_scores else 0
        },
        "quality_distribution": {
            "excellent": len([r for r in results if r["weighted_analysis"].get("quality_category") == "excellent"]),
            "good": len([r for r in results if r["weighted_analysis"].get("quality_category") == "good"]),
            "average": len([r for r in results if r["weighted_analysis"].get("quality_category") == "average"]),
            "poor": len([r for r in results if r["weighted_analysis"].get("quality_category") == "poor"])
        }
    }
    
    # Save results
    output_data = {
        "analysis_date": "2025-10-07T23:15:00.000000",
        "statistics": statistics,
        "results": results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"Results saved to: {output_file}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("WEIGHTED SCORING ANALYSIS SUMMARY")
    print("=" * 80)
    print(f"Total Images: {statistics['total_images']}")
    print(f"Mean Score: {statistics['score_statistics']['mean']:.3f}")
    print(f"Median Score: {statistics['score_statistics']['median']:.3f}")
    print(f"Score Range: {statistics['score_statistics']['min']:.3f} - {statistics['score_statistics']['max']:.3f}")
    
    print(f"\nQuality Distribution:")
    for category, count in statistics['quality_distribution'].items():
        percentage = (count / statistics['total_images']) * 100
        print(f"  {category.capitalize()}: {count} ({percentage:.1f}%)")
    
    print(f"\nTop 5 Images:")
    for i, result in enumerate(results[:5]):
        score = result["weighted_analysis"]["final_score"]
        category = result["weighted_analysis"]["quality_category"]
        print(f"  {i+1}. {result['image_name']} - {score:.3f} ({category})")
    
    print(f"\nBottom 5 Images:")
    for i, result in enumerate(results[-5:]):
        score = result["weighted_analysis"]["final_score"]
        category = result["weighted_analysis"]["quality_category"]
        print(f"  {i+1}. {result['image_name']} - {score:.3f} ({category})")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(description="Apply weighted scoring strategy to MUSIQ results")
    parser.add_argument('--directory', required=True, help='Directory containing JSON files')
    parser.add_argument('--output', help='Output file for weighted scoring results')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.directory):
        print(f"Error: Directory not found: {args.directory}")
        return 1
    
    process_json_files(args.directory, args.output)
    return 0


if __name__ == "__main__":
    exit(main())
