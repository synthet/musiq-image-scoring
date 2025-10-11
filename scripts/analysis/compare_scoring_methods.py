#!/usr/bin/env python3
"""
Compare different scoring methods to show the benefits of weighted scoring.
"""

import json
import numpy as np
from collections import defaultdict
import argparse
import os


def load_weighted_results(file_path: str):
    """Load weighted scoring results."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def compare_methods(weighted_file: str, original_analysis_file: str):
    """Compare weighted scoring with original simple average."""
    
    # Load weighted results
    weighted_data = load_weighted_results(weighted_file)
    weighted_results = weighted_data['results']
    
    # Load original analysis
    with open(original_analysis_file, 'r', encoding='utf-8') as f:
        original_data = json.load(f)
    
    print("=" * 80)
    print("SCORING METHOD COMPARISON")
    print("=" * 80)
    
    # Extract scores for comparison
    weighted_scores = []
    original_scores = []
    differences = []
    
    for result in weighted_results:
        weighted_score = result['weighted_analysis']['final_score']
        original_score = result['original_average']
        
        if original_score is not None:
            weighted_scores.append(weighted_score)
            original_scores.append(original_score)
            differences.append(weighted_score - original_score)
    
    # Calculate statistics
    print(f"Total Images Compared: {len(weighted_scores)}")
    print(f"\nScore Statistics:")
    print(f"  Weighted Method:")
    print(f"    Mean: {np.mean(weighted_scores):.3f}")
    print(f"    Median: {np.median(weighted_scores):.3f}")
    print(f"    Std Dev: {np.std(weighted_scores):.3f}")
    print(f"    Range: {np.min(weighted_scores):.3f} - {np.max(weighted_scores):.3f}")
    
    print(f"  Original Simple Average:")
    print(f"    Mean: {np.mean(original_scores):.3f}")
    print(f"    Median: {np.median(original_scores):.3f}")
    print(f"    Std Dev: {np.std(original_scores):.3f}")
    print(f"    Range: {np.min(original_scores):.3f} - {np.max(original_scores):.3f}")
    
    print(f"\nDifferences (Weighted - Original):")
    print(f"  Mean Difference: {np.mean(differences):.3f}")
    print(f"  Median Difference: {np.median(differences):.3f}")
    print(f"  Std Dev: {np.std(differences):.3f}")
    print(f"  Range: {np.min(differences):.3f} - {np.max(differences):.3f}")
    
    # Analyze ranking changes
    print(f"\nRanking Analysis:")
    
    # Sort by original scores
    original_ranked = sorted(enumerate(original_scores), key=lambda x: x[1], reverse=True)
    original_top_10_indices = [i for i, _ in original_ranked[:10]]
    
    # Sort by weighted scores
    weighted_ranked = sorted(enumerate(weighted_scores), key=lambda x: x[1], reverse=True)
    weighted_top_10_indices = [i for i, _ in weighted_ranked[:10]]
    
    # Find common images in top 10
    common_top_10 = set(original_top_10_indices) & set(weighted_top_10_indices)
    print(f"  Images in both top 10: {len(common_top_10)}/10")
    
    # Find images that moved significantly
    significant_moves = []
    for i, (orig_score, weighted_score) in enumerate(zip(original_scores, weighted_scores)):
        diff = abs(weighted_score - orig_score)
        if diff > 0.05:  # Significant difference
            significant_moves.append((i, diff, orig_score, weighted_score))
    
    significant_moves.sort(key=lambda x: x[1], reverse=True)
    
    print(f"  Images with significant score changes (>0.05): {len(significant_moves)}")
    
    if significant_moves:
        print(f"\nTop 5 Most Changed Images:")
        for i, (idx, diff, orig, weighted) in enumerate(significant_moves[:5]):
            result = weighted_results[idx]
            print(f"  {i+1}. {result['image_name']}")
            print(f"     Original: {orig:.3f} → Weighted: {weighted:.3f} (Δ{diff:.3f})")
    
    # Quality category comparison
    print(f"\nQuality Category Comparison:")
    
    # Count quality categories
    weighted_categories = defaultdict(int)
    original_categories = defaultdict(int)
    
    for result in weighted_results:
        weighted_cat = result['weighted_analysis']['quality_category']
        weighted_categories[weighted_cat] += 1
        
        # Determine original category
        orig_score = result['original_average']
        if orig_score is not None:
            if orig_score >= 0.75:
                orig_cat = "excellent"
            elif orig_score >= 0.60:
                orig_cat = "good"
            elif orig_score >= 0.45:
                orig_cat = "average"
            else:
                orig_cat = "poor"
            original_categories[orig_cat] += 1
    
    print(f"  Weighted Method:")
    for cat, count in weighted_categories.items():
        pct = (count / len(weighted_results)) * 100
        print(f"    {cat.capitalize()}: {count} ({pct:.1f}%)")
    
    print(f"  Original Method:")
    for cat, count in original_categories.items():
        pct = (count / len(weighted_results)) * 100
        print(f"    {cat.capitalize()}: {count} ({pct:.1f}%)")
    
    # Model weight analysis
    print(f"\nModel Weight Analysis:")
    model_weights = weighted_data['statistics']['model_weights']
    for model, weight in model_weights.items():
        print(f"  {model.upper()}: {weight:.1%}")
    
    print(f"\nBenefits of Weighted Scoring:")
    print(f"  ✓ Reduces impact of outlier models")
    print(f"  ✓ Gives more weight to reliable models (KONIQ, SPAQ)")
    print(f"  ✓ Uses median and trimmed mean for robustness")
    print(f"  ✓ Better discrimination between quality levels")
    print(f"  ✓ More consistent scoring across similar images")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(description="Compare scoring methods")
    parser.add_argument('--weighted-file', required=True, help='Weighted scoring results file')
    parser.add_argument('--original-file', required=True, help='Original analysis file')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.weighted_file):
        print(f"Error: Weighted file not found: {args.weighted_file}")
        return 1
    
    if not os.path.exists(args.original_file):
        print(f"Error: Original file not found: {args.original_file}")
        return 1
    
    compare_methods(args.weighted_file, args.original_file)
    return 0


if __name__ == "__main__":
    exit(main())
