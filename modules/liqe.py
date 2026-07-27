import contextlib
import io

from PIL import Image

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from torchvision.transforms import functional as TF
except ImportError:
    pass

class LiqeScorer:
    """
    Persistent LIQE scorer class to avoid re-loading model for every image.
    """
    # Default max dimension (longest edge) before downscaling; config can override.
    DEFAULT_MAX_DIM = 518

    def __init__(self, device='cuda', max_dimension=None):
        self.device = device
        self.available = False
        self.metric = None
        self.max_dimension = int(max_dimension) if max_dimension is not None else self._load_max_dimension()
        
        if not TORCH_AVAILABLE:
            print("LIQE: PyTorch not installed. LIQE scoring will be unavailable.")
            return

        # Check torch availability
        if not torch.cuda.is_available() and self.device == 'cuda':
            print("LIQE: CUDA not available, falling back to CPU")
            self.device = 'cpu'
            
        try:
            import pyiqa
            # Suppress "Loading pretrained model..." output
            with contextlib.redirect_stdout(io.StringIO()):
                self.metric = pyiqa.create_metric('liqe', device=self.device)
            self.available = True
            print(f"LIQE model loaded on {self.device}")
        except ImportError:
            print("LIQE: pyiqa not installed. Install with 'pip install pyiqa'")
        except Exception as e:
            print(f"LIQE: Failed to load model: {e}")

    def _load_max_dimension(self):
        """Read LIQE max dimension from config (scoring.liqe_max_dimension or raw_conversion.liqe_max_dimension)."""
        try:
            from modules.config import get_config_value

            v = get_config_value("scoring.liqe_max_dimension") or get_config_value(
                "raw_conversion.liqe_max_dimension"
            )
            if v is not None:
                return max(224, min(2048, int(v)))
        except Exception:
            pass
        return self.DEFAULT_MAX_DIM

    def predict(self, image_path):
        """
        Score a single image.
        """
        if not self.available:
            return {"error": "Model not loaded", "status": "failed"}

        try:
             # Load and resize logic from original script
             # using PIL to ensure consistent loading
             img = Image.open(image_path).convert('RGB')
             
             # Resize if too large (LIQE optimization; threshold from config or default 518)
             if max(img.size) > self.max_dimension:
                ratio = self.max_dimension / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.BICUBIC)
             
             # Convert to tensor
             # We assume torchvision is available if pyiqa is available (it's a dep)
             img_tensor = TF.to_tensor(img).unsqueeze(0).to(self.device)
             
             with torch.no_grad():
                 score = self.metric(img_tensor).item()
                 
             return {
                "score": score,
                "status": "success",
                "device": self.device,
                "score_range": "1.0-5.0"
            }
            
        except Exception as e:
            # Fallback for complex failures
            try:
                # Direct file path fallback if something went wrong with PIL/Tensor
                if self.metric:
                     with torch.no_grad():
                        score = self.metric(image_path).item()
                     return {
                        "score": score,
                        "status": "success",
                        "device": self.device,
                        "note": "fallback_path",
                        "score_range": "1.0-5.0"
                    }
            except Exception:
                pass

            return {
                "error": str(e),
                "status": "failed"
            }
