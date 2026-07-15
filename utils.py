import re


def normalize_phone(phone: str) -> str:
    """Strip everything except digits from a phone number for consistent matching."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def clean_html(raw_html: str) -> str:
    """Strip HTML tags from text (e.g. WooCommerce descriptions)."""
    if not raw_html:
        return ""
    return re.sub(r"<[^<]+?>", "", raw_html).strip()


def parse_height(height_str: str) -> float | None:
    """
    Parse height string and return height in inches.
    Supported formats:
    - Feet and inches: 5'6", 5'6, 5-6, 5.6, 5 feet 6 inches, 5 ft 6
    - Centimeters: 170 cm, 170cm, 170
    """
    h_clean = height_str.lower().strip()
    
    # 1. Match centimeters (e.g. 170 cm, 170cm, 170)
    cm_match = re.search(r"\b(\d{3})\s*(?:cm|centimeters)?\b", h_clean)
    if cm_match:
        cm_val = float(cm_match.group(1))
        if 120 <= cm_val <= 250:
            return cm_val / 2.54
            
    cm_decimal_match = re.search(r"\b(\d{3}\.\d+)\s*(?:cm|centimeters)?\b", h_clean)
    if cm_decimal_match:
        cm_val = float(cm_decimal_match.group(1))
        if 120 <= cm_val <= 250:
            return cm_val / 2.54

    # 2. Match feet and inches
    ft_in_match = re.search(r"(\d+)\s*(?:feet|foot|ft|'|’|′)\s*(\d+)?\s*(?:inches|inch|in|\"|”|″|'')?", h_clean)
    if ft_in_match:
        feet = int(ft_in_match.group(1))
        inches = int(ft_in_match.group(2)) if ft_in_match.group(2) else 0
        if 3 <= feet <= 8:
            return feet * 12 + inches

    dash_match = re.search(r"\b([3-8])[-–—_]([0-9]|1[0-1])\b", h_clean)
    if dash_match:
        feet = int(dash_match.group(1))
        inches = int(dash_match.group(2))
        return feet * 12 + inches

    dot_match = re.search(r"\b([3-8])[.,]([0-9]|1[0-1])\b", h_clean)
    if dot_match:
        feet = int(dot_match.group(1))
        inches = int(dot_match.group(2))
        return feet * 12 + inches

    single_num = re.search(r"\b([3-8])\b", h_clean)
    if single_num:
        feet = int(single_num.group(1))
        return feet * 12

    float_match = re.search(r"(\d+(?:\.\d+)?)", h_clean)
    if float_match:
        val = float(float_match.group(1))
        if 120 <= val <= 250:
            return val / 2.54
        if 3.0 <= val <= 8.0:
            return val * 12

    return None


def parse_weight(weight_str: str) -> float | None:
    """
    Parse weight string and return weight in kg.
    Supported formats:
    - 65 kg, 65kg, 65, 65.5 kgs
    - 140 lbs, 140lbs, 140 pounds
    """
    w_clean = weight_str.lower().strip()
    
    match = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kgs|kilogram|kilograms|lbs|lb|pound|pounds)?", w_clean)
    if not match:
        return None
        
    val = float(match.group(1))
    unit = match.group(2)
    
    if unit in ["lbs", "lb", "pound", "pounds"]:
        return val / 2.20462
        
    if not unit:
        if val > 120:
            return val / 2.20462
            
    return val


def recommend_size(height_inches: float, weight_kg: float) -> dict:
    """
    Determine clothing size recommendation based on height and weight.
    Size chart from CRM_AGENT_RULES.md:
    - Height 5'2"-5'5" (62-65 in), Weight 50-60 kg: S (Small, Chest: 38")
    - Height 5'5"-5'7" (65-67 in), Weight 60-70 kg: M (Medium, Chest: 40")
    - Height 5'7"-5'10" (67-70 in), Weight 70-80 kg: L (Large, Chest: 42")
    - Height 5'10"-6'0" (70-72 in), Weight 80-90 kg: XL (Extra Large, Chest: 44")
    - Height 6'0"+ (72+ in), Weight 90+ kg: XXL (Double Extra Large, Chest: 46")
    """
    if height_inches < 62:
        h_idx = 0
    elif height_inches < 65:
        h_idx = 0
    elif height_inches < 67:
        h_idx = 1
    elif height_inches < 70:
        h_idx = 2
    elif height_inches < 72:
        h_idx = 3
    else:
        h_idx = 4
        
    if weight_kg < 50:
        w_idx = 0
    elif weight_kg < 60:
        w_idx = 0
    elif weight_kg < 70:
        w_idx = 1
    elif weight_kg < 80:
        w_idx = 2
    elif weight_kg < 90:
        w_idx = 3
    else:
        w_idx = 4

    sizes = [
        {"size": "S", "chest": "38\"", "name": "Small"},
        {"size": "M", "chest": "40\"", "name": "Medium"},
        {"size": "L", "chest": "42\"", "name": "Large"},
        {"size": "XL", "chest": "44\"", "name": "Extra Large"},
        {"size": "XXL", "chest": "46\"", "name": "Double Extra Large"}
    ]
    
    if h_idx == w_idx:
        rec = sizes[h_idx]
        return {
            "size": rec["size"],
            "chest": rec["chest"],
            "confidence": "High",
            "fit_notes": f"Perfect fit! Both your height and weight align with size *{rec['size']}* (Chest: {rec['chest']})."
        }
    else:
        rec_idx = max(h_idx, w_idx)
        smaller_idx = min(h_idx, w_idx)
        
        rec = sizes[rec_idx]
        small_rec = sizes[smaller_idx]
        
        if abs(h_idx - w_idx) == 1:
            return {
                "size": rec["size"],
                "chest": rec["chest"],
                "confidence": "Medium",
                "fit_notes": f"Your height suggests size *{small_rec['size']}* and weight suggests size *{rec['size']}* (or vice versa). We recommend size *{rec['size']}* (Chest: {rec['chest']}) for a comfortable, regular fit. You can choose *{small_rec['size']}* if you prefer a tighter, slim fit."
            }
        else:
            avg_idx = (h_idx + w_idx) // 2
            avg_rec = sizes[avg_idx]
            return {
                "size": avg_rec["size"],
                "chest": avg_rec["chest"],
                "confidence": "Medium",
                "fit_notes": f"There is a significant difference between your height and weight proportions. We recommend size *{avg_rec['size']}* (Chest: {avg_rec['chest']}) as a balanced compromise. If you prefer a loose fit, choose *{rec['size']}*."
            }
