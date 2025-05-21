from image_metadata_conversational_assistant.store.session_store import SessionStore
import imagehash
from PIL import Image
import json

def detect_duplicate_image(session_id: str, image_id: str, image_path: str, threshold: int = 5):
    """
    Computes a perceptual hash for the uploaded image and compares it with hashes of images already in the session.
    Returns a dict with duplicate info and stores the hash if not already present.
    """
    store = SessionStore()
    # Compute perceptual hash for the new image
    try:
        with Image.open(image_path) as img:
            img_hash = str(imagehash.phash(img))
    except Exception as e:
        return {"success": False, "error": f"Failed to compute hash: {e}"}
    # Compare with existing hashes in the session
    all_metadata = store.get_all_metadata(session_id)
    duplicates = []
    for other_id in all_metadata.keys():
        if other_id == image_id:
            continue
        other_hash = store.get_value(session_id, f"hash_{other_id}")
        if other_hash:
            try:
                dist = imagehash.hex_to_hash(img_hash) - imagehash.hex_to_hash(other_hash)
                if dist <= threshold:
                    duplicates.append({"image_id": other_id, "distance": dist})
            except Exception:
                continue
    # Only store the hash if not a duplicate
    if not duplicates:
        try:
            store.set_value(session_id, f"hash_{image_id}", img_hash)
        except Exception as e:
            return {"success": False, "error": f"Failed to store hash: {e}"}
    return {
        "success": True,
        "image_id": image_id,
        "duplicates": duplicates,
        "hash": img_hash
    }
