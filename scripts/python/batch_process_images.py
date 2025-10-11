#!/usr/bin/env python3
"""
Batch process all images in a directory with comprehensive logging.
Redirects all output to a log file with current date in the filename.
"""

import argparse
import json
import os
import sys
import glob
from datetime import datetime
from pathlib import Path
from typing import List

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import our multi-model MUSIQ class
from run_all_musiq_models import MultiModelMUSIQ


class BatchImageProcessor:
    """Batch process images with comprehensive logging."""
    
    def __init__(self, log_file: str = None, output_dir: str = None):
        if log_file is None:
            log_file = f"musiq_batch_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        # If output_dir is provided and log_file is relative, put it in output_dir
        if output_dir and not os.path.isabs(log_file):
            log_file = os.path.join(output_dir, log_file)
        elif not os.path.isabs(log_file):
            log_file = os.path.abspath(log_file)
        
        self.log_file = log_file
        self.processed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] [{level}] {message}"
        
        # Print to console
        print(log_entry)
        
        # Write to log file
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry + '\n')
    
    def find_images(self, directory: str) -> List[str]:
        """Find all image files in the specified directory."""
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.tif']
        image_files = []
        
        for ext in image_extensions:
            pattern = os.path.join(directory, ext)
            image_files.extend(glob.glob(pattern))
            # Also check subdirectories
            pattern = os.path.join(directory, '**', ext)
            image_files.extend(glob.glob(pattern, recursive=True))
        
        return sorted(list(set(image_files)))  # Remove duplicates and sort
    
    def process_single_image(self, image_path: str, scorer: MultiModelMUSIQ, output_dir: str) -> dict:
        """Process a single image and return results."""
        try:
            self.log(f"Processing: {image_path}")
            
            # Check if already processed with current version
            if scorer.is_already_processed(image_path, output_dir):
                self.log(f"Skipping {image_path} - already processed with version {scorer.VERSION}")
                
                # Load existing results for summary
                image_name = os.path.splitext(os.path.basename(image_path))[0]
                json_path = os.path.join(output_dir, f"{image_name}.json")
                
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    
                    # Extract key metrics from existing data
                    summary = {
                        "image_path": image_path,
                        "image_name": image_name,
                        "json_path": json_path,
                        "status": "skipped",
                        "models_successful": existing_data["summary"]["successful_predictions"],
                        "models_failed": existing_data["summary"]["failed_predictions"],
                        "average_normalized_score": existing_data["summary"]["average_normalized_score"],
                        "individual_scores": {},
                        "version": existing_data.get("version", "unknown")
                    }
                    
                    # Add individual model scores
                    for model_name, model_result in existing_data["models"].items():
                        if model_result["status"] == "success":
                            summary["individual_scores"][model_name] = {
                                "score": model_result["score"],
                                "normalized_score": model_result["normalized_score"]
                            }
                    
                    self.log(f"Skipped: {image_path} - Version: {summary['version']} - Average Score: {summary['average_normalized_score']}")
                    return summary
                    
                except Exception as e:
                    self.log(f"Error loading existing results for {image_path}: {e}", "WARNING")
                    # Fall through to reprocess
            
            # Run all models on the image
            results = scorer.run_all_models(image_path)
            
            # Save results to JSON
            image_name = Path(image_path).stem
            json_path = os.path.join(output_dir, f"{image_name}.json")
            scorer.save_results(results, json_path)
            
            # Extract key metrics
            summary = {
                "image_path": image_path,
                "image_name": image_name,
                "json_path": json_path,
                "status": "success",
                "models_successful": results["summary"]["successful_predictions"],
                "models_failed": results["summary"]["failed_predictions"],
                "average_normalized_score": results["summary"]["average_normalized_score"],
                "individual_scores": {}
            }
            
            # Add individual model scores
            for model_name, model_result in results["models"].items():
                if model_result["status"] == "success":
                    summary["individual_scores"][model_name] = {
                        "score": model_result["score"],
                        "normalized_score": model_result["normalized_score"]
                    }
            
            self.log(f"Completed: {image_path} - Average Score: {summary['average_normalized_score']}")
            return summary
            
        except Exception as e:
            error_msg = f"Failed to process {image_path}: {str(e)}"
            self.log(error_msg, "ERROR")
            return {
                "image_path": image_path,
                "image_name": Path(image_path).stem,
                "status": "failed",
                "error": str(e)
            }
    
    def process_directory(self, input_dir: str, output_dir: str = None):
        """Process all images in a directory."""
        if output_dir is None:
            output_dir = input_dir  # Default: save JSON files in same directory as images
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Log start event
        self.log("=" * 80)
        self.log("BATCH PROCESSING STARTED")
        self.log("=" * 80)
        self.log(f"Input directory: {input_dir}")
        self.log(f"Output directory: {output_dir}")
        self.log(f"Log file: {self.log_file}")
        
        # Find all images
        self.log("Scanning for images...")
        image_files = self.find_images(input_dir)
        
        if not image_files:
            self.log("No image files found in the specified directory.", "WARNING")
            return
        
        self.log(f"Found {len(image_files)} image files to process")
        
        # Initialize MUSIQ scorer
        self.log("Initializing MUSIQ models...")
        try:
            scorer = MultiModelMUSIQ()
            load_results = scorer.load_all_models()
            
            successful_loads = sum(1 for success in load_results.values() if success)
            self.log(f"Loaded {successful_loads}/{len(load_results)} models successfully")
            
            if successful_loads == 0:
                self.log("No models loaded successfully. Aborting batch processing.", "ERROR")
                return
                
        except Exception as e:
            self.log(f"Failed to initialize MUSIQ models: {str(e)}", "ERROR")
            return
        
        # Process each image
        self.log("Starting image processing...")
        self.log("-" * 80)
        
        for i, image_path in enumerate(image_files, 1):
            self.log(f"Progress: {i}/{len(image_files)}")
            
            result = self.process_single_image(image_path, scorer, output_dir)
            self.results.append(result)
            
            if result["status"] == "success":
                self.processed_count += 1
            elif result["status"] == "skipped":
                self.skipped_count += 1
            else:
                self.failed_count += 1
            
            self.log("-" * 40)
        
        # Log completion summary
        self.log("=" * 80)
        self.log("BATCH PROCESSING COMPLETED")
        self.log("=" * 80)
        self.log(f"Total images processed: {len(image_files)}")
        self.log(f"Successful: {self.processed_count}")
        self.log(f"Skipped (already processed): {self.skipped_count}")
        self.log(f"Failed: {self.failed_count}")
        
        if self.processed_count > 0:
            # Calculate overall statistics
            successful_results = [r for r in self.results if r["status"] == "success"]
            avg_scores = [r["average_normalized_score"] for r in successful_results if r["average_normalized_score"] is not None]
            
            if avg_scores:
                overall_avg = sum(avg_scores) / len(avg_scores)
                self.log(f"Overall average normalized score: {overall_avg:.3f}")
                
                # Find best and worst images
                best_image = max(successful_results, key=lambda x: x["average_normalized_score"] or 0)
                worst_image = min(successful_results, key=lambda x: x["average_normalized_score"] or 0)
                
                self.log(f"Best image: {best_image['image_name']} (score: {best_image['average_normalized_score']})")
                self.log(f"Worst image: {worst_image['image_name']} (score: {worst_image['average_normalized_score']})")
        
        # Save batch summary
        summary_file = os.path.join(output_dir, f"batch_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        batch_summary = {
            "processing_date": datetime.now().isoformat(),
            "input_directory": input_dir,
            "output_directory": output_dir,
            "log_file": self.log_file,
            "version": scorer.VERSION,
            "total_images": len(image_files),
            "successful": self.processed_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
            "results": self.results
        }
        
        with open(summary_file, 'w') as f:
            json.dump(batch_summary, f, indent=2)
        
        self.log(f"Batch summary saved to: {summary_file}")
        self.log(f"Detailed log saved to: {self.log_file}")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Batch process images with MUSIQ models and comprehensive logging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_process_images.py --input-dir "D:/Photos/Export/2025"
  python batch_process_images.py --input-dir "D:/Photos/Export/2025" --output-dir "D:/Results"
  python batch_process_images.py --input-dir "D:/Photos/Export/2025" --log-file "custom_log.log"
        """
    )
    
    parser.add_argument('--input-dir', required=True, help='Input directory containing images')
    parser.add_argument('--output-dir', help='Output directory for JSON results (default: same as input)')
    parser.add_argument('--log-file', help='Custom log file name (default: auto-generated with timestamp)')
    
    args = parser.parse_args()
    
    # Validate input directory
    if not os.path.exists(args.input_dir):
        print(f"Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    if not os.path.isdir(args.input_dir):
        print(f"Error: Input path is not a directory: {args.input_dir}")
        sys.exit(1)
    
    # Initialize processor with output directory for log file
    processor = BatchImageProcessor(args.log_file, args.output_dir)
    
    # Process directory
    try:
        processor.process_directory(args.input_dir, args.output_dir)
    except KeyboardInterrupt:
        processor.log("Batch processing interrupted by user", "WARNING")
        sys.exit(1)
    except Exception as e:
        processor.log(f"Unexpected error during batch processing: {str(e)}", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
