from flask import Flask, jsonify, request, send_file
import requests
import re
from datetime import datetime
from pathlib import Path

PICTURES_DIR = Path("pictures")
PICTURES_DIR.mkdir(exist_ok=True)

NINJA_API_KEY = "V00gLHAVVVI2hzOBGlyZKw==AYJdHaNxAMDY7zEI"  # לפי המטלה: מותר לשים ישירות בקוד
NINJA_URL = "https://api.api-ninjas.com/v1/animals"

prev_url_by_pet = {}

app = Flask(__name__)

pet_types = {}
next_id = 1
def gen_id():
    global next_id
    new_id = str(next_id)
    next_id += 1
    return new_id

def pick_attributes(ninja_obj: dict) -> list:

    ch = ninja_obj.get("characteristics") or {}
    text = ch.get("temperament") or ch.get("group_behavior") or ""
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

def find_pet_index(pets_list, target_name: str):
    low = target_name.strip().lower()
    for i, p in enumerate(pets_list):
        if str(p.get("name", "")).strip().lower() == low:
            return i
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

    public_result = []
    for pt in result:
        public_pt = dict(pt)
        public_pt["pets"] = [p.get("name") for p in pt.get("pets", [])]
        public_result.append(public_pt)

    return jsonify(public_result), 200

@app.route('/pet-types', methods=['POST'])
def add_pet_type():
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

    public_pt = dict(pt)
    public_pt["pets"] = [p.get("name") for p in pt.get("pets", [])]
    return jsonify(public_pt), 200

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

    # כפילות שם בתוך אותו type (case-insensitive)
    if any((p.get('name') or '').strip().lower() == name.strip().lower()
           for p in pet_types[id].get('pets', [])):
        return jsonify({"error": "Malformed data"}), 400

    # ולידציית תאריך אם סופק
    if birthdate != "NA" and parse_birthdate(birthdate) is None:
        return jsonify({"error": "Malformed data"}), 400

    # תמונה (אופציונלי)
    picture_file = "NA"
    if picture_url:
        fn = download_picture(picture_url, id, name)
        if not fn:
            return jsonify({"error": "Malformed data"}), 400
        picture_file = fn
        # נשמור את ה-URL האחרון לחיה הזו (לבדיקת PUT)
        prev_url_by_pet[(id, name)] = picture_url

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
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404

    pets = pet_types[id].get("pets", [])
    idx = find_pet_index(pets, name)
    if idx is None:
        return jsonify({"error": "Not found"}), 404

    return jsonify(pets[idx]), 200

@app.route('/pet-types/<string:id>/pets/<string:name>', methods=['DELETE'])
def delete_pet_by_name(id, name):
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404

    pets = pet_types[id].get("pets", [])
    idx = find_pet_index(pets, name)
    if idx is None:
        return jsonify({"error": "Not found"}), 404

    pic = pets[idx].get("picture", "NA")
    if pic and pic != "NA":
        try:
            (PICTURES_DIR / pic).unlink(missing_ok=True)
        except Exception:
            pass

    pets.pop(idx)

    prev_url_by_pet.pop((id, name), None)
    return '', 204

@app.route('/pet-types/<string:id>/pets/<string:name>', methods=['PUT'])
def update_pet_by_name(id, name):
    if id not in pet_types:
        return jsonify({"error": "Not found"}), 404

    content_type = request.headers.get('Content-Type')
    if content_type != 'application/json':
        return jsonify({"error": "Expected application/json media type"}), 415

    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "Malformed data"}), 400

    pets = pet_types[id].get("pets", [])
    idx = find_pet_index(pets, name)
    if idx is None:
        return jsonify({"error": "Not found"}), 404

    current = pets[idx]
    new_name = data['name']
    new_birthdate = data.get('birthdate', current.get('birthdate', "NA"))
    if new_birthdate != "NA" and parse_birthdate(new_birthdate) is None:
        return jsonify({"error": "Malformed data"}), 400

    new_picture = "NA"

    if 'picture-url' in data:
        url = data['picture-url']
        # האם זה אותו URL כמו האחרון ששמרנו לחיה הזו?
        last_key_old_name = (id, current.get('name'))
        last_url = prev_url_by_pet.get(last_key_old_name)

        if last_url and str(last_url).strip() == str(url).strip():
            new_picture = current.get('picture', "NA")

        else:
            # URL חדש: ננסה להוריד ולשמור
            fn = download_picture(url, id, new_name)
            if not fn:
                return jsonify({"error": "Malformed data"}), 400
            new_picture = fn
            prev_url_by_pet[(id, new_name)] = url

    # עדכון הרשומה
    updated = {
        "name": new_name,
        "birthdate": new_birthdate,
        "picture": new_picture
    }
    pets[idx] = updated

    # אם השם השתנה, ננקה את המפתח הישן במיפוי ה-URL
    if new_name != name:
        prev_url_by_pet.pop((id, name), None)

    return jsonify(updated), 200


# ---------- /pictures/<file-name> ----------

@app.route('/pictures/<string:filename>', methods=['GET'])
def get_picture(filename):
    # לפי המטלה: מחזירים את הקובץ עצמו (200) או 404 אם לא קיים.
    file_path = PICTURES_DIR / filename
    if not file_path.is_file():
        return jsonify({"error": "Not found"}), 404  # לפי ההוראות

    lower = filename.lower()
    if lower.endswith('.jpg') or lower.endswith('.jpeg'):
        mimetype = 'image/jpeg'
    elif lower.endswith('.png'):
        mimetype = 'image/png'
    else:
        # המטלה מגבילה לקבצי jpg/png בלבד
        return jsonify({"error": "Not found"}), 404

    # מחזירים גם את הקובץ וגם סטטוס 200, בדיוק לפי המטלה
    return send_file(file_path, mimetype=mimetype), 200







if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)