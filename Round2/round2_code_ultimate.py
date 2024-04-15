import jsonpickle
from datamodel import OrderDepth, UserId, TradingState, Order
from typing import Any, List, Dict
import math
import numpy as np

POSITION_LIMIT = 20

POSITION_LIMITS = {
    "AMETHYSTS": 20,
    "STARFRUIT": 20,
    "ORCHIDS": 100,  # Updated position limit for Orchids
}

PRICE_AGGRESSION = 0

THRESHOLDS = {
    "over": 0,
    "mid": 10
}

class Trader:
    previous_prices = {
        "STARFRUIT": [],
        "AMETHYSTS": [],
        "ORCHIDS" : [],
        "SMA_1" : [],
        "SMA_2":[],
        "LMA": [],
        "SWITCH":0
    }

    def update_price_history(self, previousTradingState, tradingState: TradingState):
        # Update price history from previous state
        if "previous_prices" in previousTradingState:
            self.previous_prices = previousTradingState["previous_prices"]

        for product in ["STARFRUIT", "AMETHYSTS","ORCHIDS"]:
        
            if product == "ORCHIDS":
                order_depth = tradingState.order_depths[product]
                lowest_sell_price = sorted(order_depth.sell_orders.keys())[0]
                highest_buy_price = sorted(order_depth.buy_orders.keys(), reverse=True)[0]
                current_mid_price = (lowest_sell_price + highest_buy_price) / 2
                if len(self.previous_prices[product]) < 100:
                    self.previous_prices[product].append(current_mid_price)
                if len(self.previous_prices[product]) == 100:
                    self.previous_prices[product].append(current_mid_price)
                    self.previous_prices[product].pop(0)
                    prices_array = np.array(self.previous_prices[product])
                    ma_13 = np.mean(prices_array[-13:])
                    ma_26 = np.mean(prices_array[-26:])
                    ma_100 = np.mean(prices_array[-100:])
                    self.previous_prices["SMA_1"].append(ma_13)
                    self.previous_prices["SMA_2"].append(ma_26)
                    self.previous_prices["LMA"].append(ma_100)
                    if len(self.previous_prices["LMA"])>1:
                        self.previous_prices["SMA_1"].pop(0)
                        self.previous_prices["SMA_2"].pop(0)
                        self.previous_prices["LMA"].pop(0)       
            else:
                order_depth = tradingState.order_depths[product]
                lowest_sell_price = sorted(order_depth.sell_orders.keys())[0]
                highest_buy_price = sorted(order_depth.buy_orders.keys(), reverse=True)[0]
                current_mid_price = (lowest_sell_price + highest_buy_price) / 2
                if len(self.previous_prices[product]) < 25:
                    self.previous_prices[product].append(current_mid_price)
                if len(self.previous_prices[product]) == 25:
                    self.previous_prices[product].append(current_mid_price)
                    self.previous_prices[product].pop(0)
        
    def get_price(self, product) -> float | None:
        if len(self.previous_prices[product]) < 25:
            if product == "AMETHYSTS":
                return 10000
            else:
                return None
        # Linear model prediction (example: y = ax + b, derived from regression analysis)
        x_values = np.arange(1, 26)
        y_values = np.array(self.previous_prices[product])
        x_mean = np.mean(x_values)
        y_mean = np.mean(y_values)
        numerator = np.sum((x_values - x_mean) * (y_values - y_mean))
        denominator = np.sum((x_values - x_mean)**2)
        slope = numerator / denominator
        intercept = y_mean - slope * x_mean
        expected_value = slope * 26 + intercept
        return expected_value

    def get_orders(self, state: TradingState, acceptable_price: int | float, product: str) -> List[Order]:
        product_order_depth = state.order_depths[product]
        product_position_limit = POSITION_LIMITS[product]
        acceptable_buy_price = math.floor(acceptable_price)
        acceptable_sell_price = math.ceil(acceptable_price)
        orders = []
        
        orders_sell = sorted(list(product_order_depth.sell_orders.items()), key=lambda x: x[0])
        orders_buy = sorted(list(product_order_depth.buy_orders.items()), key=lambda x: x[0], reverse=True)

        lowest_sell_price = orders_sell[0][0]
        lowest_buy_price = orders_buy[0][0]
        
        buying_pos = state.position.get(product, 0)
        for ask, vol in orders_sell:
            
            if product_position_limit - buying_pos <= 0:
                break
            if ask < acceptable_buy_price - PRICE_AGGRESSION:
                buy_amount = min(-vol, product_position_limit - buying_pos)
                buying_pos += buy_amount
                orders.append(Order(product, ask, buy_amount))
            
            if ask == acceptable_buy_price and buying_pos < 0:
                buy_amount = min(-vol, -buying_pos)
                buying_pos += buy_amount
                assert(buy_amount > 0)
                orders.append(Order(product, ask, buy_amount))
                print(f"{product} buy order 2: {vol} at {ask}")
					# skip if there is no quota left
				# once we exhaust all profitable sell orders, we place additional buy orders
				# at a price acceptable to us
				# what that price looks like will depend on our position		
            if product_position_limit - buying_pos > 0: # if we have capacity
                if buying_pos < THRESHOLDS["over"]: # if we are overleveraged to sell, buy at parity for price up to neutral position
                    target_buy_price = min(acceptable_buy_price, lowest_buy_price + 1)
                    vol = -buying_pos + THRESHOLDS["over"]
                    orders.append(Order(product, target_buy_price, vol))
                    print(f"{product} buy order 3: {vol} at {target_buy_price}")
                    buying_pos += vol
                if THRESHOLDS["over"] <= buying_pos <= THRESHOLDS["mid"]:
                    target_buy_price = min(acceptable_buy_price - 1, lowest_buy_price + 1)
                    vol = -buying_pos + THRESHOLDS["mid"] # if we are close to neutral
                    orders.append(Order(product, target_buy_price, vol))
                    print(f"{product} buy order 4: {vol} at {target_buy_price}")
                    buying_pos += vol
                if buying_pos >= THRESHOLDS["mid"]:
                    target_buy_price = min(acceptable_buy_price - 3, lowest_buy_price + 1)
                    vol = product_position_limit - buying_pos
                    orders.append(Order(product, target_buy_price, vol))
                    print(f"{product} buy order 5: {vol} at {target_buy_price}")
                    buying_pos += vol
            
            

                
        selling_pos = state.position.get(product, 0)
        for bid, vol in orders_buy:
            if -product_position_limit - selling_pos >= 0:
                break
            if bid > acceptable_sell_price + PRICE_AGGRESSION:
                sell_amount = max(-vol, -product_position_limit - selling_pos)
                selling_pos += sell_amount
                orders.append(Order(product, bid, sell_amount))
            
            if bid == acceptable_sell_price and selling_pos > 0:
                sell_amount = max(-vol, -selling_pos)
                selling_pos += sell_amount
                assert(sell_amount < 0)
                orders.append(Order(product, bid, sell_amount))
                print("{product} sell order 2: ", sell_amount, bid)

					# start market making with remaining quota
					# if selling_pos
            if -product_position_limit - selling_pos < 0:
                if selling_pos > -THRESHOLDS["over"]:
                    target_sell_price = max(acceptable_sell_price, lowest_sell_price - 1)
                    vol = -selling_pos - THRESHOLDS["over"]
                    orders.append(Order(product, target_sell_price, vol))
                    selling_pos += vol
                    print(f"{product} sell order 3: selling {vol} at {target_sell_price}")
                if -THRESHOLDS["over"] >= selling_pos >= -THRESHOLDS["mid"]:
                    target_sell_price = max(acceptable_sell_price + 1, lowest_sell_price - 1)
                    vol = -selling_pos - THRESHOLDS["mid"]
                    orders.append(Order(product, target_sell_price, vol))
                    selling_pos += vol
                    print(f"{product} sell order 4: selling {vol} at {target_sell_price}")
                if -THRESHOLDS["mid"] >= selling_pos:
                    target_sell_price = max(acceptable_sell_price + 2, lowest_sell_price - 1)
                    vol = -product_position_limit - selling_pos
                    orders.append(Order(product, target_sell_price, vol))
                    selling_pos += vol
                    print(f"{product} sell order 5: selling {vol} at {target_sell_price}")        
        return orders
    
    def get_orders_orchid(self, state: TradingState, product: str) -> List[Order]:
        conversion = 0
        orders = []
        
        if len(self.previous_prices[product])<100:
            return None
        
        product_order_depth = state.order_depths[product]
        product_position_limit = POSITION_LIMITS[product]
        
        orders_buy = sorted(list(product_order_depth.buy_orders.items()), key=lambda x: x[0], reverse=True)
        
        prices_array = np.array(self.previous_prices[product])
        
        ma_13 = np.mean(prices_array[-13:])  # Last 25 prices for 25-period MA
        ma_26=np.mean(prices_array[-26:])
        ma_100 = np.mean(prices_array[-100:])  
        
        selling_pos = state.position.get(product, 0)
        if self.previous_prices["SWITCH"]==0:
            if ma_100>ma_13 and ma_26>ma_13:
                sell_amount = max(-orders_buy[0][1], -product_position_limit - selling_pos)
                selling_pos += sell_amount
                orders.append(Order(product,orders_buy[0][0],sell_amount))
                self.previous_prices["SWITCH"]=1
        else:    
            buying_pos = state.position.get(product, 0)
            if buying_pos<0:
                if ma_13>ma_100 and ma_13>ma_26:
                    conversion = -buying_pos     
                    self.previous_prices["SWITCH"] = 0                    
        
        return [orders,conversion]
        
    
    def run(self, state: TradingState):
        try:
            previousStateData = jsonpickle.decode(state.traderData) 
        except:
            previousStateData = {}
           
        conversions = 0 
        self.update_price_history(previousStateData, state)
        result = {}
        for product in ["STARFRUIT", "AMETHYSTS", "ORCHIDS"]:
            if product!="ORCHIDS":
                product_acceptable_price = self.get_price(product)
                if product_acceptable_price is not None:
                    orders = self.get_orders(state, product_acceptable_price, product)
                    result[product] = orders
            else:  
                x = self.get_orders_orchid(state, product)
                if x is not None:
                    result[product] = x[0]
                    conversions=x[1]
        
        traderData = {
            "previous_prices": self.previous_prices    
        }
        
        serialisedTraderData = jsonpickle.encode(traderData)
        
        try:
            traderDataDecoded = jsonpickle.decode(state.traderData)  # Decoding traderData
            print(state.observations)
            print(traderDataDecoded)
            
        except Exception as e:
            print("Error decoding or accessing traderData:", str(e))
        
        
        
        return result, conversions, serialisedTraderData
