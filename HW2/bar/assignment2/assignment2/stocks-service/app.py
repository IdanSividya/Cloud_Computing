import os
from flask import Flask, request, jsonify
import datetime
import requests
import uuid
from pymongo import MongoClient
import sys

app = Flask(__name__)

# MongoDB Connection
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/stocks1')
try:
    client = MongoClient(MONGODB_URI)
    db = client.get_database()
    stocks_collection = db.stocks
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}", file=sys.stderr)
    sys.exit(1)

# API configuration
url = "https://api.api-ninjas.com/v1/stockprice"
API_Key = "a0I23j/LmvEOAGJVfTm6WQ==wobTmfZ9FXI8MBEp"

# Helper functions
def format_float(value):
    return round(float(value), 2)

def validate_date(date_text):
    if date_text == "NA":
        return True
    try:
        datetime.datetime.strptime(date_text, "%d-%m-%Y")
        return True
    except ValueError:
        return False

def stock_to_json(stock):
    """Convert MongoDB document to JSON, handling ObjectId"""
    if stock:
        stock['id'] = str(stock.get('_id', ''))
        del stock['_id']
    return stock

@app.route('/stocks', methods=['GET'])
def getstocks():
    try:
        query_params = request.args.to_dict()
        
        # Build MongoDB query from parameters
        mongo_query = {}
        for key, value in query_params.items():
            if key.lower() in ['symbol', 'name']:
                mongo_query[key] = value.upper() if key == 'symbol' else value

        # Query MongoDB
        stocks = list(stocks_collection.find(mongo_query))
        result = [stock_to_json(stock) for stock in stocks]
        
        return jsonify(result), 200
    except Exception as e:
        return {"server error": str(e)}, 500

@app.route('/stocks', methods=['POST'])
def poststocks():
    if not request.is_json:
        return {"error": "Expected application/json media type"}, 415
    try:
        data = request.get_json()
        required_fields = ['symbol', 'purchase price', 'shares']
        if not all(field in data for field in required_fields):
            return {"error": "Malformed data"}, 400

        # Check if a stock with the same symbol already exists
        symbol_upper = data["symbol"].upper()
        existing_stock = stocks_collection.find_one({"symbol": symbol_upper})
        if existing_stock:
            return {"error": "Malformed data"}, 400

        # Validate purchase date if provided
        purchase_date = data.get("purchase date", "NA")
        if not validate_date(purchase_date):
            return {"error": "Malformed data"}, 400

        if not isinstance(data.get("shares"), int):
            return {"error": "Malformed data"}, 400

        stock = {
            "_id": str(uuid.uuid4()),
            "name": data.get("name", "NA"),
            "symbol": symbol_upper,
            "purchase price": format_float(data["purchase price"]),
            "purchase date": purchase_date,
            "shares": int(data["shares"])
        }
        
        result = stocks_collection.insert_one(stock)
        return {'id': str(result.inserted_id)}, 201
    except Exception as e:
        return {"server error": str(e)}, 500

@app.route('/stocks/<id>', methods=['GET'])
def getstock_id(id):
    try:
        stock = stocks_collection.find_one({"_id": id})
        if stock:
            return jsonify(stock_to_json(stock)), 200
        else:
            return {"error": "Not found"}, 404
    except Exception as e:
        return {"server error": str(e)}, 500

@app.route('/stocks/<id>', methods=['PUT'])
def putstock_id(id):
    if not request.is_json:
        return {"error": "Expected application/json media type"}, 415
    try:
        try:
            data = request.get_json()
        except Exception:
            return {"error": "Malformed data"}, 400
            
        # Check if stock exists
        existing_stock = stocks_collection.find_one({"_id": id})
        if not existing_stock:
            return {"error": "Not found"}, 404

        required_fields = ['id', 'symbol', 'purchase price', 'shares', 'name', 'purchase date']
        if not all(field in data for field in required_fields):
            return {"error": "Malformed data"}, 400
            
        if data['id'] != id:
            return {"error": "Malformed data"}, 400

        # Validate purchase date
        if not validate_date(data["purchase date"]):
            return {"error": "Malformed data"}, 400

        # Check for symbol uniqueness
        symbol_upper = data["symbol"].upper()
        duplicate_stock = stocks_collection.find_one({
            "symbol": symbol_upper,
            "_id": {"$ne": id}
        })
        if duplicate_stock:
            return {"error": "Malformed data"}, 400

        # Update the stock
        updated_stock = {
            "_id": id,
            "name": data["name"],
            "symbol": symbol_upper,
            "purchase price": format_float(data["purchase price"]),
            "purchase date": data["purchase date"],
            "shares": int(data["shares"])
        }
        
        stocks_collection.replace_one({"_id": id}, updated_stock)
        return {"id": id}, 200
    except Exception as e:
        return {"error": "Malformed data"}, 400
    
@app.route('/stocks/<id>', methods=['DELETE'])
def deletestock_id(id):
    try:
        result = stocks_collection.delete_one({"_id": id})
        if result.deleted_count > 0:
            return '', 204
        else:
            return {"error": "Not found"}, 404
    except Exception as e:
        return {"server error": str(e)}, 500

@app.route('/stock-value/<id>', methods=['GET'])
def getstock_value(id):
    try:
        stock = stocks_collection.find_one({"_id": id})
        if not stock:
            return {"error": "Not found"}, 404

        symbol = stock["symbol"]
        api_url = f'https://api.api-ninjas.com/v1/stockprice?ticker={symbol}'
        headers = {'X-Api-Key': API_Key}
        response = requests.get(api_url, headers=headers)

        if response.status_code != 200:
            try:
                error_message = response.json().get('error', 'Unknown error')
            except ValueError:
                error_message = 'Unknown error'
            return {"server error": "API response code " + str(error_message)}, 500

        data = response.json()
        if 'price' in data:
            ticker_price = float(data['price'])
        else:
            return {"server error": "API response code " + str(response.status_code)}, 500

        stock_value = format_float(ticker_price * stock["shares"])
        result = {
            "symbol": stock["symbol"],
            "ticker": format_float(ticker_price),
            "stock value": stock_value
        }
        return jsonify(result), 200
    except Exception as e:
        return {"server error": str(e)}, 500

@app.route('/portfolio-value', methods=['GET'])
def getportfolio_Value():
    try:
        total_value = 0.0
        stocks = stocks_collection.find()
        
        for stock in stocks:
            symbol = stock["symbol"]
            api_url = f'https://api.api-ninjas.com/v1/stockprice?ticker={symbol}'
            headers = {'X-Api-Key': API_Key}
            response = requests.get(api_url, headers=headers)

            if response.status_code != 200:
                try:
                    error_message = response.json().get('error', 'Unknown error')
                except ValueError:
                    error_message = 'Unknown error'
                return {"server error": "API response code " + str(error_message)}, 500

            data = response.json()
            if 'price' in data:
                ticker_price = float(data['price'])
            else:
                return {"server error": "API response code " + str(response.status_code)}, 500

            stock_value = ticker_price * stock["shares"]
            total_value += stock_value

        total_value = format_float(total_value)
        current_date = datetime.datetime.now().strftime("%d-%m-%Y")
        result = {
            "date": current_date,
            "portfolio value": total_value
        }
        return jsonify(result), 200
    except Exception as e:
        return {"server error": str(e)}, 500

@app.route('/kill', methods=['GET'])
def kill_container():
    """Endpoint for testing container restart functionality"""
    os._exit(1)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port)