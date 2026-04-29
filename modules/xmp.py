"""
XMP Sidecar Module for Lightroom Cloud Integration

Non-destructive XMP sidecar file handler that writes star ratings and color labels
to .xmp sidecar files, which Lightroom Cloud can read when syncing.

This module NEVER modifies original RAW/JPEG files.
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from xml.etree import ElementTree as ET
from modules import utils

logger = logging.getLogger(__name__)

# XMP Namespaces
NAMESPACES = {
    'x': 'adobe:ns:meta/',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'xmp': 'http://ns.adobe.com/xap/1.0/',
    'xmpMM': 'http://ns.adobe.com/xap/1.0/mm/',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'photoshop': 'http://ns.adobe.com/photoshop/1.0/',
    'xmpDM': 'http://ns.adobe.com/xmp/1.0/DynamicMedia/',
    'MicrosoftPhoto': 'http://ns.microsoft.com/photo/1.0/',
}

# Register namespaces for clean XML output
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


def get_xmp_path(image_path: str) -> str:
    """
    Returns the XMP sidecar path for an image.
    For 'IMG_001.NEF' -> 'IMG_001.xmp'
    
    Handles path conversion for WSL: database stores Windows paths,
    but we need local (WSL) paths for file operations.
    """
    # Convert to local path (WSL or Windows depending on platform)
    local_path = utils.convert_path_to_local(image_path)
    p = Path(local_path)
    return str(p.with_suffix('.xmp'))


def xmp_exists(image_path: str) -> bool:
    """Check if XMP sidecar exists for the image."""
    return os.path.exists(get_xmp_path(image_path))


def write_image_unique_id(image_path: str, image_uuid: str) -> bool:
    """
    Write ImageUniqueID to XMP sidecar.
    
    Args:
        image_path: Path to the image file
        image_uuid: UUID string to identify the image
        
    Returns:
        True if successful
    """
    if not image_uuid:
        return False
    
    try:
        root, xmp_path = _get_or_create_xmp(image_path)
        desc = _get_description(root)
        
        # Write xmp:ImageUniqueID
        desc.set(f'{{{NAMESPACES["xmp"]}}}ImageUniqueID', image_uuid)
        
        # Add modification timestamp
        desc.set(f'{{{NAMESPACES["xmp"]}}}ModifyDate', datetime.now().isoformat())
        
        # Write file
        tree = ET.ElementTree(root)
        tree.write(xmp_path, encoding='utf-8', xml_declaration=True)
        
        logger.debug(f"Wrote ImageUniqueID {image_uuid} to {xmp_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write ImageUniqueID to XMP for {image_path}: {e}")
        return False


def write_burst_uuid(image_path: str, burst_uuid: str) -> bool:
    """
    Write BurstUUID/StackId to XMP sidecar.
    
    Uses MicrosoftPhoto:StackId for compatibility with Windows Photos
    and also writes a custom xmp:BurstUUID attribute.
    
    Args:
        image_path: Path to the image file
        burst_uuid: UUID string to identify the burst/stack
        
    Returns:
        True if successful
    """
    if not burst_uuid:
        logger.warning("Empty burst_uuid provided")
        return False
    
    try:
        root, xmp_path = _get_or_create_xmp(image_path)
        desc = _get_description(root)
        
        # Write MicrosoftPhoto:StackId (Windows Photos compatible)
        desc.set(f'{{{NAMESPACES["MicrosoftPhoto"]}}}StackId', burst_uuid)
        
        # Also write custom xmp:BurstUUID for our own use
        desc.set(f'{{{NAMESPACES["xmp"]}}}BurstUUID', burst_uuid)
        
        # Add modification timestamp
        desc.set(f'{{{NAMESPACES["xmp"]}}}ModifyDate', datetime.now().isoformat())
        
        # Write file
        tree = ET.ElementTree(root)
        tree.write(xmp_path, encoding='utf-8', xml_declaration=True)
        
        logger.debug(f"Wrote BurstUUID {burst_uuid} to {xmp_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write BurstUUID to {image_path}: {e}")
        return False


def read_burst_uuid_from_xmp(image_path: str) -> str | None:
    """
    Read BurstUUID/StackId from XMP sidecar.
    
    Returns:
        BurstUUID string if present, None otherwise
    """
    xmp_path = get_xmp_path(image_path)
    
    if not os.path.exists(xmp_path):
        return None
    
    try:
        tree = ET.parse(xmp_path)
        root = tree.getroot()
        
        desc = root.find('.//rdf:Description', NAMESPACES)
        if desc is None:
            return None
        
        # Try xmp:BurstUUID first (our custom attribute)
        burst_uuid = desc.get(f'{{{NAMESPACES["xmp"]}}}BurstUUID')
        if burst_uuid:
            return burst_uuid
        
        # Try MicrosoftPhoto:StackId
        stack_id = desc.get(f'{{{NAMESPACES["MicrosoftPhoto"]}}}StackId')
        if stack_id:
            return stack_id
        
        return None
        
    except Exception as e:
        logger.warning(f"Failed to read BurstUUID from {xmp_path}: {e}")
        return None


def read_xmp(image_path: str) -> dict:
    """
    Read existing XMP sidecar data.
    Returns dict with 'rating', 'label', 'picked' keys.
    """
    xmp_path = get_xmp_path(image_path)
    result = {'rating': None, 'label': None, 'picked': None}
    
    if not os.path.exists(xmp_path):
        return result
    
    try:
        tree = ET.parse(xmp_path)
        root = tree.getroot()
        
        # Find the Description element
        desc = root.find('.//rdf:Description', NAMESPACES)
        if desc is None:
            return result
        
        # Read rating
        rating = desc.get(f'{{{NAMESPACES["xmp"]}}}Rating')
        if rating:
            result['rating'] = int(rating)
        
        # Read label (color)
        label = desc.get(f'{{{NAMESPACES["xmp"]}}}Label')
        if label:
            result['label'] = label
            
        # Read pick flag (crs:Picked or xmp custom)
        picked = desc.get(f'{{{NAMESPACES["xmp"]}}}Picked')
        if picked:
            result['picked'] = picked.lower() == 'true'
            
    except Exception as e:
        logger.warning(f"Failed to read XMP {xmp_path}: {e}")
    
    return result


def _create_xmp_template() -> ET.Element:
    """Create a minimal XMP document structure."""
    # Root xmpmeta element
    root = ET.Element(f'{{{NAMESPACES["x"]}}}xmpmeta')
    root.set('x:xmptk', 'Vexlum Scoring')
    
    # RDF wrapper
    rdf = ET.SubElement(root, f'{{{NAMESPACES["rdf"]}}}RDF')
    
    # Description element (where all metadata goes)
    desc = ET.SubElement(rdf, f'{{{NAMESPACES["rdf"]}}}Description')
    desc.set(f'{{{NAMESPACES["rdf"]}}}about', '')
    
    return root


def _get_or_create_xmp(image_path: str) -> tuple[ET.Element, Path]:
    """
    Get existing XMP tree or create new one.
    Returns (root_element, xmp_path).
    """
    xmp_path = Path(get_xmp_path(image_path))
    
    if xmp_path.exists():
        try:
            tree = ET.parse(xmp_path)
            return tree.getroot(), xmp_path
        except Exception as e:
            logger.warning(f"Corrupted XMP, recreating: {e}")
    
    return _create_xmp_template(), xmp_path


def _get_description(root: ET.Element) -> ET.Element:
    """Get or create the rdf:Description element."""
    desc = root.find('.//rdf:Description', NAMESPACES)
    if desc is None:
        rdf = root.find('.//rdf:RDF', NAMESPACES)
        if rdf is None:
            rdf = ET.SubElement(root, f'{{{NAMESPACES["rdf"]}}}RDF')
        desc = ET.SubElement(rdf, f'{{{NAMESPACES["rdf"]}}}Description')
        desc.set(f'{{{NAMESPACES["rdf"]}}}about', '')
    return desc


def write_rating(image_path: str, rating: int) -> bool:
    """
    Write star rating (0-5) to XMP sidecar.
    Creates sidecar if it doesn't exist.
    """
    if not 0 <= rating <= 5:
        logger.error(f"Invalid rating {rating}, must be 0-5")
        return False
    
    try:
        root, xmp_path = _get_or_create_xmp(image_path)
        desc = _get_description(root)
        
        # Set rating attribute
        desc.set(f'{{{NAMESPACES["xmp"]}}}Rating', str(rating))
        
        # Write file
        tree = ET.ElementTree(root)
        tree.write(xmp_path, encoding='utf-8', xml_declaration=True)
        
        logger.info(f"Wrote rating {rating} to {xmp_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write rating to {image_path}: {e}")
        return False


def write_label(image_path: str, label: str) -> bool:
    """
    Write color label to XMP sidecar.
    Valid labels: Red, Yellow, Green, Blue, Purple, None
    """
    valid_labels = ['Red', 'Yellow', 'Green', 'Blue', 'Purple', 'None', '']
    if label not in valid_labels:
        logger.error(f"Invalid label '{label}', must be one of {valid_labels}")
        return False
    
    try:
        root, xmp_path = _get_or_create_xmp(image_path)
        desc = _get_description(root)
        
        # Set or remove label
        if label and label != 'None':
            desc.set(f'{{{NAMESPACES["xmp"]}}}Label', label)
        else:
            # Remove label attribute if exists
            key = f'{{{NAMESPACES["xmp"]}}}Label'
            if key in desc.attrib:
                del desc.attrib[key]
        
        # Write file
        tree = ET.ElementTree(root)
        tree.write(xmp_path, encoding='utf-8', xml_declaration=True)
        
        logger.info(f"Wrote label '{label}' to {xmp_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write label to {image_path}: {e}")
        return False


def write_pick_flag(image_path: str, is_picked: bool) -> bool:
    """
    [DEPRECATED] Write pick/reject flag to XMP sidecar using old schema.
    
    This function uses the legacy xmp:Picked and xmp:Label approach.
    Use write_pick_reject_flag() instead for Lightroom-compatible flags.
    
    For Lightroom: picked images get Rating >= 1 if unrated.
    This also sets a custom Picked attribute.
    
    .. deprecated:: Use write_pick_reject_flag() instead
    """
    import warnings
    warnings.warn(
        "write_pick_flag() is deprecated. Use write_pick_reject_flag() instead for Lightroom-compatible flags.",
        DeprecationWarning,
        stacklevel=2
    )
    logger.warning(f"write_pick_flag() is deprecated. Called for {image_path}")
    
    try:
        root, xmp_path = _get_or_create_xmp(image_path)
        desc = _get_description(root)
        
        # Set custom picked flag
        desc.set(f'{{{NAMESPACES["xmp"]}}}Picked', str(is_picked).lower())
        
        # Lightroom Cloud convention: picked = Green label, rejected = Red label
        # (But only if user hasn't set a label already)
        existing_label = desc.get(f'{{{NAMESPACES["xmp"]}}}Label')
        if not existing_label:
            if is_picked:
                desc.set(f'{{{NAMESPACES["xmp"]}}}Label', 'Green')
            else:
                desc.set(f'{{{NAMESPACES["xmp"]}}}Label', 'Red')
        
        # Write file
        tree = ET.ElementTree(root)
        tree.write(xmp_path, encoding='utf-8', xml_declaration=True)
        
        logger.info(f"Wrote pick={is_picked} to {xmp_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write pick flag to {image_path}: {e}")
        return False


def write_pick_reject_flag(image_path: str, pick_status: int) -> bool:
    """
    Write Lightroom-compatible Pick/Reject flag to XMP sidecar.
    
    Args:
        image_path: Path to the image file
        pick_status: 1 = Picked, -1 = Rejected, 0 = Unflagged
    
    Uses xmpDM namespace properties:
        - xmpDM:pick: 1 (picked), -1 (rejected), 0 (unflagged)
        - xmpDM:good: true (picked), false (rejected)
    
    These are the standard Lightroom Classic 13.2+ flag properties.
    """
    if pick_status not in (1, -1, 0):
        logger.error(f"Invalid pick_status {pick_status}, must be 1, -1, or 0")
        return False
    
    try:
        root, xmp_path = _get_or_create_xmp(image_path)
        desc = _get_description(root)
        
        # Write xmpDM:pick (1, -1, or 0)
        desc.set(f'{{{NAMESPACES["xmpDM"]}}}pick', str(pick_status))
        
        # Write xmpDM:good (true/false) - only for picked/rejected, not unflagged
        if pick_status == 1:
            desc.set(f'{{{NAMESPACES["xmpDM"]}}}good', 'true')
        elif pick_status == -1:
            desc.set(f'{{{NAMESPACES["xmpDM"]}}}good', 'false')
        else:
            # Remove good attribute if unflagging
            good_key = f'{{{NAMESPACES["xmpDM"]}}}good'
            if good_key in desc.attrib:
                del desc.attrib[good_key]
        
        # Add modification timestamp
        desc.set(f'{{{NAMESPACES["xmp"]}}}ModifyDate', datetime.now().isoformat())
        
        # Write file
        tree = ET.ElementTree(root)
        tree.write(xmp_path, encoding='utf-8', xml_declaration=True)
        
        status_name = {1: 'Picked', -1: 'Rejected', 0: 'Unflagged'}[pick_status]
        logger.info(f"Wrote pick_status={status_name} to {xmp_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write pick/reject flag to {image_path}: {e}")
        return False


def read_pick_reject_flag(image_path: str) -> int:
    """
    Read Lightroom Pick/Reject flag from XMP sidecar.
    
    Returns:
        1 = Picked, -1 = Rejected, 0 = Unflagged/Not set
    """
    xmp_path = get_xmp_path(image_path)
    
    if not os.path.exists(xmp_path):
        return 0
    
    try:
        tree = ET.parse(xmp_path)
        root = tree.getroot()
        
        desc = root.find('.//rdf:Description', NAMESPACES)
        if desc is None:
            return 0
        
        # Read xmpDM:pick
        pick = desc.get(f'{{{NAMESPACES["xmpDM"]}}}pick')
        if pick:
            return int(pick)
        
        return 0
        
    except Exception as e:
        logger.warning(f"Failed to read pick/reject flag from {xmp_path}: {e}")
        return 0


def read_xmp_full(image_path: str) -> dict:
    """
    Read full XMP sidecar data for IMAGE_XMP cache.
    
    Returns dict with keys: rating, label, pick_status, burst_uuid, stack_id,
    keywords, title, description, create_date, modify_date.
    """
    xmp_path = get_xmp_path(image_path)
    result = {
        'rating': None,
        'label': None,
        'pick_status': 0,
        'burst_uuid': None,
        'stack_id': None,
        'keywords': None,
        'title': None,
        'description': None,
        'create_date': None,
        'modify_date': None,
    }
    
    if not os.path.exists(xmp_path):
        return result
    
    try:
        tree = ET.parse(xmp_path)
        root = tree.getroot()
        
        desc = root.find('.//rdf:Description', NAMESPACES)
        if desc is None:
            return result
        
        # Attributes
        rating = desc.get(f'{{{NAMESPACES["xmp"]}}}Rating')
        if rating:
            try:
                result['rating'] = int(rating)
            except ValueError:
                pass
        
        label = desc.get(f'{{{NAMESPACES["xmp"]}}}Label')
        if label:
            result['label'] = label
        
        pick = desc.get(f'{{{NAMESPACES["xmpDM"]}}}pick')
        if pick:
            try:
                result['pick_status'] = int(pick)
            except ValueError:
                pass
        
        burst_uuid = desc.get(f'{{{NAMESPACES["xmp"]}}}BurstUUID')
        if burst_uuid:
            result['burst_uuid'] = burst_uuid
        
        stack_id = desc.get(f'{{{NAMESPACES["MicrosoftPhoto"]}}}StackId')
        if stack_id:
            result['stack_id'] = stack_id
        
        title = desc.get(f'{{{NAMESPACES["xmp"]}}}Title')
        if title:
            result['title'] = title
        
        description = desc.get(f'{{{NAMESPACES["xmp"]}}}Description')
        if description:
            result['description'] = description
        
        create_date = desc.get(f'{{{NAMESPACES["xmp"]}}}CreateDate')
        if create_date:
            result['create_date'] = create_date
        if not result['create_date']:
            ps_created = desc.get(f'{{{NAMESPACES["photoshop"]}}}DateCreated')
            if ps_created:
                result['create_date'] = ps_created

        modify_date = desc.get(f'{{{NAMESPACES["xmp"]}}}ModifyDate')
        if modify_date:
            result['modify_date'] = modify_date
        
        # dc:subject (rdf:Bag with rdf:li)
        dc_ns = NAMESPACES['dc']
        subject = desc.find(f'.//{{{dc_ns}}}subject')
        if subject is not None:
            li_elems = subject.findall('.//rdf:li', NAMESPACES)
            if not li_elems:
                li_elems = subject.findall('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li')
            if li_elems:
                result['keywords'] = [li.text.strip() for li in li_elems if li.text and li.text.strip()]
        
        # dc:title / dc:description (rdf:Alt with rdf:li) - fallback if not in attributes
        if not result['title']:
            title_elem = desc.find(f'.//{{{dc_ns}}}title')
            if title_elem is not None:
                li = title_elem.find('.//rdf:li', NAMESPACES) or title_elem.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li')
                if li is not None and li.text:
                    result['title'] = li.text.strip()
        
        if not result['description']:
            desc_elem = desc.find(f'.//{{{dc_ns}}}description')
            if desc_elem is not None:
                li = desc_elem.find('.//rdf:li', NAMESPACES) or desc_elem.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li')
                if li is not None and li.text:
                    result['description'] = li.text.strip()
        
    except Exception as e:
        logger.warning(f"Failed to read XMP full {xmp_path}: {e}")
    
    return result


def extract_and_upsert_xmp(image_path: str, image_id: int) -> bool:
    """
    Read XMP sidecar and upsert into IMAGE_XMP table.
    
    Returns True if XMP sidecar existed and upsert succeeded.
    """
    from modules import db
    
    if not xmp_exists(image_path):
        return False
    data = read_xmp_full(image_path)
    return db.upsert_image_xmp(image_id, data)


def write_culling_results(image_path: str, rating: int = None, label: str = None, 
                          is_picked: bool = None) -> bool:
    """
    Write all culling results to XMP in a single operation.
    Only writes non-None values.
    """
    try:
        root, xmp_path = _get_or_create_xmp(image_path)
        desc = _get_description(root)
        
        if rating is not None and 0 <= rating <= 5:
            desc.set(f'{{{NAMESPACES["xmp"]}}}Rating', str(rating))
        
        if label is not None:
            if label and label != 'None':
                desc.set(f'{{{NAMESPACES["xmp"]}}}Label', label)
        
        if is_picked is not None:
            desc.set(f'{{{NAMESPACES["xmp"]}}}Picked', str(is_picked).lower())
        
        # Add modification timestamp
        desc.set(f'{{{NAMESPACES["xmp"]}}}ModifyDate', 
                datetime.now().isoformat())
        
        # Write file
        tree = ET.ElementTree(root)
        tree.write(xmp_path, encoding='utf-8', xml_declaration=True)
        
        logger.info(f"Wrote culling results to {xmp_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to write culling results to {image_path}: {e}")
        return False


def delete_xmp(image_path: str) -> bool:
    """
    Delete XMP sidecar file (if user wants to remove culling decisions).
    """
    xmp_path = get_xmp_path(image_path)
    
    if os.path.exists(xmp_path):
        try:
            os.remove(xmp_path)
            logger.info(f"Deleted XMP sidecar: {xmp_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {xmp_path}: {e}")
            return False
    
    return True  # Nothing to delete


# =============================================================================
# Unified Metadata Write Functions
# =============================================================================

def write_metadata_unified(image_path: str, 
                           rating: int = None, 
                           label: str = None,
                           keywords: list = None,
                           title: str = None,
                           description: str = None,
                           is_picked: bool = None,
                           use_sidecar: bool = True,
                           use_embedded: bool = False) -> bool:
    """
    Unified metadata write function.
    
    Can write to XMP sidecar (non-destructive) and/or embedded EXIF/XMP.
    This provides a single entry point for all metadata operations.
    
    Args:
        image_path: Path to the image file
        rating: Star rating (0-5)
        label: Color label (Red, Yellow, Green, Blue, Purple, None)
        keywords: List of keyword strings
        title: Image title
        description: Image description/caption
        is_picked: Pick/reject flag for culling
        use_sidecar: Write to .xmp sidecar file (default: True)
        use_embedded: Write to embedded EXIF/XMP in file (default: False)
    
    Returns:
        True if at least one write succeeded
    """
    # Validate label against known values
    VALID_LABELS = {'Red', 'Yellow', 'Green', 'Blue', 'Purple', 'None', '', None}
    if label not in VALID_LABELS:
        logger.warning("Invalid label value '%s', ignoring", label)
        label = None

    success = False

    # 1. Write to XMP sidecar (preferred for non-destructive workflow)
    if use_sidecar:
        try:
            root, xmp_path = _get_or_create_xmp(image_path)
            desc = _get_description(root)
            
            if rating is not None and 0 <= rating <= 5:
                desc.set(f'{{{NAMESPACES["xmp"]}}}Rating', str(rating))
            
            if label is not None:
                if label and label != 'None':
                    desc.set(f'{{{NAMESPACES["xmp"]}}}Label', label)
                else:
                    key = f'{{{NAMESPACES["xmp"]}}}Label'
                    if key in desc.attrib:
                        del desc.attrib[key]
            
            if is_picked is not None:
                desc.set(f'{{{NAMESPACES["xmp"]}}}Picked', str(is_picked).lower())
            
            # Keywords as dc:subject (Dublin Core)
            if keywords:
                # Add dc namespace if needed
                dc_ns = 'http://purl.org/dc/elements/1.1/'
                ET.register_namespace('dc', dc_ns)
                
                # Remove existing subjects
                existing_subject = desc.find(f'{{{dc_ns}}}subject')
                if existing_subject is not None:
                    desc.remove(existing_subject)
                
                # Add new subjects as RDF Bag
                subject = ET.SubElement(desc, f'{{{dc_ns}}}subject')
                bag = ET.SubElement(subject, f'{{{NAMESPACES["rdf"]}}}Bag')
                for kw in keywords:
                    li = ET.SubElement(bag, f'{{{NAMESPACES["rdf"]}}}li')
                    li.text = kw.strip()
            
            if title:
                desc.set(f'{{{NAMESPACES["xmp"]}}}Title', title)
                # Also add dc:title
                dc_ns = 'http://purl.org/dc/elements/1.1/'
                existing_title = desc.find(f'{{{dc_ns}}}title')
                if existing_title is not None:
                    desc.remove(existing_title)
                title_elem = ET.SubElement(desc, f'{{{dc_ns}}}title')
                alt = ET.SubElement(title_elem, f'{{{NAMESPACES["rdf"]}}}Alt')
                li = ET.SubElement(alt, f'{{{NAMESPACES["rdf"]}}}li')
                li.set('{http://www.w3.org/XML/1998/namespace}lang', 'x-default')
                li.text = title
            
            if description:
                desc.set(f'{{{NAMESPACES["xmp"]}}}Description', description)
                # Also add dc:description
                dc_ns = 'http://purl.org/dc/elements/1.1/'
                existing_desc = desc.find(f'{{{dc_ns}}}description')
                if existing_desc is not None:
                    desc.remove(existing_desc)
                desc_elem = ET.SubElement(desc, f'{{{dc_ns}}}description')
                alt = ET.SubElement(desc_elem, f'{{{NAMESPACES["rdf"]}}}Alt')
                li = ET.SubElement(alt, f'{{{NAMESPACES["rdf"]}}}li')
                li.set('{http://www.w3.org/XML/1998/namespace}lang', 'x-default')
                li.text = description
            
            # Add modification timestamp
            desc.set(f'{{{NAMESPACES["xmp"]}}}ModifyDate', datetime.now().isoformat())
            
            # Write file
            tree = ET.ElementTree(root)
            tree.write(xmp_path, encoding='utf-8', xml_declaration=True)
            
            logger.info(f"Wrote metadata to XMP sidecar: {xmp_path}")
            success = True
            
        except Exception as e:
            logger.error(f"Failed to write XMP sidecar for {image_path}: {e}")
    
    # 2. Write to embedded EXIF/XMP via exiftool (optional)
    if use_embedded:
        try:
            embedded_success = _write_metadata_embedded(
                image_path, rating, label, keywords, title, description
            )
            if embedded_success:
                success = True
        except Exception as e:
            logger.error(f"Failed to write embedded metadata for {image_path}: {e}")
    
    return success


def _write_metadata_embedded(image_path: str, 
                              rating: int = None, 
                              label: str = None,
                              keywords: list = None,
                              title: str = None,
                              description: str = None) -> bool:
    """
    Write metadata to embedded EXIF/IPTC/XMP using exiftool.
    This modifies the original file.
    """
    import subprocess
    
    # Convert to local path
    local_path = utils.convert_path_to_local(image_path)
    
    if not os.path.exists(local_path):
        logger.error(f"File not found: {local_path}")
        return False
    
    cmd = ['exiftool', '-overwrite_original', '-sep', ',']
    
    # Build command arguments
    if rating is not None and 0 <= rating <= 5:
        cmd.append(f'-Rating={rating}')
        cmd.append(f'-XMP:Rating={rating}')
    
    if label:
        cmd.append(f'-Label={label}')
        cmd.append(f'-XMP:Label={label}')
    
    if keywords:
        kw_str = ",".join(keywords)
        cmd.append(f'-Subject={kw_str}')
        cmd.append(f'-Keywords={kw_str}')
        cmd.append(f'-XMP:Subject={kw_str}')
    
    if title:
        cmd.append(f'-Title={title}')
        cmd.append(f'-XMP:Title={title}')
        cmd.append(f'-XPTitle={title}')
    
    if description:
        cmd.append(f'-Description={description}')
        cmd.append(f'-ImageDescription={description}')
        cmd.append(f'-XMP:Description={description}')
        cmd.append(f'-XPComment={description}')
        cmd.append(f'-IPTC:Caption-Abstract={description}')
    
    # Only run if we have something to write
    if len(cmd) <= 3:
        logger.debug("No metadata to write")
        return True
    
    cmd.append(local_path)
    
    try:
        from modules.exif_extractor import get_exiftool_timeout_seconds

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=get_exiftool_timeout_seconds(write=True)
        )
        if result.returncode == 0:
            logger.info(f"Wrote embedded metadata to {local_path}")
            return True
        else:
            logger.warning(f"exiftool failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        logger.error(f"exiftool timeout for {local_path}")
        return False
    except FileNotFoundError:
        logger.error("exiftool not found in PATH")
        return False
    except Exception as e:
        logger.error(f"Embedded metadata write failed: {e}")
        return False


def write_gps_and_location_to_files(
    image_path: str,
    lat: float,
    lon: float,
    *,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    location_label: str | None = None,
    write_embedded: bool = True,
    write_sidecar: bool = True,
) -> bool:
    """
    Write GPS and optional IPTC-style location tags using exiftool.
    Skips sidecar if the .xmp file does not exist (does not create it).
    """
    import subprocess

    from modules.exif_extractor import get_exiftool_path, get_exiftool_timeout_seconds

    exiftool = get_exiftool_path()
    if not exiftool:
        logger.error("exiftool not found in PATH for GPS/location write")
        return False

    local_path = utils.convert_path_to_local(image_path)
    if not local_path or not os.path.exists(local_path):
        logger.error("File not found for GPS/location write: %s", image_path)
        return False

    def _args_for_target(target: str) -> list:
        cmd = [exiftool, "-overwrite_original", "-P", "-m"]
        gps_lat = abs(float(lat))
        gps_lat_ref = "N" if float(lat) >= 0 else "S"
        gps_lon = abs(float(lon))
        gps_lon_ref = "E" if float(lon) >= 0 else "W"
        cmd.append(f"-GPS:GPSLatitude={gps_lat}")
        cmd.append(f"-GPS:GPSLatitudeRef={gps_lat_ref}")
        cmd.append(f"-GPS:GPSLongitude={gps_lon}")
        cmd.append(f"-GPS:GPSLongitudeRef={gps_lon_ref}")
        if city:
            cmd.append(f"-City={city}")
        if state:
            cmd.append(f"-State={state}")
        if country:
            cmd.append(f"-Country={country}")
        if location_label:
            cmd.append(f"-Location={location_label}")
        cmd.append(target)
        return cmd

    success = False
    timeout = get_exiftool_timeout_seconds(write=True)
    if write_embedded:
        try:
            result = subprocess.run(
                _args_for_target(local_path),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                success = True
                logger.info("Wrote GPS/location to embedded metadata: %s", local_path)
            else:
                logger.warning("exiftool embedded GPS/location: %s", result.stderr)
        except subprocess.TimeoutExpired:
            logger.error("exiftool timeout writing GPS to %s", local_path)
        except Exception as e:
            logger.error("exiftool embedded GPS/location failed: %s", e)
    if write_sidecar:
        xmp_path = get_xmp_path(image_path)
        if os.path.exists(xmp_path):
            try:
                result = subprocess.run(
                    _args_for_target(xmp_path),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if result.returncode == 0:
                    success = True
                    logger.info("Wrote GPS/location to XMP sidecar: %s", xmp_path)
                else:
                    logger.warning("exiftool XMP GPS/location: %s", result.stderr)
            except subprocess.TimeoutExpired:
                logger.error("exiftool timeout writing GPS to XMP %s", xmp_path)
            except Exception as e:
                logger.error("exiftool XMP GPS/location failed: %s", e)
        else:
            logger.debug("No XMP sidecar for GPS write: %s", xmp_path)
    return success


def sync_xmp_to_db(image_path: str) -> dict:
    """
    Read XMP sidecar and return data that can be used to update database.
    Useful for importing Lightroom edits back into the scoring database.
    
    Returns dict with rating, label, picked suitable for db.update_image_metadata()
    """
    return read_xmp(image_path)