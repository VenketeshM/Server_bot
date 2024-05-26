from binance.um_futures import UMFutures
import ta
import ta.trend
import pandas as pd
from time import sleep
from binance.error import ClientError

key = "Xl7Bw0U7EVkuRykpxwHr2n7zIMVhlDhaxalRgL3TKFkSd5n8EPrRuVmtEF7Y2XOa"
secret ="wpHKKRmaQsvbHhbBSsaDVqNUxJlTgKcMevjEGfzp4U7ee02tqVMafFpCgUGPBIeS"

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
        print_error(error)

# Function to calculate volume based on trading balance in USDC
def set_volume():
    trading_balance = get_balance_usdc()
    risk_factor = 1
    volume = trading_balance * risk_factor * 10
    return volume

# Function to handle error printing
def print_error(error):
    print(
        "Found error. status: {}, error code: {}, error message: {}".format(
            error.status_code, error.error_code, error.error_message
        )
    )

# Function to get candles for the needed symbol
def klines(symbol):
    try:
        resp = pd.DataFrame(client.klines(symbol, '15m'))
        resp = resp.iloc[:,:6]
        resp.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume']
        resp = resp.set_index('Time')
        resp.index = pd.to_datetime(resp.index, unit='ms')
        resp = resp.astype(float)
        return resp
    except ClientError as error:
        print_error(error)

# Set leverage for the needed symbol
def set_leverage(symbol, level):
    try:
        response = client.change_leverage(
            symbol=symbol, leverage=level, recvWindow=6000
        )
        print(response)
    except ClientError as error:
        print_error(error)

# Open new order with the last price
def open_order(symbol, side, volume):
    price = float(client.ticker_price(symbol)['price'])
    qty_precision = get_qty_precision(symbol)
    qty = round(volume / price, qty_precision)
    try:
        resp = client.new_order(symbol=symbol, side=side.upper(), type='MARKET', quantity=qty)
        print(symbol, side, "placing order")
        print(resp)
        sleep(2)
    except ClientError as error:
        print_error(error)

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
            except ClientError as error:
                print_error(error)

# Your current positions
def get_pos():
    try:
        resp = client.get_position_risk()
        pos = []
        for elem in resp:
            if float(elem['positionAmt']) != 0:
                pos.append({'symbol': elem['symbol'], 'side': 'BUY' if float(elem['positionAmt']) > 0 else 'SELL', 'positionAmt': float(elem['positionAmt'])})
        return pos
    except ClientError as error:
        print_error(error)

# Get price precision for the symbol
def get_price_precision(symbol):
    resp = client.exchange_info()['symbols']
    for elem in resp:
        if elem['symbol'] == symbol:
            return elem['pricePrecision']

# Get amount precision for the symbol
def get_qty_precision(symbol):
    resp = client.exchange_info()['symbols']
    for elem in resp:
        if elem['symbol'] == symbol:
            return elem['quantityPrecision']

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
    volume = set_volume()
    balance = get_balance_usdc()
    symbol = 'BTCUSDC'
    price = float(client.ticker_price(symbol)['price'])
    qty_precision = get_qty_precision(symbol)
    sleep(1)
    if balance is None:
        print('Cannot connect to API. Check IP, restrictions, or wait some time.')
        continue
    print("My balance is:", balance, "USDC")
    pos = get_pos()
    print(f'You have {len(pos)} opened positions:\n{pos}')
    qty = round(volume / price, qty_precision)
    signal = sma_signal(symbol)
    if len(pos) > 0:
        if pos[0]['side'] == 'BUY' and signal == 'down':
            close_opposite_position(symbol, 'buy')
            sleep(1)
            set_leverage(symbol, leverage)
            sleep(1)
            print('Closing BUY position for', symbol)
            open_order(symbol, 'sell', volume)
            sleep(10)
        elif pos[0]['side'] == 'SELL' and signal == 'up':
            close_opposite_position(symbol, 'sell')
            sleep(1)
            set_leverage(symbol, leverage)
            sleep(1)
            print('Closing SELL position for', symbol)
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
    print('Waiting 3 min')
    sleep(180)
