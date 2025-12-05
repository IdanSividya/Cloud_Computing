import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Get service URLs from environment variables
STOCKS1_A_URL = os.getenv('STOCKS1_A_URL', 'http://stocks1-a:8000')
STOCKS1_B_URL = os.getenv('STOCKS1_B_URL', 'http://stocks1-b:8000')  # Not used directly as per requirements
STOCKS2_URL = os.getenv('STOCKS2_URL', 'http://stocks2:8000')

def get_stock_data(service_url):
    """Fetch all stocks from a specific service"""
    try:
        response = requests.get(f"{service_url}/stocks")
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        print(f"Error fetching stocks from {service_url}: {str(e)}")
        return []

def get_current_stock_value(service_url, stock_id):
    """Get current value of a specific stock"""
    try:
        response = requests.get(f"{service_url}/stock-value/{stock_id}")
        if response.status_code == 200:
            return response.json().get('stock value', 0)
        return 0
    except Exception as e:
        print(f"Error fetching stock value from {service_url}: {str(e)}")
        return 0

def calculate_stock_gain(service_url, stock):
    """Calculate capital gain for a single stock"""
    current_value = get_current_stock_value(service_url, stock['id'])
    purchase_value = float(stock['purchase price']) * stock['shares']
    return current_value - purchase_value

def filter_stocks(stocks, num_shares_gt=None, num_shares_lt=None):
    """Filter stocks based on number of shares criteria"""
    filtered_stocks = stocks.copy()
    
    if num_shares_gt is not None:
        filtered_stocks = [s for s in filtered_stocks if s['shares'] > num_shares_gt]
    
    if num_shares_lt is not None:
        filtered_stocks = [s for s in filtered_stocks if s['shares'] < num_shares_lt]
    
    return filtered_stocks

@app.route('/capital-gains', methods=['GET'])
def get_capital_gains():
    try:
        # Get query parameters
        portfolio = request.args.get('portfolio')
        if portfolio is not None:
            if portfolio not in ['stocks1', 'stocks2']:
                return {"error": "Malformed data"}, 400
        num_shares_gt = request.args.get('numsharesgt')
        num_shares_lt = request.args.get('numshareslt')
        if num_shares_gt is not None:
            try:
                num_shares_gt = int(num_shares_gt)
                if num_shares_gt < 0:
                    return {"error": "numsharesgt must be non-negative"}, 400
            except ValueError:
                return {"error": "numsharesgt must be a valid integer"}, 400

        # Validate num_shares_lt
        if num_shares_lt is not None:
            try:
                num_shares_lt = int(num_shares_lt)
                if num_shares_lt < 0:
                    return {"error": "numshareslt must be non-negative"}, 400
            except ValueError:
                return {"error": "numshareslt must be a valid integer"}, 400
        # Convert share number filters to integers if provided
        if num_shares_gt is not None:
            num_shares_gt = int(num_shares_gt)
        if num_shares_lt is not None:
            num_shares_lt = int(num_shares_lt)

        total_gain = 0
        
        # Process stocks1 portfolio if needed
        if portfolio is None or portfolio == 'stocks1':
            stocks1 = get_stock_data(STOCKS1_A_URL)
            filtered_stocks1 = filter_stocks(stocks1, num_shares_gt, num_shares_lt)
            for stock in filtered_stocks1:
                total_gain += calculate_stock_gain(STOCKS1_A_URL, stock)
        
        # Process stocks2 portfolio if needed
        if portfolio is None or portfolio == 'stocks2':
            stocks2 = get_stock_data(STOCKS2_URL)
            filtered_stocks2 = filter_stocks(stocks2, num_shares_gt, num_shares_lt)
            for stock in filtered_stocks2:
                total_gain += calculate_stock_gain(STOCKS2_URL, stock)
        
        # Round to 2 decimal places
        total_gain = round(total_gain, 2)
        
        return jsonify(total_gain)
    
    except ValueError as ve:
        return {"error": "Invalid parameter values"}, 400
    except Exception as e:
        return {"error": f"Server error: {str(e)}"}, 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port)