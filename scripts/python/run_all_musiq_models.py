#!/usr/bin/env python3
"""
Run all available MUSIQ models on an image and save results to JSON file.
The JSON file will have the same name as the image but with .json extension.
"""

import argparse
import json
import os
import sys
import tempfile
import base64
import io
import shutil
import subprocess
import logging
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import numpy as np
import tensorflow as tf
import tensorflow_hub as hub
import kagglehub
from PIL import Image, ImageOps
import rawpy

# Add project root to path to import modules
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)


def _merged_app_config() -> dict:
    """config.json merged with environment.json (same as the WebUI)."""
    try:
        from modules.config import load_config

        return load_config()
    except Exception:
        return {}

try:
    from modules.liqe import LiqeScorer
except Exception:
    try:
        from modules.liqe import LiqeScorer
    except Exception:
        logging.getLogger(__name__).warning("Could not import LiqeScorer. LIQE scoring will be unavailable.")
        LiqeScorer = None

try:
    from modules import score_normalization as snorm
except ImportError:
    snorm = None


class MultiModelMUSIQ:
    """Run multiple MUSIQ and VILA models on a single image."""
    
    # Version identifier for this implementation
    VERSION = "5.0.0"  # Percentile normalization, JPEG caching, rebalanced weights
    
    # RAW file extensions to detect (case insensitive)
    RAW_EXTENSIONS = {'.nef', '.NEF', '.nrw', '.NRW', '.cr2', '.CR2', '.cr3', '.CR3', 
                     '.arw', '.ARW', '.dng', '.DNG', '.orf', '.ORF', '.pef', '.PEF', 
                     '.raf', '.RAF', '.rw2', '.RW2', '.x3f', '.X3F'}
    
    # Nikon NEF extensions for rating (case insensitive)
    NEF_EXTENSIONS = {'.nef', '.NEF', '.nrw', '.NRW'}
    
    @staticmethod
    def wsl_to_windows_path(path: str) -> str:
        """Convert WSL path to Windows path for browser compatibility."""
        if path.startswith('/mnt/'):
            # Extract drive letter and path: /mnt/d/Path/To/File -> D:/Path/To/File
            parts = path[5:].split('/', 1)  # Remove '/mnt/' prefix
            if len(parts) == 2:
                drive_letter = parts[0].upper()
                rest_of_path = parts[1]
                return f"{drive_letter}:/{rest_of_path}"
            elif len(parts) == 1:
                # Just drive letter
                return f"{parts[0].upper()}:/"
        return path
    
    def is_raw_file(self, file_path: str) -> bool:
        """Check if file is a RAW image."""
        ext = Path(file_path).suffix.lower()
        return ext in self.RAW_EXTENSIONS
    
    def _get_cache_path(self, file_path: str, resolution_override: Optional[int] = None) -> Optional[str]:
        """Return path to cached preprocessed JPEG, or None if caching disabled.
        Cache key includes max_resolution so changing config invalidates cache."""
        try:
            cfg = _merged_app_config()

            prep_cfg = cfg.get("preprocessing", {})
            if not prep_cfg.get("cache_enabled", False):
                return None

            raw_cfg = cfg.get("raw_conversion", {})
            max_res = int(resolution_override) if resolution_override is not None else int(raw_cfg.get("max_resolution", 512))
            max_res = max(224, min(2048, max_res))

            cache_dir = prep_cfg.get("cache_dir", ".cache/preprocessed_512")
            if cache_dir == ".cache/preprocessed_512" or "{resolution}" not in cache_dir:
                cache_dir = f".cache/preprocessed_{max_res}"
            if not os.path.isabs(cache_dir):
                cache_dir = os.path.join(self.project_root, cache_dir)

            os.makedirs(cache_dir, exist_ok=True)

            import hashlib
            path_hash = hashlib.sha256(file_path.encode("utf-8")).hexdigest()[:16]
            mtime = str(int(os.path.getmtime(file_path)))
            cache_name = f"{path_hash}_{mtime}.jpg"
            return os.path.join(cache_dir, cache_name)
        except Exception:
            return None

    def _get_raw_conversion_config(self) -> dict:
        """Read raw_conversion and preprocessing config. Returns defaults if missing."""
        try:
            cfg = _merged_app_config()
            raw_cfg = cfg.get("raw_conversion", {})
            return {
                "method": raw_cfg.get("method", "rawpy_half"),
                "max_resolution": int(raw_cfg.get("max_resolution", 512)),
                "jpeg_quality": int(raw_cfg.get("jpeg_quality", 85)),
            }
        except Exception:
            pass
        return {"method": "rawpy_half", "max_resolution": 512, "jpeg_quality": 85}

    def preprocess_image(self, file_path: str, output_dir: Optional[str] = None, resolution_override: Optional[int] = None) -> Optional[str]:
        """
        Preprocess image for optimal model input:
        1. Check preprocessed cache (if enabled, and no resolution_override)
        2. (RAW only) Convert using config raw_conversion.method order (exiftool_jpgfromraw or rawpy_half)
        3. Resize: Bicubic to fit within config max_resolution (or resolution_override)
        4. Pad: Add black borders to make exactly target_size x target_size

        Args:
            file_path: Path to image or RAW file.
            output_dir: If set, write preprocessed JPEG here and return path (caller owns cleanup).
                        If None, use internal temp dir and append to self.temp_files.
            resolution_override: If set, use this size instead of config max_resolution (for per-model preprocessing).

        Returns:
            Path to preprocessed JPEG, or None on failure.
        """
        raw_cfg = self._get_raw_conversion_config()
        target_size = int(resolution_override) if resolution_override is not None else max(224, min(2048, raw_cfg["max_resolution"]))
        target_size = max(224, min(2048, target_size))
        jpeg_quality = max(50, min(100, raw_cfg["jpeg_quality"]))
        conversion_prefer = (raw_cfg["method"] or "exiftool_jpgfromraw").strip().lower()

        if output_dir is None and resolution_override is None:
            cache_path = self._get_cache_path(file_path)
            if cache_path and os.path.exists(cache_path):
                logging.getLogger(__name__).info(
                    "preprocess_image: method=cache_hit path=%s cache=%s", file_path, cache_path
                )
                return cache_path

        if output_dir is not None:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"preprocessed_{target_size}.jpg")
        else:
            temp_dir = self.setup_temp_directory()
            output_path = os.path.join(temp_dir, f"preprocessed_{os.path.basename(file_path)}.jpg")
        
        try:
            pil_image = None
            
            # RAW: use config conversion order (preferred method first)
            decode_method: Optional[str] = None
            if self.is_raw_file(file_path):
                try_rawpy = lambda: self._extract_jpeg_rawpy(file_path)
                if conversion_prefer == "rawpy_half":
                    pil_image = try_rawpy()
                    decode_method = "rawpy_half" if pil_image is not None else None
                    if pil_image is None:
                        pil_image, em = self._extract_jpeg_exiftool(file_path)
                        decode_method = em
                else:
                    pil_image, em = self._extract_jpeg_exiftool(file_path)
                    decode_method = em
                    if pil_image is None:
                        pil_image = try_rawpy()
                        decode_method = "rawpy_half" if pil_image is not None else None
                if pil_image is not None and decode_method:
                    logging.getLogger(__name__).info(
                        "preprocess_image: method=%s path=%s", decode_method, file_path
                    )
            else:
                pil_image = Image.open(file_path).convert("RGB")
                logging.getLogger(__name__).info(
                    "preprocess_image: method=pil_open path=%s", file_path
                )

            if pil_image is None:
                if self.is_raw_file(file_path):
                    logging.getLogger(__name__).warning(
                        "preprocess_image: failed (no RAW decoder succeeded) path=%s", file_path
                    )
                return None

            if pil_image.size == (target_size, target_size):
                if output_dir is not None:
                    pil_image.save(output_path, "JPEG", quality=jpeg_quality)
                    return output_path
                return file_path
                
            pil_image.thumbnail((target_size, target_size), Image.BICUBIC)
            delta_w = target_size - pil_image.size[0]
            delta_h = target_size - pil_image.size[1]
            padding = (delta_w//2, delta_h//2, delta_w-(delta_w//2), delta_h-(delta_h//2))
            padded_image = ImageOps.expand(pil_image, padding, fill=0)
            
            if padded_image.size != (target_size, target_size):
                padded_image = padded_image.resize((target_size, target_size), Image.BICUBIC)
            
            padded_image.save(output_path, "JPEG", quality=jpeg_quality)
            if output_dir is None:
                self.temp_files.append(output_path)
                cache_path = self._get_cache_path(file_path)
                if cache_path and not os.path.exists(cache_path):
                    try:
                        import shutil as _shutil
                        _shutil.copy2(output_path, cache_path)
                    except Exception:
                        pass
            return output_path
            
        except Exception as e:
            logging.getLogger(__name__).error(f"Preprocessing failed: {e}")
            return None

    def _exiftool_extract_preview_bytes(self, raw_path: str) -> Optional[Tuple[str, bytes]]:
        """
        Pull embedded preview bytes via ExifTool (tags ordered largest-first intent).
        Returns (tag_name, data) for JPEG or TIFF/other raster ExifTool exposes.
        """
        if shutil.which("exiftool") is None:
            return None
        min_len = 500
        for tag in ("JpgFromRaw", "PreviewImage", "OtherImage", "ThumbnailImage"):
            try:
                cmd = ["exiftool", "-b", f"-{tag}", raw_path]
                result = subprocess.run(cmd, capture_output=True, text=False, timeout=10)
            except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
                continue
            if result.returncode != 0 or len(result.stdout) < min_len:
                continue
            data = result.stdout
            if data.startswith(b"\xff\xd8"):
                return (tag, data)
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
                img.close()
                return (tag, data)
            except Exception:
                continue
        return None

    def _extract_jpeg_exiftool(self, file_path: str) -> Tuple[Optional[Image.Image], Optional[str]]:
        """Extract embedded preview via exiftool. Returns (PIL Image, method label e.g. exiftool:JpgFromRaw)."""
        try:
            pair = self._exiftool_extract_preview_bytes(file_path)
            if not pair:
                return None, None
            tag, data = pair
            img = Image.open(io.BytesIO(data))
            img.load()
            return img.convert("RGB"), f"exiftool:{tag}"
        except Exception as e:
            logging.getLogger(__name__).debug(f"ExifTool extraction failed: {e}")
        return None, None

    def _extract_jpeg_rawpy(self, file_path: str):
        """Extract JPEG via rawpy half-size. Returns PIL Image or None."""
        if not self._is_safe_for_rawpy(file_path):
            logging.getLogger(__name__).warning("Skipping rawpy for incompatible file (Nikon HE)")
            return None
        try:
            with rawpy.imread(file_path) as raw:
                rgb = raw.postprocess(use_camera_wb=True, half_size=True)
                return Image.fromarray(rgb)
        except Exception as e:
            logging.getLogger(__name__).error(f"Rawpy conversion failed: {e}")
            return None
    
    def is_nef_file(self, file_path: str) -> bool:
        """Check if file is a Nikon NEF file that can be rated."""
        ext = Path(file_path).suffix.lower()
        return ext in self.NEF_EXTENSIONS
    
    def score_to_rating(self, score: float) -> int:
        """Convert rescaled general score to 1-5 star rating.
        Delegates to score_normalization module when available."""
        if snorm is not None:
            return snorm.score_to_rating(score)
        s = max(0.0, min(1.0, score))
        if s >= 0.90: return 5
        elif s >= 0.72: return 4
        elif s >= 0.50: return 3
        elif s >= 0.30: return 2
        else: return 1
            
    def determine_lightroom_label(self, scores: Dict[str, float]) -> Optional[str]:
        """Determine Lightroom color label. Delegates to score_normalization module."""
        if snorm is not None:
            return snorm.determine_label(scores)

        def get_s(model):
            return scores.get(model, 0.0)

        tech_score = get_s('liqe')
        art_score = 0.55 * get_s('ava') + 0.45 * get_s('spaq')

        if tech_score < 0.30: return "Red"
        if art_score > 0.65 and tech_score < 0.50: return "Purple"
        if art_score > 0.65 and tech_score > 0.65: return "Blue"
        if tech_score > 0.55: return "Green"
        return "Yellow"
    

    
    def write_metadata_to_nef(self, nef_path: str, rating: int, label: str = None) -> bool:
        """Write rating and color label to Nikon NEF file EXIF/XMP metadata."""
        if rating < 1 or rating > 5:
            print(f"Invalid rating: {rating}. Must be 1-5.")
            return False
        
        if not self.is_nef_file(nef_path):
            print(f"File is not a Nikon NEF file: {nef_path}")
            return False
        
        try:
            # Try pyexiv2 first (best for NEF files)
            return self._write_metadata_pyexiv2(nef_path, rating, label)
        except ImportError:
            try:
                # Fallback to exiftool
                return self._write_metadata_exiftool(nef_path, rating, label)
            except Exception as e:
                logging.getLogger(__name__).error(f"Failed to write metadata to NEF file: {e}")
                logging.getLogger(__name__).info("Install pyexiv2 for best NEF support: pip install pyexiv2")
                return False
    
    def _write_metadata_pyexiv2(self, nef_path: str, rating: int, label: str = None) -> bool:
        """Write metadata using pyexiv2 library."""
        try:
            import pyexiv2
            
            # Backup original file
            backup_path = f"{nef_path}.backup"
            shutil.copy2(nef_path, backup_path)
            
            # Open and modify EXIF
            with pyexiv2.Image(nef_path) as img:
                # Set rating in multiple EXIF fields for compatibility
                img.modify_exif({
                    'Exif.Photo.UserComment': f'MUSIQ Quality Rating: {rating}/5',
                    'Exif.Image.Rating': rating,
                    'Exif.Image.RatingPercent': rating * 20,  # 1=20%, 2=40%, etc.
                })
                
                # Also set XMP rating and label for broader compatibility
                xmp_data = {'Xmp.xmp.Rating': rating}
                if label:
                    xmp_data['Xmp.xmp.Label'] = label
                
                img.modify_xmp(xmp_data)
            
            logging.getLogger(__name__).info(f"✓ Rating {rating}/5 and Label '{label}' written to NEF file: {nef_path}")
            
            # Remove backup if successful
            if os.path.exists(backup_path):
                os.remove(backup_path)
            
            return True
            
        except ImportError:
            logging.getLogger(__name__).warning("pyexiv2 not available - install with: pip install pyexiv2")
            raise
        except Exception as e:
            logging.getLogger(__name__).error(f"pyexiv2 rating write failed: {e}")
            # Restore backup if it exists
            backup_path = f"{nef_path}.backup"
            if os.path.exists(backup_path):
                shutil.move(backup_path, nef_path)
                logging.getLogger(__name__).info("Restored backup file")
            return False
    
    def _write_metadata_exiftool(self, nef_path: str, rating: int, label: str = None) -> bool:
        """Write metadata using exiftool command line."""
        try:
            # Backup original file
            backup_path = f"{nef_path}.backup"
            shutil.copy2(nef_path, backup_path)
            
            # Use exiftool to write rating
            cmd = [
                'exiftool',
                '-overwrite_original',  # Modify in place
                '-Rating=' + str(rating),
                '-RatingPercent=' + str(rating * 20),
                '-UserComment=MUSIQ Quality Rating: ' + str(rating) + '/5',
            ]
            
            if label:
                cmd.append(f'-Label={label}')
                
            cmd.append(nef_path)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                logging.getLogger(__name__).info(f"✓ Rating {rating}/5 written to NEF file: {nef_path}")
                # Remove backup if successful
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                return True
            else:
                logging.getLogger(__name__).error(f"exiftool failed: {result.stderr}")
                # Restore backup
                if os.path.exists(backup_path):
                    shutil.move(backup_path, nef_path)
                return False
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logging.getLogger(__name__).warning(f"exiftool not available or failed: {e}")
            logging.getLogger(__name__).info("Install exiftool for NEF rating support")
            # Restore backup
            backup_path = f"{nef_path}.backup"
            if os.path.exists(backup_path):
                shutil.move(backup_path, nef_path)
            return False
    
    def setup_temp_directory(self) -> str:
        """Setup temporary directory for RAW conversion."""
        if self.temp_dir is None:
            self.temp_dir = tempfile.mkdtemp(prefix='musiq_raw_')
            logging.getLogger(__name__).debug(f"Created temporary directory: {self.temp_dir}")
        return self.temp_dir
    
    def cleanup_temp_files(self):
        """Clean up all temporary files and directories."""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logging.getLogger(__name__).debug(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logging.getLogger(__name__).warning(f"Warning: Could not remove temporary file {temp_file}: {e}")
        
        self.temp_files.clear()
        
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logging.getLogger(__name__).debug(f"Cleaned up temporary directory: {self.temp_dir}")
                self.temp_dir = None
            except Exception as e:
                logging.getLogger(__name__).warning(f"Warning: Could not remove temporary directory {self.temp_dir}: {e}")
    
    def _is_safe_for_rawpy(self, raw_path: str) -> bool:
        """
        Check if RAW file is safe for rawpy (libraw).
        Nikon Z8/Z9 HE/HE* (TicoRAW) compression causes libraw to hang/fail slowly.
        Returns:
            True if file is likely compatible (or check fails)
            False if file is definitely incompatible (Nikon HE detected)
        """
        try:
            # Requires exiftool
            if shutil.which("exiftool") is None:
                return True # assume safe if we can't check
                
            cmd = ['exiftool', '-Model', '-Compression', '-s', '-S', raw_path]
            # Fast timeout (2s) because we want to be quicker than the 7s rawpy hang
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            
            if result.returncode == 0:
                output = result.stdout.strip()
                # Parse output (Model\nCompression)
                lines = output.splitlines()
                model = ""
                compression = ""
                
                # Exiftool -s -S output is just values, one per line usually, but order depends on args?
                # Actually -s -S prints tag names if -s is used? No -S is very short (no tag name).
                # But order is preserved?
                # Safest is to not use -S so we get "Tag: Value"
                
            # Retry with tags to be safe
            cmd = ['exiftool', '-Model', '-Compression', '-s', '-s', '-s', raw_path] # -s -s -s = values only
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if result.returncode == 0:
                 # We can't guarantee order if we just ask for values.
                 # Let's parse proper json? No, too heavy?
                 # JSON is robust.
                 pass

            # Robust approach: Use JSON
            cmd = ["exiftool", "-Model", "-Compression", "-NEFCompression", "-j", raw_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if result.returncode == 0:
                import json
                data = json.loads(result.stdout)
                if data and isinstance(data, list):
                    info = data[0]
                    model = info.get("Model", "")
                    compression = info.get("Compression", "")
                    nef_compression = info.get("NEFCompression", "") or ""

                    # 1. Explicit HE detection
                    if "Nikon HE" in compression:
                        return False

                    # 1b. NEFCompression often names High Efficiency* explicitly
                    nef_l = nef_compression.lower()
                    if "high efficiency" in nef_l:
                        return False

                    # 2. Ambiguous Z8/Z9 Compressed detection
                    # "Nikon NEF Compressed" on Z8/Z9 often fails in LibRaw (TicoRAW?)
                    if "Z 8" in model or "Z 9" in model:
                        if "Nikon NEF Compressed" in compression:
                            return False

            return True
        except Exception as e:
            # If check fails, default to trying rawpy
            return True

    def _convert_with_exiftool(self, raw_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """
        Convert RAW using exiftool to extract embedded JPEG.
        This is often the most robust method for modern proprietary formats like Z8/Z9 HE*.
        """
        try:
            pair = self._exiftool_extract_preview_bytes(raw_path)
            if not pair:
                return False, None
            tag, data = pair
            if data.startswith(b"\xff\xd8"):
                with open(output_path, "wb") as f:
                    f.write(data)
            else:
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img.save(output_path, "JPEG", quality=85, optimize=True)
            return True, f"exiftool:{tag}"
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False, None

    def convert_raw_to_jpeg(self, raw_path: str) -> Optional[str]:
        """Convert RAW file to temporary JPEG for processing."""
        logging.getLogger(__name__).info(f"Converting RAW file: {raw_path}")
        
        # Setup temp directory
        temp_dir = self.setup_temp_directory()
        
        # Generate temp JPEG path
        raw_name = Path(raw_path).stem
        temp_jpeg = os.path.join(temp_dir, f"{raw_name}_temp.jpg")
        
        # Try different RAW conversion tools in order of preference
        # Research recommendation: exiftool first (fast, sufficient), then rawpy
        if self._is_safe_for_rawpy(raw_path):
             conversion_methods = [
                 self._convert_with_exiftool,
                 self._convert_with_rawpy,
                 self._convert_with_dcraw,
                 self._convert_with_imagemagick,
                 self._convert_with_pillow
             ]
        else:
             logging.getLogger(__name__).info(f"Skipping rawpy for likely HE/HE* compressed file: {raw_name}")
             conversion_methods = [
                 self._convert_with_exiftool,  # Priority 1 for HE* files
                 self._convert_with_dcraw,
                 self._convert_with_imagemagick,
                 self._convert_with_pillow
             ]

        for method in conversion_methods:
            try:
                ok, used = method(raw_path, temp_jpeg)
                if ok:
                    self.temp_files.append(temp_jpeg)
                    label = used or method.__name__.replace("_convert_with_", "")
                    logging.getLogger(__name__).info(
                        "✓ RAW conversion successful path=%s method=%s", temp_jpeg, label
                    )
                    return temp_jpeg
            except Exception as e:
                msg = str(e).lower()
                if "corrupted" in msg or "data error" in msg:
                    logging.getLogger(__name__).error(f"⚠ File appears corrupted, skipping fallback methods: {raw_path}")
                    break
                logging.getLogger(__name__).warning(f"⚠ Conversion method failed: {method.__name__}: {e}")
                continue
        
        logging.getLogger(__name__).error(f"✗ All RAW conversion methods failed for: {raw_path}")
        return None
    
    def _convert_with_rawpy(self, raw_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """Convert RAW using rawpy library (best quality)."""
        try:
            import rawpy
            with rawpy.imread(raw_path) as raw:
                # Process with minimal settings for speed
                rgb = raw.postprocess(
                    half_size=True,  # Half resolution for speed
                    use_camera_wb=True,  # Use camera white balance
                    output_color=rawpy.ColorSpace.sRGB,
                    output_bps=8  # 8-bit for smaller files
                )
                
                # Save as JPEG
                from PIL import Image
                img = Image.fromarray(rgb)
                img.save(output_path, 'JPEG', quality=85, optimize=True)
                return True, "rawpy_half"
        except ImportError:
            print("rawpy not available - install with: pip install rawpy")
            return False, None
        except Exception as e:
            msg = str(e).lower()
            if "corrupted" in msg or "unsupported" in msg:
                logging.getLogger(__name__).warning(f"⚠ rawpy cannot read file (likely Nikon Z8 HE* or unsupported format): {e}")
                logging.getLogger(__name__).info("  Attempting fallback to dcraw/magick...")
            else:
                logging.getLogger(__name__).warning(f"rawpy conversion failed: {e}")
            return False, None
    
    def _convert_with_dcraw(self, raw_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """
        Convert RAW using dcraw command line tool.
        Prioritizes extracting embedded JPEG (fast, correct colors) over full decode.
        """
        try:
            if shutil.which("dcraw") is None:
                return False, None
                
            # Method 1: Extraction (-e) - Fast & Compatible with Z8
            cmd_extract = ['dcraw', '-e', '-c', raw_path] 
            res_extract = subprocess.run(cmd_extract, capture_output=True, text=False, timeout=10)
            
            if res_extract.returncode == 0 and len(res_extract.stdout) > 1000:
                # Check for JPEG header (FF D8)
                if res_extract.stdout.startswith(b'\xff\xd8'):
                    try:
                        with open(output_path, 'wb') as f:
                            f.write(res_extract.stdout)
                        return True, "dcraw:embedded_jpeg"
                    except Exception as e:
                        logging.getLogger(__name__).warning(f"Failed to write extracted JPEG: {e}")
            
            # Method 2: Full Decode (-c -w -h) - Slow, Fallback
            logging.getLogger(__name__).info(f"Fallback to dcraw full decode...")
            # Try dcraw command
            cmd = [
                'dcraw',
                '-h',  # Half-size
                '-w',  # Use camera white balance
                '-c',  # Output to stdout
                raw_path
            ]
            
            # Run dcraw (output is binary PPM)
            result = subprocess.run(cmd, capture_output=True, text=False, timeout=60) # Increased timeout
            if result.returncode == 0:
                # Pipe output to convert to JPEG (input must be binary)
                jpeg_cmd = ['convert', '-', '-quality', '85', output_path]
                convert_result = subprocess.run(jpeg_cmd, input=result.stdout, 
                                             capture_output=True, text=False, timeout=30)
                if convert_result.returncode == 0:
                    return True, "dcraw:full_decode+convert"
                return False, None
            return False, None
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logging.getLogger(__name__).warning(f"dcraw conversion failed: {e}")
            return False, None
    
    def _convert_with_imagemagick(self, raw_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """Convert RAW using ImageMagick."""
        try:
            # Check if magick is available first to avoid noise
            if shutil.which("magick") is None:
                return False, None

            cmd = [
                'magick',
                raw_path,
                '-resize', '50%',  # Half size for speed
                '-quality', '85',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and os.path.exists(output_path):
                return True, "imagemagick:magick_resize50"
            return False, None
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            # logging.getLogger(__name__).debug(f"ImageMagick conversion failed: {e}") # Debug only
            return False, None
    
    def _convert_with_pillow(self, raw_path: str, output_path: str) -> Tuple[bool, Optional[str]]:
        """Convert RAW using Pillow (limited RAW support)."""
        try:
            # Pillow has limited RAW support, mainly for DNG
            img = Image.open(raw_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize for speed
            img.thumbnail((img.width // 2, img.height // 2), Image.Resampling.LANCZOS)
            img.save(output_path, 'JPEG', quality=85, optimize=True)
            return True, "pillow:open"
        except Exception as e:
            print(f"Pillow conversion failed: {e}")
            return False, None
    
    def __init__(self, skip_gpu: bool = False):
        self.device = None

        # Configure persistent TF Hub cache
        try:
            # Resolve project root: scripts/python/ -> scripts/ -> root/
            current_file = os.path.abspath(__file__)
            # scripts/python -> scripts -> image-scoring
            self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            
            # Use 'models/tfhub_cache' for persistent storage
            self.tfhub_cache_dir = os.path.join(self.project_root, "models", "tfhub_cache")
            
            # Create directory if it doesn't exist
            os.makedirs(self.tfhub_cache_dir, exist_ok=True)
            
            # Set environment variable BEFORE loading any models
            os.environ['TFHUB_CACHE_DIR'] = self.tfhub_cache_dir
            logging.getLogger(__name__).info(f"TF Hub cache directory set to: {self.tfhub_cache_dir}")
            
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to set custom TF Hub cache directory: {e}")

        self.gpu_available = False
        self.models = {}
        self.temp_dir = None
        self.temp_files = []
        
        # Model availability on different platforms
        # All models with TensorFlow Hub, Kaggle Hub, and local checkpoint paths
        # Format: {"model": {"tfhub": "url", "kaggle": "path", "local": "checkpoint_file"}}
        # Fallback order: TF Hub → Kaggle Hub → Local Checkpoints
        
        # Get base directory for local checkpoints
        checkpoint_dir = os.path.join(self.project_root, "models", "checkpoints")
        
        self.model_sources = {
            "liqe": {
                "type": "pyiqa",
                "local": None # Loaded internally by pyiqa/LiqeScorer
            },
            "spaq": {
                "tfhub": "https://tfhub.dev/google/musiq/spaq/1",
                "kaggle": "google/musiq/tensorFlow2/spaq",
                "local": os.path.join(checkpoint_dir, "spaq_ckpt.npz")
            },
            "ava": {
                "tfhub": "https://tfhub.dev/google/musiq/ava/1",
                "kaggle": "google/musiq/tensorFlow2/ava",
                "local": os.path.join(checkpoint_dir, "ava_ckpt.npz")
            },
            # "koniq": {
            #     "tfhub": None,  # Not available on TF Hub
            #     "kaggle": "google/musiq/tensorFlow2/koniq-10k",
            #     "local": os.path.join(checkpoint_dir, "koniq_ckpt.npz")
            # },
            # "paq2piq": {
            #     "tfhub": "https://tfhub.dev/google/musiq/paq2piq/1",
            #     "kaggle": "google/musiq/tensorFlow2/paq2piq",
            #     "local": os.path.join(checkpoint_dir, "paq2piq_ckpt.npz")
            # }
            # "vila": {
            #     "tfhub": "https://tfhub.dev/google/vila/image/1",
            #     "kaggle": "google/vila/tensorFlow2/image",
            #     "local": os.path.join(checkpoint_dir, "vila-tensorflow2-image-v1")
            # }
        }
        
        # Model types (for processing logic)
        self.model_types = {
            "liqe": "pyiqa",
            "spaq": "musiq",
            "ava": "musiq",
            "koniq": "musiq",
            "paq2piq": "musiq",
            "vila": "vila"
        }
        
        # Model score ranges for reference (from official documentation)
        self.model_ranges = {
            "liqe": (1.0, 5.0),        # LIQE: 1-5
            "spaq": (0.0, 100.0),      # SPAQ dataset: 0-100
            "ava": (1.0, 10.0),        # AVA dataset: 1-10
            "koniq": (0.0, 100.0),     # KONIQ-10k dataset: 0-100
            "paq2piq": (0.0, 100.0),   # PAQ2PIQ dataset: 0-100
            "vila": (0.0, 1.0)         # VILA aesthetic score: 0-1 (official range)
        }
        
        # Initialize GPU support
        if not skip_gpu:
            self._setup_gpu()
        else:
             self.gpu_available = False
             self.device = '/CPU:0'
        
        # Model weights for weighted scoring
        # Load from config if available, otherwise use defaults
        default_weights = {
            "liqe": 0.50,
            "ava": 0.30,
            "spaq": 0.20,
            "paq2piq": 0.00,
            "koniq": 0.00,
            "vila": 0.00
        }
        
        # Try to load from config (merged with environment.json)
        try:
            config_data = _merged_app_config()
            self.model_weights = config_data.get("model_weights", default_weights)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Could not load model weights from config: {e}")
            self.model_weights = default_weights
    
    def _setup_gpu(self):
        """Setup GPU configuration."""
        gpus = tf.config.experimental.list_physical_devices('GPU')
        if gpus:
            try:
                for gpu in gpus:
                    tf.config.experimental.set_memory_growth(gpu, True)
                self.gpu_available = True
                self.device = '/GPU:0'
                self.gpu_available = True
                self.device = '/GPU:0'
                logging.getLogger(__name__).info(f"GPU detected: {len(gpus)} device(s) available")
                logging.getLogger(__name__).info(f"Using device: {self.device}")
            except RuntimeError as e:
                logging.getLogger(__name__).error(f"GPU setup failed: {e}")
                logging.getLogger(__name__).warning("Falling back to CPU")
                self.gpu_available = False
                self.device = '/CPU:0'
        else:
            print("No GPU detected, using CPU")
            self.gpu_available = False
            self.device = '/CPU:0'
    
    def load_model(self, model_name: str) -> bool:
        """
        Load a model with triple fallback mechanism:
        1. TensorFlow Hub (fast, no auth) 
        2. Kaggle Hub (requires auth)
        3. Local checkpoints (offline fallback)
        
        This provides maximum reliability across different network conditions,
        authentication states, and offline scenarios.
        """
        if model_name not in self.model_sources:
            logging.getLogger(__name__).error(f"Error: Unknown model variant '{model_name}'")
            return False
        
        sources = self.model_sources[model_name]
        tfhub_url = sources.get("tfhub")
        kaggle_path = sources.get("kaggle")
        local_path = sources.get("local")
        model_type = sources.get("type", "tfhub")

        # Special handling for LIQE
        if model_name == "liqe" or model_type == "pyiqa":
            try:
                if LiqeScorer is None:
                    return False
                logging.getLogger(__name__).info(f"Loading {model_name.upper()} model via pyiqa...")
                self.models[model_name] = LiqeScorer(device=self.device.replace('/GPU:0', 'cuda').replace('/CPU:0', 'cpu'))
                if self.models[model_name].available:
                    logging.getLogger(__name__).info(f"✓ {model_name.upper()} model loaded successfully")
                    return True
                else:
                    logging.getLogger(__name__).error(f"✗ {model_name.upper()} model failed to initialize")
                    return False
            except Exception as e:
                logging.getLogger(__name__).error(f"✗ Failed to load {model_name.upper()}: {e}")
                return False
        
        # Try TensorFlow Hub first (preferred - no auth needed, usually faster)
        if tfhub_url:
            try:
                logging.getLogger(__name__).info(f"Loading {model_name.upper()} model from TensorFlow Hub: {tfhub_url}")
                with tf.device(self.device):
                    model = hub.load(tfhub_url)
                    self.models[model_name] = model
                    logging.getLogger(__name__).info(f"✓ {model_name.upper()} model loaded successfully from TensorFlow Hub")
                    return True
            except Exception as e:
                logging.getLogger(__name__).warning(f"⚠ TensorFlow Hub failed for {model_name.upper()}: {str(e)[:80]}...")
                logging.getLogger(__name__).info(f"  Falling back to Kaggle Hub...")
        
        # Fall back to Kaggle Hub (requires authentication)
        if kaggle_path:
            try:
                logging.getLogger(__name__).info(f"Loading {model_name.upper()} model from Kaggle Hub: {kaggle_path}")
                
                # Download model from Kaggle Hub
                model_path = kagglehub.model_download(kaggle_path)
                logging.getLogger(__name__).debug(f"Model downloaded to: {model_path}")
                
                # Load the model
                with tf.device(self.device):
                    model = tf.saved_model.load(model_path)
                    self.models[model_name] = model
                    logging.getLogger(__name__).info(f"✓ {model_name.upper()} model loaded successfully from Kaggle Hub")
                    return True
                    
            except Exception as e:
                logging.getLogger(__name__).warning(f"⚠ Kaggle Hub failed for {model_name.upper()}: {str(e)[:80]}...")
                logging.getLogger(__name__).info(f"  Falling back to local checkpoint...")
        
        # Fall back to local checkpoint (offline, no network needed)
        if local_path and os.path.exists(local_path):
            try:
                logging.getLogger(__name__).info(f"Loading {model_name.upper()} model from local checkpoint: {local_path}")
                
                with tf.device(self.device):
                    # Check if it's a SavedModel directory or .npz file
                    if os.path.isdir(local_path):
                        # Load SavedModel (VILA cached model)
                        model = tf.saved_model.load(local_path)
                        self.models[model_name] = model
                        logging.getLogger(__name__).info(f"✓ {model_name.upper()} model loaded successfully from local SavedModel")
                        return True
                    elif local_path.endswith('.npz'):
                        # Load .npz checkpoint (MUSIQ models)
                        # Note: .npz files require the original MUSIQ loading code
                        # For now, try loading as SavedModel if conversion exists
                        logging.getLogger(__name__).warning(f"⚠ .npz checkpoint loading not yet implemented for {model_name.upper()}")
                        logging.getLogger(__name__).info(f"  Checkpoint available at: {local_path}")
                        logging.getLogger(__name__).info(f"  Consider using TF Hub or Kaggle Hub sources instead")
                        return False
                    else:
                        logging.getLogger(__name__).warning(f"⚠ Unknown local checkpoint format: {local_path}")
                        return False
                        
            except Exception as e:
                logging.getLogger(__name__).error(f"✗ Failed to load {model_name.upper()} model from local checkpoint: {str(e)[:80]}...")
        elif local_path:
            logging.getLogger(__name__).warning(f"⚠ Local checkpoint not found: {local_path}")
            logging.getLogger(__name__).info(f"  Download checkpoints from: https://storage.googleapis.com/gresearch/musiq/")
        
        # All sources failed or unavailable
        logging.getLogger(__name__).error(f"✗ Failed to load {model_name.upper()} model: All available sources failed")
        if "vila" in model_name.lower():
            logging.getLogger(__name__).info("\nNote: For VILA model:")
            logging.getLogger(__name__).info("  - TF Hub: No authentication needed")
            logging.getLogger(__name__).info("  - Kaggle Hub: Requires kaggle.json authentication")
            logging.getLogger(__name__).info("  See docs/vila/README_VILA.md for setup instructions.")
        else:
            logging.getLogger(__name__).info("\nNote: For MUSIQ models:")
            logging.getLogger(__name__).info("  - TF Hub: No authentication needed (recommended)")
            logging.getLogger(__name__).info("  - Kaggle Hub: Requires kaggle.json authentication")
            logging.getLogger(__name__).info("  - Local .npz: Download from https://storage.googleapis.com/gresearch/musiq/")
        
        return False
    
    def load_all_models(self) -> Dict[str, bool]:
        """Load all available MUSIQ models."""
        results = {}
        for model_name in self.model_sources.keys():
            results[model_name] = self.load_model(model_name)
        return results
    
    def predict_quality(self, image_path: str, model_name: str) -> Optional[float]:
        """Predict image quality using a specific model."""
        if model_name not in self.models:
            logging.getLogger(__name__).error(f"Error: Model '{model_name}' not loaded")
            return None
        
        model = self.models[model_name]
        model_type = self.model_types.get(model_name, "musiq")
        
        try:
            # Read image bytes
            with open(image_path, 'rb') as f:
                image_bytes = f.read()
            
            # Ensure tensor is on correct device
            with tf.device(self.device):
                # TensorFlow Hub/Kaggle models expect image bytes as string tensor
                image_bytes_tensor = tf.constant(image_bytes)
                
                # Determine correct parameter name for model
                # VILA models use 'image_bytes', MUSIQ models use 'image_bytes_tensor'
                if model_type == "vila":
                    predictions = model.signatures['serving_default'](image_bytes=image_bytes_tensor)
                elif model_type == "pyiqa":
                    # LIQE / pyiqa prediction
                    # image_path is passed directly
                    result = model.predict(image_path)
                    if result and result.get("status") == "success":
                         return float(result.get("score", 0.0))
                    else:
                         logging.getLogger(__name__).warning(f"{model_name.upper()} prediction failed: {result.get('error')}")
                         return None
                else:
                    predictions = model.signatures['serving_default'](image_bytes_tensor=image_bytes_tensor)
            
            # Extract score based on model type
            if model_type == "vila":
                # VILA models may have different output structure
                if isinstance(predictions, dict):
                    # Try common output names for aesthetic scores
                    if 'aesthetic_score' in predictions:
                        score = float(predictions['aesthetic_score'].numpy().squeeze())
                    elif 'score' in predictions:
                        score = float(predictions['score'].numpy().squeeze())
                    elif 'output_0' in predictions:
                        score = float(predictions['output_0'].numpy().squeeze())
                    else:
                        # Use first numeric output
                        score = float(list(predictions.values())[0].numpy().squeeze())
                else:
                    score = float(predictions.numpy().squeeze())
            else:
                # MUSIQ models
                if isinstance(predictions, dict):
                    if 'output_0' in predictions:
                        score = float(predictions['output_0'].numpy().squeeze())
                    elif 'predictions' in predictions:
                        score = float(predictions['predictions'].numpy().squeeze())
                    elif 'output' in predictions:
                        score = float(predictions['output'].numpy().squeeze())
                    else:
                        score = float(list(predictions.values())[0].numpy().squeeze())
                else:
                    score = float(predictions.numpy().squeeze())
            
            return score
            
        except Exception as e:
            logging.getLogger(__name__).error(f"Error predicting with {model_name.upper()} model: {e}")
            return None
    
    def run_all_models(self, image_path: str, external_scores: Dict[str, any] = None, logger=print, write_metadata: bool = True) -> Dict[str, any]:
        """
        Run all loaded models on the image and return results.
        
        Args:
            image_path: Path to the image file
            external_scores: Dictionary of pre-calculated scores to include (e.g. {'liqe': {'score': 0.8, ...}})
            logger: Function to use for logging (default: print)
            write_metadata: Whether to write ratings back to the image file (default: True)
        """
        # Check if this is a RAW file
        is_raw = self.is_raw_file(image_path)
        processing_path = image_path
        
        if is_raw:
            logger(f"RAW file detected: {image_path}")
            # Use new preprocessing pipeline
            processed_path = self.preprocess_image(image_path)
            
            if processed_path is None:
                # Failed
                return {
                    "version": self.VERSION,
                    "image_path": self.wsl_to_windows_path(image_path),
                    "image_name": os.path.basename(image_path),
                    "device": "GPU" if self.gpu_available else "CPU",
                    "gpu_available": self.gpu_available,
                    "models": {},
                    "summary": {
                        "total_models": 0,
                        "successful_predictions": 0,
                        "failed_predictions": 0,
                        "average_normalized_score": None,
                        "error": "RAW/Image preprocessing failed"
                    },
                    "raw_conversion": {
                        "original_raw": image_path,
                        "temp_jpeg": None,
                        "conversion_success": False
                    }
                }
            processing_path = processed_path
        else:
             # Skip preprocessing if already at target size (e.g. pipeline preprocessed)
             raw_cfg = self._get_raw_conversion_config()
             target_size = max(224, min(2048, raw_cfg["max_resolution"]))
             try:
                 with Image.open(image_path) as img:
                     w, h = img.size
                 if w == target_size and h == target_size:
                     processing_path = image_path
                 else:
                     processed_path = self.preprocess_image(image_path)
                     if processed_path:
                         processing_path = processed_path
                     else:
                         logger("Warning: Preprocessing failed for standard image, using original.")
             except Exception:
                 processed_path = self.preprocess_image(image_path)
                 if processed_path:
                     processing_path = processed_path
                 else:
                     logger("Warning: Preprocessing failed for standard image, using original.")
        
        # Convert WSL path to Windows path for browser compatibility
        browser_path = self.wsl_to_windows_path(image_path)
        
        results = {
            "version": self.VERSION,
            "image_path": browser_path,
            "image_name": os.path.basename(image_path),
            "device": "GPU" if self.gpu_available else "CPU",
            "gpu_available": self.gpu_available,
            "models": {},
            "summary": {
                "total_models": len(self.models),
                "successful_predictions": 0,
                "failed_predictions": 0
            }
        }
        
        # Add RAW conversion info if applicable
        if is_raw:
            results["raw_conversion"] = {
                "original_raw": image_path,
                "temp_jpeg": processing_path,
                "conversion_success": True
        }
        
        logger(f"\nRunning all models on: {image_path}")
        if is_raw:
            logger(f"Processing converted JPEG: {processing_path}")
        logger("=" * 60)
        
        normalized_scores = []
        
        # Merge external scores if provided
        if external_scores:
            for model_name, model_data in external_scores.items():
                # Skip non-dictionary items (like 'image_hash') which are metadata, not model results
                if not isinstance(model_data, dict):
                     continue

                results["models"][model_name] = model_data
                
                if model_data.get("status") == "success":
                    norm_score = model_data.get("normalized_score")
                    
                    # If normalized score not provided, try to calculate from score if we know the model
                    if norm_score is None and model_data.get("score") is not None:
                        # For LIQE, range is typically 1-5
                        if model_name.lower() == 'liqe':
                            raw_score = model_data.get("score", 0)
                            min_val = 1.0
                            max_val = 5.0
                            norm_score = (raw_score - min_val) / (max_val - min_val)
                            # Clamp
                            norm_score = max(0.0, min(1.0, norm_score))
                            
                            results["models"][model_name]["normalized_score"] = norm_score
                            results["models"][model_name]["score_range"] = "1.0-5.0"
                    
                    if norm_score is not None:
                        normalized_scores.append(norm_score)
                        results["summary"]["successful_predictions"] += 1
                        rng = model_data.get("score_range", "unknown")
                        logger(f"  {model_name.upper()} score: {model_data.get('score', 0):.2f} (range: {rng})")
                    else:
                        logger(f"  {model_name.upper()} score: {model_data.get('score')} (external, normalization failed)")
                else:
                    results["summary"]["failed_predictions"] += 1
                    logger(f"  {model_name.upper()} model: FAILED (external)")
        
        for model_name in self.model_sources.keys():
            # Check if already computed (external)
            if model_name in results["models"]:
                continue

            if model_name in self.models:
                # Time the model inference
                start_time = time.time()
                score = self.predict_quality(processing_path, model_name)
                inference_time = time.time() - start_time
                
                if score is not None:
                    min_score, max_score = self.model_ranges[model_name]
                    normalized_score = (score - min_score) / (max_score - min_score)
                    normalized_scores.append(normalized_score)
                    
                    results["models"][model_name] = {
                        "score": round(score, 2),
                        "score_range": f"{min_score}-{max_score}",
                        "normalized_score": round(normalized_score, 3),
                        "inference_time_seconds": round(inference_time, 3),
                        "status": "success"
                    }
                    results["summary"]["successful_predictions"] += 1
                    logger(f"  {model_name.upper()} score: {score:.2f} (range: {min_score}-{max_score}) [{inference_time:.3f}s]")
                else:
                    results["models"][model_name] = {
                        "score": None,
                        "error": "Prediction failed",
                        "inference_time_seconds": round(inference_time, 3),
                        "status": "failed"
                    }
                    results["summary"]["failed_predictions"] += 1
                    logger(f"  {model_name.upper()} model: FAILED [{inference_time:.3f}s]")
            else:
                results["models"][model_name] = {
                    "score": None,
                    "error": "Model not loaded",
                    "status": "not_loaded"
                }
                results["summary"]["failed_predictions"] += 1
                logger(f"  {model_name.upper()} model: NOT LOADED")
        
        normalized_scores_dict = {}
        total_inference_time = 0.0
        model_times = {}
        
        for model_name, model_result in results["models"].items():
            if model_result["status"] == "success":
                normalized_scores_dict[model_name] = model_result["normalized_score"]
            # Collect inference times
            if "inference_time_seconds" in model_result:
                model_time = model_result["inference_time_seconds"]
                model_times[model_name] = model_time
                total_inference_time += model_time
        
        # Add performance summary
        if model_times:
            results["summary"]["performance"] = {
                "total_inference_time_seconds": round(total_inference_time, 3),
                "average_inference_time_seconds": round(total_inference_time / len(model_times), 3),
                "model_times": model_times
            }
        
        if normalized_scores_dict:
             weighted_scores = self.calculate_weighted_categories(normalized_scores_dict)
             results["summary"]["weighted_scores"] = weighted_scores
             
             # Calculate rating and label
             avg_score = weighted_scores["general"]
             results["summary"]["average_normalized_score"] = avg_score
             
             # Write rating to NEF files if applicable
             if write_metadata and self.is_nef_file(image_path):
                 if avg_score is not None:
                     rating = self.score_to_rating(avg_score)
                     label = self.determine_lightroom_label(normalized_scores_dict)
                     
                     success = self.write_metadata_to_nef(image_path, rating, label)
                     results["summary"]["nef_metadata"] = {
                         "rating": rating,
                         "label": label,
                         "write_success": success,
                         "score_mapping": f"{avg_score:.3f} -> {rating}/5, {label}"
                     }

        
        return results
    
    def is_already_processed(self, image_path: str, output_dir: str) -> bool:
        """Check if image has already been processed with current version and correct path."""
        image_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Default to image directory if output_dir is not specified
        if output_dir is None:
            output_dir = os.path.dirname(image_path)
            
        json_path = os.path.join(output_dir, f"{image_name}.json")
        
        if not os.path.exists(json_path):
            return False
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            
            # Check for version compatibility and missing fields
            existing_version = existing_data.get('version', 'unknown')
            
            # Versions that are compatible but might miss the thumbnail (2.3.2+)
            compatible_versions = ["2.3.2", "2.4.0", "2.5.0"]
            
            needs_patch = False
            # Check if version is compatible OR if it matches current version
            if existing_version in compatible_versions or existing_version == self.VERSION:
                if "thumbnail" not in existing_data:
                    needs_patch = True
            
            if needs_patch:
                print(f"Patching existing result for {image_name} (adding thumbnail)...")
                
                # Check if we need to convert RAW for thumbnail
                is_raw = self.is_raw_file(image_path)
                processing_path = image_path
                conversion_success = True
                
                if is_raw:
                    # Convert RAW to temp JPEG for thumbnail generation
                    # Only do this if strictly necessary to avoid overhead
                    processing_path = self.convert_raw_to_jpeg(image_path)
                    if not processing_path:
                        print(f"⚠ Failed to convert RAW for thumbnail patch: {image_path}")
                        conversion_success = False
                
                if conversion_success:
                    # Generate thumbnail
                    thumb_b64 = self.generate_thumbnail_base64(processing_path)
                    
                    # Clean up any temp files created
                    self.cleanup_temp_files()
                    
                    if thumb_b64:
                        existing_data["thumbnail"] = thumb_b64
                        existing_data["version"] = self.VERSION  # Update version
                        
                        # Save updated JSON
                        self.save_results(existing_data, json_path)
                        print(f"✓ Patched {image_name}.json with thumbnail")
                        return True
                    else:
                        print("⚠ Failed to generate thumbnail base64 data")
                else:
                    self.cleanup_temp_files()
            
            # Standard checks if no patch was performed (or if patch logic passed execution)
            # If we just patched it and returned True above, we are done.
            # If we didn't patch, check version strict
            
            if existing_version != self.VERSION:
                # If we are here, it means it's an old version that wasn't patched (incompatible)
                print(f"Version mismatch - existing: {existing_version}, current: {self.VERSION}")
                return False
            
            # Check if image_path matches current working folder
            existing_image_path = existing_data.get('image_path', '')
            # Allow some flexibility in path format (WSL vs Windows)
            # But if filenames don't match, that's an issue
            if os.path.basename(existing_image_path) != os.path.basename(image_path):
                print(f"Path mismatch - existing: {existing_image_path}, current: {image_path}")
                return False
            
            print(f"Image already processed with version {self.VERSION}: {image_path}")
            return True
                
        except Exception as e:
            print(f"Error checking existing results: {e}")
            return False
    
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
    
    def calculate_weighted_categories(self, scores: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate weighted scores with percentile-based rescaling.
        Delegates to score_normalization module when available.
        """
        if snorm is not None:
            return snorm.compute_composites(scores)

        def get_s(model):
            return scores.get(model, 0.0)

        technical = get_s('liqe')
        aesthetic = 0.55 * get_s('ava') + 0.45 * get_s('spaq')
        general = 0.45 * get_s('liqe') + 0.30 * get_s('ava') + 0.25 * get_s('spaq')

        return {
            "technical": round(technical, 3),
            "aesthetic": round(aesthetic, 3),
            "general": round(general, 3),
        }
    
    def save_results(self, results: Dict[str, any], output_path: str):
        """Save results to JSON file."""
        try:
            with open(output_path, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {output_path}")
        except Exception as e:
            print(f"Error saving results: {e}")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Run all available MUSIQ models on an image and save results to JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all_musiq_models.py --image sample.jpg
  python run_all_musiq_models.py --image /path/to/image.jpg --output-dir /path/to/output/
  python run_all_musiq_models.py --image sample.jpg --models spaq ava vila

Available Models:
  MUSIQ Models (Image Quality):
  - spaq: SPAQ dataset model (range: 0-100)
  - ava: AVA dataset model (range: 1-10) 
  - koniq: KONIQ-10K dataset model (range: 0-100)
  - paq2piq: PAQ2PIQ dataset model (range: 0-100)
  
  VILA Model (Vision-Language Aesthetics):
  - vila: VILA aesthetic assessment (range: 0-1)
        """
    )
    
    parser.add_argument('--image', required=True, help='Path to input image')
    parser.add_argument('--output-dir', help='Output directory for JSON file (default: same as image directory)')
    parser.add_argument('--models', nargs='+', 
                       choices=['spaq', 'ava', 'koniq', 'paq2piq', 'vila'],
                       help='Specific models to run (default: all models)')
    
    args = parser.parse_args()
    
    # Validate input image
    if not os.path.exists(args.image):
        print(f"Error: Image file not found: {args.image}")
        sys.exit(1)
    
    # Determine output path
    image_path = Path(args.image)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{image_path.stem}.json"
    else:
        output_path = image_path.parent / f"{image_path.stem}.json"
    
    # Initialize multi-model scorer
    scorer = MultiModelMUSIQ()
    
    # Load models
    if args.models:
        # Load specific models
        print(f"Loading specified models: {', '.join(args.models)}")
        for model_name in args.models:
            scorer.load_model(model_name)
    else:
        # Load all models
        print("Loading all available MUSIQ models...")
        load_results = scorer.load_all_models()
        
        # Check if any models loaded successfully
        if not any(load_results.values()):
            print("Error: No models loaded successfully")
            sys.exit(1)
    
    # Check if already processed with current version
    if scorer.is_already_processed(args.image, args.output_dir):
        print(f"Skipping {args.image} - already processed with version {scorer.VERSION}")
        sys.exit(0)
    
    # Run all models on the image
    results = scorer.run_all_models(args.image)
    
    # Save results
    scorer.save_results(results, str(output_path))
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Image: {results['image_name']}")
    print(f"Device: {results['device']}")
    print(f"Models loaded: {results['summary']['total_models']}")
    print(f"Successful predictions: {results['summary']['successful_predictions']}")
    print(f"Failed predictions: {results['summary']['failed_predictions']}")
    
    if results['summary']['average_normalized_score'] is not None:
        print(f"Average normalized score: {results['summary']['average_normalized_score']}")
    
    # Show weighted scoring if available
    if 'weighted_scores' in results['summary']:
        weighted = results['summary']['weighted_scores']
        print(f"Technical Score: {weighted['technical']}")
        print(f"Aesthetic Score: {weighted['aesthetic']}")
        print(f"General Score:   {weighted['general']}")
    
    if results['summary']['successful_predictions'] > 0:
        print("\nScores:")
        for model_name, model_result in results['models'].items():
            if model_result['status'] == 'success':
                print(f"  {model_name.upper()}: {model_result['score']} ({model_result['score_range']}) - Normalized: {model_result['normalized_score']}")
    
    # Clean up temporary files
    scorer.cleanup_temp_files()
    
    sys.exit(0)


if __name__ == "__main__":
    main()

