from binance.um_futures import UMFutures
import ta
import ta.trend
import pandas as pd
from time import sleep
from binance.error import ClientError

key = "czmJx25NMHl0v2Kx43fzPOHU8582h2uOzOIm96jEV9ZEF1HtMKQtVFg3zKimIzhW"
secret = "6JA5N4uB9BeKAPHxQq18ylGHpsRuBrXtoFZn6pULxkCNp4V5ggtCxsfhAn36fzeH"

client = UMFutures(key=key, secret=secret)

# Constants
leverage = 10
type = 'ISOLATED'

# Function to get balance in USDC
def get_balance_usdc():
    try:
        response = client.balance(recvWindow=6000)
        for elem in response:
            if elem['asset'] == 'USDC':
                return float(elem['balance'])
    except ClientError as error:
        handle_error(error)
    return None

# Function to calculate volume based on trading balance in USDC
def set_volume(trading_balance):
    risk_factor = 1
    volume = trading_balance * risk_factor * leverage
    return volume

# Function to handle error printing
def handle_error(error):
    error_message = f"Error encountered. Status: {error.status_code}, Code: {error.error_code}, Message: {error.error_message}"
    print(error_message)
    with open("error_log.txt", "a") as f:
        f.write(error_message + "\n")

# Function to get candles for the needed symbol
def klines(symbol):
    try:
        resp = pd.DataFrame(client.klines(symbol, '15m'))
        resp = resp.iloc[:, :6]
        resp.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume']
        resp = resp.set_index('Time')
        resp.index = pd.to_datetime(resp.index, unit='ms')
        resp = resp.astype(float)
        return resp
    except ClientError as error:
        handle_error(error)
    return pd.DataFrame()

# Set leverage for the needed symbol
def set_leverage(symbol, level):
    try:
        response = client.change_leverage(
            symbol=symbol, leverage=level, recvWindow=6000
        )
        print(response)
    except ClientError as error:
        handle_error(error)

# Open new order with the last price
def open_order(symbol, side, volume):
    price = float(client.ticker_price(symbol)['price'])
    qty_precision = get_qty_precision(symbol)
    qty = round(volume / price, qty_precision)
    try:
        resp = client.new_order(symbol=symbol, side=side.upper(), type='MARKET', quantity=qty)
        print(f"{symbol} {side} placing order")
        print(resp)
        sleep(2)
        # Wait for order to be filled
        order_id = resp['orderId']
        wait_for_order_filled(symbol, order_id)
    except ClientError as error:
        handle_error(error)

# Close opposite position
def close_opposite_position(symbol, side):
    pos = get_pos()
    for p in pos:
        if p['symbol'] == symbol and p['side'] != side.upper():
            try:
                qty_precision = get_qty_precision(symbol)
                close_qty = round(abs(p['positionAmt']), qty_precision)
                opposite_side = 'SELL' if p['side'] == 'BUY' else 'BUY'
                resp = client.new_order(symbol=symbol, side=opposite_side, type='MARKET', quantity=close_qty)
                print(f'Closed {p["side"]} position for {symbol}')
                print(resp)
                sleep(2)
                # Wait for order to be filled
                order_id = resp['orderId']
                wait_for_order_filled(symbol, order_id)
            except ClientError as error:
                handle_error(error)

# Wait for order to be filled
def wait_for_order_filled(symbol, order_id):
    while True:
        try:
            order_status = client.get_order(symbol=symbol, orderId=order_id)
            if order_status['status'] == 'FILLED':
                print(f'Order {order_id} for {symbol} filled.')
                break
            sleep(1)
        except ClientError as error:
            handle_error(error)
            break

# Your current positions
def get_pos():
    try:
        resp = client.get_position_risk()
        pos = []
        for elem in resp:
            if float(elem['positionAmt']) != 0:
                pos.append({'symbol': elem['symbol'], 'side': 'BUY' if float(elem['positionAmt']) > 0 else 'SELL',
                            'positionAmt': float(elem['positionAmt'])})
        return pos
    except ClientError as error:
        handle_error(error)
    return []

# Get price precision for the symbol
def get_price_precision(symbol):
    resp = client.exchange_info()['symbols']
    for elem in resp:
        if elem['symbol'] == symbol:
            return elem['pricePrecision']
    return 8

# Get amount precision for the symbol
def get_qty_precision(symbol):
    resp = client.exchange_info()['symbols']
    for elem in resp:
        if elem['symbol'] == symbol:
            return elem['quantityPrecision']
    return 8

# Strategy - SMA signal
def sma_signal(symbol):
    kl = klines(symbol)
    sma15 = ta.trend.sma_indicator(kl.Close, window=15)
    sma25 = ta.trend.sma_indicator(kl.Close, window=25)

    if sma15.iloc[-1] > sma25.iloc[-1]:
        return 'up'
    elif sma15.iloc[-1] < sma25.iloc[-1]:
        return 'down'
    else:
        return 'none'

# Main loop for trading
while True:
    balance = get_balance_usdc()
    if balance is None:
        print('Cannot connect to API. Check IP, restrictions, or wait some time.')
        continue

    volume = set_volume(balance)
    symbol = 'BTCUSDC'
    price = float(client.ticker_price(symbol)['price'])
    qty_precision = get_qty_precision(symbol)
    sleep(1)

    print("My balance is:", balance, "USDC")
    pos = get_pos()
    print(f'You have {len(pos)} opened positions:\n{pos}')
    qty = round(volume / price, qty_precision)
    signal = sma_signal(symbol)

    if len(pos) > 0:
        if pos[0]['side'] == 'BUY' and signal == 'down':
            close_opposite_position(symbol, 'buy')
            sleep(3)
            balance = get_balance_usdc()
            print("Balance after closing position:", balance, "USDC")
            sleep(30)  # Wait for 30 seconds after checking the balance
            volume = set_volume(balance)
            print("Updated volume after 30-second wait:", volume)
            set_leverage(symbol, leverage)
            sleep(1)
            print('Placing SELL order for', symbol)
            open_order(symbol, 'sell', volume)
            sleep(10)
        elif pos[0]['side'] == 'SELL' and signal == 'up':
            close_opposite_position(symbol, 'sell')
            sleep(3)
            balance = get_balance_usdc()
            print("Balance after closing position:", balance, "USDC")
            sleep(30)  # Wait for 30 seconds after checking the balance
            volume = set_volume(balance)
            print("Updated volume after 30-second wait:", volume)
            set_leverage(symbol, leverage)
            sleep(1)
            print('Placing BUY order for', symbol)
            open_order(symbol, 'buy', volume)
            sleep(10)
        elif pos[0]['side'] == 'BUY' and signal == 'up':
            print('Signal is BUY, already in a BUY position. Doing nothing.')
        elif pos[0]['side'] == 'SELL' and signal == 'down':
            print('Signal is SELL, already in a SELL position. Doing nothing.')
    else:
        if signal == 'up':
            set_leverage(symbol, leverage)
            sleep(1)
            print('Placing BUY order for', symbol)
            open_order(symbol, 'buy', volume)
            sleep(10)
        elif signal == 'down':
            set_leverage(symbol, leverage)
            sleep(1)
            print('Placing SELL order for', symbol)
            open_order(symbol, 'sell', volume)
            sleep(10)

    balance = get_balance_usdc()  # Calculate balance after executing an order
    volume = set_volume(balance)  # Calculate new volume based on the updated balance
    print("Updated balance is:", balance, "USDC")
    print('Waiting 3 min')
    sleep(180)
