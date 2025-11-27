from flask import Flask, request, render_template
from datetime import date, datetime, timedelta
import math
import json

app = Flask(__name__)


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes_price(S, K, T, r, sigma, option_type):
    """
    Very simple European Black-Scholes price.
    S = stock price
    K = strike
    T = time to expiry in years
    r = risk-free rate
    sigma = volatility (as decimal, e.g. 0.35)
    option_type = "call" or "put"
    """
    # If at expiry or zero vol, fall back to intrinsic
    if T <= 0 or sigma <= 0:
        if option_type == "call":
            return max(0.0, S - K)
        else:
            return max(0.0, K - S)

    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "call":
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def build_price_points(stock_min, stock_max, step=1.0):
    prices = []
    current = stock_min
    while current <= stock_max + 1e-9:
        prices.append(round(current, 2))
        current += step
    return prices


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            # --- Get and convert form inputs ---

            stock_price = float(request.form.get('stock_price'))
            strike_price = float(request.form.get('strike_price'))
            premium = float(request.form.get('premium'))  # price per option contract
            contracts = int(request.form.get('contracts'))
            option_type = request.form.get('option_type')  # "call" or "put"
            expiry_date_str = request.form.get('expiry_date')  # string e.g. "2025-12-19"
            implied_volatility = float(request.form.get('implied_volatility'))
            stock_min = float(request.form.get('stock_min'))
            stock_max = float(request.form.get('stock_max'))

            if stock_max < stock_min:
                error_message = "Max stock price must be greater than or equal to min stock price."
                return render_template('index.html', error=error_message)

            # Parse expiry date
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
            today = date.today()
            total_days = max(0, (expiry_date - today).days)

            # --- Build stock price points for grid (expiry table & wheels) ---
            step = 1.0  # $1 increments for now
            price_points = build_price_points(stock_min, stock_max, step)

            # --- Expiry-only P/L table ---

            rows = []
            cost_per_contract = premium * 100

            for p in price_points:
                if option_type == "call":
                    intrinsic = max(0.0, p - strike_price)
                else:  # put
                    intrinsic = max(0.0, strike_price - p)

                value_per_contract = intrinsic * 100
                pl_per_contract = value_per_contract - cost_per_contract
                total_pl = pl_per_contract * contracts

                rows.append({
                    "price": p,
                    "pl_total": total_pl,
                    "pl_per_contract": pl_per_contract
                })

            # --- Date + price grid for the wheels (using Black–Scholes) ---

            r = 0.02  # 2% risk-free rate (simple assumption)
            sigma = implied_volatility / 100.0

            date_list = []
            grid = {}  # grid[date_str][price_str] = total P/L

            for day_offset in range(total_days + 1):
                d = today + timedelta(days=day_offset)
                date_str = d.isoformat()
                date_list.append(date_str)

                # time remaining from this date to expiry (in years)
                days_to_expiry = max(0, (expiry_date - d).days)
                T = days_to_expiry / 365.0

                daily_map = {}
                for p in price_points:
                    # Option theoretical price on that date at that stock price
                    option_price = black_scholes_price(
                        S=p,
                        K=strike_price,
                        T=T,
                        r=r,
                        sigma=sigma,
                        option_type=option_type
                    )

                    value_per_contract = option_price * 100
                    pl_per_contract = value_per_contract - cost_per_contract
                    total_pl = pl_per_contract * contracts

                    price_key = f"{p:.2f}"
                    daily_map[price_key] = total_pl

                grid[date_str] = daily_map

            # JSON for JS on the frontend
            grid_json = json.dumps(grid)

            return render_template(
                'results.html',
                stock_price=stock_price,
                strike_price=strike_price,
                premium=premium,
                contracts=contracts,
                option_type=option_type,
                expiry_date=expiry_date_str,
                implied_volatility=implied_volatility,
                stock_min=stock_min,
                stock_max=stock_max,
                rows=rows,  # expiry table
                price_points=price_points,
                date_labels=date_list,
                grid_json=grid_json
            )

        except (ValueError, TypeError):
            error_message = "Invalid input. Please make sure all numeric fields contain valid numbers."
            return render_template('index.html', error=error_message)

    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)
