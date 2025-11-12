from flask import Flask, jsonify, request
import requests
import re
import os
from datetime import datetime
from pathlib import Path

PICTURES_DIR = Path("pictures")
PICTURES_DIR.mkdir(exist_ok=True)

NINJA_API_KEY = "V00gLHAVVVI2hzOBGlyZKw==AYJdHaNxAMDY7zEI"  # לפי המטלה: מותר לשים ישירות בקוד
NINJA_URL = "https://api.api-ninjas.com/v1/animals"



app = Flask(__name__)

pet_types = {}
next_id = 1
def gen_id():
    global next_id
    new_id = str(next_id)
    next_id += 1
    return new_id

def make_empty_pet_type(type_name):
    return {
        "id": gen_id(),       # string
        "type": type_name,    # string
        "family": None,       # יתמלא מאוחר יותר
        "genus": None,        # יתמלא מאוחר יותר
        "attributes": [],     # יתמלא מאוחר יותר
        "lifespan": None,     # יתמלא מאוחר יותר
        "pets": []            # רשימת חיות תחת סוג זה
    }

def pick_attributes(ninja_obj: dict) -> list:

    ch = ninja_obj.get("characteristics") or {}
    text = ch.get("temperament") or ch.get("group_behavior") or ""
    # פירוק למילים באנגלית: אותיות/מספרים, מורידים רווחים/פסיקים וכו'
    words = re.findall(r"[A-Za-z]+", text)
    return words

def parse_lifespan(ninja_obj: dict):
    ch = ninja_obj.get("characteristics") or {}
    text = ch.get("lifespan") or ""
    nums = re.findall(r"\d+", text)
    if not nums:
        return None
    return int(min(nums, key=int))

def extract_family_genus(ninja_obj: dict):
    tax = ninja_obj.get("taxonomy") or {}
    family = tax.get("family")
    genus = tax.get("genus")
    return family, genus

def fetch_ninja_exact_type(type_name: str):

    headers = {"X-Api-Key": NINJA_API_KEY}
    params = {"name": type_name}
    resp = requests.get(NINJA_URL, headers=headers, params=params, timeout=10)
    if resp.status_code != 200:
        return None, f"API response code {resp.status_code}"
    try:
        data = resp.json() or []
    except Exception as e:
        return None, f"API response code {resp.status_code}"
    lower = type_name.strip().lower()
    for item in data:
        if isinstance(item, dict) and (item.get("name", "").strip().lower() == lower):
            return item, None
    return None, None  # 200 אבל אין התאמה מדויקת -> יטופל כ-400 במתודת ה-POST

def parse_birthdate(s):
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except Exception:
        return None
def download_picture(url, type_id, pet_name):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None

        content_type = r.headers.get("Content-Type", "")
        if content_type not in ("image/jpeg", "image/png"):
            return None

        ext = ".jpg" if content_type == "image/jpeg" else ".png"
        file_name = f"{type_id}_{pet_name}{ext}"

        with open(PICTURES_DIR / file_name, "wb") as f:
            f.write(r.content)

        return file_name

    except Exception:
        return None


# /pet-types
@app.route('/pet-types', methods=['GET'])
def get_all_pet_types():
    result = list(pet_types.values())

    args = request.args  # Query string params

    # 1) סינון לפי שדות: id/type/family/genus/lifespan
    for field in ['id', 'type', 'family', 'genus', 'lifespan']:
        if field in args:
            value = args.get(field, '')
            if field == 'lifespan':
                # השוואה מספרית; אם הערך לא מספר -> פשוט לא תמצא התאמות (ואין קוד שגיאה)
                try:
                    wanted = int(value)
                except ValueError:
                    result = []
                else:
                    result = [pt for pt in result if pt.get('lifespan') == wanted]
            else:
                wanted = (value or '').strip().lower()
                result = [
                    pt for pt in result
                    if ((pt.get(field) or '')).strip().lower() == wanted
                ]

    # 2) סינון hasAttribute=<attr> (case-insensitive)
    if 'hasAttribute' in args:
        attr = (args.get('hasAttribute') or '').strip().lower()
        result = [
            pt for pt in result
            if any((a or '').strip().lower() == attr for a in pt.get('attributes', []))
        ]

    return jsonify(result), 200

@app.route('/pet-types', methods=['POST'])
def add_pet_type():
    print("POST pet-types")
    try:
        # בדיוק כמו בשקף: בדיקת תוכן מדויקת, לא startswith
        content_type = request.headers.get('Content-Type')
        if content_type != 'application/json':
            return jsonify({"error": "Expected application/json media type"}), 415

        data = request.get_json()
        # Check if required fields are present (לנו יש שדה חובה יחיד: 'type')
        required_fields = ['type']
        if not data or not all(field in data for field in required_fields):
            return jsonify({"error": "Malformed data"}), 400

        req_type = data['type']

        # בדיקת כפילות (הוגדר במטלה כ-400 על כפילות)
        if any(pt.get("type", "").strip().lower() == req_type.strip().lower()
               for pt in pet_types.values()):
            return jsonify({"error": "Malformed data"}), 400

        # קריאה ל-Ninja
        record, api_err = fetch_ninja_exact_type(req_type)
        if api_err:
            print("Exception (Ninja):", api_err)
            return jsonify({"server error": api_err}), 500
        if record is None:
            return jsonify({"error": "Malformed data"}), 400

        # נרמול נתונים מהתשובה:
        family, genus = extract_family_genus(record)
        attributes = pick_attributes(record)
        lifespan = parse_lifespan(record)

        new_id = gen_id()
        pet_type = {
            "id": new_id,
            "type": req_type,
            "family": family,
            "genus": genus,
            "attributes": attributes,
            "lifespan": lifespan,
            "pets": []
        }
        pet_types[new_id] = pet_type
        return jsonify(pet_type), 201

    except Exception as e:
        print("Exception: ", str(e))
        return jsonify({"server error": str(e)}), 500

# /pet-types/<id>
@app.route('/pet-types/<string:id>', methods=['GET'])
def get_pet_type_by_id(id):
    pt = pet_types.get(id)
    if pt is None:
        return jsonify({"error": "Not found"}), 404  # 404
    return jsonify(pt), 200  # 200

@app.route('/pet-types/<string:id>', methods=['DELETE'])
def delete_pet_type_by_id(id):
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404
    if pet_types[id].get("pets"):
        return jsonify({"error": "Malformed data"}), 400
    del pet_types[id]
    return '', 204

# ---------- /pet-types/<id>/pets ----------
@app.route('/pet-types/<string:id>/pets', methods=['GET'])
def get_pets_by_type(id):
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404

    pets = list(pet_types[id].get("pets", []))

    gt_raw = request.args.get("birthdateGT")
    lt_raw = request.args.get("birthdateLT")
    gt_date = parse_birthdate(gt_raw) if gt_raw else None
    lt_date = parse_birthdate(lt_raw) if lt_raw else None

    def pet_date(p):
        d = p.get("birthdate")
        if not d or d == "NA":
            return None
        return parse_birthdate(d)

    if gt_date:
        pets = [p for p in pets if (pet_date(p) and pet_date(p) > gt_date)]
    if lt_date:
        pets = [p for p in pets if (pet_date(p) and pet_date(p) < lt_date)]

    return jsonify(pets), 200

@app.route('/pet-types/<string:id>/pets', methods=['POST'])
def add_pet_under_type(id):
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404

    content_type = request.headers.get('Content-Type')
    if content_type != 'application/json':
        return jsonify({"error": "Expected application/json media type"}), 415

    data = request.get_json()
    required_fields = ['name']
    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "Malformed data"}), 400

    name = data['name']
    birthdate = data.get('birthdate', "NA")
    picture_url = data.get('picture-url')

    if any((p.get('name') or '').strip().lower() == name.strip().lower()
           for p in pet_types[id].get('pets', [])):
        return jsonify({"error": "Malformed data"}), 400

    if birthdate != "NA" and parse_birthdate(birthdate) is None:
        return jsonify({"error": "Malformed data"}), 400

    picture_file = "NA"
    if picture_url:
        fn = download_picture(picture_url, id, name)
        if not fn:
            return jsonify({"error": "Malformed data"}), 400
        picture_file = fn

    pet = {
        "name": name,
        "birthdate": birthdate,
        "picture": picture_file
    }
    pet_types[id].setdefault("pets", []).append(pet)
    return jsonify(pet), 201




# ---------- /pet-types/<id>/pets/<name> ----------
@app.route('/pet-types/<string:id>/pets/<string:name>', methods=['GET'])
def get_pet_by_name(id, name):
    # מותר: 200, 404
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404
    pet = next((p for p in pet_types[id].get("pets", []) if p.get("name") == name), None)
    if pet is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(pet), 200

@app.route('/pet-types/<string:id>/pets/<string:name>', methods=['DELETE'])
def delete_pet_by_name(id, name):
    # מותר: 204, 404
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404
    pets = pet_types[id].get("pets", [])
    idx = next((i for i, p in enumerate(pets) if p.get("name") == name), None)
    if idx is None:
        return jsonify({"error": "Not found"}), 404
    # (שלב 8–9: אם יש picture ≠ "NA" — למחוק גם קובץ)
    pets.pop(idx)
    return '', 204
@app.route('/pet-types/<string:id>/pets/<string:name>', methods=['PUT'])
def update_pet_by_name(id, name):
    # מותר: 200, 400, 404, 415
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404

    content_type = request.headers.get('Content-Type')
    if content_type != 'application/json':
        return jsonify({"error": "Expected application/json media type"}), 415

    data = request.get_json()
    required_fields = ['name']  # לפי המטלה, חייב לפחות name
    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "Malformed data"}), 400

    pets = pet_types[id].get("pets", [])
    idx = next((i for i, p in enumerate(pets) if p.get("name") == name), None)
    if idx is None:
        return jsonify({"error": "Not found"}), 404

    # (שלב 8–9: טיפול 'picture-url' אם שונה; כאן מינימלי)
    updated = {
        "name": data['name'],
        "birthdate": data.get('birthdate', "NA"),
        "picture": pets[idx].get('picture', "NA")
    }
    pets[idx] = updated
    return jsonify(updated), 200


# ---------- /pictures/<file-name> ----------
@app.route('/pictures/<string:filename>', methods=['GET'])
def get_picture(filename):
    # מותר: 200 (תמונה), 404
    # (שלב 9: קריאת קובץ והחזרת image/jpeg/png; אם אין — 404)
    return jsonify({"message": f"GET picture file {filename}"}), 200





if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)